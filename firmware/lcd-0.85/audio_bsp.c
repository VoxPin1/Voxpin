#include "audio_bsp.h"

#include <string.h>

#include "board_pins.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "src/codec_board/codec_board.h"
#include "src/codec_board/codec_init.h"
#include "src/esp_codec_dev/include/esp_codec_dev.h"

static const char *TAG = "audio_bsp";

static esp_codec_dev_handle_t playback = NULL;
static esp_codec_dev_handle_t record = NULL;
static volatile bool playing = false;
// Internal RAM bounce buffer so I2S never DMA-reads from PSRAM (causes dropouts).
static uint8_t play_ram[2048];

void audio_bsp_init(void)
{
  gpio_config_t pa = {};
  pa.intr_type = GPIO_INTR_DISABLE;
  pa.mode = GPIO_MODE_OUTPUT;
  pa.pin_bit_mask = 1ULL << PA_CTRL_PIN;
  pa.pull_up_en = GPIO_PULLUP_DISABLE;
  pa.pull_down_en = GPIO_PULLDOWN_DISABLE;
  gpio_config(&pa);
  gpio_set_level((gpio_num_t)PA_CTRL_PIN, 1);

  set_codec_board_type("S3_LCD_0_85");
  if (init_i2c(0) != 0) {
    ESP_LOGE(TAG, "i2c init failed");
    return;
  }
  codec_init_cfg_t codec_cfg = {
    .in_mode = CODEC_I2S_MODE_TDM,
    .out_mode = CODEC_I2S_MODE_STD,
    .in_use_tdm = true,
    .reuse_dev = false,
  };
  if (init_codec(&codec_cfg) != 0) {
    ESP_LOGE(TAG, "codec init failed");
    return;
  }
  playback = get_playback_handle();
  record = get_record_handle();
}

void audio_play_init(void)
{
  if (playback == NULL || record == NULL) {
    ESP_LOGE(TAG, "codec handles missing");
    return;
  }

  esp_codec_dev_set_out_vol(playback, 82.0);

  esp_codec_dev_sample_info_t out_fs = {};
  out_fs.sample_rate = 16000;
  out_fs.channel = 2;
  out_fs.bits_per_sample = 16;
  if (esp_codec_dev_open(playback, &out_fs) != ESP_CODEC_DEV_OK) {
    ESP_LOGE(TAG, "playback open failed");
  }

  // Match Waveshare factory: 4-slot TDM, keep MIC1 (slot 0) as mono.
  esp_codec_dev_sample_info_t in_fs = {};
  in_fs.sample_rate = 16000;
  in_fs.channel = 4;
  in_fs.bits_per_sample = 16;
  in_fs.channel_mask = ESP_CODEC_DEV_MAKE_CHANNEL_MASK(0);
  if (esp_codec_dev_open(record, &in_fs) != ESP_CODEC_DEV_OK) {
    ESP_LOGE(TAG, "record open failed");
    return;
  }
  esp_codec_dev_set_in_channel_gain(record, ESP_CODEC_DEV_MAKE_CHANNEL_MASK(0), 37.5);
  esp_codec_dev_set_in_gain(record, 40.0);
  ESP_LOGI(TAG, "record open: 4ch TDM slot0 mono");
}

void audio_playback_read(void *data_ptr, uint32_t len)
{
  if (record == NULL) {
    return;
  }
  esp_codec_dev_read(record, data_ptr, len);
}

void audio_playback_write(void *data_ptr, uint32_t len)
{
  if (playback == NULL || data_ptr == NULL || len == 0) {
    return;
  }

  uint8_t *src = (uint8_t *)data_ptr;
  while (len > 0) {
    uint32_t n = len;
    if (n > sizeof(play_ram)) {
      n = sizeof(play_ram);
    }
    n &= ~3u;
    if (n == 0) {
      break;
    }
    memcpy(play_ram, src, n);
    int ret = esp_codec_dev_write(playback, play_ram, n);
    if (ret != ESP_CODEC_DEV_OK) {
      vTaskDelay(1);
      ret = esp_codec_dev_write(playback, play_ram, n);
    }
    if (ret != ESP_CODEC_DEV_OK) {
      ESP_LOGW(TAG, "I2S write dropped %u bytes", n);
    }
    src += n;
    len -= n;
  }
}

void audio_set_playing(bool on)
{
  playing = on;
}

bool audio_is_playing(void)
{
  return playing;
}
