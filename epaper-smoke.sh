#!/usr/bin/env bash
# Waveshare ESP32-S3-ePaper-1.54 smoke-test helper
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
export ARDUINO_CLI="${ROOT}/.tools/arduino-cli"
export ARDUINO_CONFIG_FILE="${ROOT}/arduino-cli.yaml"

# Detected board: V2 (ESP32-S3-PICO-1, 8MB flash, 8MB OPI PSRAM)
FQBN='esp32:esp32:esp32s3:CDCOnBoot=cdc,FlashMode=qio,FlashSize=8M,PartitionScheme=huge_app,PSRAM=opi,UploadMode=default,USBMode=hwcdc,UploadSpeed=921600'
SKETCH="${ROOT}/ESP32-S3-ePaper-1.54/02_Example/Arduino/09_LVGL_V8_Test"
PATCH_DIR="${ROOT}/firmware/smoke-test"
PORT="${PORT:-/dev/cu.usbmodem2401}"

AUDIO_SRC="${ROOT}/ESP32-S3-ePaper-1.54/02_Example/Arduino/08_Audio_Test"

sync_patches() {
  cp "${PATCH_DIR}/09_LVGL_V8_Test.ino" "${SKETCH}/"
  cp "${PATCH_DIR}/user_app.cpp" "${SKETCH}/"
  cp "${PATCH_DIR}/user_app.h" "${SKETCH}/"
  cp "${PATCH_DIR}/wifi_connect.h" "${SKETCH}/"
  cp "${PATCH_DIR}/wifi_connect.cpp" "${SKETCH}/"
  cp "${PATCH_DIR}/adc_bsp.cpp" "${SKETCH}/"
  cp "${PATCH_DIR}/adc_bsp.h" "${SKETCH}/"
  cp "${PATCH_DIR}/i2c_bsp.c" "${SKETCH}/"
  cp "${PATCH_DIR}/i2c_bsp.h" "${SKETCH}/"
  cp "${PATCH_DIR}/i2c_equipment.cpp" "${SKETCH}/"
  cp "${PATCH_DIR}/i2c_equipment.h" "${SKETCH}/"
  cp "${PATCH_DIR}/voice_note.cpp" "${SKETCH}/"
  cp "${PATCH_DIR}/voice_note.h" "${SKETCH}/"
  if [[ -f "${PATCH_DIR}/backend_config.h" ]]; then
    cp "${PATCH_DIR}/backend_config.h" "${SKETCH}/"
  else
    echo "Missing ${PATCH_DIR}/backend_config.h — copy backend_config.example.h" >&2
    exit 1
  fi
  if [[ -f "${PATCH_DIR}/wifi_secrets.h" ]]; then
    cp "${PATCH_DIR}/wifi_secrets.h" "${SKETCH}/"
  else
    echo "Missing ${PATCH_DIR}/wifi_secrets.h — copy wifi_secrets.example.h" >&2
    exit 1
  fi

  cp "${AUDIO_SRC}/audio_bsp.c" "${SKETCH}/"
  cp "${AUDIO_SRC}/audio_bsp.h" "${SKETCH}/"
  rm -rf "${SKETCH}/src/codec_board" "${SKETCH}/src/esp_codec_dev"
  cp -R "${AUDIO_SRC}/src/codec_board" "${SKETCH}/src/codec_board"
  cp -R "${AUDIO_SRC}/src/esp_codec_dev" "${SKETCH}/src/esp_codec_dev"
}

cmd="${1:-build}"

case "$cmd" in
  build)
    sync_patches
    "$ARDUINO_CLI" compile --libraries "${ROOT}/arduino-libraries" --fqbn "$FQBN" "$SKETCH"
    ;;
  flash)
    sync_patches
    "$ARDUINO_CLI" compile --export-binaries --libraries "${ROOT}/arduino-libraries" --fqbn "$FQBN" "$SKETCH"
    ESPTOOL="$(ls -d "${HOME}/Library/Arduino15/packages/esp32/tools/esptool_py/"*/esptool | head -1)"
    BIN="${SKETCH}/build/esp32.esp32.esp32s3"
    "$ESPTOOL" --chip esp32s3 --port "$PORT" --before usb_reset --after hard_reset write_flash \
      --flash_mode dio --flash_freq 80m --flash_size 8MB \
      0x0 "${BIN}/09_LVGL_V8_Test.ino.bootloader.bin" \
      0x8000 "${BIN}/09_LVGL_V8_Test.ino.partitions.bin" \
      0x10000 "${BIN}/09_LVGL_V8_Test.ino.bin"
    ;;
  monitor)
    "$ARDUINO_CLI" monitor -p "$PORT" -c baudrate=115200
    ;;
  all)
    "$0" build
    "$0" flash
    "$0" monitor
    ;;
  chip-info)
    ESPTOOL="$(ls -d "${HOME}/Library/Arduino15/packages/esp32/tools/esptool_py/"*/esptool | head -1)"
    "$ESPTOOL" --port "$PORT" chip_id
    "$ESPTOOL" --port "$PORT" flash_id
    ;;
  *)
    echo "Usage: $0 {build|flash|monitor|all|chip-info}" >&2
    exit 1
    ;;
esac
