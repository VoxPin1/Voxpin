#include "power.h"

#include "board_pins.h"
#include "driver/gpio.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_log.h"

static const char *TAG = "power";

static adc_oneshot_unit_handle_t adc_handle = NULL;
static adc_cali_handle_t cali_handle = NULL;
static bool calibrated = false;
static const adc_channel_t kAdcChannel = ADC_CHANNEL_0;  // GPIO1

static int voltage_to_percent(float voltage)
{
  if (voltage >= 4.15f) {
    return 100;
  }
  if (voltage <= 3.20f) {
    return 0;
  }
  return (int)((voltage - 3.20f) / (4.15f - 3.20f) * 100.0f);
}

void power_hold_on(void)
{
  gpio_config_t io = {};
  io.intr_type = GPIO_INTR_DISABLE;
  io.mode = GPIO_MODE_OUTPUT;
  io.pin_bit_mask = 1ULL << BAT_EN_PIN;
  io.pull_up_en = GPIO_PULLUP_DISABLE;
  io.pull_down_en = GPIO_PULLDOWN_DISABLE;
  gpio_config(&io);
  gpio_set_level(BAT_EN_PIN, 1);
}

void power_off(void)
{
  gpio_set_level(BAT_EN_PIN, 0);
}

void power_init(void)
{
  power_hold_on();

  gpio_config_t chg = {};
  chg.intr_type = GPIO_INTR_DISABLE;
  chg.mode = GPIO_MODE_INPUT;
  chg.pin_bit_mask = 1ULL << CHG_STAT_PIN;
  chg.pull_up_en = GPIO_PULLUP_ENABLE;
  chg.pull_down_en = GPIO_PULLDOWN_DISABLE;
  gpio_config(&chg);

  adc_oneshot_unit_init_cfg_t init_config = {};
  init_config.unit_id = ADC_UNIT_1;
  init_config.ulp_mode = ADC_ULP_MODE_DISABLE;
  if (adc_oneshot_new_unit(&init_config, &adc_handle) != ESP_OK) {
    ESP_LOGE(TAG, "ADC init failed");
    adc_handle = NULL;
    return;
  }

  adc_oneshot_chan_cfg_t config = {};
  config.bitwidth = ADC_BITWIDTH_DEFAULT;
  config.atten = ADC_ATTEN_DB_12;
  if (adc_oneshot_config_channel(adc_handle, kAdcChannel, &config) != ESP_OK) {
    ESP_LOGE(TAG, "ADC channel config failed");
    adc_handle = NULL;
    return;
  }

  adc_cali_curve_fitting_config_t cali_config = {};
  cali_config.unit_id = ADC_UNIT_1;
  cali_config.chan = kAdcChannel;
  cali_config.atten = ADC_ATTEN_DB_12;
  cali_config.bitwidth = ADC_BITWIDTH_DEFAULT;
  if (adc_cali_create_scheme_curve_fitting(&cali_config, &cali_handle) == ESP_OK) {
    calibrated = true;
    ESP_LOGI(TAG, "ADC calibration ready");
  } else {
    ESP_LOGW(TAG, "ADC calibration unavailable");
  }
}

float power_battery_voltage(void)
{
  if (adc_handle == NULL) {
    return 0.0f;
  }

  int raw = 0;
  if (adc_oneshot_read(adc_handle, kAdcChannel, &raw) != ESP_OK) {
    return 0.0f;
  }

  if (calibrated) {
    int mv = 0;
    if (adc_cali_raw_to_voltage(cali_handle, raw, &mv) == ESP_OK) {
      return (mv / 1000.0f) * 3.0f;
    }
  }
  return ((float)raw * 3.3f / 4095.0f) * 3.0f;
}

int power_battery_percent(void)
{
  return voltage_to_percent(power_battery_voltage());
}

bool power_is_charging(void)
{
  return gpio_get_level(CHG_STAT_PIN) == 0;
}
