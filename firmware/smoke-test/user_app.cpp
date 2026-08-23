#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "user_app.h"
#include "driver/gpio.h"
#include "user_config.h"
#include "esp_log.h"
#include "esp_err.h"

#include "driver/rtc_io.h"
#include "esp_sleep.h"
#include "esp_system.h"
  
#include "src/ui_src/generated/gui_guider.h"
#include "src/power/board_power_bsp.h"

epaper_driver_display *driver = NULL;
board_power_bsp_t board_div(EPD_PWR_PIN,Audio_PWR_PIN,VBAT_PWR_PIN);

lv_ui src_ui;


void user_app_init(void)
{
  board_div.POWEER_EPD_ON();
  board_div.POWEER_Audio_ON();
  /*epaper init*/
  custom_lcd_spi_t driver_config = {};
    driver_config.cs = EPD_CS_PIN;
    driver_config.dc = EPD_DC_PIN;
    driver_config.rst = EPD_RST_PIN;
    driver_config.busy = EPD_BUSY_PIN;
    driver_config.mosi = EPD_MOSI_PIN;
    driver_config.scl = EPD_SCK_PIN;
    driver_config.spi_host = EPD_SPI_NUM;
    driver_config.buffer_len  = 5000;
  driver = new epaper_driver_display(EPD_WIDTH,EPD_HEIGHT,driver_config);
  driver->EPD_Init();
  driver->EPD_Clear();
  driver->EPD_DisplayPartBaseImage();
  driver->EPD_Init_Partial();            //局部刷新初始化
}

void led_test_task(void *arg)
{
  gpio_config_t gpio_conf = {};
  gpio_conf.intr_type = GPIO_INTR_DISABLE;
  gpio_conf.mode = GPIO_MODE_OUTPUT;
  gpio_conf.pin_bit_mask = 0x1ULL<<3;
  gpio_conf.pull_down_en = GPIO_PULLDOWN_DISABLE;
  gpio_conf.pull_up_en = GPIO_PULLUP_ENABLE;

  ESP_ERROR_CHECK_WITHOUT_ABORT(gpio_config(&gpio_conf));
  for(;;)
  {
    gpio_set_level((gpio_num_t)3,0);
    vTaskDelay(pdMS_TO_TICKS(200));
    gpio_set_level((gpio_num_t)3,1);
    vTaskDelay(pdMS_TO_TICKS(200));
  }
}

void hello_voxpin_task(void *arg)
{
  lv_ui *ui = (lv_ui *)arg;
  lv_obj_add_flag(ui->screen_img_1, LV_OBJ_FLAG_HIDDEN);
  lv_obj_add_flag(ui->screen_img_2, LV_OBJ_FLAG_HIDDEN);

  lv_obj_t *label = lv_label_create(ui->screen);
  lv_obj_set_style_text_align(label, LV_TEXT_ALIGN_CENTER, 0);
  lv_obj_center(label);

  uint32_t counter = 0;
  for (;;)
  {
    char text[48];
    snprintf(text, sizeof(text), "HELLO VOXPIN\nboot: %lu", (unsigned long)counter);
    lv_label_set_text(label, text);
    lv_obj_invalidate(label);
    counter++;
    /* Full refresh every 10s — avoid rapid updates (ghosting / wear). */
    vTaskDelay(pdMS_TO_TICKS(10000));
  }
}

void user_ui_init(void)
{
  setup_ui(&src_ui);
  xTaskCreatePinnedToCore(led_test_task, "led_test_task", 4 * 1024, NULL, 4, NULL, 1);
  xTaskCreatePinnedToCore(hello_voxpin_task, "hello_voxpin_task", 4 * 1024, &src_ui, 4, NULL, 1);
}
