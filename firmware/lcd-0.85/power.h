#pragma once

void power_init(void);
float power_battery_voltage(void);
int power_battery_percent(void);
bool power_is_charging(void);
void power_hold_on(void);
void power_off(void);
