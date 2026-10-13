Go-Green Technologies Pvt. Ltd. — GSTN: 27AABCY4791J1ZS — V14 / Lab Manual V4

# EDU_ROBO IoT Trainer Kit — ESP32 Reference Spec Sheet

AI-agent reference · All pin assignments, components, and operational parameters for the ESP32-WROOM-32 DevKit V1 (30-pin) platform

✔ Soldered on PCB

R1–R13 (all resistors) · D1, D3 (diodes) · Q3 (BC547) · 7805 · LD117AS33TR · 74HC595 · CD4051 · L293D · PC817 · IC2 (Hall) · LDR · TSOP1838 · Buzzer · MOC7811 · LED1–LED5 · ESP32 DevKit · Push switch · Female burg headers · Power jack (J1)

⬡ Header-Mounted (plug-in modules)

HC-SR04 Ultrasonic — ULTRA connector (IO25/IO26)\
DHT-11 Temp/Humidity — DHT-11 connector (IO19)\
HW-870 IR/Gas Sensor — IR-GAS1 connector (MUX X0)

✗ Not Present on This Build

C1–C3 (caps) · DC Motors · Relay (K1) · 16×2 LCD · Motor clamps · Power connectors · USB cable · Battery connector · 5-pin motor connector · Dummy wheel · BO tyres · 10k Potentiometer · Plastic box · Jumper wires

## Board Identity & Power

Microcontroller

- MCUESP32-WROOM-32 DevKit V1 (30-pin)
- Board name (Arduino IDE)DOIT ESP32DEVKIT-V1
- Wi-Fi / BTYes (built-in)
- Signal voltage max3.3 V (no negatives)
- Max current per pin10 mA
- Programming keyHold BOOT, release after upload
- ResetRESET switch
- USB portMicro USB Type-B

Power Rails

- Input+12 V DC (board supply)
- Regulated +5 Vvia 7805 TO-92
- Regulated +3.3 Vvia LD117AS33TR
- ESP32 / LCD powerUSB (isolated from DC supply)
- Onboard power to ESP322-pin jumper option
- Power indicator+5 V LED (Push-to-ON switch)
- Reverse polarity protection1N4004 diode (D3) at jack

Key ICs on Board

- Shift register (LCD/74HC595)74HC595-SO16
- Analog muxCD4051-SO16
- Motor driverL293D
- Opto-isolator (relay)PC817
- Hall effect ICIC2 (on-board)
- 5 V regulator7805 TO-92
- 3.3 V regulatorLD117AS33TR

## ESP32 GPIO Pin Map — Full Reference

| GPIO | Connected Device / Function | Notes |
| --- | --- | --- |
| GPIO 1 | TV IR Receiver (TSOP1838) | Input only |
| GPIO 2 | CD4051 Select Line B | Mux control |
| GPIO 3 | Relay | via PC817 opto → BC547 → G5LE relay |
| GPIO 4 | CD4051 Select Line A | Mux control |
| GPIO 5 | CD4051 Select Line C | Mux control |
| GPIO 12 | LED-3 & L293D Motor Driver 3A | Shared with motor / LED3 |
| GPIO 13 | LED-4 & L293D Motor Driver 4A | Shared with motor / LED4 |
| GPIO 14 | LED-2 & L293D Motor Driver 2A | Shared with motor / LED2 |
| GPIO 15 | Buzzer | 5 V buzzer (BUZ) |
| GPIO 16 | GSM-GPS Module & 74HC595 SCK | UART2 RXD / shift reg clock |
| GPIO 17 | GSM-GPS Module & 74HC595 SER | UART2 TXD / shift reg data |
| GPIO 18 | Touch Sensor | VSPI_CLK capable |
| GPIO 19 | DHT-11 Sensor | Temp & humidity |
| GPIO 21 | 74HC595 RCK & LCD Enable | SDA capable; latch for shift reg |
| GPIO 22 | L293D Motor Driver EN (Enable) | Both 1-2EN and 3-4EN tied to IO22 |
| GPIO 23 | Vibration Sensor / BMP180 SDA | Also Ultrasonic Echo pin |
| GPIO 25 | BMP180 SDA & Ultrasonic Trigger | DAC_1 capable |
| GPIO 26 | BMP180 SCL & Ultrasonic Echo | DAC_2 capable |
| GPIO 27 | LED-1 & L293D Motor Driver 1A | Shared with motor / LED1 |
| GPIO 32 | Sound Sensor | ADC1 capable |
| GPIO 33 | Servo Motor | PWM output |
| GPIO 34 | Optocoupler (MOC7811) | Input only (no internal pull-up) |
| GPIO 35 | LDR Sensor | Input only; ADC1 |
| GPIO 36 | CD4051 Multiplexer Output (ADO) | Input only; SENSOR_VP |
| GPIO 39 | LM35 Temperature Sensor | Input only; SENSOR_VN |

