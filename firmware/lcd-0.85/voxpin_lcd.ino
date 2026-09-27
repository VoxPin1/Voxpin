#include "wifi_connect.h"
#include "home_ui.h"
#include "power.h"
#include "ble_companion.h"
#include "voice_note.h"
#include "side_buttons.h"
#include "idle.h"
#include "reminder_alert.h"

void setup()
{
  power_hold_on();
  Serial.begin(115200);
  Serial.setTxTimeoutMs(0);
  delay(300);
  Serial.println("VoxPin LCD-0.85 starting...");
  Serial.flush();

  power_init();

  // Light the screen before Wi-Fi. Joining venue access points can take
  // a minute, and a black screen looks like the pin is off.
  home_ui_begin();
  home_ui_set_status("Connecting");

  if (wifi_connect_begin(45000)) {
    Serial.print("WiFi connected, IP: ");
    Serial.println(wifi_connect_ip());
    if (home_ui_sync_time_from_ntp()) {
      Serial.println("Time synced from NTP");
    } else {
      Serial.println("NTP not ready yet — will retry");
    }
  } else {
    home_ui_sync_time_from_ntp();
    Serial.println("WiFi failed — clock will sync once WiFi is up");
  }
  home_ui_set_status("");

  ble_companion_begin();
  voice_note_init();
  voice_note_start(home_ui_set_status);
  side_buttons_start(home_ui_set_status);
  reminder_alert_start();
  idle_start();
  Serial.println("Home screen ready.");
  Serial.flush();
}

void loop()
{
  wifi_maintain();
  delay(100);
}
