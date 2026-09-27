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
#include "idle.h"
#include "wifi_connect.h"

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
static constexpr uint32_t kHeldReleaseTailBytes = kBytesPerSec / 4;
static constexpr uint32_t kSilenceStopBytes = kBytesPerSec / 3;
static constexpr uint32_t kMaxAfterReleaseBytes = kBytesPerSec * 2;
// Clips upload at half the mic rate: half the bytes, still fine for speech.
static constexpr uint32_t kUploadSampleRate = kSampleRate / 2;

static uint8_t *audio_buf = NULL;
static voice_status_cb_t status_cb = NULL;
static volatile bool voice_busy = false;

static bool chunk_is_loud(const uint8_t *data, uint32_t len)
{
  const int16_t *samples = (const int16_t *)data;
  const uint32_t count = len / 2;
  uint32_t hits = 0;
  for (uint32_t i = 0; i < count; i += 8) {
    int16_t sample = samples[i];
    if (sample < 0) {
      sample = (int16_t)-sample;
    }
    if (sample > 500) {
      hits++;
    }
  }
  return hits >= 3;
}

static uint32_t trim_pcm16(uint8_t *data, uint32_t len)
{
  if (data == NULL || len < 4) {
    return len;
  }
  int16_t *samples = (int16_t *)data;
  uint32_t count = len / 2;
  const int16_t thresh = 450;
  uint32_t start = 0;
  uint32_t end = count;
  while (start < count) {
    int16_t sample = samples[start];
    if (sample < 0) {
      sample = (int16_t)-sample;
    }
    if (sample >= thresh) {
      break;
    }
    start++;
  }
  while (end > start) {
    int16_t sample = samples[end - 1];
    if (sample < 0) {
      sample = (int16_t)-sample;
    }
    if (sample >= thresh) {
      break;
    }
    end--;
  }
  const uint32_t pad = kSampleRate / 10;
  if (start > pad) {
    start -= pad;
  } else {
    start = 0;
  }
  if (end + pad < count) {
    end += pad;
  } else {
    end = count;
  }
  const uint32_t out_n = end - start;
  if (start > 0 && out_n > 0) {
    memmove(samples, samples + start, out_n * 2);
  }
  return out_n * 2;
}

// IMA ADPCM, bit-for-bit what Python's audioop.adpcm2lin decodes: state starts
// at 0/0 and the first sample of each pair goes in the high nibble. Encodes in
// place and returns the new length. A quarter of the bytes matters because the
// ESP32's 5.7 KB TCP window caps hotspot uploads near 5 KB/s.
static uint32_t pcm16_to_ima_adpcm(uint8_t *data, uint32_t len)
{
  static const int8_t kIndexTable[16] = {
    -1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8,
  };
  static const int16_t kStepTable[89] = {
    7,     8,     9,     10,    11,    12,    13,    14,    16,    17,
    19,    21,    23,    25,    28,    31,    34,    37,    41,    45,
    50,    55,    60,    66,    73,    80,    88,    97,    107,   118,
    130,   143,   157,   173,   190,   209,   230,   253,   279,   307,
    337,   371,   408,   449,   494,   544,   598,   658,   724,   796,
    876,   963,   1060,  1166,  1282,  1411,  1552,  1707,  1878,  2066,
    2272,  2499,  2749,  3024,  3327,  3660,  4026,  4428,  4871,  5358,
    5894,  6484,  7132,  7845,  8630,  9493,  10442, 11487, 12635, 13899,
    15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767,
  };
  const int16_t *in = (const int16_t *)data;
  const uint32_t count = (len / 2) & ~1u;
  int valpred = 0;
  int index = 0;
  uint8_t high = 0;
  for (uint32_t i = 0; i < count; i++) {
    int step = kStepTable[index];
    int diff = in[i] - valpred;
    const int sign = diff < 0 ? 8 : 0;
    if (sign) {
      diff = -diff;
    }
    int delta = 0;
    int vpdiff = step >> 3;
    if (diff >= step) {
      delta = 4;
      diff -= step;
      vpdiff += step;
    }
    step >>= 1;
    if (diff >= step) {
      delta |= 2;
      diff -= step;
      vpdiff += step;
    }
    step >>= 1;
    if (diff >= step) {
      delta |= 1;
      vpdiff += step;
    }
    valpred += sign ? -vpdiff : vpdiff;
    if (valpred > 32767) {
      valpred = 32767;
    } else if (valpred < -32768) {
      valpred = -32768;
    }
    delta |= sign;
    index += kIndexTable[delta];
    if (index < 0) {
      index = 0;
    } else if (index > 88) {
      index = 88;
    }
    if ((i & 1) == 0) {
      high = (uint8_t)(delta << 4);
    } else {
      data[i >> 1] = high | (uint8_t)delta;
    }
  }
  return count / 2;
}

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

