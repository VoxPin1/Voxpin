#pragma once

#include <Arduino.h>

bool wifi_connect_begin(uint32_t timeout_ms = 30000);
String wifi_connect_ip();
