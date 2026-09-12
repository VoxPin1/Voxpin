#include "wifi_connect.h"
#include "home_ui.h"
#include "power.h"
#include "ble_companion.h"
#include "voice_note.h"
#include "side_buttons.h"

void setup()
{
  power_hold_on();
  Serial.begin(115200);
  Serial.setTxTimeoutMs(0);
  delay(300);
  Serial.println("VoxPin LCD-0.85 starting...");
  Serial.flush();

  power_init();

  if (wifi_connect_begin(45000)) {
    Serial.print("WiFi connected, IP: ");
    Serial.println(wifi_connect_ip());
    home_ui_sync_time_from_ntp();
    Serial.println("Time synced from NTP");
  } else {
    Serial.println("WiFi failed — clock waits for NTP");
  }

  ble_companion_begin();
  home_ui_begin();
  voice_note_init();
  voice_note_start(home_ui_set_status);
  side_buttons_start(home_ui_set_status);
  Serial.println("Home screen ready.");
  Serial.flush();
}

void loop() {}