// Halve the sample rate in place by averaging sample pairs. Returns new length.
static uint32_t downsample_half(uint8_t *data, uint32_t len)
{
  int16_t *s = (int16_t *)data;
  const uint32_t out = len / 4;
  for (uint32_t i = 0; i < out; i++) {
    s[i] = (int16_t)(((int32_t)s[i * 2] + (int32_t)s[i * 2 + 1]) / 2);
  }
  return out * 2;
}

static bool handle_clip_inner(uint8_t *data, uint32_t len)
{
  len = downsample_half(data, len);
  len = pcm16_to_ima_adpcm(data, len);

  if (WiFi.status() != WL_CONNECTED) {
    show_status("Connecting", 0);
    if (!wifi_wait_connected(30000)) {
      show_status("No WiFi", 2500);
      return false;
    }
    show_status("Sending", 0);
  }

  bool tried_cloud = false;
  int local_tries = 0;
  for (;;) {
    WiFiClientSecure tls;
    WiFiClient plain;
    HTTPClient http;
    http.setTimeout(20000);
    if (!backend_http_begin(http, tls, plain, "/note")) {
      http.end();
      if (!tried_cloud && backend_fallback_cloud()) {
        tried_cloud = true;
        continue;
      }
      show_status("Send failed", 2500);
      return false;
    }

    http.addHeader("Content-Type", "application/octet-stream");
    http.addHeader("X-Sample-Rate", String(kUploadSampleRate));
    http.addHeader("X-Reply-Rate", String(kSampleRate));
    http.addHeader("X-Channels", "1");
    http.addHeader("X-Bits", "16");
    http.addHeader("X-Encoding", "ima-adpcm");
    const char *header_keys[] = {"X-Action", "X-Status", "X-Channels"};
    http.collectHeaders(header_keys, 3);

    int code = http.POST(data, len);
    String pin_status = http.header("X-Status");
    // Venue Wi-Fi often drops the first upload. Retry this Mac before
    // spending time on the cloud fallback.
    if (code < 0 && !tried_cloud && local_tries < 2) {
      http.end();
      local_tries++;
      delay(250);
      continue;
    }
    if (code < 0 && !tried_cloud && backend_fallback_cloud()) {
      http.end();
      tried_cloud = true;
      continue;
    }
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
      } else if (action == "ask") {
        show_status("Answered", 3500);
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

    audio_set_playing(true);
    play_pcm(data, spoken, src_channels ? src_channels : kPlayChannels);
    audio_set_playing(false);
    return true;
  }
}

// Upload and reply download run with WiFi power save off so talking stays snappy.
static bool handle_clip(uint8_t *data, uint32_t len)
{
  wifi_set_fast(true);
  const bool ok = handle_clip_inner(data, len);
  wifi_set_fast(false);
  return ok;
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

    idle_touch();
    if (idle_is_sleeping()) {
      show_status("Waking", 0);
      idle_wake_sync();
    }

    show_status("Recording", 0);
    voice_busy = true;
    memset(audio_buf, 0, kMaxBytes);
    uint32_t written = 0;
    const uint32_t press_started = millis();
    bool saw_release = false;
    uint32_t silence_bytes = 0;
    uint32_t after_release = 0;

    while (written + kChunkBytes <= kMaxRecordBytes) {
      audio_playback_read(audio_buf + written, kChunkBytes);
      const bool loud = chunk_is_loud(audio_buf + written, kChunkBytes);
      written += kChunkBytes;

      const bool down = boot_pressed();
      if (!down) {
        saw_release = true;
      } else if (saw_release) {
        wait_boot_release();
        break;
      }

      if (saw_release) {
        after_release += kChunkBytes;
        if (loud) {
          silence_bytes = 0;
        } else {
          silence_bytes += kChunkBytes;
        }
        const bool held = (millis() - press_started) >= kHoldToTalkMs;
        // Hold-to-talk: releasing means done. Don't wait for silence, which
        // never comes in a noisy room.
        if (held && (silence_bytes >= kSilenceStopBytes || after_release >= kHeldReleaseTailBytes)) {
          break;
        }
        if (!held && (silence_bytes >= kSilenceStopBytes || after_release >= kMaxAfterReleaseBytes)) {
          break;
        }
      }
    }

    wait_boot_release();
    written = trim_pcm16(audio_buf, written);

    if (written < kMinBytes) {
      voice_busy = false;
      show_status("Too short", 2000);
      show_status("", 0);
      continue;
    }

    show_status("Sending", 0);
    handle_clip(audio_buf, written);
    voice_busy = false;
    show_status("", 0);
  }
}

bool voice_note_is_busy(void)
{
  return voice_busy;
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
