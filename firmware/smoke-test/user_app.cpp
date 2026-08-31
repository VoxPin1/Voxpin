#include <stdio.h>
#include <time.h>
#include <WiFi.h>
#include "freertos/FreeRTOS.h"
#include "user_app.h"
#include "driver/gpio.h"
#include "user_config.h"
#include "esp_log.h"
#include "esp_err.h"

#include "src/ui_src/generated/gui_guider.h"
#include "src/power/board_power_bsp.h"
#include "i2c_bsp.h"
#include "i2c_equipment.h"
#include "adc_bsp.h"
#include "voice_note.h"

epaper_driver_display *driver = NULL;
board_power_bsp_t board_div(EPD_PWR_PIN, Audio_PWR_PIN, VBAT_PWR_PIN);
i2c_equipment *rtc_dev = NULL;

lv_ui src_ui;
static lv_obj_t *status_label = NULL;

typedef struct {
  lv_obj_t *time_label;
  lv_obj_t *date_label;
  lv_obj_t *battery_label;
} home_screen_t;

static int battery_percent(float voltage)
{
  if (voltage >= 4.15f) {
    return 100;
  }
  if (voltage <= 3.20f) {
    return 0;
  }
  return (int)((voltage - 3.20f) / (4.15f - 3.20f) * 100.0f);
}

void user_app_sync_time_from_ntp(void)
{
  if (WiFi.status() != WL_CONNECTED || rtc_dev == NULL) {
    return;
  }

  configTzTime("PST8PDT", "pool.ntp.org");
  struct tm timeinfo {};
  for (int i = 0; i < 20; i++) {
    if (getLocalTime(&timeinfo, 1000)) {
      rtc_dev->set_rtcTime(
        (uint16_t)(timeinfo.tm_year + 1900),
        (uint8_t)(timeinfo.tm_mon + 1),
        (uint8_t)timeinfo.tm_mday,
        (uint8_t)timeinfo.tm_hour,
        (uint8_t)timeinfo.tm_min,
        (uint8_t)timeinfo.tm_sec);
      return;
    }
    delay(500);
  }
}

static void voice_status(const char *text)
{
  if (status_label == NULL) {
    return;
  }
  lv_label_set_text(status_label, (text != NULL) ? text : "");
  lv_obj_invalidate(status_label);
}

void user_app_init(void)
{
  board_div.VBAT_POWER_ON();
  board_div.POWEER_EPD_ON();
  board_div.POWEER_Audio_ON();

  i2c_master_Init();
  rtc_dev = new i2c_equipment();
  adc_bsp_init();
  voice_note_init();

  custom_lcd_spi_t driver_config = {};
  driver_config.cs = EPD_CS_PIN;
  driver_config.dc = EPD_DC_PIN;
  driver_config.rst = EPD_RST_PIN;
  driver_config.busy = EPD_BUSY_PIN;
  driver_config.mosi = EPD_MOSI_PIN;
  driver_config.scl = EPD_SCK_PIN;
  driver_config.spi_host = EPD_SPI_NUM;
  driver_config.buffer_len = 5000;

  driver = new epaper_driver_display(EPD_WIDTH, EPD_HEIGHT, driver_config);
  driver->EPD_Init();
  driver->EPD_Clear();
  driver->EPD_DisplayPartBaseImage();
  driver->EPD_Init_Partial();
}

static void update_home_labels(home_screen_t *home)
{
  RtcDateTime_t dt = rtc_dev->get_rtcTime();
  float voltage = 0.0f;
  int raw = 0;
  adc_get_value(&voltage, &raw);
  int pct = battery_percent(voltage);

  static const char *days[] = {"Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"};
  static const char *months[] = {"Jan", "Feb", "Mar", "Apr", "May", "Jun",
                                 "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"};
  const char *day_name = (dt.week <= 6) ? days[dt.week] : "---";
  const char *month_name = (dt.month >= 1 && dt.month <= 12) ? months[dt.month - 1] : "---";

  int hour12 = dt.hour % 12;
  if (hour12 == 0) {
    hour12 = 12;
  }
  const char *ampm = (dt.hour >= 12) ? "PM" : "AM";

  char time_text[16];
  char date_text[24];
  char battery_text[24];

  snprintf(time_text, sizeof(time_text), "%d:%02d", hour12, dt.minute);
  snprintf(date_text, sizeof(date_text), "%s  %s %d  %s", day_name, month_name, dt.day, ampm);
  snprintf(battery_text, sizeof(battery_text), "Battery %d%%", pct);

  lv_label_set_text(home->time_label, time_text);
  lv_label_set_text(home->date_label, date_text);
  lv_label_set_text(home->battery_label, battery_text);

  lv_obj_invalidate(home->time_label);
  lv_obj_invalidate(home->date_label);
  lv_obj_invalidate(home->battery_label);
}

static uint32_t ms_until_next_minute(void)
{
  RtcDateTime_t dt = rtc_dev->get_rtcTime();
  uint32_t sec = dt.second;
  if (sec >= 59) {
    return 60000;
  }
  return (60 - sec) * 1000;
}

void home_screen_task(void *arg)
{
  lv_ui *ui = (lv_ui *)arg;
  lv_obj_add_flag(ui->screen_img_1, LV_OBJ_FLAG_HIDDEN);
  lv_obj_add_flag(ui->screen_img_2, LV_OBJ_FLAG_HIDDEN);

  home_screen_t home = {};

  home.time_label = lv_label_create(ui->screen);
  lv_obj_set_style_text_font(home.time_label, &lv_font_montserrat_48, 0);
  lv_obj_set_style_text_align(home.time_label, LV_TEXT_ALIGN_CENTER, 0);
  lv_obj_set_width(home.time_label, EPD_WIDTH);
  lv_obj_align(home.time_label, LV_ALIGN_TOP_MID, 0, 18);

  home.date_label = lv_label_create(ui->screen);
  lv_obj_set_style_text_font(home.date_label, &lv_font_montserrat_24, 0);
  lv_obj_set_style_text_align(home.date_label, LV_TEXT_ALIGN_CENTER, 0);
  lv_obj_set_width(home.date_label, EPD_WIDTH);
  lv_obj_align(home.date_label, LV_ALIGN_TOP_MID, 0, 88);

  home.battery_label = lv_label_create(ui->screen);
  lv_obj_set_style_text_font(home.battery_label, &lv_font_montserrat_28, 0);
  lv_obj_set_style_text_align(home.battery_label, LV_TEXT_ALIGN_CENTER, 0);
  lv_obj_set_width(home.battery_label, EPD_WIDTH);
  lv_obj_align(home.battery_label, LV_ALIGN_TOP_MID, 0, 138);

  status_label = lv_label_create(ui->screen);
  lv_obj_set_style_text_font(status_label, &lv_font_montserrat_14, 0);
  lv_obj_set_style_text_align(status_label, LV_TEXT_ALIGN_CENTER, 0);
  lv_obj_set_width(status_label, EPD_WIDTH);
  lv_obj_align(status_label, LV_ALIGN_TOP_MID, 0, 172);
  lv_label_set_text(status_label, "");

  update_home_labels(&home);
  voice_note_start(voice_status);

  for (;;) {
    vTaskDelay(pdMS_TO_TICKS(ms_until_next_minute()));
    update_home_labels(&home);
  }
}

void user_ui_init(void)
{
  setup_ui(&src_ui);
  xTaskCreatePinnedToCore(home_screen_task, "home_screen_task", 4 * 1024, &src_ui, 4, NULL, 1);
}
