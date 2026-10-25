# NEXUS — Hardware Reference & EDU_ROBO V14 Integration Guide

> **Document Status:** Authoritative Hardware & Pinout Specification  
> **Target Platform:** **EDU_ROBO V14** ESP32 Trainer PCB (`ESP32-WROOM-32` / `ESP32-D0WD-V3` rev `v3.1`, 2 MB Flash)  
> **Evidence Sources:** `firmware/main/sensors/*.c`, `firmware/main/command/nexus_command_dispatcher.c`, `docs/SPEC_SHEET.md`, `docs/validation/M10_QUALIFICATION_MATRIX.md`, `docs/validation/m10_b*.log`, `docs/validation/m10_c_hcsr04_live.log`

---

## 1. Platform Overview & Electrical Safety Rules

The NEXUS embedded node runs on the **EDU_ROBO V14** multi-peripheral trainer board centered on an **ESP32-WROOM-32** module (`Dual-Core Xtensa LX6 @ 160/240 MHz`, `520 KB SRAM`, `2 MB SPI Flash`, onboard `3.3 V` LDO regulator, and USB-to-UART0 bridge mapped to `/dev/ttyUSB0` at `115200 8N1`).

### Mandatory Electrical & Pin-Strapping Precautions

1. **`3.3 V` Absolute GPIO Logic Limit (`GPIO 26` HC-SR04 Echo):**
   - ESP32 GPIOs are **NOT `5 V` tolerant** (`V_IH_max = 3.6 V`).
   - On the EDU_ROBO V14 `ULTRA` 4-pin header (`docs/SPEC_SHEET.md:155-160`), Pin 1 supplies **`+3V3`** (requiring a `3.3 V`-compatible HC-SR04+/RCWL-1601 module or onboard divider). During Milestone 10 physical qualification, `GPIO 26` Echo peak voltage was verified on-bench at **`3.32 V`** before live ranging (`docs/validation/M10_QUALIFICATION_MATRIX.md:71`).
   - **WARNING:** Never connect a standard `5 V`-powered HC-SR04 `ECHO` pin directly to `GPIO 26` without a resistive divider (e.g., `1 kOhm` series / `2 kOhm` to `GND`). Note also that `firmware/main/sensors/nexus_hcsr04.c:18-22` compiles `s_live_hw_enabled = true` on `ESP_PLATFORM` by default (diverging from the comment in `nexus_hcsr04.h:21-22`).
2. **ESP32 Strapping Pins (`GPIO 12`, `GPIO 2`, `GPIO 15`, `GPIO 5`):**
   - `GPIO 12` (`MTDI`, wired to `LED3` / `L293D 3A`): Determines VDD_SDIO flash voltage at reset (`LOW` = `3.3 V` flash). Do **not** attach external pull-ups holding `GPIO 12` `HIGH` during reset, or SPI flash boot will fail.
   - `GPIO 2` (`CD4051 Select B`) and `GPIO 15` (`Buzzer Q2 base`): Boot strapping pins; firmware configures pull-downs/LOW outputs after boot (`nexus_cd4051.c:61`, `nexus_command_dispatcher.c:90`).
3. **`L293D` H-Bridge Shared-Bus Lock (`GPIO 22`):**
   - `LED1..LED4` (`GPIO 27, 14, 12, 13`) are wired in parallel with `L293D` (`IC4`) motor direction inputs `1A..4A`. Firmware drives `GPIO 22` (`1,2EN` & `3,4EN`) strictly `LOW` (`0`) at boot and on every `ACTUATE LED` call (`nexus_command_dispatcher.c:68-70, 539`) so LED toggling can never energize motor outputs.
4. **Input-Only Pins (`GPIO 34, 35, 36, 39`):**
   - Lack internal pull-up/pull-down resistors and output drivers on ESP32 silicon. `GPIO 34` (`MOC7811`) relies on external `10 kOhm` pull-up `R7` (`nexus_moc7811.c:26-29` explicitly sets `pull_up_en = DISABLE`), and `GPIO 35` (`LDR`) / `GPIO 36` (`CD4051 OUT`) are analog inputs on `ADC_UNIT_1`.
