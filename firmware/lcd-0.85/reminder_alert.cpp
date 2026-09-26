#include "reminder_alert.h"

#include <Arduino.h>
#include <HTTPClient.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <WiFiClientSecure.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "audio_bsp.h"
#include "backend_http.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "home_ui.h"
#include "idle.h"
#include "voice_note.h"
#include "wifi_connect.h"

static const char *TAG = "remind";

static constexpr uint32_t kSampleRate = 16000;
static constexpr uint32_t kPlayChannels = 2;
static constexpr uint32_t kBits = 16;
static constexpr uint32_t kMaxSpeakSeconds = 10;
static constexpr uint32_t kMaxSpeakBytes =
  kSampleRate * kPlayChannels * (kBits / 8) * kMaxSpeakSeconds;
static constexpr int kStayAwakeMinutes = 12;
static constexpr uint32_t kAwakePollMs = 20000;
// While asleep, check less often when the next event is far away. Waking the
// radio is the pin's biggest battery cost, so a 45 s poll drained it fast.
static constexpr uint32_t kSleepPollMinMs = 45000;
static constexpr uint32_t kSleepPollMaxMs = 10 * 60 * 1000;

static uint8_t *speak_buf = NULL;
static char last_alert_key[96] = "";

static bool json_str(const char *json, const char *key, char *out, size_t out_len)
{
  char needle[40];
  snprintf(needle, sizeof(needle), "\"%s\"", key);
  const char *p = strstr(json, needle);
  if (p == NULL) {
    out[0] = '\0';
    return false;
  }
  p = strchr(p + 1, ':');
  if (p == NULL) {
    out[0] = '\0';
    return false;
  }
  p++;
  while (*p == ' ') {
    p++;
  }
  if (*p != '"') {
    out[0] = '\0';
    return false;
  }
  p++;
  size_t i = 0;
  while (*p != '\0' && *p != '"' && i + 1 < out_len) {
    if (*p == '\\' && p[1] != '\0') {
      p++;
    }
    out[i++] = *p++;
  }
  out[i] = '\0';
  return true;
}

static bool json_int(const char *json, const char *key, int *out)
{
  char needle[40];
  snprintf(needle, sizeof(needle), "\"%s\"", key);
  const char *p = strstr(json, needle);
  if (p == NULL) {
    return false;
  }
  p = strchr(p + 1, ':');
  if (p == NULL) {
    return false;
  }
  p++;
  while (*p == ' ') {
    p++;
  }
  if (*p != '-' && (*p < '0' || *p > '9')) {
    return false;
  }
  *out = atoi(p);
  return true;
}

static bool json_bool(const char *json, const char *key, bool *out)
{
  char needle[40];
  snprintf(needle, sizeof(needle), "\"%s\"", key);
  const char *p = strstr(json, needle);
  if (p == NULL) {
    return false;
  }
  p = strchr(p + 1, ':');
  if (p == NULL) {
    return false;
  }
  p++;
  while (*p == ' ') {
    p++;
  }
  if (strncmp(p, "true", 4) == 0) {
    *out = true;
    return true;
  }
  if (strncmp(p, "false", 5) == 0) {
    *out = false;
    return true;
  }
  return false;
}

static void play_pcm(const uint8_t *data, uint32_t len, uint32_t src_channels)
{
  src_channels = src_channels == 0 ? 1 : src_channels;
  if (src_channels >= kPlayChannels) {
    audio_playback_write((void *)data, len);
    return;
  }

  uint8_t stereo[512];
  uint32_t offset = 0;
  while (offset + 2 <= len) {
    uint32_t frames = (len - offset) / 2;
    if (frames > 128) {
      frames = 128;
    }
    const int16_t *src = (const int16_t *)(data + offset);
    int16_t *dst = (int16_t *)stereo;
    for (uint32_t i = 0; i < frames; i++) {
      dst[i * 2] = src[i];
      dst[i * 2 + 1] = src[i];
    }
    audio_playback_write(stereo, frames * 4);
    offset += frames * 2;
  }
}

