#include "wifi_setup.h"

#include <Arduino.h>
#include <DNSServer.h>
#include <WebServer.h>
#include <WiFi.h>

#include "board_pins.h"
#include "driver/gpio.h"
#include "idle.h"
#include "power.h"
#include "wifi_connect.h"

static const char *kSetupSsid = "VoxPin-Setup";
static const uint32_t kNoClientTimeoutMs = 120000;
static const uint32_t kJoinTimeoutMs = 20000;
static const uint32_t kPwrHoldOffMs = 2000;

static WebServer *server = nullptr;
static DNSServer dns;
static String options_html;
static String message;
static String pending_ssid;
static String pending_password;
static bool pending = false;
static volatile bool setup_busy = false;
static volatile bool setup_wanted = false;

static void input_pullup(gpio_num_t pin)
{
  gpio_config_t io = {};
  io.intr_type = GPIO_INTR_DISABLE;
  io.mode = GPIO_MODE_INPUT;
  io.pin_bit_mask = 1ULL << pin;
  io.pull_up_en = GPIO_PULLUP_ENABLE;
  io.pull_down_en = GPIO_PULLDOWN_DISABLE;
  gpio_config(&io);
}

bool wifi_setup_requested(void)
{
  input_pullup(PLUS_BUTTON_PIN);
  delay(20);
  if (gpio_get_level(PLUS_BUTTON_PIN) != 0) {
    return false;
  }
  const uint32_t start = millis();
  while (gpio_get_level(PLUS_BUTTON_PIN) == 0 && (millis() - start) < 10000) {
    delay(20);
  }
  return true;
}

static String html_escape(const String &in)
{
  String out;
  out.reserve(in.length() + 8);
  for (unsigned i = 0; i < in.length(); i++) {
    const char c = in[i];
    if (c == '&') {
      out += "&amp;";
    } else if (c == '<') {
      out += "&lt;";
    } else if (c == '>') {
      out += "&gt;";
    } else if (c == '"') {
      out += "&quot;";
    } else if (c == '\'') {
      out += "&#39;";
    } else {
      out += c;
    }
  }
  return out;
}

static void scan_networks(void)
{
  options_html = "";
  const int n = WiFi.scanNetworks(false, false);
  for (int i = 0; i < n; i++) {
    const String ssid = WiFi.SSID(i);
    if (ssid.length() == 0) {
      continue;
    }
    bool seen = false;
    for (int j = 0; j < i && !seen; j++) {
      seen = WiFi.SSID(j) == ssid;
    }
    if (!seen) {
      options_html += "<option>" + html_escape(ssid) + "</option>";
    }
  }
  WiFi.scanDelete();
  Serial.printf("Setup: %d networks in scan\n", n);
}

static const char kHead[] =
  "<!doctype html><html><head><meta charset=utf-8>"
  "<meta name=viewport content='width=device-width,initial-scale=1'>"
  "<title>VoxPin Wi-Fi</title><style>"
  "body{font-family:-apple-system,Helvetica,sans-serif;max-width:420px;margin:24px auto;padding:0 16px}"
  "label{font-weight:600}"
  "select,input,button{width:100%;font-size:17px;padding:10px;margin:6px 0 16px;box-sizing:border-box}"
  "button{background:#0a7d4f;color:#fff;border:0;border-radius:8px}"
  ".msg{color:#b00020}.note{color:#555;font-size:14px}"
  "</style></head><body><h2>VoxPin Wi-Fi</h2>";

static void send_page(void)
{
  String page = kHead;
  if (message.length() > 0) {
    page += "<p class=msg>" + html_escape(message) + "</p>";
  }
  page += "<form method=post action=/save><label>Network</label><select name=s>";
  page += options_html;
  page += "<option value=''>Other (type it below)</option></select>"
          "<label>Or type the network name</label>"
          "<input name=h autocapitalize=off autocorrect=off spellcheck=false>"
          "<label>Password</label><input name=p type=password>"
          "<button>Connect</button></form>"
          "<p class=note>The pin only works on 2.4 GHz Wi-Fi without a sign-in page. "
          "The Mac running the VoxPin helper must be on the same network.</p>"
          "</body></html>";
  server->send(200, "text/html", page);
}

static void redirect_home(void)
{
  server->sendHeader("Location", "http://" + WiFi.softAPIP().toString() + "/", true);
  server->send(302, "text/plain", "");
}

