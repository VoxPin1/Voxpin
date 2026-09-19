#pragma once

#include <Arduino.h>

bool wifi_connect_begin(uint32_t timeout_ms = 30000);
bool wifi_reconnect(uint32_t timeout_ms = 25000);
void wifi_wake_start(void);
void wifi_radio_off(void);
String wifi_connect_ip();
bool wifi_is_connected(void);
