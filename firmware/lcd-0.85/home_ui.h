#pragma once

#include <stdbool.h>
#include <stdint.h>

void home_ui_begin(void);
void home_ui_sync_time_from_ntp(void);
void home_ui_set_status(const char *text);
void home_ui_set_paused(bool paused);
void home_ui_set_backlight(uint8_t duty);
