---
description: Join the phone hotspot and start the VoxPin helper for a venue demo
---

The user is at a public venue (or wants demo Wi-Fi setup).

1. If needed, tell them to turn on iPhone Personal Hotspot with **Maximize Compatibility**.
2. From the repo root, run `./venue.sh` with unrestricted/`all` permissions. That script joins this Mac to the hardcoded phone hotspot and starts the voice-notes helper.
3. Report the Mac IP, helper health, and whether the pin USB port is present.
4. Do not flash firmware unless they ask.
5. If join fails, the hotspot is off or still on 5 GHz — ask them to enable Maximize Compatibility and rerun `./venue.sh`.
