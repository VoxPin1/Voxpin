#include "wifi_connect.h"

#include "backend_http.h"
#include "wifi_secrets.h"

#include <Preferences.h>

#include <ESPmDNS.h>

#include <HTTPClient.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <WiFiClientSecure.h>
#include <WiFiUdp.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "idle.h"

char g_backend_host[64] = BACKEND_HOST;
int g_backend_port = BACKEND_PORT;
char g_backend_scheme[8] = BACKEND_SCHEME;

#ifndef WIFI_SSID_2
#define WIFI_SSID_2 ""
#define WIFI_PASSWORD_2 ""
#endif

static const uint16_t kBeaconPort = 8766;

// The iPhone hotspot is joined with a fixed address so the pin does not wait on
// its DHCP. Every other network uses DHCP.
static const IPAddress kHotspotIp(172, 20, 10, 2);
static const IPAddress kHotspotGateway(172, 20, 10, 1);
static const IPAddress kHotspotSubnet(255, 255, 255, 240);
static const IPAddress kHotspotDns(172, 20, 10, 1);
static const uint32_t kHotspotJoinMs = 20000;
static const int kHotspotAttempts = 3;

static void use_hotspot_address(void)
{
  if (!WiFi.config(kHotspotIp, kHotspotGateway, kHotspotSubnet, kHotspotDns)) {
    Serial.println("WiFi fixed hotspot address failed");
  }
}

static void use_dhcp(void)
{
  WiFi.config(INADDR_NONE, INADDR_NONE, INADDR_NONE);
}

// Power save makes the iPhone drop the pin and stops it answering ping.
static void on_hotspot_up(void)
{
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);
}

static void on_wifi_disconnected(arduino_event_id_t event, arduino_event_info_t info)
{
  (void)event;
  const wifi_event_sta_disconnected_t &d = info.wifi_sta_disconnected;
  char ssid[33] = "";
  const size_t len = d.ssid_len < 32 ? d.ssid_len : 32;
  memcpy(ssid, d.ssid, len);
  ssid[len] = '\0';
  Serial.printf("WiFi disconnected from '%s': reason %u (%s) rssi=%d\n", ssid,
                (unsigned)d.reason, WiFi.disconnectReasonName((wifi_err_reason_t)d.reason),
                (int)d.rssi);
}

static void watch_disconnects(void)
{
  static bool registered = false;
  if (!registered) {
    WiFi.onEvent(on_wifi_disconnected, ARDUINO_EVENT_WIFI_STA_DISCONNECTED);
    registered = true;
  }
}

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

static void wifi_idle(void)
{
  WiFi.disconnect(true, false);
  const uint32_t start = millis();
  while (WiFi.status() == WL_CONNECTED && (millis() - start) < 1500) {
    delay(50);
  }
  delay(250);
}

static bool probe_health(const char *host, int port, const char *scheme = "http",
                         uint32_t timeout_ms = 0);
static bool discover_helper_v6(void);

