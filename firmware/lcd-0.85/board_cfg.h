#ifndef BOARD_CFG_H
#define BOARD_CFG_H

const char board_cfg_data[] = {
  "Board: S3_LCD_0_85\n"
  "i2c: {sda: 42, scl: 41}\n"
  "i2s: {mclk: 8, bclk: 9, ws: 10, dout: 12, din: 11}\n"
  "out: {codec: ES8311, pa: 7, use_mclk: 1, pa_gain:6}\n"
  "in: {codec: ES7210}\n"
};
const char *board_cfg_start = board_cfg_data;
const char *board_cfg_end = board_cfg_data + sizeof(board_cfg_data) - 1;

#endif
