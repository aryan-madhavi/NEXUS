# NEXUS — Clean-Machine Development & Toolchain Setup Guide

> **Document Status:** Authoritative Reproducible Setup Specification  
> **Target OS:** Linux (Ubuntu 22.04/24.04 LTS, Debian 12, Fedora 39+, Arch Linux)  
> **Firmware Target:** ESP32 (`ESP-IDF v6.0.1`, Xtensa toolchain)  
> **Ground Station Target:** Python 3.10–3.12 (Virtual Environment)  
> **Container Runtime:** Podman (recommended rootless) or Docker Engine

---

## 1. System Prerequisites & Host Dependencies

### 1.1 Linux Packages & Serial Permissions
Install core development tools, serial library support, and container engines:

```bash
# Debian / Ubuntu:
sudo apt update && sudo apt install -y \
    build-essential git cmake ninja-build python3 python3-venv python3-pip \
    libffi-dev libssl-dev curl netcat-openbsd \
    podman podman-compose  # Or: docker.io docker-compose-plugin

# Fedora:
sudo dnf install -y \
    gcc gcc-c++ git cmake ninja-build python3 python3-devel \
    curl nc podman podman-compose
```

#### USB Serial Device Permissions (`/dev/ttyUSB0`)
The onboard CP2102/CH340 USB-to-UART bridge mounts as `/dev/ttyUSB0` (or `/dev/ttyACM0`). Grant your non-root user dialout permissions:
```bash
sudo usermod -aG dialout "$USER"   # Debian/Ubuntu
# Or: sudo usermod -aG uucp "$USER" # Arch/Fedora

# Log out and back in, or activate group in current shell:
newgrp dialout
```
Verify device access without root:
```bash
ls -l /dev/ttyUSB0
# Expected: crw-rw---- 1 root dialout ... /dev/ttyUSB0
```

---

## 2. Python Virtual Environment & Ground Station Setup

NEXUS uses standard Python virtual environment tooling (`.venv`). Avoid installing packages globally.

```bash
# 1. Navigate to the repository root
cd /path/to/NEXUS

# 2. Create isolated Python virtual environment
python3 -m venv .venv

# 3. Activate environment
source .venv/bin/activate

# 4. Install all runtime and testing dependencies
pip install --upgrade pip
pip install -r ground_station/requirements.txt
```

### Dependency Audit
`ground_station/requirements.txt` contains exactly 4 packages:
- `pyserial>=3.5` (USB UART transport adapter)
- `paho-mqtt>=2.0.0` (MQTT v3.1.1 network transport adapter)
- `influxdb-client>=1.40.0` (InfluxDB v2 line protocol writer and Flux query engine)
- `pytest>=8.0.0` (Host testing framework)

*All other Ground Station modules (`http.server`, `sqlite3`, `threading`, `urllib`, `dataclasses`, `math`, `re`, `json`) use standard Python library modules.*

---

## 3. Environment Configuration (`.env` & `credentials/`)

### 3.1 Host Services Configuration (`.env`)
Copy the provided `.env.example` template to `.env`:
```bash
cp .env.example .env
chmod 600 .env
```

Edit `.env` to configure your environment:
```dotenv
# InfluxDB Configuration
INFLUXDB_VERSION=2.7.11
INFLUXDB_PORT=8086
INFLUXDB_INIT_USERNAME=nexus_admin
INFLUXDB_INIT_PASSWORD=nexus_admin_password_change_me
INFLUXDB_INIT_ORG=nexus
INFLUXDB_INIT_BUCKET=nexus_telemetry
INFLUXDB_INIT_ADMIN_TOKEN=nexus_secret_admin_token_change_me

# MQTT Broker Configuration
MOSQUITTO_VERSION=2.1.2
MQTT_PORT=1883
# CRITICAL BINDING NOTICE:
# docker-compose.yml binds both 127.0.0.1 and ${MQTT_BIND_IP:-10.12.252.18}.
# If your laptop LAN IP is not 10.12.252.18, set your actual LAN IP or 127.0.0.1:
MQTT_BIND_IP=127.0.0.1

# Grafana Configuration
GRAFANA_VERSION=11.5.0
GRAFANA_PORT=3000
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=nexus_grafana_password_change_me
GRAFANA_ANONYMOUS_ENABLED=false
```

> [!WARNING]
> **The `MQTT_BIND_IP` Multi-Interface Trap:**  
> In `docker-compose.yml` line 65, the Mosquitto broker maps ports to:
> ```yaml
> - "127.0.0.1:${MQTT_PORT:-1883}:1883"
> - "${MQTT_BIND_IP:-10.12.252.18}:${MQTT_PORT:-1883}:1883"
> ```
> If `MQTT_BIND_IP` is unset on a machine without interface `10.12.252.18`, container startup will fail with `listen tcp 10.12.252.18:1883: bind: cannot assign requested address`. Always define `MQTT_BIND_IP=127.0.0.1` (or your actual Wi-Fi/Ethernet IP) in `.env`.

