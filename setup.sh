#!/usr/bin/env bash
# One command: Wi-Fi + phone number. Everything else is automatic.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
FW="${ROOT}/firmware/lcd-0.85"
HELPER="${ROOT}/backend/voice_notes"
export ARDUINO_CLI="${ROOT}/.tools/arduino-cli"
export ARDUINO_CONFIG_FILE="${ROOT}/arduino-cli.yaml"

prompt() {
  local label="$1"
  local value=""
  printf "%s" "$label" >&2
  IFS= read -r value
  printf "%s" "$value"
}

if [[ -n "${VOXPIN_WIFI_SSID:-}" && -n "${VOXPIN_WIFI_PASSWORD:-}" && -n "${VOXPIN_IMESSAGE_TO:-}" ]]; then
  WIFI_SSID="$VOXPIN_WIFI_SSID"
  WIFI_PASSWORD="$VOXPIN_WIFI_PASSWORD"
  PHONE="$VOXPIN_IMESSAGE_TO"
else
  if [[ ! -t 0 ]]; then
    echo "Set VOXPIN_WIFI_SSID, VOXPIN_WIFI_PASSWORD, and VOXPIN_IMESSAGE_TO, or run in a terminal." >&2
    exit 1
  fi
  echo "VoxPin setup — only Wi-Fi and the SOS phone number."
  WIFI_SSID="$(prompt "Wi-Fi name: ")"
  WIFI_PASSWORD="$(prompt "Wi-Fi password: ")"
  PHONE="$(prompt "SOS phone (10 digits or +1...): ")"
fi

if [[ -z "$WIFI_SSID" || -z "$WIFI_PASSWORD" || -z "$PHONE" ]]; then
  echo "Need Wi-Fi name, Wi-Fi password, and a phone number." >&2
  exit 1
fi

LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
if [[ -z "$LAN_IP" ]]; then
  LAN_IP="127.0.0.1"
  echo "No LAN IP yet; helper host set to 127.0.0.1 (re-run setup after Wi-Fi is up)." >&2
fi

python3 - "$WIFI_SSID" "$WIFI_PASSWORD" "$PHONE" "$LAN_IP" "$FW" "$HELPER" <<'PY'
import pathlib, re, sys

ssid, password, phone, ip, fw, helper = sys.argv[1:7]

def c_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

digits = re.sub(r"\D", "", phone)
if phone.strip().startswith("+") and digits:
    dest = "+" + digits
elif len(digits) == 10:
    dest = "+1" + digits
elif len(digits) == 11 and digits.startswith("1"):
    dest = "+" + digits
else:
    raise SystemExit("Phone number should be 10 digits or +1...")

wifi = pathlib.Path(fw) / "wifi_secrets.h"
wifi.write_text(
    "#pragma once\n\n"
    f"#define WIFI_SSID {c_string(ssid)}\n"
    f"#define WIFI_PASSWORD {c_string(password)}\n"
    "#define WIFI_SSID_2 \"\"\n"
    "#define WIFI_PASSWORD_2 \"\"\n"
)
(pathlib.Path(fw) / "backend_config.h").write_text(
    "#pragma once\n\n"
    "#define BACKEND_SCHEME \"http\"\n"
    f"#define BACKEND_HOST {c_string(ip)}\n"
    "#define BACKEND_PORT 8765\n"
)
(pathlib.Path(helper) / "imessage_to.txt").write_text(dest + "\n")
print("wrote wifi_secrets.h, backend_config.h, imessage_to.txt")
print("helper IP", ip)
PY

mkdir -p "${ROOT}/.tools"
if [[ ! -x "$ARDUINO_CLI" ]]; then
  echo "Installing arduino-cli…"
  curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | BINDIR="${ROOT}/.tools" sh
fi

if [[ ! -d "${ROOT}/ESP32-S3-LCD-0.85/.git" && ! -d "${ROOT}/ESP32-S3-LCD-0.85/example" ]]; then
  echo "Cloning Waveshare LCD examples…"
  git clone --depth 1 https://github.com/waveshareteam/ESP32-S3-LCD-0.85.git "${ROOT}/ESP32-S3-LCD-0.85"
fi
if [[ ! -d "${ROOT}/ESP32-S3-ePaper-1.54/.git" && ! -d "${ROOT}/ESP32-S3-ePaper-1.54/02_Example" ]]; then
  echo "Cloning Waveshare audio examples…"
  git clone --depth 1 https://github.com/waveshareteam/ESP32-S3-ePaper-1.54.git "${ROOT}/ESP32-S3-ePaper-1.54"
fi

if [[ "$(uname -s)" == "Darwin" ]]; then
  "${HELPER}/install-helper.sh"
else
  echo "SOS iMessage needs a Mac. Start the helper with: cd backend/voice_notes && ./run.sh"
fi

if [[ "$(uname -s)" == "Darwin" ]] && ls /dev/cu.usbmodem* >/dev/null 2>&1; then
  echo "Pin USB found — flashing…"
  "$ARDUINO_CLI" config set board_manager.additional_urls https://espressif.github.io/arduino-esp32/package_esp32_index.json >/dev/null
  "$ARDUINO_CLI" core update-index >/dev/null
  "$ARDUINO_CLI" core install esp32:esp32@3.2.0 >/dev/null || "$ARDUINO_CLI" core install esp32:esp32
  "${ROOT}/lcd-0.85.sh" flash
  echo "Flashed. First PLUS tap: click Allow if macOS asks to control Messages."
else
  echo "Plug the pin in over USB, then run: ./lcd-0.85.sh flash"
fi

echo
echo "Done. Mac helper stays running. PLUS sends SOS to that phone number."
echo "Keep this computer on, awake, and on the same 2.4 GHz Wi-Fi as the pin."
