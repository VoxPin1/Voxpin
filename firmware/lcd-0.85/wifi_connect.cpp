#include "wifi_connect.h"

#include "backend_http.h"
#include "wifi_secrets.h"

#include <HTTPClient.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <WiFiClientSecure.h>
#include <WiFiUdp.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

char g_backend_host[64] = BACKEND_HOST;
int g_backend_port = BACKEND_PORT;
char g_backend_scheme[8] = BACKEND_SCHEME;

#ifndef WIFI_SSID_2
#define WIFI_SSID_2 ""
#define WIFI_PASSWORD_2 ""
#endif

static const uint16_t kBeaconPort = 8766;

static String fold_ssid(const String &input)
{
  String out;
  out.reserve(input.length());
  for (unsigned i = 0; i < input.length();) {
    const uint8_t a = (uint8_t)input[i];
    if (a == 0xE2 && i + 2 < input.length() &&
        (uint8_t)input[i + 1] == 0x80 &&
        ((uint8_t)input[i + 2] == 0x99 || (uint8_t)input[i + 2] == 0x98)) {
      out += '\'';
      i += 3;
      continue;
    }
    out += (char)a;
    i++;
  }
  out.toLowerCase();
  return out;
}

static bool ssid_match(const String &seen, const char *want)
{
  if (want == NULL || want[0] == '\0') {
    return false;
  }
  return fold_ssid(seen) == fold_ssid(String(want));
}

static String scanned_ssid(int n, const char *want)
{
  for (int i = 0; i < n; i++) {
    if (ssid_match(WiFi.SSID(i), want)) {
      return WiFi.SSID(i);
    }
  }
  return String();
}

static void wifi_idle(void)
{
  WiFi.disconnect(true, false);
  const uint32_t start = millis();
  while (WiFi.status() == WL_CONNECTED && (millis() - start) < 1500) {
    delay(50);
  }
  delay(250);
}

static bool try_join(const char *ssid, const char *password, uint32_t timeout_ms)
{
  if (ssid == NULL || ssid[0] == '\0') {
    return false;
  }

  wifi_idle();
  Serial.printf("WiFi joining '%s'\n", ssid);
  if (password == NULL || password[0] == '\0') {
    WiFi.begin(ssid);
  } else {
    WiFi.begin(ssid, password);
  }

  const unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && (millis() - start) < timeout_ms) {
    delay(250);
    Serial.print(".");
  }
  Serial.println();
  Serial.printf("WiFi status=%d\n", (int)WiFi.status());
  return WiFi.status() == WL_CONNECTED;
}

static bool probe_health(const char *host, int port, const char *scheme = "http")
{
  if (host == NULL || host[0] == '\0' || port <= 0 || scheme == NULL || scheme[0] == '\0') {
    return false;
  }
  char url[160];
  if ((port == 443 && strcmp(scheme, "https") == 0) ||
      (port == 80 && strcmp(scheme, "http") == 0)) {
    snprintf(url, sizeof(url), "%s://%s/health", scheme, host);
  } else {
    snprintf(url, sizeof(url), "%s://%s:%d/health", scheme, host, port);
  }

  HTTPClient http;
  const bool tls_mode = strcmp(scheme, "https") == 0;
  http.setTimeout(tls_mode ? 6000 : 2000);
  int code = -1;
  if (tls_mode) {
    WiFiClientSecure tls;
    tls.setInsecure();
    if (!http.begin(tls, url)) {
      return false;
    }
    code = http.GET();
    http.end();
  } else {
    WiFiClient plain;
    if (!http.begin(plain, url)) {
      return false;
    }
    code = http.GET();
    http.end();
  }
  Serial.printf("helper %s:%d -> HTTP %d\n", host, port, code);
  return code == 200;
}