5. **UART0 Console Pin Conflicts (`GPIO 1` & `GPIO 3`):**
   - `GPIO 1` (`U0TXD`) is shared on the PCB with `TSOP1838` IR receiver output; `GPIO 3` (`U0RXD`) is shared with `PC817` relay optocoupler input (`K1` relay is unpopulated). Firmware reserves both pins exclusively for `UART0` (`115200` baud JSON + `ESP_LOG*` output and Serial command RX).
6. **Wi-Fi vs ADC Coexistence:**
   - All analog measurements (`GPIO 35` = `ADC1_CH7`, `GPIO 36` = `ADC1_CH0`) use **`ADC_UNIT_1`**, avoiding ESP32 `ADC_UNIT_2` hardware contention with the Wi-Fi radio (`nexus_adc.c:17-34`).

---

## 2. Authoritative GPIO Pin Map

Reconciled across `firmware/main/**` (primary truth), `docs/validation/M10_QUALIFICATION_MATRIX.md` (physical PCB inspection), and `docs/SPEC_SHEET.md`:

| ESP32 Pin | Direction / Mode | EDU_ROBO V14 Net (`SPEC_SHEET.md`) | Firmware Module & Symbol | Active Runtime Role & Physical PCB Truth |
| :--- | :--- | :--- | :--- | :--- |
| `GPIO 1` (`U0TXD`) | UART0 TX | `TSOP1838` IR Receiver *(conflict)* | `nexus_serial_transport.c:75` (`stdout`) | **Active:** Serial JSON TX + `ESP_LOG*` (`115200 8N1`). IR driver barred |
| `GPIO 2` | GPIO Out (Pull-down) | `IC3 CD4051` Select `B` (`Pin 10`) | `nexus_cd4051.c:55-64` (`pin_b`) | **Active:** Multiplexer address bit `B` (`(ch >> 1) & 1`) |
| `GPIO 3` (`U0RXD`) | UART0 RX | `PC817` -> `Q3` -> Relay `K1` *(unmounted)* | `nexus_connection_manager.c:51` (`stdin`) | **Active:** Serial JSON command RX. `ACTUATE RELAY` returns `UNSUPPORTED` |
| `GPIO 4` | GPIO Out (Pull-down) | `IC3 CD4051` Select `A` (`Pin 11`) | `nexus_cd4051.c:55-64` (`pin_a`) | **Active:** Multiplexer address bit `A` (`ch & 1`) |
| `GPIO 5` | GPIO Out (Pull-down) | `IC3 CD4051` Select `C` (`Pin 9`) | `nexus_cd4051.c:55-64` (`pin_c`) | **Active:** Multiplexer address bit `C` (`(ch >> 2) & 1`) |
| `GPIO 12` (`MTDI`) | GPIO Out | `LED3` + `L293D 3A` | `nexus_command_dispatcher.c:73` | **Active:** `ACTUATE LED` (`led_id=3`); initialized `LOW` |
| `GPIO 13` | GPIO Out | `LED4` + `L293D 4A` | `nexus_command_dispatcher.c:73` | **Active:** `ACTUATE LED` (`led_id=4`); initialized `LOW` |
| `GPIO 14` | GPIO Out | `LED2` + `L293D 2A` | `nexus_command_dispatcher.c:73` | **Active:** `ACTUATE LED` (`led_id=2`); initialized `LOW` |
| `GPIO 15` | GPIO Out | `BZ1` Piezo Buzzer (`Q2 BC547`) | `nexus_command_dispatcher.c:90` | **Active:** `ACTUATE BUZZER` (`0..5000 ms` `esp_timer` auto-off) |
| `GPIO 16` | Unconfigured | `74HC595 SRCLK` / `LCD` / `UART2 RX` | *(None — stubbed)* | **Unconfigured:** `74HC595` soldered, `16x2 LCD` unpopulated; `ACTUATE SHIFT_REGISTER` is a no-op |
| `GPIO 17` | Unconfigured | `74HC595 RCLK` / `LCD` / `UART2 TX` | *(None — stubbed)* | **Unconfigured:** See `GPIO 16` |
| `GPIO 18` | Unconfigured | Touch Sensor Header (`TOUCH1`) | *(None)* | **Unmounted:** Listed in `GET CAPABILITIES` `"unmounted"` |
| `GPIO 19` | GPIO I/O Open-Drain + Pull-up | `DHT11` Data (`R5` `10 kOhm` pull-up) | `nexus_dht11.c:69-77` | **Active:** 1-wire Temp/Humidity (`0.5 Hz` via `"nexus_dht11"` worker task) |
| `GPIO 21` | Unconfigured | `74HC595 SER` (`Pin 14`) | *(None — stubbed)* | **Unconfigured:** See `GPIO 16` |
| `GPIO 22` | GPIO Out (Locked `0`) | `IC4 L293D` Enable (`1,2EN` & `3,4EN`) | `nexus_command_dispatcher.c:68, 539` | **Safety Lock:** Forced `LOW` (`0`) at init and on every `ACTUATE LED` |
| `GPIO 23` | Unconfigured | Vibration Header (`VIB1`) | *(None)* | **Unmounted.** *(Note: `SPEC_SHEET.md:73` erroneously comments `"Also Ultrasonic Echo pin"`; actual Echo is `GPIO 26` per `SPEC_SHEET.md:75, 157, 220` and `nexus_sensors.c:71`.)* |
| `GPIO 25` | GPIO Out | `ULTRA` Header `TRIG` (shared `BMP180 SDA`) | `nexus_hcsr04.c:45-53` (`pin_trig`) | **Active:** `10 us` ultrasonic trigger pulse (`1 Hz`) |
| `GPIO 26` | GPIO In | `ULTRA` Header `ECHO` (shared `BMP180 SCL`) | `nexus_hcsr04.c:55-63` (`pin_echo`) | **Active:** Ultrasonic echo pulse width (`1 Hz`, `3.32 V` verified) |
| `GPIO 27` | GPIO Out | `LED1` + `L293D 1A` | `nexus_command_dispatcher.c:73` | **Active:** `ACTUATE LED` (`led_id=1`); initialized `LOW` |
| `GPIO 32` | Unconfigured | Sound Sensor Header (`MIC1`) | *(None)* | **Unmounted** |
| `GPIO 33` | Unconfigured | Servo PWM Header (`SERVO1`) | *(None)* | **Unmounted** (`ACTUATE SERVO` returns `UNSUPPORTED`) *(Note: `test_milestone9_host.c:98` uses `33` only as a host-mock dummy pin for MOC7811; real firmware uses `GPIO 34` at `nexus_sensors.c:64`.)* |
| `GPIO 34` (`GPI`) | GPIO In (No Pulls) | `MOC7811` Optical Slot (`R7` `10 kOhm`) | `nexus_moc7811.c:23-31` | **Active:** Optical beam state (`0`=clear, `1`=blocked, `1 Hz`) |
| `GPIO 35` (`ADC1_CH7`) | Analog In (`12 dB`) | `LDR` Photoresistor (`R6` `10 kOhm`) | `nexus_adc_ldr.c:21-32` | **Active:** Ambient light raw 12-bit ADC (`0..4095`, `2 Hz`) |
| `GPIO 36` (`ADC1_CH0`) | Analog In (`12 dB`) | `IC3 CD4051` Common `OUT` (`Pin 3`) | `nexus_cd4051.c:66-73` | **Active:** Multiplexed analog input (`X0`, `X1` @ `1 Hz`) |
| `GPIO 39` (`ADC1_CH3`) | Unconfigured | `LM35` Analog Temp Header | *(None)* | **Unmounted** |

