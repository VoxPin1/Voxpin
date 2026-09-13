# VoxPin setup

They only type **Wi-Fi name**, **Wi-Fi password**, and the **SOS phone number**.

```bash
./setup.sh
```

That writes the local secret files, starts the Mac helper so it stays running, clones the Waveshare trees if needed, and flashes if the pin is on USB.

Plug the pin in first if you want flash to happen in that same command. First PLUS tap: click **Allow** if macOS asks to control Messages (Apple requires that click).

Keep the Mac on, awake, and on the same 2.4 GHz Wi‑Fi as the pin.
