#pragma once

#include <Arduino.h>

// Connect to configured WiFi. Returns true if connected within timeout_ms.
bool wifi_connect_begin(uint32_t timeout_ms = 30000);

// Empty string if not connected.
String wifi_connect_ip();