bool backend_fallback_cloud()
{
  if (BACKEND_CLOUD_HOST[0] == '\0') {
    return false;
  }
  if (strcmp(g_backend_host, BACKEND_CLOUD_HOST) == 0 &&
      g_backend_port == BACKEND_CLOUD_PORT) {
    return false;
  }
  if (!probe_health(BACKEND_CLOUD_HOST, BACKEND_CLOUD_PORT, BACKEND_CLOUD_SCHEME)) {
    return false;
  }
  backend_set_target(BACKEND_CLOUD_HOST, BACKEND_CLOUD_PORT, BACKEND_CLOUD_SCHEME);
  Serial.printf("Helper via cloud %s:%d\n", BACKEND_CLOUD_HOST, BACKEND_CLOUD_PORT);
  return true;
}

static bool parse_beacon(const char *msg, char *host, size_t host_len, int *port)
{
  if (strncmp(msg, "VOXPIN ", 7) != 0) {
    return false;
  }
  const char *p = msg + 7;
  size_t i = 0;
  while (*p && *p != ' ' && i + 1 < host_len) {
    host[i++] = *p++;
  }
  host[i] = '\0';
  if (host[0] == '\0') {
    return false;
  }
  while (*p == ' ') {
    p++;
  }
  int parsed = 8765;
  if (*p) {
    parsed = atoi(p);
  }
  if (parsed <= 0) {
    parsed = 8765;
  }
  *port = parsed;
  return true;
}

bool backend_discover(uint32_t timeout_ms)
{
  char found_host[64] = "";
  int found_port = 8765;

  WiFiUDP udp;
  udp.begin(kBeaconPort);
  const uint32_t start = millis();
  while (millis() - start < timeout_ms) {
    int n = udp.parsePacket();
    if (n > 0) {
      char buf[96];
      int got = udp.read(buf, sizeof(buf) - 1);
      if (got > 0) {
        buf[got] = '\0';
        if (parse_beacon(buf, found_host, sizeof(found_host), &found_port) &&
            probe_health(found_host, found_port)) {
          backend_set_target(found_host, found_port, "http");
          udp.stop();
          Serial.printf("Helper via beacon %s:%d\n", found_host, found_port);
          return true;
        }
      }
    }
    delay(50);
  }
  udp.stop();

  const char *candidates[] = {
    g_backend_host,
    BACKEND_HOST,
    "192.168.68.56",
    "192.168.68.85",
    "172.20.10.2",
    "192.0.0.2",
  };
  IPAddress gw = WiFi.gatewayIP();
  char gw_text[16];
  snprintf(gw_text, sizeof(gw_text), "%u.%u.%u.%u", gw[0], gw[1], gw[2], gw[3]);

  for (size_t i = 0; i < sizeof(candidates) / sizeof(candidates[0]); i++) {
    if (probe_health(candidates[i], 8765)) {
      backend_set_target(candidates[i], 8765, "http");
      return true;
    }
  }
  if (gw[0] != 0 && probe_health(gw_text, 8765)) {
    backend_set_target(gw_text, 8765, "http");
    return true;
  }
  if (backend_fallback_cloud()) {
    return true;
  }

  Serial.println("Helper not found yet");
  return false;
}

void backend_set_target(const char *host, int port, const char *scheme)
{
  if (host != NULL && host[0] != '\0') {
    strncpy(g_backend_host, host, sizeof(g_backend_host) - 1);
    g_backend_host[sizeof(g_backend_host) - 1] = '\0';
  }
  if (port > 0) {
    g_backend_port = port;
  }
  if (scheme != NULL && scheme[0] != '\0') {
    strncpy(g_backend_scheme, scheme, sizeof(g_backend_scheme) - 1);
    g_backend_scheme[sizeof(g_backend_scheme) - 1] = '\0';
  }
}

// iPhone Personal Hotspot often uses a curly apostrophe (U+2019).
static const char kHotspotSsidCurly[] = "Rian\xe2\x80\x99s iPhone 16";