---

## 3. Sensor & Peripheral Driver Specifications

### 3.1 ADC Subsystem (`nexus_adc.c`) & LDR (`nexus_adc_ldr.c`)
- **Configuration:** `adc_oneshot_new_unit` on `ADC_UNIT_1`, `ADC_BITWIDTH_DEFAULT` (12-bit, `0..4095`), `ADC_ATTEN_DB_12` (~`0..3.1 V` linear range on ESP32 silicon).
- **Calibration Status (`Implemented` — Raw Counts Only):** `esp_adc/adc_cali.h` curve-fitting/line-fitting is **not** instantiated (`nexus_adc.c:17-34`). Telemetry reports honest raw 12-bit counts (`ldr`, `x0`, `x1`), avoiding fabricated lux or gas ppm values.
- **LDR (`ID 1` `"ldr"`, `GPIO 35`):** Sampled every `500 ms` (`ldr_acq`, budget `10 ms`). `processed_value = (raw * 100) / 4095` (`0..100%` internal), while outbound `"telem"` publishes raw `ldr` (`0..4095`).

### 3.2 `CD4051` 8-Channel Analog Multiplexer (`nexus_cd4051.c`)
- **Select Truth Table (`C = GPIO5`, `B = GPIO2`, `A = GPIO4` -> `OUT = GPIO36`):**

