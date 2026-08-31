#include "wifi_connect.h"
#include "wifi_secrets.h"

#include <WiFi.h>

bool wifi_connect_begin(uint32_t timeout_ms)
{
  WiFi.mode(WIFI_STA);
  WiFi.disconnect(true);
  delay(100);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  const unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && (millis() - start) < timeout_ms) {
    delay(500);
  }
  return WiFi.status() == WL_CONNECTED;
}

String wifi_connect_ip()
{
  if (WiFi.status() != WL_CONNECTED) {
    return String();
  }
  return WiFi.localIP().toString();
}
