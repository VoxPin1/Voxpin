# VoxPin Context Vault

> Agent handoff document. Paste into a new Cursor session to restore full project context.
> Last updated: 2026-09-13

---

## Project

**VoxPin** — ESP32-S3 voice pin firmware on a Waveshare ESP32-S3-LCD-0.85 board (GC9107, 128×128), plus a Mac helper for notes, translation, calendar, and SOS iMessage.

| Field | Value |
|---|---|
| Workspace | `/Users/riangadey/Voxpin` |
| GitHub | https://github.com/VoxPin1/Voxpin |
| Git remote | `origin` → `https://github.com/VoxPin1/Voxpin.git` |
| Branch | `main` |
| Latest commit | See `git log -1` |

---

## Hardware

| Field | Value |
|---|---|
| Board | Waveshare ESP32-S3-LCD-0.85 |
| Chip | ESP32-S3R8 |
| Flash | **8 MB** |
| PSRAM | **8 MB OPI** |
| Display | 128×128 color LCD, GC9107 SPI |
| Audio | ES8311 out, ES7210 in |

### LCD GPIO pins (from `firmware/lcd-0.85/board_pins.h`)

| Signal | GPIO |
|---|---|
| DC | 45 |
| CS | 21 |
| SCK | 38 |
| MOSI | 39 |
| RST | 40 |
| BL | 46 |

**Power:** BAT_EN GPIO 2 (hold high), BAT_ADC GPIO 1, CHG_STAT GPIO 3.

**Buttons:** BOOT GPIO 0, PWR GPIO 5, PLUS GPIO 4.

**Download mode if flash fails:** Hold BOOT → tap RST → release BOOT → retry flash.

---

## Repo structure

```
Voxpin/
├── CONTEXT_VAULT.md
├── README.md
├── SETUP.md
├── lcd-0.85.sh                 # build | flash | monitor | all | chip-info
├── setup.sh                    # Wi-Fi + SOS number + flash
├── firmware/lcd-0.85/          # VoxPin application firmware
└── .gitignore                  # Excludes .tools/, Waveshare clone, secrets, build/
```

### NOT in git (local only, gitignored)

```
.tools/                          # arduino-cli
ESP32-S3-LCD-0.85/               # Waveshare official repo clone
firmware/lcd-0.85/wifi_secrets.h
firmware/lcd-0.85/backend_config.h
backend/voice_notes/imessage_to.txt
```

### Fresh clone workflow

```bash
git clone https://github.com/VoxPin1/Voxpin.git
cd Voxpin
# Plug the pin in over USB, then:
./setup.sh
```

`./setup.sh` writes secrets, clones the Waveshare LCD examples if needed, and flashes.

---

## Toolchain

| Tool | Location / version |
|---|---|
| `arduino-cli` | `.tools/arduino-cli` |
| ESP32 Arduino core | `esp32:esp32@3.2.0` |
| `esptool` | `~/Library/Arduino15/packages/esp32/tools/esptool_py/*/esptool` |

### FQBN (8MB flash, OPI PSRAM)

```
esp32:esp32:esp32s3:CDCOnBoot=cdc,FlashMode=qio,FlashSize=8M,PartitionScheme=huge_app,PSRAM=opi,UploadMode=default,USBMode=hwcdc,UploadSpeed=921600
```

### Arduino board settings

| Setting | Value |
|---|---|
| Board | ESP32S3 Dev Module |
| USB CDC On Boot | Enabled |
| Flash Mode | QIO 80MHz |
| Flash Size | 8MB |
| Partition Scheme | Huge APP (3MB No OTA/1MB SPIFFS) |
| PSRAM | OPI PSRAM |
| Upload Mode | UART0 / Hardware CDC |
| USB Mode | Hardware CDC and JTAG |

---

## Firmware

**Source:** `firmware/lcd-0.85/`

Build copies the sketch into `ESP32-S3-LCD-0.85/example/Arduino-3.2.0/examples/voxpin_lcd` and uses Waveshare Arduino libraries (LVGL v8, Arduino_GFX). Codec sources live in `firmware/lcd-0.85/src/` (`codec_board`, `esp_codec_dev`).

**Architecture:**
- LVGL v8 home UI
- Arduino_GFX GC9107 for the LCD
- `power.cpp` for battery ADC and power hold
- ES8311 / ES7210 via vendored codec components

---

## Commands

```bash
./setup.sh                # Wi-Fi + SOS number + flash if USB is present
./lcd-0.85.sh build       # compile
./lcd-0.85.sh flash       # compile + upload USB
./lcd-0.85.sh monitor     # serial @ 115200 (press RST if empty)
./lcd-0.85.sh all         # build + flash + monitor
./lcd-0.85.sh chip-info   # detect chip/flash

PORT=/dev/cu.usbmodemXXXX ./lcd-0.85.sh flash
```

Expected serial output:

```
VoxPin LCD-0.85 starting...
Home screen ready.
```

---

## Waveshare references

- Repo: https://github.com/waveshareteam/ESP32-S3-LCD-0.85
- Wiki: https://www.waveshare.com/wiki/ESP32-S3-LCD-0.85
- Arduino examples: `example/Arduino-3.2.0/examples/`
- LVGL: use lvgl8 **or** lvgl9, never both

---

## Agent rules

- Never fabricate pin numbers, FQBNs, or flash/PSRAM settings
- Stay within official Waveshare LCD libraries for display
- Work incrementally; stop after 2–3 failures and explain
- Do not commit `.tools/`, Waveshare clone, or `build/`
- Only commit when user asks
```