### 3.2 Mosquitto Broker Authentication Files
Container Mosquitto mounts credential files read-only from `./credentials/` (`docker-compose.yml:68-70`). Ensure these files exist before starting Compose:
```bash
mkdir -p credentials
chmod 700 credentials

# 1. Mosquitto Broker Config (credentials/mosquitto.conf)
cat > credentials/mosquitto.conf << 'EOF'
listener 1883
allow_anonymous false
password_file /mosquitto/config/mosquitto.passwd
acl_file /mosquitto/config/mosquitto.acl
persistence true
persistence_location /mosquitto/data/
log_dest file /mosquitto/log/mosquitto.log
log_dest stdout
EOF

# 2. Mosquitto Passwords (credentials/mosquitto.passwd)
# Generate via: mosquitto_passwd -c credentials/mosquitto.passwd nexus_ground_station
# Or copy pre-existing baseline credentials if preserving a configured workspace.

# 3. Mosquitto ACLs (credentials/mosquitto.acl)
cat > credentials/mosquitto.acl << 'EOF'
user nexus_ground_station
topic readwrite nexus/+/telemetry
topic readwrite nexus/+/cmd
topic readwrite nexus/+/event

user nexus_esp32
topic write nexus/nexus_esp32/telemetry
topic read nexus/nexus_esp32/cmd
EOF
```

### 3.3 Firmware Wi-Fi/MQTT Configuration (`credentials/sdkconfig.local`)
`firmware/CMakeLists.txt` is configured to look for `../credentials/sdkconfig.local`. If present, it overrides default settings without dirtying tracked `firmware/sdkconfig`:
```ini
# credentials/sdkconfig.local
CONFIG_NEXUS_WIFI_SSID="Your_WiFi_SSID"
CONFIG_NEXUS_WIFI_PASSWORD="Your_WiFi_Password"
CONFIG_NEXUS_MQTT_BROKER_URI="mqtt://192.168.1.100:1883"
CONFIG_NEXUS_MQTT_CLIENT_ID="nexus_esp32"
CONFIG_NEXUS_MQTT_USERNAME="nexus_esp32"
CONFIG_NEXUS_MQTT_PASSWORD="esp32_mqtt_secret_password"
CONFIG_NEXUS_MQTT_TOPIC_PREFIX="nexus/nexus_esp32"
```

---

## 4. Container Infrastructure Provisioning

Start the background container stack (`nexus_influxdb`, `nexus_broker`, `nexus_grafana`):

```bash
# Using Podman (rootless recommended):
podman-compose up -d

# Or using Docker:
docker compose up -d
```

### Health Verification
Verify all three containers pass their health checks:
```bash
# Check container status:
podman ps   # Or: docker compose ps

# Verify InfluxDB 2.x health:
curl -s http://127.0.0.1:8086/health | jq .
# Expected: {"name":"influxdb","message":"ready for queries and writes","status":"pass"}

# Verify Mosquitto MQTT port:
nc -z -v 127.0.0.1 1883
# Expected: Connection to 127.0.0.1 1883 port [tcp/*] succeeded!

# Verify Grafana HTTP health:
curl -s http://127.0.0.1:3000/api/health | jq .
# Expected: {"commit":"...","database":"ok","version":"11.5.0"}
```

> [!CAUTION]
> **Data Loss Prevention:**  
> Never shut down containers with `podman-compose down -v` or `docker compose down -v`. The `-v` flag permanently destroys the persistent named volumes `nexus_influxdb_data`, `nexus_mosquitto_data`, and `nexus_grafana_data`. Use `podman-compose stop` or `podman-compose down` (without `-v`).

---

## 5. Native Host-Side C Firmware Unit Tests

NEXUS firmware is designed for native host compilation and execution on Linux without requiring ESP-IDF or an attached board (`tests/test_milestone*_host.c`).

Compile and run all 5 native C test suites (45 tests total):