| Channel | `C` (`IO5`) | `B` (`IO2`) | `A` (`IO4`) | EDU_ROBO V14 Net (`SPEC_SHEET.md:109-120`) | Physical & Firmware Status |
| :---: | :---: | :---: | :---: | :--- | :--- |
| `X0` (`0`) | `0` | `0` | `0` | `IR-GAS1` Header (**HW-870** module) | **Mounted & Polled (`1 Hz`)** -> `"x0"` (`ID 4` `"hw870_x0"`) |
| `X1` (`1`) | `0` | `0` | `1` | `IC2` Hall Effect Sensor footprint | **PCB Unpopulated (`IC2` missing)**, **still polled (`1 Hz`)** -> floating `"x1"` (`ID 5` `"hall_x1"`) |
| `X2` (`2`) | `0` | `1` | `0` | Soil Moisture Header | Unmounted; not polled in `acquire_all()` |
| `X3` (`3`) | `0` | `1` | `1` | Rain Drop Header | Unmounted; not polled |
| `X4..X6` (`4..6`) | `1` | `0/1` | `0/1` | Line Follower IR (`L`, `C`, `R`) | Unmounted; not polled |
| `X7` (`7`) | `1` | `1` | `1` | Potentiometer `RV1` (`NOT PRESENT`) | Unpopulated; not polled |

- **Switching Timing:** After driving `GPIO 4/2/5`, firmware delays `NEXUS_CD4051_SETTLE_US = 20U` (`esp_rom_delay_us(20)`, `nexus_cd4051.c:108`) before triggering `adc_oneshot_read()` on `ADC1_CH0`.
- **`IC2` Documentation-vs-PCB Discrepancy:** `docs/SPEC_SHEET.md:9, 50, 91` lists `IC2 Hall Sensor` as `SOLDERED`, whereas physical inspection in `docs/validation/M10_QUALIFICATION_MATRIX.md:11, 26, 82` confirmed `IC2` is **unpopulated**. Firmware still reads `X1` and emits floating mux capacitance (`~0..2029` counts) in `"telem"`, while Mission Control (`app.js:716`) overrides the UI display to `NOT INSTALLED` and AI tools annotate `x1_raw` as unpopulated.

