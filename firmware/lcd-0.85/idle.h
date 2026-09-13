#pragma once

#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

void idle_touch(void);
void idle_start(void);
bool idle_is_sleeping(void);
void idle_wake_sync(void);

#ifdef __cplusplus
}
#endif
