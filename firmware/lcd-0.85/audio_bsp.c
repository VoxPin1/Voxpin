#include "audio_bsp.h"

#include "esp_heap_caps.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "src/codec_board/codec_board.h"
#include "src/codec_board/codec_init.h"
#include "src/esp_codec_dev/include/esp_codec_dev.h"

static const char *TAG = "audio_bsp";

static esp_codec_dev_handle_t playback = NULL;
static esp_codec_dev_handle_t record = NULL;

void audio_bsp_init(void)
{
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

  esp_codec_dev_set_out_vol(playback, 80.0);
  esp_codec_dev_set_in_gain(record, 40.0);

  esp_codec_dev_sample_info_t out_fs = {};
  out_fs.sample_rate = 16000;
  out_fs.channel = 2;
  out_fs.bits_per_sample = 16;
  if (esp_codec_dev_open(playback, &out_fs) != ESP_CODEC_DEV_OK) {
    ESP_LOGE(TAG, "playback open failed");
  }

  esp_codec_dev_sample_info_t in_fs = {};
  in_fs.sample_rate = 16000;
  in_fs.channel = 2;
  in_fs.bits_per_sample = 16;
  in_fs.channel_mask = ESP_CODEC_DEV_MAKE_CHANNEL_MASK(0);
  if (esp_codec_dev_open(record, &in_fs) != ESP_CODEC_DEV_OK) {
    ESP_LOGW(TAG, "record open with 2ch failed, trying 4ch TDM");
    in_fs.channel = 4;
    in_fs.channel_mask = ESP_CODEC_DEV_MAKE_CHANNEL_MASK(0);
    if (esp_codec_dev_open(record, &in_fs) != ESP_CODEC_DEV_OK) {
      ESP_LOGE(TAG, "record open failed");
    }
  }
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
  if (playback == NULL) {
    return;
  }
  esp_codec_dev_write(playback, data_ptr, len);
}