### 3.3 `DHT11` Temperature & Humidity Sensor (`nexus_dht11.c`)
- **Async Offload Architecture:** Because DHT11's start signal requires pulling `GPIO 19` `LOW` for `>= 18 ms` (`vTaskDelay(pdMS_TO_TICKS(20) + 1)` = `20..30 ms`), executing inline would violate the `10 ms` `CLASS_1` job budget. `"nexus_dht11"` (`2048 B` stack, Priority `2`) runs the bus transaction asynchronously every `2000 ms` (`NEXUS_DHT11_INTERVAL_MS`), publishing `(temp_c, hum_pct, status)` under `s_dht11_spinlock` for `dht11_acq` (`ID 2` & `ID 3`) to snapshot in `< 50 us`.
- **Protocol & Error Classification:** `30 us` pull-up wait -> `120 us` × 3 response handshake -> 40 bits measured under `portENTER_CRITICAL` (`LOW <= 80 us`, `HIGH <= 95 us`, `'1'` when `HIGH > 45 us`) -> checksum `((d0 + d1 + d2 + d3) & 0xFF) == d4`. Classifies `TIMEOUT_RESPONSE`, `TIMEOUT_DATA`, and `CHECKSUM` errors (`nexus_dht11.c:145-248`); when invalid, `"telem"` sets `"dht_valid": false` and omits `"temp"` and `"hum"`.

### 3.4 `MOC7811` Slotted Opto-Isolator (`nexus_moc7811.c`)
- Reads `gpio_get_level(GPIO_NUM_34)` every `1000 ms` (`ID 6` `"moc7811"`): `0` = optical slot clear (`BEAM CLEAR`), `1` = beam interrupted (`BLOCKED`).

### 3.5 `HC-SR04` Ultrasonic Distance Sensor (`nexus_hcsr04.c`)
- **Timing & Scaling:** Drives `GPIO 25` `LOW` (`4 us`), `HIGH` (`10 us`), `LOW`, then busy-waits on `GPIO 26` for rising edge and falling edge; computes integer/float `dist_cm = echo_us / 58U` (`nexus_hcsr04.c:101-107`, valid math range `116..23320 us` = `2..400 cm`).
- **Critical Range-Cap Limitation (`Implemented` Bug):** `NEXUS_HCSR04_DEFAULT_TIMEOUT_US` (`nexus_hcsr04.h:16`) is `8000U` (`8 ms`), capping the physical Echo pulse wait (`nexus_hcsr04.c:239`) to **`8000 / 58 = 137 cm`** (so targets at `1.38..4.0 m` time out and omit `"dist"`). Wait-rise (`8 ms`) + wait-fall (`8 ms`) can spin `"nexus_exec"` for up to `16 ms` (`< 20 ms` deadline).

---

## 4. Sensor & Peripheral Support Matrix

