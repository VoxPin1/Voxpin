#include "side_buttons.h"

#include <HTTPClient.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <WiFiClientSecure.h>
#include <stdio.h>
#include <string.h>

#include "backend_http.h"
#include "board_pins.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "side_btn";
static void (*status_cb)(const char *text) = NULL;

static void set_status(const char *text, uint32_t hold_ms)
{
  if (status_cb != NULL) {
    status_cb(text);
  }
  ESP_LOGI(TAG, "%s", text);
  if (hold_ms > 0) {
    vTaskDelay(pdMS_TO_TICKS(hold_ms));
  }
}

static bool plus_pressed(void)
{
  return gpio_get_level(PLUS_BUTTON_PIN) == 0;
}

static void wait_release(void)
{
  while (plus_pressed()) {
    vTaskDelay(pdMS_TO_TICKS(20));
  }
  vTaskDelay(pdMS_TO_TICKS(40));
}

static int scan_wifi_json(char *out, size_t out_len)
{
  int n = WiFi.scanNetworks(false, true, false, 300);
  if (n < 0) {
    n = 0;
  }
  if (n > 8) {
    n = 8;
  }
  size_t used = 0;
  int wrote = snprintf(out, out_len, "{\"wifi\":[");
  if (wrote < 0) {
    return 0;
  }
  used = (size_t)wrote;
  for (int i = 0; i < n && used + 48 < out_len; i++) {
    wrote = snprintf(
      out + used,
      out_len - used,
      "%s{\"mac\":\"%s\",\"rssi\":%d}",
      i ? "," : "",
      WiFi.BSSIDstr(i).c_str(),
      WiFi.RSSI(i));
    if (wrote < 0) {
      break;
    }
    used += (size_t)wrote;
  }
  snprintf(out + used, out_len - used, "]}");
  return n;
}

static bool post_event(const char *path, const char *ok_status)
{
  if (WiFi.status() != WL_CONNECTED) {
    set_status("No WiFi", 2500);
    return false;
  }

  char body[640];
  scan_wifi_json(body, sizeof(body));

  WiFiClientSecure tls;
  WiFiClient plain;
  HTTPClient http;
  http.setTimeout(15000);
  if (!backend_http_begin(http, tls, plain, path)) {
    set_status("Send failed", 2500);
    return false;
  }
  http.addHeader("Content-Type", "application/json");
  const char *header_keys[] = {"X-Action", "X-Status"};
  http.collectHeaders(header_keys, 2);
  int code = http.POST((uint8_t *)body, strlen(body));
  String status = http.header("X-Status");
  http.end();
  if (code == 200) {
    set_status(status.length() ? status.c_str() : ok_status, 3500);
    set_status("", 0);
    return true;
  }
  ESP_LOGE(TAG, "%s HTTP %d", path, code);
  set_status(code < 0 ? "No server" : "Send failed", 2500);
  set_status("", 0);
  return false;
}

static void side_buttons_task(void *arg)
{
  (void)arg;
  gpio_config_t io = {};
  io.intr_type = GPIO_INTR_DISABLE;
  io.mode = GPIO_MODE_INPUT;
  io.pin_bit_mask = 1ULL << PLUS_BUTTON_PIN;
  io.pull_up_en = GPIO_PULLUP_ENABLE;
  io.pull_down_en = GPIO_PULLDOWN_DISABLE;
  gpio_config(&io);

  for (;;) {
    while (!plus_pressed()) {
      vTaskDelay(pdMS_TO_TICKS(20));
    }
    const uint32_t started = millis();
    while (plus_pressed() && (millis() - started) < 900) {
      vTaskDelay(pdMS_TO_TICKS(20));
    }
    const bool held = plus_pressed() && (millis() - started) >= 900;
    wait_release();
    if (held) {
      set_status("Sending help", 0);
      post_event("/sos", "Help sent");
    } else {
      set_status("Sending loc", 0);
      post_event("/ping", "Sent loc");
    }
  }
}

void side_buttons_start(void (*cb)(const char *text))
{
  status_cb = cb;
  xTaskCreatePinnedToCore(side_buttons_task, "side_btn", 8 * 1024, NULL, 5, NULL, 1);
}
