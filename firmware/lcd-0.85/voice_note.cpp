#include "voice_note.h"

#include <HTTPClient.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <WiFiClientSecure.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>

#include "audio_bsp.h"
#include "backend_http.h"
#include "board_pins.h"
#include "driver/gpio.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "voice_note";

static constexpr uint32_t kSampleRate = 16000;
static constexpr uint32_t kChannels = 1;
static constexpr uint32_t kPlayChannels = 2;
static constexpr uint32_t kBits = 16;
static constexpr uint32_t kBytesPerSec = kSampleRate * kChannels * (kBits / 8);
static constexpr uint32_t kChunkBytes = 4096;
static constexpr uint32_t kMaxSeconds = 20;
static constexpr uint32_t kMaxRecordBytes = kBytesPerSec * kMaxSeconds;
static constexpr uint32_t kMaxBytes = kSampleRate * kPlayChannels * (kBits / 8) * kMaxSeconds;
static constexpr uint32_t kMinBytes = kBytesPerSec / 4;
static constexpr uint32_t kHoldToTalkMs = 400;
static constexpr uint32_t kClickAutoSendMs = 8000;

static uint8_t *audio_buf = NULL;
static voice_status_cb_t status_cb = NULL;

static void set_status(const char *text)
{
  if (status_cb != NULL) {
    status_cb(text);
  }
  ESP_LOGI(TAG, "%s", text);
}

static bool boot_pressed(void)
{
  return gpio_get_level(BOOT_BUTTON_PIN) == 0;
}

static void wait_boot_release(void)
{
  while (boot_pressed()) {
    vTaskDelay(pdMS_TO_TICKS(20));
  }
  vTaskDelay(pdMS_TO_TICKS(40));
}

static void show_status(const char *text, uint32_t hold_ms)
{
  set_status(text);
  if (hold_ms > 0) {
    vTaskDelay(pdMS_TO_TICKS(hold_ms));
  }
}

static void play_pcm(const uint8_t *data, uint32_t len, uint32_t src_channels)
{
  src_channels = src_channels == 0 ? 1 : src_channels;
  if (src_channels >= kPlayChannels) {
    uint32_t offset = 0;
    while (offset < len) {
      uint32_t n = len - offset;
      if (n > kChunkBytes) {
        n = kChunkBytes;
      }
      audio_playback_write((void *)(data + offset), n);
      offset += n;
    }
    return;
  }

  uint8_t stereo[kChunkBytes * 2];
  uint32_t offset = 0;
  while (offset < len) {
    uint32_t frames = (len - offset) / 2;
    if (frames > kChunkBytes / 2) {
      frames = kChunkBytes / 2;
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

static uint32_t read_response(HTTPClient &http, uint8_t *dest, uint32_t max_len)
{
  int remaining = http.getSize();
  WiFiClient *stream = http.getStreamPtr();
  uint32_t got = 0;
  uint32_t deadline = millis() + 90000;

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

static bool handle_clip(uint8_t *data, uint32_t len)
{
  if (WiFi.status() != WL_CONNECTED) {
    show_status("No WiFi", 2500);
    return false;
  }

  WiFiClientSecure tls;
  WiFiClient plain;
  HTTPClient http;
  http.setTimeout(90000);
  if (!backend_http_begin(http, tls, plain, "/note")) {
    show_status("Send failed", 2500);
    return false;
  }

  http.addHeader("Content-Type", "application/octet-stream");
  http.addHeader("X-Sample-Rate", "16000");
  http.addHeader("X-Channels", "1");
  http.addHeader("X-Bits", "16");
  const char *header_keys[] = {"X-Action", "X-Status", "X-Channels"};
  http.collectHeaders(header_keys, 3);

  int code = http.POST(data, len);
  String pin_status = http.header("X-Status");
  if (code == 204) {
    http.end();
    show_status("Didn't hear", 2500);
    return false;
  }
  if (code == 200) {
    String action = http.header("X-Action");
    http.end();
    if (pin_status.length() > 0) {
      show_status(pin_status.c_str(), 3500);
    } else if (action == "remind") {
      show_status("Reminded", 3500);
    } else if (action == "timer") {
      show_status("Timer set", 3500);
    } else if (action == "ping") {
      show_status("Sent loc", 3500);
    } else if (action == "sos") {
      show_status("Help sent", 3500);
    } else if (action == "need_login") {
      show_status("Sign in", 3500);
    } else if (action == "note_local") {
      show_status("Saved local", 3500);
    } else {
      show_status("Saved", 3500);
    }
    return true;
  }
  if (code != 201) {
    ESP_LOGE(TAG, "POST failed, HTTP %d", code);
    http.end();
    if (code < 0) {
      show_status("No server", 2500);
    } else {
      char msg[24];
      snprintf(msg, sizeof(msg), "Fail %d", code);
      show_status(msg, 2500);
    }
    return false;
  }

  show_status(pin_status.length() ? pin_status.c_str() : "Speaking", 0);
  uint32_t spoken = read_response(http, data, kMaxBytes);
  uint32_t src_channels = (uint32_t)http.header("X-Channels").toInt();
  http.end();

  if (spoken < 2048) {
    show_status("Speak failed", 2500);
    return false;
  }

  play_pcm(data, spoken, src_channels ? src_channels : kPlayChannels);
  return true;
}

static void voice_note_task(void *arg)
{
  (void)arg;

  gpio_config_t io = {};
  io.intr_type = GPIO_INTR_DISABLE;
  io.mode = GPIO_MODE_INPUT;
  io.pin_bit_mask = 1ULL << BOOT_BUTTON_PIN;
  io.pull_up_en = GPIO_PULLUP_ENABLE;
  io.pull_down_en = GPIO_PULLDOWN_DISABLE;
  gpio_config(&io);

  for (;;) {
    while (!boot_pressed()) {
      vTaskDelay(pdMS_TO_TICKS(20));
    }

    show_status("Recording", 0);
    memset(audio_buf, 0, kMaxBytes);
    uint32_t written = 0;
    const uint32_t press_started = millis();
    bool saw_release = false;

    while (written + kChunkBytes <= kMaxRecordBytes) {
      audio_playback_read(audio_buf + written, kChunkBytes);
      written += kChunkBytes;

      const bool down = boot_pressed();
      if (!down) {
        if (!saw_release && (millis() - press_started) >= kHoldToTalkMs) {
          break;
        }
        saw_release = true;
      } else if (saw_release) {
        wait_boot_release();
        break;
      }

      if (saw_release && (millis() - press_started) >= kClickAutoSendMs) {
        break;
      }
    }

    wait_boot_release();

    if (written < kMinBytes) {
      show_status("Too short", 2000);
      show_status("", 0);
      continue;
    }

    show_status("Sending", 0);
    handle_clip(audio_buf, written);
    show_status("", 0);
  }
}

void voice_note_init(void)
{
  audio_buf = (uint8_t *)heap_caps_malloc(kMaxBytes, MALLOC_CAP_SPIRAM);
  if (audio_buf == NULL) {
    ESP_LOGE(TAG, "PSRAM alloc failed");
    return;
  }
  audio_bsp_init();
  audio_play_init();
  ESP_LOGI(TAG, "Mic ready, max %u seconds", kMaxSeconds);
}

void voice_note_start(voice_status_cb_t cb)
{
  status_cb = cb;
  if (audio_buf == NULL) {
    ESP_LOGE(TAG, "voice_note_init was not called or alloc failed");
    return;
  }
  xTaskCreatePinnedToCore(voice_note_task, "voice_note", 8 * 1024, NULL, 5, NULL, 1);
}
