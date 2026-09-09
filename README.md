# VoxPin

ESP32-S3 e-paper (Waveshare 1.54") firmware and tooling.

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

1. Clone the official Waveshare examples (not stored in this repo):

   ```bash
   git clone https://github.com/waveshareteam/ESP32-S3-ePaper-1.54.git
   ```

2. Copy bundled libraries and apply the smoke-test firmware patch — see [EPAPER_SMOKE_TEST.md](EPAPER_SMOKE_TEST.md). For full agent context, see [CONTEXT_VAULT.md](CONTEXT_VAULT.md).

3. Build and flash:

   ```bash
   ./epaper-smoke.sh flash
   ```
