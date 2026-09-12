#pragma once

#include "driver/gpio.h"

#define LCD_WIDTH  128
#define LCD_HEIGHT 128

#define LCD_DC_PIN   45
#define LCD_CS_PIN   21
#define LCD_SCK_PIN  38
#define LCD_MOSI_PIN 39
#define LCD_RST_PIN  40
#define LCD_BL_PIN   46

#define BAT_EN_PIN      GPIO_NUM_2
#define BAT_ADC_PIN     GPIO_NUM_1
#define CHG_STAT_PIN    GPIO_NUM_3

#define BOOT_BUTTON_PIN GPIO_NUM_0
#define PWR_BUTTON_PIN  GPIO_NUM_5
#define PLUS_BUTTON_PIN GPIO_NUM_4

#define I2C_SDA_PIN 42
#define I2C_SCL_PIN 41

#define PA_CTRL_PIN  7
#define I2S_MCLK_PIN 8
#define I2S_BCLK_PIN 9
#define I2S_LRCK_PIN 10
#define I2S_DIN_PIN  11
#define I2S_DOUT_PIN 12
