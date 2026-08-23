# ESP32-S3-ePaper-1.54 — first-light smoke test

Board: **Waveshare ESP32-S3-ePaper-1.54** (standard 2-color 200×200 panel)

## Detected hardware (this unit)

| Field | Value |
|---|---|
| Revision | **V2** |
| Chip | ESP32-S3-PICO-1 (LGA56) |
| Flash | **8 MB** |
| PSRAM | **8 MB OPI** |
| USB port | `/dev/cu.usbmodem2401` |
| MAC | `ac:27:6e:d1:ff:9c` |

Detected via:

```bash
./epaper-smoke.sh chip-info
```

## E-paper GPIO pins (from official `user_config.h`)

| Signal | GPIO |
|---|---|
| BUSY | 8 |
| RST | 9 |
| DC | 10 |
| CS | 11 |
| SCK | 12 |
| MOSI | 13 |
| PWR | 6 |

Driver: official `epaper_driver_bsp` (1.54" waveform tables `WF_Full_1IN54` / `WF_PARTIAL_1IN54`).

## Example used

`ESP32-S3-ePaper-1.54/02_Example/Arduino/09_LVGL_V8_Test`

Stock demo cycles two 200×200 images. Custom smoke-test firmware shows **`HELLO VOXPIN`** plus an incrementing boot counter (10 s refresh).

## Prerequisites

- `arduino-cli` installed at `.tools/arduino-cli`
- ESP32 Arduino core **3.2.0** (`esp32:esp32@3.2.0`)
- Official libraries copied to `arduino-libraries/` (`lvgl` + `lv_conf.h`, `SensorLib`)

## Build / flash / monitor

```bash
./epaper-smoke.sh build      # compile only
./epaper-smoke.sh flash      # compile + upload over USB
./epaper-smoke.sh monitor    # serial @ 115200 (USB CDC)
./epaper-smoke.sh all        # build + flash + monitor
```

Override port: `PORT=/dev/cu.usbmodemXXXX ./epaper-smoke.sh flash`

## Arduino board settings (V2, detected 8 MB flash)

| Setting | Value |
|---|---|
| Board | ESP32S3 Dev Module |
| USB CDC On Boot | **Enabled** |
| Flash Mode | QIO 80MHz |
| Flash Size | **8MB** (detected; official screenshot shows 4MB for older units) |
| Partition Scheme | Huge APP (3MB No OTA/1MB SPIFFS) |
| PSRAM | **OPI PSRAM** |
| Upload Mode | UART0 / Hardware CDC |
| USB Mode | Hardware CDC and JTAG |

FQBN used by the script:

```
esp32:esp32:esp32s3:CDCOnBoot=cdc,FlashMode=qio,FlashSize=8M,PartitionScheme=huge_app,PSRAM=opi,UploadMode=default,USBMode=hwcdc,UploadSpeed=921600
```

## Download mode (if upload fails)

1. Hold **BOOT**
2. Tap **RST**
3. Release **BOOT**
4. Retry `./epaper-smoke.sh flash`

## E-paper notes

- Updates use a **full/part refresh** through the official driver — expect ~1–2 s per update.
- **Do not refresh rapidly**; ghosting and panel wear increase with frequent full refreshes.
- The custom counter updates every **10 seconds** intentionally.

## Clone official repo (one-time)

```bash
git clone https://github.com/waveshareteam/ESP32-S3-ePaper-1.54.git
cp -R ESP32-S3-ePaper-1.54/01_Arduino_Libraries/lvgl8/lvgl arduino-libraries/lvgl
cp ESP32-S3-ePaper-1.54/01_Arduino_Libraries/lvgl8/lv_conf.h arduino-libraries/
cp -R ESP32-S3-ePaper-1.54/01_Arduino_Libraries/SensorLib arduino-libraries/
```

Apply the custom smoke-test firmware (HELLO VOXPIN + counter):

```bash
cp firmware/smoke-test/user_app.cpp ESP32-S3-ePaper-1.54/02_Example/Arduino/09_LVGL_V8_Test/
cp firmware/smoke-test/09_LVGL_V8_Test.ino ESP32-S3-ePaper-1.54/02_Example/Arduino/09_LVGL_V8_Test/
```
