#include "voice_note.h"

#include <HTTPClient.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <stdio.h>

#include "audio_bsp.h"
#include "backend_config.h"
#include "driver/gpio.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "user_config.h"

static const char *TAG = "voice_note";

static constexpr uint32_t kSampleRate = 16000;
static constexpr uint32_t kChannels = 2;
static constexpr uint32_t kBits = 16;
static constexpr uint32_t kBytesPerSec = kSampleRate * kChannels * (kBits / 8);
static constexpr uint32_t kChunkBytes = 4096;
static constexpr uint32_t kMaxSeconds = 20;
static constexpr uint32_t kMaxBytes = kBytesPerSec * kMaxSeconds;
static constexpr uint32_t kMinBytes = kBytesPerSec / 4;  // ~0.25 s

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

static void play_pcm(const uint8_t *data, uint32_t len)
{
  uint32_t offset = 0;
  while (offset < len) {
    uint32_t n = len - offset;
    if (n > kChunkBytes) {
      n = kChunkBytes;
    }
    audio_playback_write((void *)(data + offset), n);
    offset += n;
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
    set_status("No WiFi");
    return false;
  }

  char url[80];
  snprintf(url, sizeof(url), "http://%s:%d/note", BACKEND_HOST, BACKEND_PORT);

  HTTPClient http;
  http.setTimeout(90000);
  if (!http.begin(url)) {
    set_status("Send failed");
    return false;
  }

  http.addHeader("Content-Type", "application/octet-stream");
  http.addHeader("X-Sample-Rate", "16000");
  http.addHeader("X-Channels", "2");
  http.addHeader("X-Bits", "16");

  int code = http.POST(data, len);
  if (code == 204) {
    http.end();
    return true;
  }
  if (code == 200) {
    http.end();
    set_status("Saved");
    vTaskDelay(pdMS_TO_TICKS(4000));
    return true;
  }
  if (code != 201) {
    ESP_LOGE(TAG, "POST failed, HTTP %d", code);
    http.end();
    set_status("Send failed");
    return false;
  }

  set_status("Translating");
  uint32_t spoken = read_response(http, data, kMaxBytes);
  http.end();

  if (spoken < 2048) {
    set_status("Speak failed");
    return false;
  }

  play_pcm(data, spoken);
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

    set_status("Recording");
    uint32_t written = 0;
    while (boot_pressed() && written + kChunkBytes <= kMaxBytes) {
      audio_playback_read(audio_buf + written, kChunkBytes);
      written += kChunkBytes;
    }

    while (boot_pressed()) {
      vTaskDelay(pdMS_TO_TICKS(20));
    }

    if (written < kMinBytes) {
      set_status("");
      vTaskDelay(pdMS_TO_TICKS(200));
      continue;
    }

    set_status("Sending");
    handle_clip(audio_buf, written);
    set_status("");
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