| Sensor / Module | Firmware Support | Physical Mounting | Transport / Reporting Support | Test Evidence | Current Status | Remaining Work |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **LDR Photoresistor** (`GPIO 35`, `ADC1_CH7`) | `nexus_adc_ldr.c` (`ID 1`, `500 ms` job) | **Soldered** (`LDR1` + `R6` `10 kOhm`) | `"telem"` key `"ldr"`, InfluxDB `nexus_telem.ldr_raw`, Grafana Panel 5, UI card, `DISPLAY LIGHT` | Host `test_milestone3_host.c`; Hardware excitation `docs/validation/m10_b1_ldr.log` (`2411 -> 4095 -> 629`) | **Verified** | Add `esp_adc_cali` mV calibration if calibrated lux/voltage is required |
| **HW-870 IR/Gas Analog** (`CD4051 X0` -> `GPIO 36`) | `nexus_cd4051.c` (`ID 4`, `1000 ms` job, `20 us` settle) | **Header-mounted** on `IR-GAS1` | `"telem"` key `"x0"`, InfluxDB `nexus_telem.x0_raw`, Grafana Panel 6, UI card, `DISPLAY ANALOG` | Host `test_milestone3_host.c`; Hardware excitation `docs/validation/m10_b2_ir_x0.log` (`2731 -> 125`) | **Verified** | Keep reported strictly as raw ADC counts unless sensor-specific gas calibration is added |
| **DHT11 Temp & Humidity** (`GPIO 19`) | `nexus_dht11.c` (`ID 2, 3`, async worker task @ `2000 ms`) | **Header-mounted** (`R5` `10 kOhm` pull-up) | `"telem"` keys `"temp"`, `"hum"`, `"dht_valid"` (omits temp/hum on invalid), Grafana Panels 1–3, UI cards, `DISPLAY ENVIRONMENT` | Host `test_milestone3_host.c`; 30-min soak `89.09%` valid (`soak_qualification_run2_report.md`); `m10_b4_dht11.log` (`29->32 °C`, `50->95 %`) | **Verified** | Optional: parse fractional byte `data[3]` or upgrade sensor to DHT22/SHT3x for higher accuracy |
| **MOC7811 Optical Slot** (`GPIO 34`) | `nexus_moc7811.c` (`ID 6`, `1000 ms` job) | **Soldered** (`R7` `10 kOhm` pull-up) | `"telem"` key `"slot"`, InfluxDB `nexus_telem.slot_state`, Grafana Panel 10, UI card, `DISPLAY MOTION` | Host `test_milestone9_host.c`; Hardware slot block/unblock `docs/validation/m10_b3_moc7811.log` (`0 <-> 1`) | **Verified** | Optional: GPIO interrupt edge counter if high-speed RPM tachometry is needed |
| **HC-SR04 Ultrasonic** (`GPIO 25` TRIG, `GPIO 26` ECHO) | `nexus_hcsr04.c` (`ID 7`, `1000 ms` job, `8000 us` timeout) | **Header-mounted** on `ULTRA` (`3.32 V` Echo verified) | `"telem"` key `"dist"`, InfluxDB `nexus_telem.dist_cm`, Grafana Panel 11, UI card, `DISPLAY DISTANCE` | Host `test_milestone9_host.c`; Live ranging `docs/validation/m10_c_hcsr04_live.log` (`5..24 cm`) | **Partially verified** | Offload Echo capture to ESP32 `RMT`/`MCPWM` capture peripheral to support full `400 cm` (`23.3 ms`) without blocking `"nexus_exec"`, and remove 1 Hz `ESP_LOGI` spam (`nexus_hcsr04.c:259`) |
| **IC2 Hall Sensor** (`CD4051 X1` -> `GPIO 36`) | `nexus_cd4051.c` (`ID 5`, polled @ `1000 ms`) | **Unpopulated** on PCB (`M10_QUALIFICATION_MATRIX.md:11`) | Emits floating `"x1"` in `"telem"` & InfluxDB `x1_raw`; Grafana Panel 9 & UI explicitly mark `Not Installed` | Host `test_milestone9_host.c` | **Blocked** *(hardware absent)* | Either populate `IC2` on PCB or disable `X1` polling in `nexus_cd4051_acquire_all()` so floating counts are not persisted |
| **Diagnostic LEDs 1–4** (`GPIO 27, 14, 12, 13` + `GPIO 22` lock) | `nexus_command_dispatcher.c:504-552` (`ACTUATE LED`) | **Soldered** (shared with `L293D 1A..4A`) | On-demand via `ACTUATE LED` (`0x0D02`) -> `"resp"`; UI Quick Actuation buttons | Host `test_milestone9_host.c`; Live matrix `docs/validation/command_matrix_results.json` | **Verified** | Maintain `GPIO 22 = 0` motor inhibit invariant |
| **Piezo Buzzer `BZ1`** (`GPIO 15` via `Q2`) | `nexus_command_dispatcher.c:554-582` (`ACTUATE BUZZER` + `esp_timer`) | **Soldered** | On-demand via `ACTUATE BUZZER` (`0x0D05`, `duration_ms` `10..5000` in Python / `0..5000` in C) | Host `test_milestone9_host.c`; Live matrix `command_matrix_results.json` | **Verified** | Fix `app.js:900` (`durationMs \|\| 200`) and `command_registry.py` `min_value=0` so UI "Off" button sends `0 ms` instead of `200 ms` |
| **74HC595 Shift Register** (`GPIO 21, 16, 17`) | **Stub only** (`nexus_command_dispatcher.c:584-588` returns `code=0` no-op) | `74HC595` **Soldered**, `16x2 LCD` **Unpopulated** | `ACTUATE SHIFT_REGISTER` (`0x0D06`) returns `"shifted":true` without toggling GPIOs | Protocol ack only (`command_matrix_results.json`) | **Planned** *(stubbed)* | Implement GPIO shift-out driver or mark `is_supported = false` until `LCD` is populated |
| **L293D DC Motors, Relay `K1`, Servo** (`GPIO 22, 3, 33`) | Explicitly blocked (`is_supported = false`, `GPIO 22 = 0`) | `L293D` soldered (no motors); `K1` unpopulated (`GPIO 3` = `UART0 RX`); Servo unmounted | `ACTUATE {MOTOR, RELAY, SERVO}` truthfully return `code=3 UNSUPPORTED` | `test_milestone8_host.c`, `command_matrix_results.json` | **Blocked** *(by hardware/pin conflict)* | Keep disabled on EDU_ROBO V14 |
| **Unpopulated Expansion Headers** (`Touch IO18`, `Vib IO23`, `Sound IO32`, `LM35 IO39`, `Mux X2..X7`) | Listed in `GET CAPABILITIES` `"unmounted"`; no drivers | **Unmounted** | Reported in `/api/sensors` & Mission Control Hardware Inventory | `test_server.py`, `validate_reference_manual.py` | **Planned** | Attach modules + register drivers in `nexus_sensors.c` (1 free slot remains in `NEXUS_SENSOR_REGISTRY_MAX = 8`) |

