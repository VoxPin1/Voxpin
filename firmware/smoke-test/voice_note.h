#pragma once

typedef void (*voice_status_cb_t)(const char *text);

void voice_note_init(void);
void voice_note_start(voice_status_cb_t status_cb);
