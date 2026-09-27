#!/usr/bin/env bash
# Venue demo: join this Mac to the phone hotspot and start the helper.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
SECRETS="${ROOT}/firmware/lcd-0.85/wifi_secrets.h"
BACKEND="${ROOT}/firmware/lcd-0.85/backend_config.h"
HELPER="${ROOT}/backend/voice_notes"
LOG="${HELPER}/venue-helper.log"
PIDFILE="${HELPER}/venue-helper.pid"

for f in "$SECRETS" "$BACKEND"; do
  if [[ ! -f "$f" ]]; then
    echo "Missing $f — copy the matching .example.h first." >&2
    exit 1
  fi
done

eval "$(python3 - "$SECRETS" "$BACKEND" <<'PY'
import re, shlex, sys
secrets = open(sys.argv[1], encoding="utf-8").read()
backend = open(sys.argv[2], encoding="utf-8").read()

def grab(text, key, name):
    m = re.search(rf'#define\s+{re.escape(key)}\s+"((?:\\.|[^"\\])*)"', text)
    if not m:
        raise SystemExit(f"missing {key} in {name}")
    # wifi_secrets.h may store an apostrophe as C hex bytes (\xe2\x80\x99).
    raw = m.group(1).encode("utf-8").decode("unicode_escape")
    return raw.encode("latin1").decode("utf-8")

print(f"SSID={shlex.quote(grab(secrets, 'WIFI_SSID_2', 'wifi_secrets.h'))}")
print(f"PASSWORD={shlex.quote(grab(secrets, 'WIFI_PASSWORD_2', 'wifi_secrets.h'))}")
print(f"HOST={shlex.quote(grab(backend, 'BACKEND_HOST', 'backend_config.h'))}")
PY
)"

case "$HOST" in
  172.20.10.*) ;;
  *)
    echo "BACKEND_HOST is $HOST; it must be on the iPhone hotspot subnet (172.20.10.x)." >&2
    exit 1
    ;;
esac

wifi_device() {
  networksetup -listallhardwareports | awk '
    /Hardware Port: Wi-Fi/ {wifi=1}
    wifi && /Device:/ {print $2; exit}
  '
}

wifi_service() {
  networksetup -listallhardwareports | awk -F ': ' '
    /Hardware Port:/ {port=$2}
    /Device:/ && $2 == dev {print port; exit}
  ' dev="$1"
}

# ipconfig redacts the SSID on recent macOS; system_profiler does not.
current_network() {
  system_profiler SPAirPortDataType 2>/dev/null | awk '
    /Current Network Information:/ {grab=1; next}
    grab && !name && /:$/ {sub(/^[ \t]+/, ""); sub(/:$/, ""); name=$0; next}
    grab && /Channel:/ {sub(/^[ \t]+Channel: /, ""); print name "\t" $0; exit}
  '
}

current_ssid() {
  current_network | cut -f1
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
    case "$IP_TRY" in
      172.20.10.*|192.0.0.*) joined=1 ;;
    esac
    if [[ $joined -eq 1 ]]; then
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

if [[ -z "$IP" ]]; then
  echo "Mac joined but has no IP yet. Wait a few seconds and retry ./venue.sh." >&2
  exit 1
fi

# The pin has BACKEND_HOST baked in, so the Mac must hold exactly that address.
if [[ "$IP" != "$HOST" ]]; then
  SERVICE="$(wifi_service "$DEV")"
  echo "Pinning Mac to $HOST (was $IP)…"
  networksetup -setmanualwithdhcprouter "${SERVICE:-Wi-Fi}" "$HOST"
  for _ in $(seq 1 20); do
    IP="$(ipconfig getifaddr "$DEV" 2>/dev/null || true)"
    [[ "$IP" == "$HOST" ]] && break
    sleep 1
  done
  if [[ "$IP" != "$HOST" ]]; then
    echo "Mac IP is ${IP:-none}, expected $HOST." >&2
    exit 1
  fi
fi

NET="$(current_network)"
NOW="$(printf '%s' "$NET" | cut -f1)"
CHANNEL="$(printf '%s' "$NET" | cut -f2)"
echo "Wi-Fi: ${NOW:-unknown} (${CHANNEL:-channel unknown})"
echo "Mac IP: $IP"
case "$CHANNEL" in
  *5GHz*|*6GHz*)
    echo "WARNING: the hotspot is on ${CHANNEL}. The pin is 2.4 GHz only and will not join." >&2
    echo "         On the phone: Settings → Personal Hotspot → Maximize Compatibility ON." >&2
    ;;
esac

if launchctl print "gui/$(id -u)/com.voxpin.helper" >/dev/null 2>&1; then
  LOG="${HELPER}/helper.log"
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
for _ in $(seq 1 60); do
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
echo "Ready. The pin joins only '${SSID}' at 172.20.10.2 and calls http://${HOST}:8765."
echo "Keep this Mac on the hotspot and leave the helper running."
