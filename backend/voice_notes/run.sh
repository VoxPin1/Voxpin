#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt

LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
if [[ -n "${LAN_IP}" ]]; then
  echo "This Mac's LAN IP is ${LAN_IP}"
  echo "Firmware backend_config.h should use: ${LAN_IP}"
fi

export PYTHONUNBUFFERED=1
exec .venv/bin/python app.py "$@"
