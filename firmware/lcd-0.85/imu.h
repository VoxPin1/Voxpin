#pragma once

#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

void imu_begin(void);
bool imu_present(void);
bool imu_moved(void);

#ifdef __cplusplus
}
#endif
