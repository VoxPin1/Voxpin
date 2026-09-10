#!/usr/bin/env bash
# VoxPin Cloud Agent environment bootstrap.
# Idempotent: safe to run repeatedly. Prepares the Python voice-notes backend
# and the ESP32-S3 firmware toolchain (arduino-cli + esp32 core).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

log() { printf '\n=== %s ===\n' "$1"; }

# --- System packages ---------------------------------------------------------
# python3-venv/-dev: build the backend virtualenv; flac: SpeechRecognition's
# Google recognizer shells out to the flac encoder.
log "System packages"
NEED_PKGS=()
dpkg -s python3-venv >/dev/null 2>&1 || NEED_PKGS+=(python3-venv)
dpkg -s python3-dev  >/dev/null 2>&1 || NEED_PKGS+=(python3-dev)
dpkg -s flac         >/dev/null 2>&1 || NEED_PKGS+=(flac)
if [[ ${#NEED_PKGS[@]} -gt 0 ]]; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq "${NEED_PKGS[@]}"
else
  echo "All system packages already present."
fi

# --- Python voice-notes backend ---------------------------------------------
log "Backend virtualenv"
BACKEND="$ROOT/backend/voice_notes"
if [[ ! -x "$BACKEND/.venv/bin/python" ]]; then
  python3 -m venv "$BACKEND/.venv"
fi
"$BACKEND/.venv/bin/pip" install -q --upgrade pip
"$BACKEND/.venv/bin/pip" install -q -r "$BACKEND/requirements.txt"
echo "Backend dependencies installed."

# --- ESP32-S3 firmware toolchain --------------------------------------------
# arduino-cli lives in .tools/ (gitignored) to match epaper-smoke.sh, which
# expects ${ROOT}/.tools/arduino-cli. The esp32 core installs into the default
# data dir (~/.arduino15) so it is captured by the environment snapshot.
log "Firmware toolchain (arduino-cli + esp32 core)"
mkdir -p "$ROOT/.tools"
ARDUINO_CLI="$ROOT/.tools/arduino-cli"
if [[ ! -x "$ARDUINO_CLI" ]]; then
  curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh \
    | BINDIR="$ROOT/.tools" sh
fi

# Config file dedicated to Cloud Agents (the committed arduino-cli.yaml points
# at a developer's local macOS library path).
CLI_CONFIG="$ROOT/.tools/arduino-cli.yaml"
ESP32_URL="https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json"
if [[ ! -f "$CLI_CONFIG" ]]; then
  "$ARDUINO_CLI" config init --dest-file "$CLI_CONFIG" --overwrite >/dev/null
  "$ARDUINO_CLI" --config-file "$CLI_CONFIG" config add board_manager.additional_urls "$ESP32_URL"
fi

if ! "$ARDUINO_CLI" --config-file "$CLI_CONFIG" core list 2>/dev/null | grep -q '^esp32:esp32'; then
  "$ARDUINO_CLI" --config-file "$CLI_CONFIG" core update-index
  "$ARDUINO_CLI" --config-file "$CLI_CONFIG" core install esp32:esp32@3.2.0
else
  echo "esp32 core already installed."
fi

log "VoxPin environment ready"
cat <<'EOF'
Backend:  cd backend/voice_notes && ./run.sh            (needs Google creds for Docs/Calendar)
Firmware: ./.tools/arduino-cli --config-file .tools/arduino-cli.yaml compile ...
          Full VoxPin sketch also needs the Waveshare clone + libs (see EPAPER_SMOKE_TEST.md).
EOF