static bool join_hotspot(const String &scanned)
{
  if (WIFI_SSID_2[0] == '\0' && WIFI_PASSWORD_2[0] == '\0') {
    return false;
  }
  if (scanned.length() && try_join(scanned.c_str(), WIFI_PASSWORD_2, 20000)) {
    return true;
  }
  if (try_join(WIFI_SSID_2, WIFI_PASSWORD_2, 18000)) {
    return true;
  }
  return try_join(kHotspotSsidCurly, WIFI_PASSWORD_2, 18000);
}

static bool join_known_networks(uint32_t timeout_ms)
{
  (void)timeout_ms;
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  wifi_idle();

  int n = WiFi.scanNetworks(false, true, false, 500);
  Serial.printf("WiFi scan found %d networks\n", n);
  for (int i = 0; i < n && i < 12; i++) {
    Serial.printf("  ch%d %s rssi=%d\n", WiFi.channel(i), WiFi.SSID(i).c_str(), WiFi.RSSI(i));
  }

  const String home_exact = scanned_ssid(n, WIFI_SSID);
  String hotspot_exact = scanned_ssid(n, WIFI_SSID_2);
  if (hotspot_exact.isEmpty()) {
    hotspot_exact = scanned_ssid(n, kHotspotSsidCurly);
  }

  // Prefer home when it is actually on the air. Do not wait on a missing
  // home SSID at a venue — go straight to the phone hotspot.
  if (home_exact.length() && try_join(home_exact.c_str(), WIFI_PASSWORD, 18000)) {
    return true;
  }
  if (join_hotspot(hotspot_exact)) {
    return true;
  }

  // Hotspot can take a moment to advertise 2.4 GHz. Rescan once and retry.
  wifi_idle();
  n = WiFi.scanNetworks(false, true, false, 500);
  hotspot_exact = scanned_ssid(n, WIFI_SSID_2);
  if (hotspot_exact.isEmpty()) {
    hotspot_exact = scanned_ssid(n, kHotspotSsidCurly);
  }
  if (join_hotspot(hotspot_exact)) {
    return true;
  }
  return WiFi.status() == WL_CONNECTED;
}

bool wifi_connect_begin(uint32_t timeout_ms)
{
  if (!join_known_networks(timeout_ms)) {
    return false;
  }
  backend_discover(4000);
  return true;
}

bool wifi_reconnect(uint32_t timeout_ms)
{
  if (WiFi.status() == WL_CONNECTED) {
    return true;
  }
  return wifi_connect_begin(timeout_ms);
}

static volatile bool wifi_wake_running = false;

static void wifi_wake_task(void *arg)
{
  (void)arg;
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin();
  const uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && (millis() - start) < 3000) {
    vTaskDelay(pdMS_TO_TICKS(40));
  }
  if (WiFi.status() != WL_CONNECTED) {
    join_known_networks(0);
  }
  if (WiFi.status() == WL_CONNECTED) {
    if (!probe_health(g_backend_host, g_backend_port, g_backend_scheme)) {
      backend_discover(1200);
    }
  }
  wifi_wake_running = false;
  vTaskDelete(NULL);
}

void wifi_wake_start(void)
{
  if (WiFi.status() == WL_CONNECTED || wifi_wake_running) {
    return;
  }
  wifi_wake_running = true;
  if (xTaskCreatePinnedToCore(wifi_wake_task, "wifi_wake", 8 * 1024, NULL, 3, NULL, 0) != pdPASS) {
    wifi_wake_running = false;
  }
}

void wifi_radio_off(void)
{
  WiFi.disconnect(true, false);
  WiFi.mode(WIFI_OFF);
}

bool wifi_is_connected(void)
{
  return WiFi.status() == WL_CONNECTED;
}

// After idle sleep the radio is off and wifi_wake_task reconnects in the
// background, so callers about to send must wait for it instead of failing.
bool wifi_wait_connected(uint32_t timeout_ms)
{
  const uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && (millis() - start) < timeout_ms) {
    wifi_wake_start();
    vTaskDelay(pdMS_TO_TICKS(100));
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
