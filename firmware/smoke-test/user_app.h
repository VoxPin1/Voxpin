#ifndef USER_APP_H
#define USER_APP_H

#include "src/display/epaper_driver_bsp.h"

extern epaper_driver_display *driver;

void user_app_sync_time_from_ntp(void);
void user_app_init(void);
void user_ui_init(void);

#endif
