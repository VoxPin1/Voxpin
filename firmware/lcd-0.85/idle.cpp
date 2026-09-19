#include "idle.h"

#include <Arduino.h>

#include "audio_bsp.h"
#include "ble_companion.h"
#include "board_pins.h"
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "home_ui.h"
#include "imu.h"
#include "power.h"
#include "wifi_connect.h"

static constexpr uint32_t kIdleMs = 5 * 60 * 1000;
static constexpr uint32_t kPwrHoldOffMs = 2000;

static volatile uint32_t last_activity_ms = 0;
static volatile bool sleeping = false;
static SemaphoreHandle_t idle_mux = NULL;

static bool pwr_pressed(void)
{
  return gpio_get_level(PWR_BUTTON_PIN) == 0;
}

static bool boot_pressed(void)
{
  return gpio_get_level(BOOT_BUTTON_PIN) == 0;
}

static bool plus_pressed(void)
{
  return gpio_get_level(PLUS_BUTTON_PIN) == 0;
}

void idle_touch(void)
{
  last_activity_ms = millis();
}

bool idle_is_sleeping(void)
{
  return sleeping;
}

static void enter_sleep(void)
{
  if (sleeping) {
    return;
  }
  sleeping = true;
  home_ui_set_status("");
  home_ui_set_paused(true);
  home_ui_set_backlight(56);
  wifi_radio_off();
  ble_companion_sleep();
  audio_pa_enable(false);
  Serial.println("Idle: home stays on, radios off");
}

static void leave_sleep(void)
{
  if (!sleeping) {
    return;
  }
  sleeping = false;
  idle_touch();
  home_ui_set_backlight(255);
  home_ui_set_paused(false);
  audio_pa_enable(true);
  ble_companion_wake();
  home_ui_set_status_for("Waking", 700);
  wifi_wake_start();
}

void idle_wake_sync(void)
{
  if (idle_mux == NULL) {
    return;
  }
  if (xSemaphoreTake(idle_mux, pdMS_TO_TICKS(1500)) != pdTRUE) {
    return;
  }
  leave_sleep();
  xSemaphoreGive(idle_mux);
}

static void idle_task(void *arg)
{
  (void)arg;
  gpio_config_t io = {};
  io.intr_type = GPIO_INTR_DISABLE;
  io.mode = GPIO_MODE_INPUT;
  io.pin_bit_mask = 1ULL << PWR_BUTTON_PIN;
  io.pull_up_en = GPIO_PULLUP_ENABLE;
  io.pull_down_en = GPIO_PULLDOWN_DISABLE;
  gpio_config(&io);

  idle_touch();

  for (;;) {
    if (imu_moved()) {
      idle_touch();
      if (sleeping) {
        if (xSemaphoreTake(idle_mux, pdMS_TO_TICKS(50)) == pdTRUE) {
          leave_sleep();
          xSemaphoreGive(idle_mux);
        }
      }
    }

    if (pwr_pressed()) {
      const uint32_t started = millis();
      while (pwr_pressed() && (millis() - started) < kPwrHoldOffMs) {
        vTaskDelay(pdMS_TO_TICKS(20));
      }
      const bool held = pwr_pressed() && (millis() - started) >= kPwrHoldOffMs;
      while (pwr_pressed()) {
        vTaskDelay(pdMS_TO_TICKS(20));
      }
      if (held) {
        home_ui_set_status("Power off");
        vTaskDelay(pdMS_TO_TICKS(400));
        power_off();
      } else if (xSemaphoreTake(idle_mux, pdMS_TO_TICKS(50)) == pdTRUE) {
        idle_touch();
        if (sleeping) {
          leave_sleep();
        } else {
          enter_sleep();
        }
        xSemaphoreGive(idle_mux);
      }
    }

    if (!sleeping) {
      if (boot_pressed() || plus_pressed()) {
        idle_touch();
      }
      if ((millis() - last_activity_ms) >= kIdleMs) {
        if (xSemaphoreTake(idle_mux, pdMS_TO_TICKS(50)) == pdTRUE) {
          enter_sleep();
          xSemaphoreGive(idle_mux);
        }
      } else if (!wifi_is_connected()) {
        static uint32_t last_retry_ms = 0;
        if (millis() - last_retry_ms > 2000) {
          last_retry_ms = millis();
          wifi_wake_start();
        }
      }
    }

    vTaskDelay(pdMS_TO_TICKS(40));
  }
}

void idle_start(void)
{
  idle_mux = xSemaphoreCreateMutex();
  imu_begin();
  xTaskCreatePinnedToCore(idle_task, "idle", 8 * 1024, NULL, 4, NULL, 1);
}
