NEXUS - Networked Environmental eXecutive with Unified Sensing

Project specification: [`docs/PROJECT_BLUEPRINT.md`](docs/PROJECT_BLUEPRINT.md)  
Milestone documentation & technical records: [`docs/milestones/README.md`](docs/milestones/README.md)

The system is developed across modular, rigorously qualified milestones:
- **Milestones 1–4**: Native ESP-IDF v6.0.1 bootstrap, application-level cooperative cyclic executive (`nexus_exec`, 100 ms tick), bounded static data structures (`nexus_job_table`, `nexus_ready_queue`, `nexus_event_queue`, `nexus_ring_buffer`), initial physical sensor drivers, timing contract quantization baseline, and Unified Connection Manager (qualified via a 30-minute continuous physical hardware soak).
- **Milestones 5–6**: Python Ground Station (`NexusHostManager`), InfluxDB 2.x time-series persistence, Grafana v11.5.0 observability, and authenticated Wi-Fi/MQTT dual-transport ingestion with Mosquitto ACL enforcement.
- **Milestone 7**: Bounded read-only Telemetry Query Engine, deterministic background Incident Monitoring Service with SQLite WAL persistence, and read-only Conversational AI Assistant (`mistral:7b` via Ollama + deterministic fallback router + Open WebUI tools).
- **Milestone 8**: Canonical 52-command Verb–Noun Registry, firmware zero-allocation Command Dispatcher (`nexus/nexus_esp32/cmd` -> `nexus/nexus_esp32/resp`), and allowlisted Ground Station Application Launcher (`OPEN DASHBOARD`, `OPEN LOGS`, `OPEN AI`, `OPEN GROUND`).
- **Milestones 9–10 (`v0.9.0-rc1`)**: Extended sensor suite integration and full physical hardware excitation qualification ([`docs/validation/M10_QUALIFICATION_MATRIX.md`](docs/validation/M10_QUALIFICATION_MATRIX.md)) across LDR (`GPIO35`), DHT11 (`GPIO19`), HW-870 (`CD4051 X0 -> GPIO36`), MOC7811 (`GPIO34`), and HC-SR04 (`GPIO25`/`GPIO26`), with documented hardware BOM findings (`IC2` Hall sensor unpopulated on EDU_ROBO V14 PCB; `TSOP1838` on `GPIO1` blocked by UART0 TX conflict).

Target: classic ESP32 (`idf.py set-target esp32`), ESP-IDF v6.0.1 + FreeRTOS. The EDU_ROBO V14 reference sheet ([`docs/SPEC_SHEET.md`](docs/SPEC_SHEET.md)) is the pin-map authority; verify hardware conflicts and electrical limits before enabling sensors.
