#!/usr/bin/env bash
# Keep the VoxPin Mac helper running across reboots and crashes.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
LABEL="com.voxpin.helper"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
PYTHON="${DIR}/.venv/bin/python"
LOG="${DIR}/helper.log"
UID_NUM="$(id -u)"
DOMAIN="gui/${UID_NUM}"

if [[ ! -d "${DIR}/.venv" ]]; then
  python3 -m venv "${DIR}/.venv"
fi
"${DIR}/.venv/bin/pip" install -q -r "${DIR}/requirements.txt"

mkdir -p "${HOME}/Library/LaunchAgents"

cat >"$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>WorkingDirectory</key>
  <string>${DIR}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${PYTHON}</string>
    <string>${DIR}/app.py</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>5</integer>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PYTHONUNBUFFERED</key>
    <string>1</string>
    <key>PATH</key>
    <string>/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>StandardOutPath</key>
  <string>${LOG}</string>
  <key>StandardErrorPath</key>
  <string>${LOG}</string>
</dict>
</plist>
EOF

# Drop any leftover one-off helper so launchd can bind port 8765.
if lsof -nP -iTCP:8765 -sTCP:LISTEN >/dev/null 2>&1; then
  lsof -nP -iTCP:8765 -sTCP:LISTEN -t | xargs kill 2>/dev/null || true
  sleep 1
fi

launchctl bootout "${DOMAIN}/${LABEL}" 2>/dev/null || true
launchctl bootstrap "${DOMAIN}" "$PLIST"
launchctl enable "${DOMAIN}/${LABEL}"
launchctl kickstart -k "${DOMAIN}/${LABEL}"

for _ in $(seq 1 20); do
  if curl -sf "http://127.0.0.1:8765/health" >/dev/null; then
    echo "VoxPin helper is running and will stay up (login + crash restart)."
    echo "Health: http://127.0.0.1:8765/health"
    exit 0
  fi
  sleep 0.5
done

echo "Helper did not become healthy. Last log lines:" >&2
tail -n 40 "$LOG" >&2 || true
exit 1
