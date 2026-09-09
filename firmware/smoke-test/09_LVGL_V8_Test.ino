#include "wifi_connect.h"
#include "user_app.h"
#include "lvgl_port.h"
#include "ble_companion.h"

void setup()
{
  Serial.begin(115200);
  delay(500);
  Serial.println("VoxPin home screen starting...");

  user_app_init();

  if (wifi_connect_begin()) {
    Serial.print("WiFi connected, IP: ");
    Serial.println(wifi_connect_ip());
    user_app_sync_time_from_ntp();
    Serial.println("RTC synced from NTP");
  } else {
    Serial.println("WiFi failed — using RTC as-is");
  }

  ble_companion_begin();

  lvgl_port();
  Serial.println("Home screen ready.");
}

void loop() {}
