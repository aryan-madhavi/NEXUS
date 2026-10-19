NEXUS - Networked Environmental eXecutive with Unified Sensing

Project specification: [`docs/PROJECT_BLUEPRINT.md`](docs/PROJECT_BLUEPRINT.md)  
Milestone documentation & technical records: [`docs/milestones/README.md`](docs/milestones/README.md)

The system is developed across modular, rigorously qualified milestones. Milestone 1 (Bootstrap), Milestone 2 (Executive & Data Structures), Milestone 3 (Sensors), Milestone 3.1 (Timing Contract Correction & Baseline), and Milestone 4 (Unified Connection Manager & Transports, qualified via a 30-minute continuous physical hardware soak) are fully verified and signed off. Milestone 5 (Python Ground Station, InfluxDB Time-Series Persistence, and Grafana Observability) is complete and accepted. Milestone 6 (Secure Wi-Fi/MQTT Transport, Broker Authentication, Topic ACLs, and Dual-Link Hardware Validation) is complete and accepted, backed by 15 host test groups, broker ACL verification, and live telemetry on physical ESP32 hardware. Milestone 6.3 (Bidirectional Command Execution & Registry) is next.

Target: classic ESP32 (`idf.py set-target esp32`), ESP-IDF v6.0.1 + FreeRTOS. The EDU_ROBO V14 reference sheet ([`docs/SPEC_SHEET.md`](docs/SPEC_SHEET.md)) is the pin-map authority; verify hardware conflicts and electrical limits before enabling sensors.
