# VoxPin

Voice pin firmware for **Waveshare ESP32-S3-LCD-0.85**, plus a Mac helper for notes, translation, calendar, and SOS iMessage.

**New pin:** plug it in, run `./setup.sh`, type Wi-Fi name, Wi-Fi password, and the SOS phone number. Details: [SETUP.md](SETUP.md).

## Companion website

Run the voice backend to open the VoxPin web app (notes, translation language, calendar):

```bash
cd backend/voice_notes
./run.sh
```

Then open [http://127.0.0.1:8765/](http://127.0.0.1:8765/).

A public preview of the companion UI is on GitHub Pages: [https://voxpin1.github.io/Voxpin/](https://voxpin1.github.io/Voxpin/). Pair the pin over Bluetooth (Chrome/Edge) to keep a profile and language settings in the browser and on the device. Sign in with Google on the Account tab, then click **Load notes & calendar**. The site displays your Google Doc (Drive) and Calendar — no VoxPin server required for that. Voice capture from the pin can still write into that same Doc via Apps Script.

- **Notes** — phrases you asked the pin to translate, stored as text (no audio clips)
- **Language** — base language the pin speaks when translating
- **Calendar** — tasks synced with Google Calendar (`./run.sh --login`)

## Quick start

Plug the pin in over USB, then:

```bash
./setup.sh
```

That writes Wi‑Fi and SOS secrets, clones the Waveshare LCD examples, and flashes. To flash later:

```bash
./lcd-0.85.sh flash
```