## CD4051 Analog Multiplexer — Channel Map

Channel → Sensor Assignment

| Channel | Connected Sensor |
| --- | --- |
| X0 | ADXL-335 (X-axis) / GAS-1 / IR-1 |
| X1 | ADXL-335 (Y-axis) / Hall Sensor / GAS-2 / IR-2 |
| X2 | ADXL-335 (Z-axis) / Moisture Sensor |
| X3 | Water Level / Rain Sensor |
| X4 | IR Line Tracker-1 |
| X5 | IR Line Tracker-2 / Sharp IR |
| X6 | IR Line Tracker-3 |
| X7 | Variable Potentiometer (10k) |

Control Lines & Output

- Select AGPIO 4
- Select BGPIO 2
- Select CGPIO 5
- Output (X pin)GPIO 36 (ADO / IO-36)
- VCC+3.3 V
- VEE / GNDGND
- INH (Inhibit)GND (always enabled)

Channel Selection Truth Table

| C (IO5) | B (IO2) | A (IO4) | Selected Channel |
| --- | --- | --- | --- |
| 0 | 0 | 0 | X0 |
| 0 | 0 | 1 | X1 |
| 0 | 1 | 0 | X2 |
| 0 | 1 | 1 | X3 |
| 1 | 0 | 0 | X4 |
| 1 | 0 | 1 | X5 |
| 1 | 1 | 0 | X6 |
| 1 | 1 | 1 | X7 |

## Subsystem Pin Summary

L293D Motor Driver

- Enable (EN / 1-2EN / 3-4EN)GPIO 22
- 1A (Motor 1, direction)GPIO 27
- 2A (Motor 2, direction)GPIO 14
- 3A (Motor 3, direction)GPIO 12
- 4A (Motor 4, direction)GPIO 13
- VCC1+3.3 V (logic)
- VCC2+5 V (motor supply)
- Motor connectorSHS-05 Male & Female (5-pin)

LCD (16×2) via 74HC595

- 74HC595 SER (data)GPIO 17
- 74HC595 SCK (clock)GPIO 16
- 74HC595 RCK (latch) / LCD EGPIO 21
- LCD RSQC of 74HC595
- LCD DB4–DB7QD–QG of 74HC595
- LCD VCC+3.3 V
- Contrast (R10)2.2 kΩ to GND
- Arduino var D1=IO21, D2=IO16, D3=IO17—

Relay Interface

- GPIOGPIO 3
- Drive chainGPIO 3 → PC817 → BC547 (Q3) → G5LE relay
- Relay type5VT73 / G5LE, 5 V DC coil
- Relay contactsX3-1 (NO), X3-2 (P/COM), X3-3 (NC)
- Flyback diode1N400x (D1) across coil

Ultrasonic (HC-SR04)

- TriggerGPIO 25
- EchoGPIO 26
- VCC+3.3 V (connector)

BMP180 Pressure Sensor

- SDAGPIO 25
- SCLGPIO 26
- NoteShares pins with Ultrasonic — use one at a time

LEDs & Buzzer

- LED1GPIO 27
- LED2GPIO 14
- LED3GPIO 12
- LED4GPIO 13
- LED typeSMD 1206 (onboard) / 5MM LED (LED5)
- LED series resistors330 Ω (R2–R5)
- BuzzerGPIO 15 (5 V, active)

Servo Motor

- Primary pinGPIO 33 (PWM)
- Alternate (DHT pin)GPIO 19
- Connector wiringBrown=GND, Red=+5V, Orange=Signal
- LibraryServoESP32

Stepper Motor

- Coil pinsGPIO 27 (1A), 14 (2A), 12 (3A), 13 (4A)
- +5 V coil supplyRed wire

GPS / GSM Module

- TX (GPS → ESP)GPIO 16 (UART2 RXD)
- RX (ESP → GPS)GPIO 17 (UART2 TXD)
- Also shared with74HC595 SCK/SER — use one at a time
- VCC+3.3 V

Direct-Read Sensors

- DHT-11 (temp/humidity)GPIO 19
- LM35 (temperature, analog)GPIO 39
- LDR (light, analog)GPIO 35
- Sound sensorGPIO 32
- Touch sensorGPIO 18
- Vibration sensorGPIO 23
- Optocoupler (MOC7811)GPIO 34
- Hall sensorMUX X1 (read via GPIO 36)
- TSOP1838 (TV IR)GPIO 1

## Sensor Connector Pin-Out Reference

