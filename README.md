NEXUS - Networked Environmental eXecutive with Unified Sensing

Project specification: [`docs/PROJECT_BLUEPRINT.md`](docs/PROJECT_BLUEPRINT.md)  
Command & Data Reference Manual: [`docs/COMMAND_REFERENCE.md`](docs/COMMAND_REFERENCE.md)  
Milestone documentation & technical records: [`docs/milestones/README.md`](docs/milestones/README.md)  
System Qualification & Closure Report: [`docs/validation/system_qualification_and_closure_report_20261025.md`](docs/validation/system_qualification_and_closure_report_20261025.md)

NEXUS Mission Control is accessible locally at `http://127.0.0.1:8000`, featuring:
- **Tab 1 (Dashboard):** Live sensor cards, UTC operational clocks, and transport health ribbon.
- **Tab 2 (Command Builder):** Dual-transport command execution with safety confirmation modals.
- **Tab 3 (Telemetry Stream):** Real-time JSON/raw telemetry frame inspector.
- **Tab 4 (Incidents):** Active monitoring alerts and incident acknowledgement workflows.
- **Tab 5 (Services):** Runtime service availability and InfluxDB/Mosquitto/AI connectivity.
- **Tab 6 (Reference Manual):** Interactive 115-command catalog, 27-parameter dictionary with expandable individual value mappings, sensor registries, and protocol specifications.

The system is developed across modular, rigorously qualified milestones:
- **Milestones 1–4**: Native ESP-IDF v6.0.1 bootstrap, application-level cooperative cyclic executive (`nexus_exec`, 100 ms tick), bounded static data structures (`nexus_job_table`, `nexus_ready_queue`, `nexus_event_queue`, `nexus_ring_buffer`), initial physical sensor drivers, timing contract quantization baseline, and Unified Connection Manager (qualified via a 30-minute continuous physical hardware soak).
- **Milestones 5–6**: Python Ground Station (`NexusHostManager`), InfluxDB 2.x time-series persistence, Grafana v11.5.0 observability, and authenticated Wi-Fi/MQTT dual-transport ingestion with Mosquitto ACL enforcement.
- **Milestone 7**: Bounded read-only Telemetry Query Engine, deterministic background Incident Monitoring Service with SQLite WAL persistence, and read-only Conversational AI Assistant (`mistral:7b` via Ollama + deterministic fallback router + Open WebUI tools).
- **Milestone 8**: Authoritative 115-command Verb–Noun Registry, firmware zero-allocation Command Dispatcher (`nexus/nexus_esp32/cmd` -> `nexus/nexus_esp32/resp`), and allowlisted Ground Station Application Launcher (`OPEN DASHBOARD`, `OPEN LOGS`, `OPEN AI`, `OPEN GROUND`).
- **Milestones 9–10 (`v0.9.0-rc1`)**: Extended sensor suite integration and full physical hardware excitation qualification ([`docs/validation/M10_QUALIFICATION_MATRIX.md`](docs/validation/M10_QUALIFICATION_MATRIX.md)) across LDR (`GPIO35`), DHT11 (`GPIO19`), HW-870 (`CD4051 X0 -> GPIO36`), MOC7811 (`GPIO34`), and HC-SR04 (`GPIO25`/`GPIO26`), with documented hardware BOM findings (`IC2` Hall sensor unpopulated on EDU_ROBO V14 PCB; `TSOP1838` on `GPIO1` blocked by UART0 TX conflict).

Target: classic ESP32 (`idf.py set-target esp32`), ESP-IDF v6.0.1 + FreeRTOS. The EDU_ROBO V14 reference sheet ([`docs/SPEC_SHEET.md`](docs/SPEC_SHEET.md)) is the pin-map authority; verify hardware conflicts and electrical limits before enabling sensors.

