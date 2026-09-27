---
name: venue-demo
description: Join this Mac to the phone hotspot and start the VoxPin voice-notes helper for a public venue demo. Use when the user says venue, we're at the venue, demo wifi, demo setup, /venue, or asks to connect to the phone hotspot.
---

# Venue demo setup

Run this instead of walking through Wi-Fi steps by hand.

## Do this

1. From the repo root, run `./venue.sh` with `all` permissions (it needs to change Wi-Fi, set the Mac's IP, and bind port 8765).
2. Report Mac SSID and channel, Mac IP, helper `http://127.0.0.1:8765/health`, and pin USB if present.
3. Remind them to leave the helper running and keep the Mac on the hotspot.
4. The pin joins only the iPhone hotspot "Rian" (`WIFI_SSID_2` in `firmware/lcd-0.85/wifi_secrets.h`). It never tries Makers, home Wi-Fi, or anything else. Do not flash unless they ask.

## Fixed addresses

Both sides are pinned so they always meet at the same IP:

- Mac: `172.20.10.5` (`BACKEND_HOST` in `backend_config.h`). `venue.sh` sets this with "Manually using DHCP router".
- Pin: `172.20.10.2`, and it calls `http://172.20.10.5:8765`.

## If join fails

The iPhone hotspot is off, or Maximize Compatibility is off (ESP32 is 2.4 GHz only). `venue.sh` prints a warning when the hotspot is on 5 GHz. Ask them to turn those on, then run `./venue.sh` again.

## Switching to a different hotspot

Change `WIFI_SSID_2` and `WIFI_PASSWORD_2` in `wifi_secrets.h`, then `./lcd-0.85.sh flash` with the pin on USB. It must be an iPhone hotspot, since the addresses above are on the iPhone's 172.20.10.0/28 subnet.

Do not print the hotspot password.
