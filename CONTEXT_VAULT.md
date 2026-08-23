# VoxPin Context Vault

> Agent handoff document. Paste into a new Cursor session to restore full project context.
> Last updated: 2026-08-23

---

## Project

**VoxPin** — ESP32-S3 e-paper device firmware on a Waveshare ESP32-S3-ePaper-1.54 board (standard 2-color 200×200 panel, **not** the 4-color `-1.54G` variant).

| Field | Value |
|---|---|
| Workspace | `/Users/riangadey/voxpin` |
| GitHub | https://github.com/VoxPin1/Voxpin |
| Git remote | `origin` → `https://github.com/VoxPin1/Voxpin.git` |
| Branch | `main` |
| Latest commit | See `git log -1` |

**GitHub auth:** `gh` CLI authenticated; git credential helper configured via `gh auth setup-git`.

---

## Hardware (confirmed on this unit)

| Field | Value |
|---|---|
| Board | Waveshare ESP32-S3-ePaper-1.54 |
| Revision | **V2** |
| Chip | ESP32-S3-PICO-1 (LGA56), rev v0.2 |
| Flash | **8 MB** |
| PSRAM | **8 MB OPI** |
| USB port | `/dev/cu.usbmodem2401` |
| MAC | `ac:27:6e:d1:ff:9c` |
| Display | 200×200 e-paper, black/white |

### E-paper GPIO pins (from official `user_config.h`)

| Signal | GPIO |
|---|---|
| BUSY | 8 |
| RST | 9 |
| DC | 10 |
| CS | 11 |
| SCK | 12 |
| MOSI | 13 |
| PWR | 6 |

**Driver:** Official Waveshare `epaper_driver_bsp` with `WF_Full_1IN54` / `WF_PARTIAL_1IN54` waveform tables.

**Onboard but ignored for smoke test:** mic + ES8311 codec, PCF85063 RTC, SHTC3 sensor, microSD, battery ADC, touch (FT6336 on touch variant).

**Download mode if flash fails:** Hold BOOT → tap RST → release BOOT → retry flash.

### V1 vs V2 reference

| Revision | Chip | Flash | PSRAM |
|---|---|---|---|
| V1 | ESP32-S3FH4R2 | 4 MB | 2 MB QSPI |
| V2 | ESP32-S3-PICO-1-N8R8 | 8 MB | 8 MB OPI |

This unit is **V2**. Official Arduino screenshot shows 4MB flash for both revisions; this board detected 8MB via esptool.

---

## Smoke test status: COMPLETE ✅

User confirmed display works. All acceptance criteria met:

1. ✅ `arduino-cli` builds official e-paper example with zero errors
2. ✅ Board flashes over USB
3. ✅ E-paper physically displays content
4. ✅ Custom **"HELLO VOXPIN"** + incrementing counter renders (10 s refresh)
5. ✅ README/docs + reproducible script on GitHub

---

## Repo structure

```
voxpin/
├── CONTEXT_VAULT.md           # This file
├── README.md                    # Quick start
├── EPAPER_SMOKE_TEST.md         # Full smoke test documentation
├── epaper-smoke.sh              # build | flash | monitor | all | chip-info
├── arduino-cli.yaml             # Arduino CLI config (user libs path)
├── firmware/smoke-test/
│   ├── user_app.cpp             # Custom HELLO VOXPIN + counter task
│   └── 09_LVGL_V8_Test.ino      # Sketch with Serial boot logs
└── .gitignore                   # Excludes .tools/, Waveshare clone, arduino-libraries/, build/
```

### NOT in git (local only, gitignored)

```
.tools/                          # arduino-cli, gh CLI binaries
ESP32-S3-ePaper-1.54/            # ~764MB Waveshare official repo clone
arduino-libraries/               # ~178MB lvgl + SensorLib from Waveshare
```

### Fresh clone workflow

```bash
git clone https://github.com/VoxPin1/Voxpin.git
cd Voxpin
git clone https://github.com/waveshareteam/ESP32-S3-ePaper-1.54.git
mkdir -p arduino-libraries
cp -R ESP32-S3-ePaper-1.54/01_Arduino_Libraries/lvgl8/lvgl arduino-libraries/lvgl
cp ESP32-S3-ePaper-1.54/01_Arduino_Libraries/lvgl8/lv_conf.h arduino-libraries/
cp -R ESP32-S3-ePaper-1.54/01_Arduino_Libraries/SensorLib arduino-libraries/
cp firmware/smoke-test/user_app.cpp ESP32-S3-ePaper-1.54/02_Example/Arduino/09_LVGL_V8_Test/
cp firmware/smoke-test/09_LVGL_V8_Test.ino ESP32-S3-ePaper-1.54/02_Example/Arduino/09_LVGL_V8_Test/
./epaper-smoke.sh flash
```

