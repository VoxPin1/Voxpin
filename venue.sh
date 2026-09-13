#!/usr/bin/env bash
# Venue demo: join this Mac to the phone hotspot and start the helper.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
SECRETS="${ROOT}/firmware/lcd-0.85/wifi_secrets.h"
HELPER="${ROOT}/backend/voice_notes"
LOG="${HELPER}/venue-helper.log"
PIDFILE="${HELPER}/venue-helper.pid"

if [[ ! -f "$SECRETS" ]]; then
  echo "Missing $SECRETS — copy wifi_secrets.example.h first." >&2
  exit 1
fi

eval "$(python3 - "$SECRETS" <<'PY'
import re, shlex, sys
text = open(sys.argv[1], encoding="utf-8").read()

def grab(key):
    m = re.search(rf'#define\s+{re.escape(key)}\s+"((?:\\.|[^"\\])*)"', text)
    if not m:
        raise SystemExit(f"missing {key} in wifi_secrets.h")
    return m.group(1)

print(f"SSID={shlex.quote(grab('WIFI_SSID_2'))}")
print(f"PASSWORD={shlex.quote(grab('WIFI_PASSWORD_2'))}")
PY
)"

wifi_device() {
  networksetup -listallhardwareports | awk '
    /Hardware Port: Wi-Fi/ {wifi=1}
    wifi && /Device:/ {print $2; exit}
  '
}

current_ssid() {
  local dev="$1"
  ipconfig getsummary "$dev" 2>/dev/null | awk -F ' : ' '/ SSID/ {print $2; exit}' || true
}

ssid_variants() {
  python3 - "$SSID" <<'PY'
import sys
ssid = sys.argv[1]
seen = []
for value in (
    ssid,
    ssid.replace("\u2019", "'").replace("\u2018", "'"),
    ssid.replace("'", "\u2019"),
):
    if value and value not in seen:
        seen.append(value)
        print(value)
PY
}

already_on_hotspot() {
  local now="$1"
  [[ -z "$now" ]] && return 1
  python3 - "$now" "$SSID" <<'PY'
import sys
now, want = sys.argv[1], sys.argv[2]
def fold(s):
    return s.replace("\u2019", "'").replace("\u2018", "'").casefold()
sys.exit(0 if fold(now) == fold(want) else 1)
PY
}

DEV="$(wifi_device)"
if [[ -z "$DEV" ]]; then
  echo "No Wi-Fi interface found." >&2
  exit 1
fi

NOW="$(current_ssid "$DEV")"
if already_on_hotspot "$NOW"; then
  echo "Mac already on hotspot: $NOW"
else
  echo "Joining phone hotspot…"
  echo "If this hangs: iPhone Settings → Personal Hotspot → Maximize Compatibility ON"
  joined=0
  deadline=$((SECONDS + 45))
  while (( SECONDS < deadline )); do
    while IFS= read -r name; do
      if networksetup -setairportnetwork "$DEV" "$name" "$PASSWORD" >/tmp/voxpin-wifi-join.txt 2>&1; then
        joined=1
        break
      fi
    done < <(ssid_variants)
    NOW="$(current_ssid "$DEV")"
    if already_on_hotspot "$NOW"; then
      joined=1
      break
    fi
    IP_TRY="$(ipconfig getifaddr "$DEV" 2>/dev/null || true)"
    if [[ $joined -eq 1 || -n "$IP_TRY" ]]; then
      break
    fi
    sleep 3
  done
  if [[ $joined -eq 0 ]]; then
    echo "Could not join the hotspot." >&2
    echo "Turn on Personal Hotspot, enable Maximize Compatibility, then run ./venue.sh again." >&2
    if [[ -s /tmp/voxpin-wifi-join.txt ]]; then
      cat /tmp/voxpin-wifi-join.txt >&2
    fi
    exit 1
  fi
fi

IP=""
for _ in $(seq 1 20); do
  IP="$(ipconfig getifaddr "$DEV" 2>/dev/null || true)"
  if [[ -n "$IP" ]]; then
    break
  fi
  sleep 1
done

NOW="$(current_ssid "$DEV")"
echo "Wi-Fi: ${NOW:-unknown}"
if [[ -z "$IP" ]]; then
  echo "Mac joined but has no IP yet. Wait a few seconds and retry ./venue.sh." >&2
  exit 1
fi
echo "Mac IP: $IP"

if launchctl print "gui/$(id -u)/com.voxpin.helper" >/dev/null 2>&1; then
  echo "Restarting always-on helper…"
  launchctl kickstart -k "gui/$(id -u)/com.voxpin.helper"
else
  LISTENERS="$(lsof -nP -iTCP:8765 -sTCP:LISTEN -t 2>/dev/null || true)"
  if [[ -n "$LISTENERS" ]]; then
    echo "Restarting helper on port 8765…"
    kill $LISTENERS 2>/dev/null || true
    sleep 1
  fi
  if [[ -f "$PIDFILE" ]]; then
    old="$(cat "$PIDFILE" || true)"
    if [[ -n "${old}" ]] && kill -0 "$old" 2>/dev/null; then
      kill "$old" 2>/dev/null || true
    fi
    rm -f "$PIDFILE"
  fi
  nohup "$HELPER/run.sh" >>"$LOG" 2>&1 &
  echo $! >"$PIDFILE"
  sleep 1
fi

healthy=0
for _ in $(seq 1 20); do
  if curl -sf "http://127.0.0.1:8765/health" >/dev/null; then
    healthy=1
    break
  fi
  sleep 0.5
done

if [[ $healthy -eq 0 ]]; then
  echo "Helper did not start. Last log lines:" >&2
  tail -n 40 "$LOG" >&2 || true
  exit 1
fi

echo "Helper: http://127.0.0.1:8765/health  OK"
echo "Beacon should advertise ${IP} 8765"
if ls /dev/cu.usbmodem* >/dev/null 2>&1; then
  echo "Pin USB: $(ls /dev/cu.usbmodem* | tr '\n' ' ')"
else
  echo "Pin USB: not plugged in (ok if it is on battery)"
fi
echo
echo "Ready. Power the pin; it will skip home Wi-Fi and join this hotspot."
echo "Keep this Mac on the hotspot and leave the helper running."