static void handle_save(void)
{
  String ssid = server->arg("h");
  ssid.trim();
  if (ssid.length() == 0) {
    ssid = server->arg("s");
  }
  if (ssid.length() == 0) {
    message = "Pick a network or type its name.";
    redirect_home();
    return;
  }
  pending_ssid = ssid;
  pending_password = server->arg("p");
  pending = true;
  String page = kHead;
  page += "<p>Connecting to <b>" + html_escape(ssid) + "</b>&hellip;</p>"
          "<p>Watch the pin's screen. <b>WiFi saved</b> means you're done and this "
          "hotspot will close. <b>Wrong pass?</b> means rejoin VoxPin-Setup and try again.</p>"
          "</body></html>";
  server->send(200, "text/html", page);
}

static bool pwr_held(void)
{
  if (gpio_get_level(PWR_BUTTON_PIN) != 0) {
    return false;
  }
  const uint32_t start = millis();
  while (gpio_get_level(PWR_BUTTON_PIN) == 0) {
    if (millis() - start >= kPwrHoldOffMs) {
      return true;
    }
    delay(20);
  }
  return false;
}

static void serve(void)
{
  dns.processNextRequest();
  server->handleClient();
}

bool wifi_setup_run(void (*status)(const char *text))
{
  setup_busy = true;
  input_pullup(PWR_BUTTON_PIN);
  WiFi.disconnect(true, false);
  delay(200);
  WiFi.mode(WIFI_AP_STA);
  WiFi.config(INADDR_NONE, INADDR_NONE, INADDR_NONE);
  WiFi.softAP(kSetupSsid);
  delay(200);
  scan_networks();

  const IPAddress ip = WiFi.softAPIP();
  dns.start(53, "*", ip);
  server = new WebServer(80);
  server->on("/", HTTP_GET, send_page);
  server->on("/save", HTTP_POST, handle_save);
  server->onNotFound(redirect_home);
  server->begin();
  message = "";
  pending = false;
  Serial.printf("Setup hotspot '%s' at %s\n", kSetupSsid, ip.toString().c_str());
  status("Join VoxPin-Setup");

  bool joined = false;
  uint32_t last_client = millis();
  for (;;) {
    serve();
    idle_touch();
    if (WiFi.softAPgetStationNum() > 0) {
      last_client = millis();
    }
    if (pwr_held()) {
      status("Power off");
      delay(400);
      power_off();
    }
    if (pending) {
      pending = false;
      // Let the reply reach the phone before the radio retunes to the new network.
      const uint32_t flush_until = millis() + 1500;
      while (millis() < flush_until) {
        serve();
        delay(10);
      }
      status("Joining");
      Serial.printf("Setup: trying '%s'\n", pending_ssid.c_str());
      if (pending_password.length() > 0) {
        WiFi.begin(pending_ssid.c_str(), pending_password.c_str());
      } else {
        WiFi.begin(pending_ssid.c_str());
      }
      const uint32_t start = millis();
      while (WiFi.status() != WL_CONNECTED && (millis() - start) < kJoinTimeoutMs) {
        serve();
        delay(50);
      }
      if (WiFi.status() == WL_CONNECTED) {
        wifi_save_network(pending_ssid, pending_password);
        Serial.printf("Setup: joined '%s' as %s; saved\n", pending_ssid.c_str(),
                      WiFi.localIP().toString().c_str());
        status("WiFi saved");
        joined = true;
        break;
      }
      Serial.printf("Setup: '%s' failed (status=%d)\n", pending_ssid.c_str(),
                    (int)WiFi.status());
      WiFi.disconnect(false, false);
      message = "Couldn't join \"" + pending_ssid +
                "\". Check the password, and that it's a 2.4 GHz network.";
      status("Wrong pass?");
      last_client = millis();
    }
    if (millis() - last_client > kNoClientTimeoutMs) {
      Serial.println("Setup: no phone joined; retrying known networks");
      break;
    }
    delay(5);
  }

  server->stop();
  delete server;
  server = nullptr;
  dns.stop();
  WiFi.softAPdisconnect(true);
  WiFi.mode(WIFI_STA);
  setup_busy = false;
  return joined;
}

void wifi_setup_request(void)
{
  setup_wanted = true;
}

bool wifi_setup_active(void)
{
  return setup_wanted || setup_busy;
}

void wifi_setup_poll(void (*status)(const char *text))
{
  if (!setup_wanted) {
    return;
  }
  Serial.println("+ held: Wi-Fi setup");
  idle_wake_sync();
  wifi_setup_run(status);
  status("Connecting");
  while (!wifi_connect_begin(45000)) {
    wifi_setup_run(status);
    status("Connecting");
  }
  status("");
  setup_wanted = false;
}