```bash
# Milestone 2: Job Table, Ready Queue, Event Queue, Ring Buffer, Executive Dispatch
gcc -std=gnu11 -Wall -Wextra -Werror \
    -I firmware/main -I firmware/main/data_structures -I firmware/main/executive \
    firmware/main/data_structures/*.c firmware/main/executive/*.c \
    tests/test_milestone2_host.c -o tests/test_milestone2_host
./tests/test_milestone2_host

# Milestone 3: Sensor Registry, LDR, CD4051, DHT11 Decoder, Deadline Accounting
gcc -std=gnu11 -Wall -Wextra -Werror \
    -I firmware/main -I firmware/main/data_structures -I firmware/main/executive -I firmware/main/sensors \
    firmware/main/data_structures/*.c firmware/main/executive/*.c firmware/main/sensors/*.c \
    tests/test_milestone3_host.c -o tests/test_milestone3_host
./tests/test_milestone3_host

# Milestone 4: Protocol v1 Envelopes, Serial/MQTT Transports, Reconnect Backoff, Concurrency
gcc -std=gnu11 -Wall -Wextra -Werror \
    -I firmware/main -I firmware/main/data_structures -I firmware/main/executive -I firmware/main/sensors -I firmware/main/transports \
    firmware/main/data_structures/*.c firmware/main/executive/*.c firmware/main/sensors/*.c firmware/main/transports/*.c \
    tests/test_milestone4_host.c -o tests/test_milestone4_host -lpthread
./tests/test_milestone4_host

# Milestone 8: 115-Command Registry, Dispatcher Parsing, Non-Destructive Fault Reset
gcc -std=gnu11 -Wall -Wextra -Werror \
    -I firmware/main -I firmware/main/command -I firmware/main/transports -I firmware/main/data_structures -I firmware/main/executive -I firmware/main/sensors \
    firmware/main/command/*.c firmware/main/transports/*.c firmware/main/data_structures/*.c firmware/main/executive/*.c firmware/main/sensors/*.c \
    tests/test_milestone8_host.c -o tests/test_milestone8_host -lpthread
./tests/test_milestone8_host

# Milestone 9: Extended M9 Sensors (CD4051 X1, MOC7811, HC-SR04) & Command Set Sweep
gcc -std=gnu11 -Wall -Wextra -Werror \
    -I firmware/main -I firmware/main/command -I firmware/main/transports -I firmware/main/data_structures -I firmware/main/executive -I firmware/main/sensors \
    firmware/main/command/*.c firmware/main/transports/*.c firmware/main/data_structures/*.c firmware/main/executive/*.c firmware/main/sensors/*.c \
    tests/test_milestone9_host.c -o tests/test_milestone9_host -lpthread
./tests/test_milestone9_host
```

*(Optional AddressSanitizer Build: replace `gcc` with `clang -fsanitize=address,undefined` to verify zero memory leaks or bounds violations).*

---

## 6. Target Firmware Toolchain (ESP-IDF v6.0.1)

### 6.1 ESP-IDF Toolchain Installation
To build and flash the physical ESP32, install official **ESP-IDF v6.0.1**:

```bash
mkdir -p ~/esp
cd ~/esp
git clone --recursive --branch v6.0.1 https://github.com/espressif/esp-idf.git esp-idf-v6.0.1
cd esp-idf-v6.0.1
./install.sh esp32
```

### 6.2 Building Firmware
Activate the ESP-IDF environment in your shell:
```bash
. ~/esp/esp-idf-v6.0.1/export.sh

cd /path/to/NEXUS/firmware
idf.py --version
# Expected: ESP-IDF v6.0.1

# Set target SoC (first build):
idf.py set-target esp32

# Build firmware binary:
idf.py build
```
Build outputs are generated in `firmware/build/`:
- `bootloader/bootloader.bin` (at `0x1000`)
- `partition_table/partition-table.bin` (at `0x8000`)
- `nexus.bin` (at `0x10000`)

### 6.3 Flashing to Physical Hardware

> [!IMPORTANT]
> **Operational Boundary Notice:**  
> In routine documentation, code audit, and local software validation tasks, **never run `idf.py flash`** without explicit user instruction and physical bench verification. Flashing modifies non-volatile MCU state.

When authorized to flash target hardware:
```bash
cd firmware
idf.py -p /dev/ttyUSB0 -b 115200 flash monitor
```
*(Press `Ctrl+]` to exit the ESP-IDF UART monitor).*

---

## 7. Python Test Suite & Mechanical Verification

Run the Python offline unit tests and reference manual validator:

```bash
source .venv/bin/activate

# 1. Run canonical reference manual validator (100% parity across 115 commands & 27 params):
python scripts/validate_reference_manual.py

# 2. Run Python unit test suite:
# (IMPORTANT: specify 'ground_station/tests' to avoid gitignored scratch/ scripts):
pytest ground_station/tests

# 3. Run passive soak capture harness unit tests:
python -m unittest tests/soak/test_soak_harness.py
```

---

## 8. Development Troubleshooting

| Issue / Error Message | Root Cause | Solution |
| :--- | :--- | :--- |
| `Permission denied: '/dev/ttyUSB0'` | Non-root user lacks dialout group permissions | Run `sudo usermod -aG dialout $USER && newgrp dialout`. |
| `listen tcp 10.12.252.18:1883: bind: cannot assign requested address` | Mosquitto `docker-compose.yml` attempts to bind to hardcoded LAN IP fallback | Set `MQTT_BIND_IP=127.0.0.1` in `.env` before running `podman-compose up -d`. |
| `InfluxDBClient is not available or library is not installed` | Python virtual environment not active or dependencies missing | Run `source .venv/bin/activate && pip install -r ground_station/requirements.txt`. |
| `ESP-IDF build error: esp_mqtt_client.h missing` | `idf_component.yml` managed components not fetched | Ensure internet connectivity and run `idf.py reconfigure` inside `firmware/`. |
| `pytest` hangs or fails during test collection | Ran bare `pytest` which picked up `scratch/test_*.py` top-level live MQTT connects | Always run `pytest ground_station/tests` or pass `--ignore=scratch`. |