static void play_buzz(void)
{
  audio_pa_enable(true);
  audio_set_playing(true);

  const int freq = 700;
  const int burst_ms = 140;
  const int gap_ms = 70;
  int16_t chunk[128];
  const uint32_t frames_per_burst = (kSampleRate * burst_ms) / 1000;
  const uint32_t frames_per_gap = (kSampleRate * gap_ms) / 1000;
  const int16_t amp = 18000;
  const uint32_t period = kSampleRate / freq;
  const uint32_t half = period > 1 ? period / 2 : 1;

  for (int pulse = 0; pulse < 3; pulse++) {
    uint32_t frame = 0;
    while (frame < frames_per_burst) {
      uint32_t n = frames_per_burst - frame;
      if (n > 64) {
        n = 64;
      }
      for (uint32_t i = 0; i < n; i++) {
        const int16_t sample = (((frame + i) / half) & 1) ? amp : (int16_t)-amp;
        chunk[i * 2] = sample;
        chunk[i * 2 + 1] = sample;
      }
      audio_playback_write(chunk, n * 4);
      frame += n;
    }
    if (pulse < 2) {
      memset(chunk, 0, sizeof(chunk));
      uint32_t frame_gap = 0;
      while (frame_gap < frames_per_gap) {
        uint32_t n = frames_per_gap - frame_gap;
        if (n > 64) {
          n = 64;
        }
        audio_playback_write(chunk, n * 4);
        frame_gap += n;
      }
    }
  }

  audio_set_playing(false);
}

static uint32_t read_response(HTTPClient &http, uint8_t *dest, uint32_t max_len)
{
  int remaining = http.getSize();
  WiFiClient *stream = http.getStreamPtr();
  uint32_t got = 0;
  uint32_t deadline = millis() + 45000;

  while (http.connected() && got < max_len && millis() < deadline) {
    if (remaining == 0) {
      break;
    }
    size_t avail = stream->available();
    if (avail == 0) {
      vTaskDelay(pdMS_TO_TICKS(1));
      continue;
    }
    uint32_t want = max_len - got;
    if (avail < want) {
      want = avail;
    }
    int n = stream->readBytes(dest + got, want);
    if (n <= 0) {
      break;
    }
    got += (uint32_t)n;
    if (remaining > 0) {
      remaining -= n;
      if (remaining <= 0) {
        break;
      }
    }
  }
  return got;
}

static bool ensure_wifi(bool *woke_radio)
{
  *woke_radio = false;
  if (wifi_is_connected()) {
    return true;
  }
  *woke_radio = idle_is_sleeping();
  if (*woke_radio) {
    setCpuFrequencyMhz(240);  // join fast, then drop back in restore_sleep_radio
  }
  return wifi_quick_join(8000);
}

static void restore_sleep_radio(bool woke_radio)
{
  (void)woke_radio;
  if (idle_is_sleeping()) {
    wifi_radio_off();
    setCpuFrequencyMhz(80);
  }
}

static bool fetch_due(bool *due, char *key, size_t key_len, int *minutes_until)
{
  *due = false;
  *minutes_until = -999;
  key[0] = '\0';

  WiFiClientSecure tls;
  WiFiClient plain;
  HTTPClient http;
  http.setTimeout(8000);
  if (!backend_http_begin(http, tls, plain, "/reminder-due")) {
    return false;
  }
  int code = http.GET();
  if (code == 204) {
    http.end();
    return true;
  }
  if (code != 200) {
    http.end();
    return false;
  }
  String body = http.getString();
  http.end();

  char id[64] = {};
  char start[48] = {};
  json_str(body.c_str(), "id", id, sizeof(id));
  json_str(body.c_str(), "start", start, sizeof(start));
  json_int(body.c_str(), "minutes_until", minutes_until);
  json_bool(body.c_str(), "due", due);
  if (id[0] == '\0') {
    *due = false;
  }
  snprintf(key, key_len, "%s|%s", id, start);
  return true;
}

