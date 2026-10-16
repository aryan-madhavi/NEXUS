NEXUS - Networked Environmental eXecutive with Unified Sensing

Project specification: [`docs/PROJECT_BLUEPRINT.md`](docs/PROJECT_BLUEPRINT.md)  
Milestone documentation & technical records: [`docs/milestones/README.md`](docs/milestones/README.md)

The firmware is developed in modular milestones. Milestone 1 (Bootstrap), Milestone 2 (Executive & Data Structures), Milestone 3 (Sensors), and Milestone 3.1 (Timing Contract Correction & Baseline) are fully implemented, verified, and accepted. Milestone 4 (Unified Connection Manager & Transports) source remediation and FreeRTOS worker lifecycle fixes are verified with 24/24 passing host test groups and a clean ESP-IDF v6.0.1 build, ready for physical hardware validation.

Target: classic ESP32 (`idf.py set-target esp32`), ESP-IDF v6.0.1 + FreeRTOS. The EDU_ROBO V14 reference sheet ([`docs/SPEC_SHEET.md`](docs/SPEC_SHEET.md)) is the pin-map authority; verify hardware conflicts and electrical limits before enabling sensors.
