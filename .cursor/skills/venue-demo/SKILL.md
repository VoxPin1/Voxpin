---
name: venue-demo
description: Join this Mac to the phone hotspot and start the VoxPin voice-notes helper for a public venue demo. Use when the user says venue, we're at the venue, demo wifi, demo setup, /venue, or asks to connect to the phone hotspot.
---

# Venue demo setup

Run this instead of walking through Wi-Fi steps by hand.

## Do this

1. From the repo root, run `./venue.sh` with `all` permissions (it needs to change Wi-Fi and bind port 8765).
2. Report Mac SSID, Mac IP, helper `http://127.0.0.1:8765/health`, and pin USB if present.
3. Remind them to leave the helper running and keep the Mac on the hotspot.
4. The pin already skips venue/guest Wi-Fi and joins the hotspot when home SSID is not in the scan. Do not flash unless they ask.

## If join fails

The iPhone hotspot is off, or Maximize Compatibility is off (ESP32 is 2.4 GHz only). Ask them to turn those on, then run `./venue.sh` again.

Do not print the hotspot password.