static bool speak_due_reminder(void)
{
  if (speak_buf == NULL) {
    return false;
  }

  WiFiClientSecure tls;
  WiFiClient plain;
  HTTPClient http;
  http.setTimeout(45000);
  if (!backend_http_begin(http, tls, plain, "/announce-reminder")) {
    return false;
  }
  const char *header_keys[] = {"X-Action", "X-Status", "X-Channels", "X-Event-Id"};
  http.collectHeaders(header_keys, 4);
  int code = http.GET();
  if (code == 204) {
    http.end();
    return false;
  }
  if (code != 201) {
    ESP_LOGW(TAG, "announce HTTP %d", code);
    http.end();
    return false;
  }

  uint32_t spoken = read_response(http, speak_buf, kMaxSpeakBytes);
  uint32_t src_channels = (uint32_t)http.header("X-Channels").toInt();
  http.end();
  if (spoken < 2048) {
    ESP_LOGW(TAG, "announce audio too short (%u)", spoken);
    return false;
  }

  audio_pa_enable(true);
  audio_set_playing(true);
  play_pcm(speak_buf, spoken, src_channels ? src_channels : 1);
  audio_set_playing(false);
  return true;
}

static uint32_t sleep_poll_ms = kSleepPollMinMs;

// Wake early enough to be inside the stay-awake window before the next event.
static void plan_sleep_poll(int minutes_until)
{
  if (minutes_until < 0) {
    sleep_poll_ms = kSleepPollMaxMs;
    return;
  }
  const int lead_min = minutes_until - kStayAwakeMinutes - 2;
  if (lead_min <= 0) {
    sleep_poll_ms = kSleepPollMinMs;
  } else {
    const uint32_t ms = (uint32_t)lead_min * 60000UL;
    sleep_poll_ms = ms < kSleepPollMinMs ? kSleepPollMinMs : (ms > kSleepPollMaxMs ? kSleepPollMaxMs : ms);
  }
}

// Sleep until the next poll, but check right away if the pin wakes up.
static void wait_next_poll(void)
{
  const bool was_sleeping = idle_is_sleeping();
  const uint32_t wait_ms = was_sleeping ? sleep_poll_ms : kAwakePollMs;
  const uint32_t start = millis();
  while ((millis() - start) < wait_ms) {
    vTaskDelay(pdMS_TO_TICKS(1000));
    if (was_sleeping && !idle_is_sleeping()) {
      return;
    }
  }
}

static void reminder_task(void *arg)
{
  (void)arg;
  for (;;) {
    wait_next_poll();
    const bool sleeping = idle_is_sleeping();

    if (voice_note_is_busy() || audio_is_playing()) {
      continue;
    }
    if (WiFi.status() != WL_CONNECTED && !sleeping) {
      continue;
    }

    bool woke_radio = false;
    if (!ensure_wifi(&woke_radio)) {
      restore_sleep_radio(woke_radio);
      continue;
    }

    bool due = false;
    char key[96] = {};
    int minutes_until = -999;
    if (!fetch_due(&due, key, sizeof(key), &minutes_until)) {
      restore_sleep_radio(woke_radio);
      continue;
    }
    plan_sleep_poll(minutes_until);

    if (minutes_until >= 0 && minutes_until <= kStayAwakeMinutes) {
      if (idle_is_sleeping()) {
        idle_wake_sync();
      }
      idle_touch();
      woke_radio = false;
    }

    if (!due || key[0] == '\0' || strcmp(key, last_alert_key) == 0) {
      restore_sleep_radio(woke_radio);
      continue;
    }

    if (idle_is_sleeping()) {
      idle_wake_sync();
    }
    idle_touch();
    home_ui_set_status_for("Reminder", 4000);
    ESP_LOGI(TAG, "buzz+speak %s (%d min)", key, minutes_until);
    strncpy(last_alert_key, key, sizeof(last_alert_key) - 1);
    last_alert_key[sizeof(last_alert_key) - 1] = '\0';
    play_buzz();
    speak_due_reminder();
    home_ui_set_status_for("", 0);
  }
}

void reminder_alert_start(void)
{
  speak_buf = (uint8_t *)heap_caps_malloc(kMaxSpeakBytes, MALLOC_CAP_SPIRAM);
  if (speak_buf == NULL) {
    ESP_LOGE(TAG, "PSRAM alloc failed");
    return;
  }
  xTaskCreatePinnedToCore(reminder_task, "remind", 8 * 1024, NULL, 3, NULL, 1);
}