---

## Toolchain

| Tool | Location / version |
|---|---|
| `arduino-cli` | `.tools/arduino-cli` |
| ESP32 Arduino core | `esp32:esp32@3.2.0` |
| `esptool` | `~/Library/Arduino15/packages/esp32/tools/esptool_py/4.9.dev3/esptool` |
| `gh` CLI | `.tools/gh_2.98.0_macOS_arm64/bin/gh` |

### FQBN (V2, 8MB flash, OPI PSRAM)

```
esp32:esp32:esp32s3:CDCOnBoot=cdc,FlashMode=qio,FlashSize=8M,PartitionScheme=huge_app,PSRAM=opi,UploadMode=default,USBMode=hwcdc,UploadSpeed=921600
```

### Arduino board settings

| Setting | Value |
|---|---|
| Board | ESP32S3 Dev Module |
| USB CDC On Boot | Enabled |
| Flash Mode | QIO 80MHz |
| Flash Size | 8MB (V2) / 4MB (V1) |
| Partition Scheme | Huge APP (3MB No OTA/1MB SPIFFS) |
| PSRAM | OPI PSRAM (V2) / QSPI PSRAM (V1) |
| Upload Mode | UART0 / Hardware CDC |
| USB Mode | Hardware CDC and JTAG |

---

## Example / sketch

**Path:** `ESP32-S3-ePaper-1.54/02_Example/Arduino/09_LVGL_V8_Test`

Note: Waveshare repo uses `02_Example/Arduino/` (not `Arduino_3.2.0/`). Libraries under `01_Arduino_Libraries/`.

**Architecture:**
- LVGL v8 for UI
- `epaper_driver_bsp` for panel SPI + refresh
- `board_power_bsp` — call `POWEER_EPD_ON()` before display init
- LVGL flush callback: RGB565 → black/white pixels → `EPD_DisplayPart()`

**Custom firmware** (`firmware/smoke-test/`):
- `hello_voxpin_task` replaces stock image-cycling
- Shows `HELLO VOXPIN` + `boot: N` counter every 10 s
- Serial boot logs in `.ino`

---

## Commands

```bash
./epaper-smoke.sh build       # compile
./epaper-smoke.sh flash       # compile + upload USB
./epaper-smoke.sh monitor     # serial @ 115200 (press RST if empty)
./epaper-smoke.sh all         # build + flash + monitor
./epaper-smoke.sh chip-info   # detect chip/flash

PORT=/dev/cu.usbmodemXXXX ./epaper-smoke.sh flash
```

Expected serial output:
```
ESP32-S3-ePaper-1.54 LVGL V8 smoke test starting...
LVGL port initialized.
```

---

## E-paper constraints

- Full/part refresh takes ~1–2 s
- Avoid rapid repeated refreshes (ghosting + wear)
- Use partial refresh when possible
- Always enable EPD power (GPIO 6) before init

---

## Waveshare references

- Repo: https://github.com/waveshareteam/ESP32-S3-ePaper-1.54
- Wiki: https://www.waveshare.com/wiki/ESP32-S3-ePaper-1.54
- Arduino examples: `02_Example/Arduino/` (01–12)
- Display examples: 07_BATT_PWR_Test, 08_Audio_Test, 09_LVGL_V8_Test, 10_LVGL_V9_Test, 11_RTC_Sleep_Test
- LVGL: use lvgl8 **or** lvgl9, never both

---

## Next steps (NOT started)

1. Real VoxPin application firmware (replace smoke test)
2. Audio — ES8311 codec (`08_Audio_Test`)
3. Sensors — SHTC3 (`03_I2C_SHTC3`), PCF85063 RTC (`02_I2C_PCF85063`)
4. SD card — `04_SD_Card`
5. WiFi — `05_WIFI_AP`, `06_WIFI_STA`
6. Battery/power — `07_BATT_PWR_Test` patterns
7. Standalone firmware project structure (PlatformIO or custom sketch)
8. CI — arduino-cli build in GitHub Actions

---

## Agent rules

- Never fabricate pin numbers, FQBNs, or flash/PSRAM settings
- Stay within official Waveshare libraries for display
- Work incrementally; stop after 2–3 failures and explain
- Do not commit `.tools/`, Waveshare clone, `arduino-libraries/`, or `build/`
- Only commit when user asks
- GitHub UI auth preferred (`GitHub: Sign in` in Cursor, or `gh auth login --web`)