| Connector Label | Pin 1 | Pin 2 | Pin 3 | Pin 4 | ESP32 Signal |
| --- | --- | --- | --- | --- | --- |
| PRESSURE (BMP180) | +3V3 | GND | IO-25 | IO-26 | SDA=IO25, SCL=IO26 |
| ADXL-335 | GND | X23 | X13 | X03 | Z=X0, Y=X1, X=X2 via MUX |
| SOUND | +3V3 | GND | IO-32 | — | IO32 |
| SERVO | GND | +5V | IO-33 | — | IO33 (PWM) |
| LEVEL/RAIN | +5V | GND | — | X33 (MUX X3) | X3 via MUX |
| MOISTURE | +5V | GND | — | X23 (MUX X2) | X2 via MUX |
| IR-GAS1 | +5V | GND | — | X03 (MUX X0) | X0 via MUX |
| IR-GAS2 | +5V | GND | — | X13 (MUX X1) | X1 via MUX |
| TRACKER (Line follower) | X43 | X53 | X63 | +5V | X4, X5, X6 via MUX |
| ULTRA (Ultrasonic) | +3V3 | IO-25 | IO-26 | GND | TRIG=IO25, ECHO=IO26 |
| GPS | +3V3 | IO-16 | IO-17 | GND | TX=IO16, RX=IO17 |
| DHT-11 | +3V3 | IO-19 | GND | — | IO19 |
| TOUCH | GND | +3V3 | IO-18 | — | IO18 |
| VIBRATION | +3V3 | GND | IO-23 | — | IO23 |
| SHARP IR | X33 (MUX X3?) | GND | +3V3 | — | X5 via MUX |
| HALL (IC2) | VCC | GND | OUT | — | X1 via MUX |
| LM35 | +3V3 | IO-39 | GND | — | IO39 |
| MOTOR (L293D output) | +5V | Q0 | Q1 | Q2 | Q3 — motor outputs |

## Bill of Materials — V14 (Actual Build Status)

SOLDERED — permanently on PCB HEADER-MOUNTED — module plugs into female pins you soldered NOT PRESENT — not on this build

| # | Reference | Component | Value / Part Number | Status |
| --- | --- | --- | --- | --- |
| 1 | R1, R9, R12, R13 | Resistor | 1 kΩ | SOLDERED |
| 2 | R2, R3, R4, R5, R11 | Resistor | 330 Ω (LED series / opto) | SOLDERED |
| 3 | R6, R8 | Resistor | 100 Ω | SOLDERED |
| 4 | R7 | Resistor | 10 kΩ | SOLDERED |
| 5 | R10 | Resistor | 2.2 kΩ (LCD contrast) | SOLDERED |
| 6 | LED1–LED4 | SMD LED | SMD 1206 | SOLDERED |
| 7 | LED5 | Through-hole LED (power indicator) | 5 mm LED | SOLDERED |
| 8 | C1, C2, C3 | Capacitor | 0.1 µF | NOT PRESENT |
| 9 | D1, D3 | Diode | 1N 4004 | SOLDERED |
| 10 | Q3 | NPN Transistor | BC 547 | SOLDERED |
| 11 | 7805 | 5 V Regulator | 7805 TO-92 | SOLDERED |
| 12 | LD117 | 3.3 V Regulator | LD117AS33TR | SOLDERED |
| 13 | 74HC595 | Shift Register | 74HC595-SO16 | SOLDERED |
| 14 | CD4051 | Analog Multiplexer | CD4051-SO16 | SOLDERED |
| 15 | L293D | Motor Driver IC | L293D | SOLDERED |
| 16 | PC817 | Opto-isolator (relay drive) | PC817 | SOLDERED |
| 17 | IC2 | Hall Effect Sensor | On-board (X1 MUX) | SOLDERED |
| 18 | LDR | Light Sensor | LDR 3 mm | SOLDERED |
| 19 | TSOP1838 | TV IR Receiver | TSOP1838 (38 kHz) | SOLDERED |
| 20 | BUZ | Buzzer | 5 V Active Buzzer | SOLDERED |
| 21 | HC-SR04 | Ultrasonic Sensor | HC-SR04 | HEADER-MOUNTED |
| 22 | MOC7811 | Optocoupler / slot sensor | MOC7811 | SOLDERED |
| 23 | DC Motor ×2 | BO1 DC Motor | VJT389, 5 V DC | NOT PRESENT |
| 24 | K1 | Relay | 5VT73 / G5LE, 5 V DC | NOT PRESENT |
| 25 | LCD1 | 16×2 LCD Display | 16×2 LCD | NOT PRESENT |
| 26 | Motor Clamp ×2 | Motor mount | VJT303 CLAMP | NOT PRESENT |
| 27 | Power Connectors | Board connectors | 58/2C Vital, 58/3C Vital | NOT PRESENT |
| 28 | USB Cable | Programming cable | Micro USB Type-B | NOT PRESENT |
| 29 | Battery Connector | 9 V snap | Black Snap Battery Connector | NOT PRESENT |
| 30 | Motor Connector | 5-pin motor connector | SHS-05 Male & Female | NOT PRESENT |
| 31 | Dummy Wheel | Caster wheel | Dummy Wheel | NOT PRESENT |
| 32 | Tyres ×2 | BO tyre | BO Tyers | NOT PRESENT |
| 33 | VM842 | Microcontroller | ESP32-WROOM-32 DevKit V1 (30-pin) | SOLDERED |
| 34 | POT | Potentiometer | 10 kΩ 3296 | NOT PRESENT |
| 35 | DHT-11 | Temp & Humidity Sensor | DHT-11 | HEADER-MOUNTED |
| 36 | HW-870 | IR / Gas Sensor | HW-870 (IR-GAS1, MUX X0) | HEADER-MOUNTED |
| 37 | SW | Push-to-ON switch | PCB Mount PUSH ON/OFF | SOLDERED |
| 38 | Burg Strip | Headers (female pins soldered for modules) | 40×1 Male & Female | SOLDERED |
| 39 | PCB | Main board | Go-Green Double-Sided PCB | SOLDERED |
| 40 | Box | Enclosure | Plastic Box 1680 mL | NOT PRESENT |
| 41 | Wires | Jumper wires | Male-Female, Female-Female | NOT PRESENT |
| 42 | J1 | Power Jack | DC Barrel Jack | SOLDERED |

