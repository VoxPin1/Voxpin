#!/usr/bin/env bash
# Deploy the voice helper to Fly.io. Never prints secret file contents.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

if ! command -v fly >/dev/null 2>&1 && ! command -v flyctl >/dev/null 2>&1; then
  echo "Installing flyctl..."
  curl -L https://fly.io/install.sh | sh
  export FLYCTL_INSTALL="${HOME}/.fly"
  export PATH="${FLYCTL_INSTALL}/bin:${PATH}"
fi

FLY="$(command -v flyctl || true)"
if [[ -z "$FLY" ]]; then
  FLY="$(command -v fly)"
fi

if ! "$FLY" auth whoami >/dev/null 2>&1; then
  echo "Log in to Fly.io in the browser window that opens."
  "$FLY" auth login
fi

APP="voxpin-helper"
if ! "$FLY" status --app "$APP" >/dev/null 2>&1; then
  echo "Creating Fly app ${APP}..."
  "$FLY" apps create "$APP" --org personal
fi

b64() { base64 < "$1" | tr -d '\n'; }

SECRET_FILE="$(mktemp)"
cleanup() { rm -f "$SECRET_FILE"; }
trap cleanup EXIT

: > "$SECRET_FILE"
if [[ -f token.json ]]; then
  printf 'VOXPIN_GOOGLE_TOKEN_B64=%s\n' "$(b64 token.json)" >> "$SECRET_FILE"
fi
if [[ -f credentials.json ]]; then
  printf 'VOXPIN_GOOGLE_CREDENTIALS_B64=%s\n' "$(b64 credentials.json)" >> "$SECRET_FILE"
fi
if [[ -f apps_script_url.txt ]]; then
  printf 'VOXPIN_APPS_SCRIPT_URL=%s\n' "$(tr -d '\n' < apps_script_url.txt)" >> "$SECRET_FILE"
fi
if [[ -f apps_script_secret.txt ]]; then
  printf 'VOXPIN_APPS_SCRIPT_SECRET=%s\n' "$(tr -d '\n' < apps_script_secret.txt)" >> "$SECRET_FILE"
fi

if [[ -s "$SECRET_FILE" ]]; then
  echo "Setting Fly secrets from local credential files (values not printed)."
  "$FLY" secrets import --app "$APP" --stage < "$SECRET_FILE"
else
  echo "Warning: no local Google/Apps Script files found to upload as secrets." >&2
fi

echo "Deploying with Fly remote builder..."
"$FLY" deploy --remote-only --app "$APP" --config fly.toml

echo
echo "Helper URL: https://${APP}.fly.dev/"
echo "Health:     https://${APP}.fly.dev/health"
echo "Point firmware backend_config.h at that host on port 443 with https."