static bool try_join(const char *ssid, const char *password, uint32_t timeout_ms)
{
  if (ssid == NULL || ssid[0] == '\0') {
    return false;
  }

  wifi_idle();
  use_dhcp();
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

static bool probe_health(const char *host, int port, const char *scheme,
                         uint32_t timeout_ms)
{
  if (host == NULL || host[0] == '\0' || port <= 0 || scheme == NULL || scheme[0] == '\0') {
    return false;
  }
  char url[192];
  const bool v6 = strchr(host, ':') != NULL;
  const bool default_port = (port == 443 && strcmp(scheme, "https") == 0) ||
                             (port == 80 && strcmp(scheme, "http") == 0);
  if (v6 && default_port) {
    snprintf(url, sizeof(url), "%s://[%s]/health", scheme, host);
  } else if (v6) {
    snprintf(url, sizeof(url), "%s://[%s]:%d/health", scheme, host, port);
  } else if (default_port) {
    snprintf(url, sizeof(url), "%s://%s/health", scheme, host);
  } else {
    snprintf(url, sizeof(url), "%s://%s:%d/health", scheme, host, port);
  }

  HTTPClient http;
  const bool tls_mode = strcmp(scheme, "https") == 0;
  http.setTimeout(timeout_ms ? timeout_ms : (tls_mode ? 6000 : 1500));
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
  return false;
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

// Boot always installs 172.20.10.5. A helper learned earlier (including the old
// 192.0.0.2 default) must not survive in NVS or in RAM.
static void overwrite_saved_helper(void)
{
  Preferences prefs;
  if (prefs.begin("voxpin", false)) {
    const String saved = prefs.getString("helper", "");
    if (saved.length() == 0 || saved == "192.0.0.2" || saved != BACKEND_HOST) {
      prefs.putString("helper", BACKEND_HOST);
    }
    prefs.end();
  }
  backend_set_target(BACKEND_HOST, BACKEND_PORT, BACKEND_SCHEME);
}

// A helper address learned on another network is useless on the phone hotspot.
// Drop it unless it is this Mac's saved address or it sits on the current subnet.
static void forget_stale_helper(void)
{
  if (g_backend_host[0] == '\0' || strcmp(g_backend_host, BACKEND_HOST) == 0) {
    return;
  }
  IPAddress saved;
  if (!saved.fromString(g_backend_host)) {
    return;
  }
  const IPAddress mine = WiFi.localIP();
  const IPAddress mask = WiFi.subnetMask();
  if ((uint32_t)mine == 0 || (uint32_t)mask == 0) {
    return;
  }
  if ((uint32_t)(saved & mask) == (uint32_t)(mine & mask)) {
    return;
  }
  Serial.printf("Drop stale helper %s\n", g_backend_host);
  backend_set_target(BACKEND_HOST, BACKEND_PORT, BACKEND_SCHEME);
}

bool backend_discover(uint32_t timeout_ms)
{
  char found_host[64] = "";
  int found_port = 8765;

  forget_stale_helper();

  // TCP often fails for the first second after the pin joins venue Wi-Fi.
  // Retry this Mac before walking a list of home and hotspot addresses.
  const char *primary = (g_backend_host[0] != '\0') ? g_backend_host : BACKEND_HOST;
  const int primary_port = g_backend_port > 0 ? g_backend_port : BACKEND_PORT;
  const char *primary_scheme = (g_backend_scheme[0] != '\0') ? g_backend_scheme : BACKEND_SCHEME;
  for (int attempt = 0; attempt < 3; attempt++) {
    if (probe_health(primary, primary_port, primary_scheme, 1500)) {
      backend_set_target(primary, primary_port, primary_scheme);
      return true;
    }
    delay(300);
  }

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
    "172.20.10.5",
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
  if (discover_helper_v6()) {
    return true;
  }

  Serial.println("Helper not found yet");
  return false;
}

// iPhone hotspot gives this Mac 192.0.0.2/32 and does not answer ARP, so the
// pin cannot open IPv4 to it. IPv6 on the same hotspot still reaches the Mac.
static bool discover_helper_v6(void)
{
#if CONFIG_LWIP_IPV6
  WiFi.enableIPv6(true);
  for (int i = 0; i < 10; i++) {
    String mine = WiFi.globalIPv6().toString();
    if (mine.indexOf(':') >= 0 && mine != "::" && mine != "0:0:0:0:0:0:0:0") {
      Serial.printf("pin v6 %s\n", mine.c_str());
      break;
    }
    delay(400);
  }
  if (!MDNS.begin("voxpin-pin")) {
    Serial.println("mDNS begin failed");
    return false;
  }
  const int found = MDNS.queryService("voxpin", "tcp");
  Serial.printf("mDNS voxpin %d\n", found);
  for (int i = 0; i < found; i++) {
    String host = MDNS.addressV6(i).toString();
    if (host.indexOf(':') < 0 || host == "::") {
      continue;
    }
    int port = MDNS.port(i);
    if (port <= 0) {
      port = 8765;
    }
    if (probe_health(host.c_str(), port, "http", 2500)) {
      backend_set_target(host.c_str(), port, "http");
      Serial.printf("Helper via mDNS %s:%d\n", host.c_str(), port);
      return true;
    }
  }
#else
  Serial.println("no ipv6 in this build");
#endif
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

// Joined by name even when the scan misses it: an iPhone hotspot often stops
// advertising until a client probes for it.
static bool join_hotspot(void)
{
  if (WIFI_SSID_2[0] == '\0' || WIFI_PASSWORD_2[0] == '\0') {
    return false;
  }
  for (int attempt = 1; attempt <= kHotspotAttempts; attempt++) {
    wifi_idle();
    use_hotspot_address();
    Serial.printf("WiFi joining '%s' at %s (attempt %d/%d)\n", WIFI_SSID_2,
                  kHotspotIp.toString().c_str(), attempt, kHotspotAttempts);
    WiFi.begin(WIFI_SSID_2, WIFI_PASSWORD_2);
    const uint32_t start = millis();
    while (WiFi.status() != WL_CONNECTED && (millis() - start) < kHotspotJoinMs) {
      delay(250);
    }
    if (WiFi.status() == WL_CONNECTED) {
      on_hotspot_up();
      Serial.printf("WiFi IP %s\n", WiFi.localIP().toString().c_str());
      return true;
    }
    Serial.printf("WiFi status=%d after %us\n", (int)WiFi.status(),
                  (unsigned)(kHotspotJoinMs / 1000));
  }
  use_dhcp();
  return false;
}

// With a hotspot configured the pin joins nothing else; wifi_maintain() keeps
// retrying it. Home Wi-Fi is used only when no hotspot is set.
static bool join_known_networks(uint32_t timeout_ms)
{
  (void)timeout_ms;
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);  // power save drops uploads on busy venue Wi-Fi
#if CONFIG_LWIP_IPV6
  WiFi.enableIPv6(true);
#endif
  watch_disconnects();
  wifi_idle();

  if (WIFI_SSID_2[0] != '\0') {
    return join_hotspot();
  }
  return try_join(WIFI_SSID, WIFI_PASSWORD, 18000);
}

static void begin_configured_network(void)
{
  if (WIFI_SSID_2[0] != '\0') {
    use_hotspot_address();
    WiFi.begin(WIFI_SSID_2, WIFI_PASSWORD_2);
  } else {
    use_dhcp();
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  }
}

static void print_link(void)
{
  char helper[96];
  backend_make_url(helper, sizeof(helper), "");
  Serial.printf("WiFi SSID: %s\n", WiFi.SSID().c_str());
  Serial.printf("WiFi IP: %s\n", WiFi.localIP().toString().c_str());
  Serial.printf("Helper: %s\n", helper);
  Serial.flush();
}

bool wifi_connect_begin(uint32_t timeout_ms)
{
  overwrite_saved_helper();
  if (!join_known_networks(timeout_ms)) {
    return false;
  }
  overwrite_saved_helper();
  backend_discover(4000);
  if (strcmp(g_backend_host, "192.0.0.2") == 0) {
    backend_set_target(BACKEND_HOST, BACKEND_PORT, BACKEND_SCHEME);
  }
  print_link();
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
  watch_disconnects();
  // Rejoin the phone hotspot by name. A bare begin() has no saved network
  // after WIFI_OFF, which forced a slow full scan on every wake.
  begin_configured_network();
  const uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && (millis() - start) < 8000) {
    vTaskDelay(pdMS_TO_TICKS(40));
  }
  if (WiFi.status() != WL_CONNECTED && !idle_is_sleeping()) {
    join_known_networks(0);
  }
  if (WiFi.status() == WL_CONNECTED) {
    forget_stale_helper();
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

// Synchronous rejoin for the sleeping reminder check. Try the phone hotspot
// directly (no scan), then fall back to the full scan.
bool wifi_quick_join(uint32_t timeout_ms)
{
  const uint32_t wait_start = millis();
  while (wifi_wake_running && (millis() - wait_start) < 30000) {
    vTaskDelay(pdMS_TO_TICKS(100));
  }
  if (WiFi.status() == WL_CONNECTED) {
    return true;
  }
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  watch_disconnects();
  begin_configured_network();
  const uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && (millis() - start) < timeout_ms) {
    vTaskDelay(pdMS_TO_TICKS(100));
  }
  if (WiFi.status() != WL_CONNECTED && !wifi_connect_begin(25000)) {
    Serial.println("Sleep check: WiFi join failed");
    return false;
  }
  forget_stale_helper();
  if (!probe_health(g_backend_host, g_backend_port, g_backend_scheme)) {
    backend_discover(1200);
  }
  return WiFi.status() == WL_CONNECTED;
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

void wifi_set_fast(bool fast)
{
  (void)fast;
  WiFi.setSleep(false);
}

static const uint32_t kKeepaliveMs = 10000;
// Auto-reconnect gets this long before a manual rejoin, so the two don't collide.
static const uint32_t kReconnectGraceMs = 8000;
static const uint32_t kReconnectEveryMs = 20000;

static void send_keepalive(void)
{
  char url[160];
  backend_make_url(url, sizeof(url), "/health");
  HTTPClient http;
  WiFiClientSecure tls;
  WiFiClient plain;
  http.setConnectTimeout(2000);
  http.setTimeout(2000);
  if (!backend_http_begin(http, tls, plain, "/health")) {
    Serial.printf("keepalive %s -> begin failed\n", url);
    return;
  }
  const int code = http.GET();
  http.end();
  if (code > 0) {
    Serial.printf("keepalive %s -> HTTP %d\n", url, code);
  } else {
    Serial.printf("keepalive %s -> error %d (%s)\n", url, code,
                  HTTPClient::errorToString(code).c_str());
  }
}

void wifi_maintain(void)
{
  static bool was_connected = false;
  static uint32_t down_since = 0;
  static uint32_t last_attempt = 0;
  static uint32_t last_keepalive = 0;

  if (wifi_wake_running) {
    return;
  }
  const uint32_t now = millis();
  if (WiFi.status() == WL_CONNECTED) {
    if (!was_connected) {
      was_connected = true;
      if (ssid_match(WiFi.SSID(), WIFI_SSID_2)) {
        on_hotspot_up();
      }
      print_link();
      // Boot only syncs the clock if Wi-Fi was up during setup().
      struct tm timeinfo {};
      if (!getLocalTime(&timeinfo, 0)) {
        Serial.println("Clock not set; starting NTP");
        configTzTime("PST8PDT", "pool.ntp.org");
      }
    }
    if (now - last_keepalive >= kKeepaliveMs) {
      last_keepalive = now;
      send_keepalive();
    }
    return;
  }

  if (was_connected || down_since == 0) {
    was_connected = false;
    down_since = now;
  }
  if (WIFI_SSID_2[0] == '\0' || now - down_since < kReconnectGraceMs ||
      (last_attempt != 0 && now - last_attempt < kReconnectEveryMs)) {
    return;
  }
  last_attempt = now;
  Serial.printf("WiFi reconnecting to '%s' at %s\n", WIFI_SSID_2,
                kHotspotIp.toString().c_str());
  WiFi.disconnect(false, false);
  use_hotspot_address();
  WiFi.begin(WIFI_SSID_2, WIFI_PASSWORD_2);
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
