#!/usr/bin/env bash
# Waveshare ESP32-S3-LCD-0.85 VoxPin firmware helper
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
export ARDUINO_CLI="${ROOT}/.tools/arduino-cli"
export ARDUINO_CONFIG_FILE="${ROOT}/arduino-cli.yaml"
export ARDUINO_DIRECTORIES_USER="${ROOT}/ESP32-S3-LCD-0.85/example/Arduino-3.2.0"

FQBN='esp32:esp32:esp32s3:CDCOnBoot=cdc,FlashMode=qio,FlashSize=8M,PartitionScheme=huge_app,PSRAM=opi,UploadMode=default,USBMode=hwcdc,UploadSpeed=921600'
SRC="${ROOT}/firmware/lcd-0.85"
SKETCH="${ROOT}/ESP32-S3-LCD-0.85/example/Arduino-3.2.0/examples/voxpin_lcd"
LIBS="${ROOT}/ESP32-S3-LCD-0.85/example/Arduino-3.2.0/libraries"
AUDIO_SRC="${ROOT}/ESP32-S3-ePaper-1.54/02_Example/Arduino/08_Audio_Test"
PORT="${PORT:-/dev/cu.usbmodem1101}"

detect_port() {
  if [[ -e "$PORT" ]]; then
    return
  fi
  local found
  found="$(ls /dev/cu.usbmodem* 2>/dev/null | head -1 || true)"
  if [[ -n "$found" ]]; then
    PORT="$found"
  fi
}

sync_sketch() {
  mkdir -p "$SKETCH/src"
  cp "${SRC}/voxpin_lcd.ino" "$SKETCH/"
  cp "${SRC}/board_pins.h" "$SKETCH/"
  cp "${SRC}/power.h" "$SKETCH/"
  cp "${SRC}/power.cpp" "$SKETCH/"
  cp "${SRC}/home_ui.h" "$SKETCH/"
  cp "${SRC}/home_ui.cpp" "$SKETCH/"
  cp "${SRC}/audio_bsp.h" "$SKETCH/"
  cp "${SRC}/audio_bsp.c" "$SKETCH/"
  cp "${SRC}/voice_note.h" "$SKETCH/"
  cp "${SRC}/voice_note.cpp" "$SKETCH/"
  cp "${SRC}/side_buttons.h" "$SKETCH/"
  cp "${SRC}/side_buttons.cpp" "$SKETCH/"
  cp "${SRC}/wifi_connect.h" "$SKETCH/"
  cp "${SRC}/wifi_connect.cpp" "$SKETCH/"
  cp "${SRC}/backend_http.h" "$SKETCH/"
  cp "${SRC}/ble_companion.h" "$SKETCH/"
  cp "${SRC}/ble_companion.cpp" "$SKETCH/"

  if [[ -f "${SRC}/backend_config.h" ]]; then
    cp "${SRC}/backend_config.h" "$SKETCH/"
  else
    echo "Missing ${SRC}/backend_config.h — copy backend_config.example.h" >&2
    exit 1
  fi
  if [[ -f "${SRC}/wifi_secrets.h" ]]; then
    cp "${SRC}/wifi_secrets.h" "$SKETCH/"
  else
    echo "Missing ${SRC}/wifi_secrets.h — copy wifi_secrets.example.h" >&2
    exit 1
  fi

  rm -rf "${SKETCH}/src/codec_board" "${SKETCH}/src/esp_codec_dev"
  cp -R "${AUDIO_SRC}/src/codec_board" "${SKETCH}/src/codec_board"
  cp -R "${AUDIO_SRC}/src/esp_codec_dev" "${SKETCH}/src/esp_codec_dev"
  cp "${SRC}/board_cfg.h" "${SKETCH}/src/codec_board/board_cfg.h"

  cp "${ROOT}/ESP32-S3-LCD-0.85/example/Arduino-3.2.0/examples/08_lvgl_arduino_v8/lv_conf.h" "${LIBS}/lv_conf.h"
  python3 - "$LIBS/lv_conf.h" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
text = path.read_text()
text = text.replace("#define LV_FONT_MONTSERRAT_28 0", "#define LV_FONT_MONTSERRAT_28 1")
path.write_text(text)
print("lv_conf.h: montserrat 28 enabled")
PY
}

cmd="${1:-build}"
detect_port

case "$cmd" in
  build)
    sync_sketch
    "$ARDUINO_CLI" compile --libraries "$LIBS" --fqbn "$FQBN" "$SKETCH"
    ;;
  flash)
    sync_sketch
    "$ARDUINO_CLI" compile --export-binaries --libraries "$LIBS" --fqbn "$FQBN" "$SKETCH"
    ESPTOOL="$(ls -d "${HOME}/Library/Arduino15/packages/esp32/tools/esptool_py/"*/esptool | head -1)"
    BIN="${SKETCH}/build/esp32.esp32.esp32s3"
    "$ESPTOOL" --chip esp32s3 --port "$PORT" --before usb_reset --after hard_reset write_flash \
      --flash_mode dio --flash_freq 80m --flash_size 8MB \
      0x0 "${BIN}/voxpin_lcd.ino.bootloader.bin" \
      0x8000 "${BIN}/voxpin_lcd.ino.partitions.bin" \
      0x10000 "${BIN}/voxpin_lcd.ino.bin"
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
