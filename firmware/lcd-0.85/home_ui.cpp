#include "home_ui.h"

#include <Arduino.h>
#include <HTTPClient.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <WiFiClientSecure.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#include "Arduino_GFX_Library.h"
#include "audio_bsp.h"
#include "backend_http.h"
#include "board_pins.h"
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "lvgl.h"
#include "power.h"

static Arduino_DataBus *bus = new Arduino_ESP32SPI(
  LCD_DC_PIN, LCD_CS_PIN, LCD_SCK_PIN, LCD_MOSI_PIN, GFX_NOT_DEFINED);
static Arduino_GFX *gfx = new Arduino_GC9107(bus, LCD_RST_PIN, 0, true);

static SemaphoreHandle_t lvgl_mux = NULL;
static lv_obj_t *battery_arc = NULL;
static lv_obj_t *battery_label = NULL;
static lv_obj_t *time_label = NULL;
static lv_obj_t *date_label = NULL;
static lv_obj_t *event_label = NULL;
static lv_obj_t *status_label = NULL;
static char last_event_text[96] = "";
static uint32_t last_event_fetch_ms = 0;
static uint32_t status_clear_at = 0;
static volatile bool ui_paused = false;

static bool ui_lock(int timeout_ms)
{
  const TickType_t ticks = (timeout_ms < 0) ? portMAX_DELAY : pdMS_TO_TICKS(timeout_ms);
  return xSemaphoreTake(lvgl_mux, ticks) == pdTRUE;
}

static void ui_unlock(void)
{
  xSemaphoreGive(lvgl_mux);
}

static void disp_flush(lv_disp_drv_t *disp, const lv_area_t *area, lv_color_t *color_p)
{
  uint32_t w = (area->x2 - area->x1 + 1);
  uint32_t h = (area->y2 - area->y1 + 1);
  gfx->draw16bitRGBBitmap(area->x1, area->y1, (uint16_t *)&color_p->full, w, h);
  lv_disp_flush_ready(disp);
}

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

static void refresh_event_label(void)
{
  if (WiFi.status() != WL_CONNECTED || audio_is_playing()) {
    return;
  }
  if (last_event_fetch_ms != 0 && (millis() - last_event_fetch_ms) < 30000) {
    return;
  }
  last_event_fetch_ms = millis();

  WiFiClientSecure tls;
  WiFiClient plain;
  HTTPClient http;
  http.setTimeout(8000);
  if (!backend_http_begin(http, tls, plain, "/next-event")) {
    return;
  }

  int code = http.GET();
  if (code == 204) {
    last_event_text[0] = '\0';
    lv_label_set_text(event_label, "No events");
    http.end();
    return;
  }
  if (code != 200) {
    http.end();
    return;
  }

  String body = http.getString();
  http.end();

  char when[32] = {};
  char title[64] = {};
  json_str(body.c_str(), "when", when, sizeof(when));
  json_str(body.c_str(), "title", title, sizeof(title));

  if (when[0] != '\0' && title[0] != '\0') {
    snprintf(last_event_text, sizeof(last_event_text), "%s\n%s", when, title);
  } else if (title[0] != '\0') {
    snprintf(last_event_text, sizeof(last_event_text), "%s", title);
  } else if (when[0] != '\0') {
    snprintf(last_event_text, sizeof(last_event_text), "%s", when);
  } else {
    last_event_text[0] = '\0';
  }
  lv_label_set_text(event_label, last_event_text[0] ? last_event_text : "No events");
}

// Only touch labels whose text changed, so the sleeping screen redraws about
// once a minute instead of every second.
static void set_label_if_changed(lv_obj_t *label, const char *text)
{
  if (strcmp(lv_label_get_text(label), text) != 0) {
    lv_label_set_text(label, text);
  }
}

