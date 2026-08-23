#!/usr/bin/env bash
# Waveshare ESP32-S3-ePaper-1.54 smoke-test helper
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
export ARDUINO_CLI="${ROOT}/.tools/arduino-cli"
export ARDUINO_CONFIG_FILE="${ROOT}/arduino-cli.yaml"

# Detected board: V2 (ESP32-S3-PICO-1, 8MB flash, 8MB OPI PSRAM)
FQBN='esp32:esp32:esp32s3:CDCOnBoot=cdc,FlashMode=qio,FlashSize=8M,PartitionScheme=huge_app,PSRAM=opi,UploadMode=default,USBMode=hwcdc,UploadSpeed=921600'
SKETCH="${ROOT}/ESP32-S3-ePaper-1.54/02_Example/Arduino/09_LVGL_V8_Test"
PORT="${PORT:-/dev/cu.usbmodem2401}"

cmd="${1:-build}"

case "$cmd" in
  build)
    "$ARDUINO_CLI" compile --libraries "${ROOT}/arduino-libraries" --fqbn "$FQBN" "$SKETCH"
    ;;
  flash)
    "$ARDUINO_CLI" compile --export-binaries --libraries "${ROOT}/arduino-libraries" --fqbn "$FQBN" "$SKETCH"
    "$ARDUINO_CLI" upload -p "$PORT" --input-dir "$SKETCH/build/esp32.esp32.esp32s3" --fqbn "$FQBN" "$SKETCH"
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
