---
description: Join the phone hotspot and start the VoxPin helper for a venue demo
---

The user is at a public venue (or wants demo Wi-Fi setup).

1. If needed, tell them to turn on the "Rian" iPhone Personal Hotspot with **Maximize Compatibility**.
2. From the repo root, run `./venue.sh` with unrestricted/`all` permissions. That script joins this Mac to the hotspot in `wifi_secrets.h`, pins the Mac to `172.20.10.5`, and starts the voice-notes helper.
3. Report the Mac IP, hotspot channel, helper health, and whether the pin USB port is present.
4. Do not flash firmware unless they ask.
5. If join fails, or `venue.sh` warns the hotspot is on 5 GHz, ask them to enable Maximize Compatibility and rerun `./venue.sh`.
