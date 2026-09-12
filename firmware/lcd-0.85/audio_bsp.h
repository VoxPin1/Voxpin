#ifndef AUDIO_BSP_H
#define AUDIO_BSP_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

void audio_bsp_init(void);
void audio_play_init(void);
void audio_playback_read(void *data_ptr, uint32_t len);
void audio_playback_write(void *data_ptr, uint32_t len);
void audio_set_playing(bool playing);
bool audio_is_playing(void);

#ifdef __cplusplus
}
#endif

#endif
