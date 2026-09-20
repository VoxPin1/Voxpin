#pragma once

#include <stdbool.h>

typedef void (*voice_status_cb_t)(const char *text);

void voice_note_init(void);
void voice_note_start(voice_status_cb_t status_cb);
bool voice_note_is_busy(void);
