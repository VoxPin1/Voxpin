#!/usr/bin/env bash
# Idempotent Cloud Agent install for the VoxPin companion backend.
set -euo pipefail

# The default base image ships Python 3.12 but not the venv/ensurepip module.
if ! python3 -c "import ensurepip" >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y --no-install-recommends python3-venv
fi

cd "$(dirname "$0")/../backend/voice_notes"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