## Arduino IDE — Software Configuration

Board Setup

- Board manager URLhttps://dl.espressif.com/dl/package_esp32_index.json
- Packageesp32 by Espressif Systems
- Board selectionDOIT ESP32DEVKIT-V1
- Upload methodPress & release BOOT key during upload
- RestartRESET switch

Required Libraries

- IoT platformBlynk, ThingSpeak
- IR remoteIRremote
- Temp/humidityDHT_sensor_library
- LCDLiquidCrystal-master
- ServoServoESP32
- StepperStepper
- Tone / buzzerTone32-master
- Kit helperEduIntro
- DDS function genMD_AD9833

## Robot Assembly — Step Summary

| Step | Action | Hardware Used |
| --- | --- | --- |
| 1 | Fix motor clamps to bottom of PCB | VJT303 clamps + 10 mm screws (through PCB) |
| 2 | Insert screws through DC motors | 25 mm screws through BO1 VJT389 motor (top & bottom) |
| 3 | Attach motors to clamps | Nuts to secure DC motors to VJT303 clamps |
| 4 | Fit caster/support screws | Three 40 mm screws on bottom of PCB + nuts |
| 5 | Attach wheels & dummy wheel | BO tyres ×2, Dummy Wheel (caster) |
| 6 | Connect motor wires | SHS-05 5-pin motor connector to board MOTOR header |

## Operational Safety Rules

**⚠ Critical — Read Before Powering**

- Switch OFF DC supply before making any external wiring connections.
- Maximum GPIO signal voltage: 3.3 V. No negative signals permitted.
- Maximum current draw per GPIO pin: 10 mA.
- Verify polarity of all ICs, LEDs, diodes, and sensors before powering.
- For LCD, Stepper, DC Motor, Servo, and Relay — consult connector details in this sheet before wiring.
- ESP32 power via USB is isolated from the board's 12 V DC supply.
- If any component becomes hot or emits burning smell — cut AC mains and remove USB immediately.
- If POWER LED does not illuminate after inspection — return kit for maintenance; do not self-diagnose live.

## Quick Reference — Peripheral Tags

IO1=TSOP IO2=MUX_B IO3=RELAY IO4=MUX_A IO5=MUX_C IO12=LED3/M3A IO13=LED4/M4A IO14=LED2/M2A IO15=BUZZER IO16=595_SCK IO17=595_SER IO18=TOUCH IO19=DHT11 IO21=595_RCK/LCD_E IO22=MOTOR_EN IO23=VIBRATION IO25=ULTRA_TRIG/BMP_SDA IO26=ULTRA_ECHO/BMP_SCL IO27=LED1/M1A IO32=SOUND IO33=SERVO IO34=OPTO IO35=LDR IO36=MUX_OUT IO39=LM35 X0=ADXL-X/GAS1/IR1 X1=ADXL-Y/HALL/GAS2/IR2 X2=ADXL-Z/MOISTURE X3=LEVEL/RAIN X4=IR_TRACKER1 X5=IR_TRACKER2/SHARP X6=IR_TRACKER3 X7=POTENTIOMETER MUX_A=IO4, MUX_B=IO2, MUX_C=IO5 Max 3.3V signal Max 10mA/pin

Go-Green Technologies Pvt. Ltd. · EDU_ROBO IoT Kit · Lab Manual V4 / Component List V14 · Generated for AI-agent reference use