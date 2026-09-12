#include "wifi_connect.h"
#include "wifi_secrets.h"

#include <WiFi.h>

bool wifi_connect_begin(uint32_t timeout_ms)
{
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  delay(100);

  int n = WiFi.scanNetworks(false, true, false, 400);
  Serial.printf("WiFi scan found %d networks\n", n);
  for (int i = 0; i < n && i < 12; i++) {
    Serial.printf("  ch%d %s rssi=%d\n", WiFi.channel(i), WiFi.SSID(i).c_str(), WiFi.RSSI(i));
  }

  Serial.printf("WiFi joining '%s'\n", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  const unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && (millis() - start) < timeout_ms) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.printf("WiFi status=%d\n", (int)WiFi.status());
  return WiFi.status() == WL_CONNECTED;
}

String wifi_connect_ip()
{
  if (WiFi.status() != WL_CONNECTED) {
    return String();
  }
  return WiFi.localIP().toString();
}
