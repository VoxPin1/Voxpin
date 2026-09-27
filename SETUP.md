# VoxPin setup

They only type **Wi-Fi name**, **Wi-Fi password**, and the **SOS phone number**.

```bash
./setup.sh
```

That writes the local secret files, starts the Mac helper so it stays running, clones the Waveshare trees if needed, and flashes if the pin is on USB.

Plug the pin in first if you want flash to happen in that same command. First PLUS tap: click **Allow** if macOS asks to control Messages (Apple requires that click).

Keep the Mac on, awake, and on the same 2.4 GHz Wi‑Fi as the pin.

## Change Wi-Fi without a computer

1. Hold **+** for 5 seconds, awake or asleep. The screen shows **Hold for WiFi**, then **Join VoxPin-Setup**. Let go before 5 seconds and + sends SOS as usual. Holding + while the pin starts up (for example when it's plugged into USB) also works, and the pin opens this hotspot by itself when it can't join any Wi-Fi it knows.
2. On your phone, join the Wi-Fi network **VoxPin-Setup**. A setup page opens; if it doesn't, open any web page.
3. Pick your Wi-Fi (or type its name), enter the password, and tap **Connect**.
4. The pin shows **Joining**, then **WiFi saved** and switches to that network. **Wrong pass?** means rejoin VoxPin-Setup and try again.

The pin remembers that network across restarts and reflashing, and tries it before the built-in hotspot. It must be 2.4 GHz with no sign-in page, and the Mac running the helper must be on the same network. On a network other than the iPhone hotspot, set the Mac back to automatic addressing (`networksetup -setdhcp Wi-Fi`), because `venue.sh` pins it to `172.20.10.5`. If no phone joins VoxPin-Setup for two minutes, the pin retries the networks it knows, then reopens setup.

## Phone hotspot (demos)

The pin can be locked to one iPhone hotspot. Currently that's **Rian**. When a hotspot is set, the pin joins it and never tries any other network.

1. In `firmware/lcd-0.85/wifi_secrets.h`, set `WIFI_SSID_2` and `WIFI_PASSWORD_2` to the hotspot.
2. In `firmware/lcd-0.85/backend_config.h`, set `BACKEND_HOST` to `172.20.10.5`.
3. On the phone: Settings → Personal Hotspot → turn on **Allow Others to Join** and **Maximize Compatibility** (the pin is 2.4 GHz only).
4. Flash the pin: `./lcd-0.85.sh flash`.
5. Run `./venue.sh`. It joins the Mac to the hotspot, pins the Mac to `172.20.10.5`, and starts the helper.

The pin takes the fixed address `172.20.10.12` and calls the Mac at `http://172.20.10.5:8765`. It has to be an iPhone hotspot, because those addresses sit on the iPhone's `172.20.10.0/28` subnet. `.12` stays clear of the low addresses the phone hands out, and of older pins that sit on `.2`.