static void update_home_labels(void)
{
  struct tm timeinfo {};
  const bool have_time = getLocalTime(&timeinfo, 10);
  int pct = power_battery_percent();
  bool charging = power_is_charging();

  static const char *days[] = {"Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"};
  static const char *months[] = {"Jan", "Feb", "Mar", "Apr", "May", "Jun",
                                 "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"};

  char time_text[16];
  char date_text[24];
  char bat_text[12];

  if (have_time) {
    int hour12 = timeinfo.tm_hour % 12;
    if (hour12 == 0) {
      hour12 = 12;
    }
    const char *ampm = (timeinfo.tm_hour >= 12) ? "PM" : "AM";
    snprintf(time_text, sizeof(time_text), "%d:%02d", hour12, timeinfo.tm_min);
    snprintf(date_text, sizeof(date_text), "%s %s %d %s",
             days[timeinfo.tm_wday], months[timeinfo.tm_mon], timeinfo.tm_mday, ampm);
  } else {
    snprintf(time_text, sizeof(time_text), "--:--");
    date_text[0] = '\0';
  }

  if (charging) {
    snprintf(bat_text, sizeof(bat_text), "%d%%+", pct);
  } else {
    snprintf(bat_text, sizeof(bat_text), "%d%%", pct);
  }

  if (lv_arc_get_value(battery_arc) != pct) {
    lv_arc_set_value(battery_arc, pct);
  }
  set_label_if_changed(battery_label, bat_text);
  set_label_if_changed(time_label, time_text);
  set_label_if_changed(date_label, date_text);
  refresh_event_label();
}

static void lvgl_task(void *arg)
{
  (void)arg;
  for (;;) {
    if (ui_lock(-1)) {
      if (status_clear_at != 0 && (int32_t)(millis() - status_clear_at) >= 0) {
        status_clear_at = 0;
        if (status_label != NULL) {
          lv_label_set_text(status_label, "");
        }
      }
      lv_timer_handler();
      ui_unlock();
    }
    vTaskDelay(pdMS_TO_TICKS(ui_paused ? 200 : 20));
  }
}

static void home_update_task(void *arg)
{
  (void)arg;
  for (;;) {
    if (ui_lock(-1)) {
      update_home_labels();
      ui_unlock();
    }
    vTaskDelay(pdMS_TO_TICKS(1000));
  }
}

void home_ui_sync_time_from_ntp(void)
{
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }
  configTzTime("PST8PDT", "pool.ntp.org");
  struct tm timeinfo {};
  for (int i = 0; i < 20; i++) {
    if (getLocalTime(&timeinfo, 1000)) {
      return;
    }
  }
}

void home_ui_set_status(const char *text)
{
  if (status_label == NULL || lvgl_mux == NULL) {
    return;
  }
  if (ui_lock(200)) {
    status_clear_at = 0;
    lv_label_set_text(status_label, (text != NULL) ? text : "");
    ui_unlock();
  }
}

void home_ui_set_status_for(const char *text, uint32_t ms)
{
  home_ui_set_status(text);
  if (ms > 0) {
    status_clear_at = millis() + ms;
  }
}

void home_ui_set_paused(bool paused)
{
  ui_paused = paused;
}

void home_ui_set_backlight(uint8_t duty)
{
  ledcWrite(LCD_BL_PIN, duty);
}

