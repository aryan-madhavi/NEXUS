# Apollo-inspired EDU_ROBO

Project specification: [`docs/PROJECT_BLUEPRINT.md`](docs/PROJECT_BLUEPRINT.md)

The firmware scaffold is being established in stages. The first development gate is to install/activate ESP-IDF on Fedora, identify the USB serial device, and build/flash a minimal heartbeat application before adding sensor drivers.

Target: classic ESP32 (`idf.py set-target esp32`), ESP-IDF + FreeRTOS. The EDU_ROBO V14 reference sheet is the pin-map authority; verify hardware conflicts and electrical limits before enabling sensors.
