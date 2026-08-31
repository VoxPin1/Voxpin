#!/usr/bin/env bash
# WiFi connect test for VoxPin board
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
export ARDUINO_CLI="${ROOT}/.tools/arduino-cli"
export ARDUINO_CONFIG_FILE="${ROOT}/arduino-cli.yaml"

FQBN='esp32:esp32:esp32s3:CDCOnBoot=cdc,FlashMode=qio,FlashSize=8M,PartitionScheme=huge_app,PSRAM=opi,UploadMode=default,USBMode=hwcdc,UploadSpeed=921600'
SKETCH="${ROOT}/firmware/wifi-test"
PORT="${PORT:-/dev/cu.usbmodem2401}"

cmd="${1:-flash}"

case "$cmd" in
  build)
    "$ARDUINO_CLI" compile --fqbn "$FQBN" "$SKETCH"
    ;;
  flash)
    "$ARDUINO_CLI" compile --export-binaries --fqbn "$FQBN" "$SKETCH"
    "$ARDUINO_CLI" upload -p "$PORT" --input-dir "$SKETCH/build/esp32.esp32.esp32s3" --fqbn "$FQBN" "$SKETCH"
    echo "Flashed. Run: $0 monitor  (then press RST on board)"
    ;;
  monitor)
    "$ARDUINO_CLI" monitor -p "$PORT" -c baudrate=115200
    ;;
  *)
    echo "Usage: $0 {build|flash|monitor}" >&2
    exit 1
    ;;
esac
