# VoxPin setup

They only type **Wi-Fi name**, **Wi-Fi password**, and the **SOS phone number**.

```bash
./setup.sh
```

That writes the local secret files, starts the Mac helper so it stays running, clones the Waveshare trees if needed, and flashes if the pin is on USB.

Plug the pin in first if you want flash to happen in that same command. First PLUS tap: click **Allow** if macOS asks to control Messages (Apple requires that click).

Keep the Mac on, awake, and on the same 2.4 GHz Wi‑Fi as the pin.

## Phone hotspot (demos)

The pin can be locked to one iPhone hotspot. Currently that's **Rian**. When a hotspot is set, the pin joins it and never tries any other network.

1. In `firmware/lcd-0.85/wifi_secrets.h`, set `WIFI_SSID_2` and `WIFI_PASSWORD_2` to the hotspot.
2. In `firmware/lcd-0.85/backend_config.h`, set `BACKEND_HOST` to `172.20.10.5`.
3. On the phone: Settings → Personal Hotspot → turn on **Allow Others to Join** and **Maximize Compatibility** (the pin is 2.4 GHz only).
4. Flash the pin: `./lcd-0.85.sh flash`.
5. Run `./venue.sh`. It joins the Mac to the hotspot, pins the Mac to `172.20.10.5`, and starts the helper.

The pin always takes `172.20.10.2` and calls `http://172.20.10.5:8765`. It has to be an iPhone hotspot, because those addresses sit on the iPhone's `172.20.10.0/28` subnet.