void home_ui_begin(void)
{
  Serial.println("lcd backlight");
  Serial.flush();
  ledcAttach(LCD_BL_PIN, 5000, 8);
  ledcWrite(LCD_BL_PIN, 255);

  Serial.println("lcd gfx begin");
  Serial.flush();
  if (!gfx->begin()) {
    Serial.println("LCD init failed");
  }
  gfx->fillScreen(RGB565_BLACK);

  lvgl_mux = xSemaphoreCreateMutex();
  lv_init();

  static lv_disp_draw_buf_t draw_buf;
  static lv_disp_drv_t disp_drv;
  const uint32_t buf_size = LCD_WIDTH * 40;
  lv_color_t *buf1 = (lv_color_t *)heap_caps_malloc(buf_size * sizeof(lv_color_t), MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
  lv_color_t *buf2 = (lv_color_t *)heap_caps_malloc(buf_size * sizeof(lv_color_t), MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
  lv_disp_draw_buf_init(&draw_buf, buf1, buf2, buf_size);

  lv_disp_drv_init(&disp_drv);
  disp_drv.hor_res = LCD_WIDTH;
  disp_drv.ver_res = LCD_HEIGHT;
  disp_drv.flush_cb = disp_flush;
  disp_drv.draw_buf = &draw_buf;
  lv_disp_drv_register(&disp_drv);

  lv_obj_t *scr = lv_scr_act();
  lv_obj_set_style_bg_color(scr, lv_color_hex(0x000000), 0);
  lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);

  // Battery arc - large green circle around the screen
  battery_arc = lv_arc_create(scr);
  lv_obj_set_size(battery_arc, 120, 120);
  lv_obj_align(battery_arc, LV_ALIGN_CENTER, 0, 0);
  lv_arc_set_rotation(battery_arc, 270);
  lv_arc_set_bg_angles(battery_arc, 0, 360);
  lv_arc_set_range(battery_arc, 0, 100);
  lv_obj_remove_style(battery_arc, NULL, LV_PART_KNOB);
  lv_obj_clear_flag(battery_arc, LV_OBJ_FLAG_CLICKABLE);
  // Background track (dark gray)
  lv_obj_set_style_arc_color(battery_arc, lv_color_hex(0x222222), LV_PART_MAIN);
  lv_obj_set_style_arc_width(battery_arc, 8, LV_PART_MAIN);
  // Indicator (green)
  lv_obj_set_style_arc_color(battery_arc, lv_color_hex(0x4CD964), LV_PART_INDICATOR);
  lv_obj_set_style_arc_width(battery_arc, 8, LV_PART_INDICATOR);

  battery_label = lv_label_create(scr);
  lv_obj_set_style_text_font(battery_label, &lv_font_montserrat_12, 0);
  lv_obj_set_style_text_color(battery_label, lv_color_hex(0x4CD964), 0);
  lv_obj_align(battery_label, LV_ALIGN_TOP_MID, 0, 12);
  lv_label_set_text(battery_label, "--%");

  time_label = lv_label_create(scr);
  lv_obj_set_style_text_font(time_label, &lv_font_montserrat_28, 0);
  lv_obj_set_style_text_color(time_label, lv_color_white(), 0);
  lv_obj_set_style_text_align(time_label, LV_TEXT_ALIGN_CENTER, 0);
  lv_obj_set_style_pad_all(time_label, 0, 0);
  lv_obj_set_style_pad_bottom(time_label, 0, 0);
  lv_obj_set_width(time_label, LCD_WIDTH);
  lv_obj_align(time_label, LV_ALIGN_CENTER, 0, -20);

  date_label = lv_label_create(scr);
  lv_obj_set_style_text_font(date_label, &lv_font_montserrat_12, 0);
  lv_obj_set_style_text_color(date_label, lv_color_hex(0xBBBBBB), 0);
  lv_obj_set_style_text_align(date_label, LV_TEXT_ALIGN_CENTER, 0);
  lv_obj_set_style_pad_all(date_label, 0, 0);
  lv_obj_set_width(date_label, LCD_WIDTH);
  lv_obj_align_to(date_label, time_label, LV_ALIGN_OUT_BOTTOM_MID, 0, 0);

  event_label = lv_label_create(scr);
  lv_obj_set_style_text_font(event_label, &lv_font_montserrat_12, 0);
  lv_obj_set_style_text_color(event_label, lv_color_hex(0x8B008B), 0);
  lv_obj_set_style_text_align(event_label, LV_TEXT_ALIGN_CENTER, 0);
  lv_obj_set_style_pad_all(event_label, 0, 0);
  lv_obj_set_style_text_line_space(event_label, 0, 0);
  lv_label_set_long_mode(event_label, LV_LABEL_LONG_WRAP);
  lv_obj_set_width(event_label, LCD_WIDTH - 8);
  lv_obj_set_height(event_label, 50);
  lv_obj_align_to(event_label, date_label, LV_ALIGN_OUT_BOTTOM_MID, 0, 2);
  lv_label_set_text(event_label, "Calendar...");

  status_label = lv_label_create(scr);
  lv_obj_set_style_text_font(status_label, &lv_font_montserrat_12, 0);
  lv_obj_set_style_text_color(status_label, lv_color_hex(0x006400), 0);
  lv_obj_set_style_text_align(status_label, LV_TEXT_ALIGN_CENTER, 0);
  lv_obj_set_width(status_label, LCD_WIDTH);
  lv_obj_align(status_label, LV_ALIGN_BOTTOM_MID, 0, -4);
  lv_label_set_text(status_label, "");

  update_home_labels();

  xTaskCreatePinnedToCore(lvgl_task, "lvgl", 6 * 1024, NULL, 4, NULL, 1);
  xTaskCreatePinnedToCore(home_update_task, "home", 8 * 1024, NULL, 3, NULL, 1);
}
