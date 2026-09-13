#include "imu.h"

#include <math.h>
#include <stdint.h>
#include <string.h>

#include "driver/i2c_master.h"
#include "esp_log.h"
#include "src/codec_board/codec_init.h"

static const char *TAG = "imu";
static i2c_master_dev_handle_t imu_dev = NULL;
static bool present = false;
static float last_mag = -1.0f;

static bool imu_read(uint8_t reg, uint8_t *data, size_t len)
{
  if (imu_dev == NULL) {
    return false;
  }
  return i2c_master_transmit_receive(imu_dev, &reg, 1, data, len, 50) == ESP_OK;
}

static bool imu_write(uint8_t reg, uint8_t value)
{
  if (imu_dev == NULL) {
    return false;
  }
  uint8_t buf[2] = {reg, value};
  return i2c_master_transmit(imu_dev, buf, 2, 50) == ESP_OK;
}

static bool attach_qmi(i2c_master_bus_handle_t bus, uint8_t addr)
{
  if (i2c_master_probe(bus, addr, 80) != ESP_OK) {
    return false;
  }
  i2c_device_config_t cfg = {};
  cfg.dev_addr_length = I2C_ADDR_BIT_LEN_7;
  cfg.device_address = addr;
  cfg.scl_speed_hz = 100000;
  if (i2c_master_bus_add_device(bus, &cfg, &imu_dev) != ESP_OK) {
    imu_dev = NULL;
    return false;
  }
  uint8_t who = 0;
  if (!imu_read(0x00, &who, 1) || who != 0x05) {
    i2c_master_bus_rm_device(imu_dev);
    imu_dev = NULL;
    return false;
  }
  imu_write(0x02, 0x60);
  imu_write(0x08, 0x01);
  ESP_LOGI(TAG, "QMI8658 at 0x%02x", addr);
  return true;
}

void imu_begin(void)
{
  present = false;
  last_mag = -1.0f;
  i2c_master_bus_handle_t bus = (i2c_master_bus_handle_t)get_i2c_bus_handle(0);
  if (bus == NULL) {
    ESP_LOGW(TAG, "no I2C bus");
    return;
  }
  if (attach_qmi(bus, 0x6A) || attach_qmi(bus, 0x6B)) {
    present = true;
    return;
  }
  ESP_LOGI(TAG, "no IMU, idle uses buttons");
}

bool imu_present(void)
{
  return present;
}

bool imu_moved(void)
{
  if (!present) {
    return false;
  }
  uint8_t raw[6];
  if (!imu_read(0x35, raw, 6)) {
    return false;
  }
  int16_t ax = (int16_t)((raw[1] << 8) | raw[0]);
  int16_t ay = (int16_t)((raw[3] << 8) | raw[2]);
  int16_t az = (int16_t)((raw[5] << 8) | raw[4]);
  float mag = sqrtf((float)ax * ax + (float)ay * ay + (float)az * az);
  if (last_mag < 0) {
    last_mag = mag;
    return false;
  }
  float delta = fabsf(mag - last_mag);
  last_mag = mag;
  return delta > 250.0f;
}