---

## 5. Bench Assembly & Hardware Qualification Reproduction

1. **Pre-Power Visual & Multimeter Check:**
   - Confirm `DHT11`, `HW-870` (`IR-GAS1`), and `HC-SR04` (`ULTRA`) modules match header polarity (`VCC`, `GND`, signal pins) per `docs/SPEC_SHEET.md`.
   - Confirm nothing pulls `GPIO 12` (`LED3`) `HIGH` at power-on.
   - Verify `HC-SR04` `ECHO` (`GPIO 26`) never exceeds `3.3 V` (`3.32 V` measured on EDU_ROBO V14 `+3V3` header).
2. **USB Connection & Linux Permissions:**
   - Connect USB Micro-B/Type-C cable from EDU_ROBO V14 UART0 bridge to laptop (`/dev/ttyUSB0`). Ensure user belongs to `dialout`/`uucp` (`groups $USER`).
3. **Passive Stimulus Verification (Without Resetting Target):**
   - Start Ground Station (`./scripts/nexus-demo-start.sh`) or inspect Mission Control (`http://127.0.0.1:8000`):
     - **LDR (`ldr`):** Shine flashlight -> approaches `4000+`; cover LDR -> drops `< 800` (ref: `docs/validation/m10_b1_ldr.log`).
     - **HW-870 (`x0`):** Place reflective surface in front of IR emitter/detector -> `x0` drops sharply from `~2700` toward `~125` (ref: `m10_b2_ir_x0.log`).
     - **MOC7811 (`slot`):** Insert card into optical U-slot -> transitions `0` (`CLEAR`) -> `1` (`BLOCKED`) within `2 s` (ref: `m10_b3_moc7811.log`).
     - **DHT11 (`temp`, `hum`):** Apply gentle warm breath near sensor -> `hum` rises toward `80-95%` and `temp` increments `1-3 °C` with `dht_valid: true` (ref: `m10_b4_dht11.log`).
     - **HC-SR04 (`dist`):** Hold flat target `5..100 cm` perpendicular to transducers -> `dist` tracks target distance within `2..137 cm` (ref: `m10_c_hcsr04_live.log`).

