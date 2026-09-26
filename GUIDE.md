# 📘 Comprehensive Deployment, Integration & Operation Guide
## LaVera - Universal EV Telemetry Hub ⚡🚗

🌐 **Language / Idioma:** **English** | [Español (GUIA.md)](GUIA.md)

This guide provides an end-to-end walkthrough for deploying the **LaVera** stack, integrating multi-brand electric vehicles, ingesting high-resolution time-series telemetry, exporting geographic routes, and configuring analytics dashboards.

---

## 📑 Table of Contents
1. [Architecture & Core Concepts](#1-architecture--core-concepts)
2. [Prerequisites & Environment](#2-prerequisites--environment)
3. [Stack Installation & Deployment](#3-stack-installation--deployment)
4. [Step 1: Telemetry Ingestion with Home Assistant](#4-step-1-telemetry-ingestion-with-home-assistant)
5. [Step 2: InfluxDB 2.7 Configuration (Buckets & Tokens)](#5-step-2-influxdb-27-configuration-buckets--tokens)
6. [Step 3: Telemetry Pipeline (Direct or via Node-RED)](#6-step-3-telemetry-pipeline-direct-or-via-node-red)
7. [Step 4: Real-Time Hybrid Gateway (Tesla Fleet & Tessie)](#7-step-4-real-time-hybrid-gateway-tesla-fleet--tessie)
8. [Step 5: Geographic Routes & Exports (GPX, KML & Google Maps)](#8-step-5-geographic-routes--exports-gpx-kml--google-maps)
9. [Step 6: Grafana Dashboards & Metrics](#9-step-6-grafana-dashboards--metrics)
10. [Step 7: Vampire Drain Prevention](#10-step-7-vampire-drain-prevention)
11. [Step 8: Maintenance, Backups & SSL Security](#11-step-8-maintenance-backups--ssl-security)
12. [Troubleshooting & FAQ](#12-troubleshooting--faq)

---

## 1. Architecture & Core Concepts

The platform operates across a modular data pipeline:
1. **Extraction & Gateway:** Home Assistant acts as a multi-brand gateway. In parallel, the internal hybrid gateway ([`ev-telemetry-hub/gateway/`](ev-telemetry-hub/gateway/)) connects directly to the official **Tesla Fleet API** (command signing using ECDSA NIST P-256 elliptic curve) and the **Tessie API**, featuring adaptive sleep algorithms to prevent phantom battery drain.
2. **Time-Series Storage:** InfluxDB v2 stores nanosecond-precision metrics via Line Protocol, while TimescaleDB (PostgreSQL 16) provides relational long-term persistence.
3. **ETL & Ingestion:** Node-RED and the streaming injector script ([`influx_telemetry_injector.py`](ev-telemetry-hub/scripts/influx_telemetry_injector.py)) perform unit conversions, cost analysis, and batch transmission.
4. **Visualization & Export:** Grafana and the All-in-One dashboard present operational metrics, battery degradation curves, and route exports in standard **GPX 1.1** and **KML 2.2** formats.

### Key Metrics Glossary
- **SoC (State of Charge):** Current battery percentage (0 - 100%).
- **SOH (State of Health):** Remaining battery capacity relative to original factory rating.
- **Charging Power (kW):** Instantaneous charging rate delivered to the battery.
- **Average Consumption (Wh/km or kWh/100 km):** Energy driving efficiency.
- **Vampire / Phantom Drain:** Energy consumed by vehicle onboard computers while parked.

---

## 2. Prerequisites & Environment

### Recommended Hardware
- **Host:** Mini PC (x86-64, e.g. Intel N100 / Celeron / Ryzen), Raspberry Pi 4 / 5 (min 4 GB RAM), or NAS (Synology, QNAP, TrueNAS).
- **Storage:** Solid State Drive (SSD) recommended (high-frequency time-series writes wear out microSD cards quickly).
- **Operating System:** Linux (Debian, Ubuntu, DietPi, Alpine) or Windows/macOS via Docker Desktop.

### Network Ports
Ensure the following ports are available on your host:
- `8088` / `8080` (LaVera All-in-One Web UI & API)
- `8123` (Home Assistant)
- `8086` (InfluxDB v2)
- `5432` (TimescaleDB / PostgreSQL 16)
- `1880` (Node-RED)
- `3000` (Grafana)

> [!TIP]
> **Native Linux Servers:** If you want Home Assistant to automatically discover wallbox chargers (Wallbox, go-eCharger, OCPP) or LAN devices via mDNS/SSDP, you can uncomment `network_mode: host` in [docker-compose.yml](file:///c:/Users/castor/Documents/GitHub/LaVera/ev-telemetry-hub/docker-compose.yml). On Windows/macOS with Docker Desktop, keep the default `bridge` network mode.

---

## 3. Stack Installation & Deployment

### Step 3.1: Clone and Navigate
```bash
git clone https://github.com/cast0rtech/LaVera.git
cd LaVera/ev-telemetry-hub
```

### Step 3.2: Configure Environment Variables
Create your `.env` file from the provided template:
```bash
cp .env.example .env
```

Edit `.env` with your desired configuration:
```ini
# InfluxDB 2.x Configuration
INFLUXDB_URL=http://influxdb:8086
INFLUXDB_TOKEN=LaVeraSuperSecretAdminToken2026!
INFLUXDB_ORG=lavera
INFLUXDB_BUCKET=ev_telemetry

# Initial Grafana Configuration
GRAFANA_PASS=PasswordAdminGrafana2026!
```

> [!IMPORTANT]
> Do not use problematic characters like dollar signs (`$`) or unescaped quotes in `.env` passwords to prevent Docker Compose interpolation errors.

### Step 3.3: Launch the Containers
Start the stack in the background:
```bash
docker compose up -d
```

Verify that all containers report `healthy` or `Up`:
```bash
docker compose ps
```

---

## 4. Step 1: Telemetry Ingestion with Home Assistant

Access Home Assistant at: **`http://<YOUR-SERVER-IP>:8123`** and complete the initial administrator setup.

### Supported Manufacturer Integrations

#### 🚗 Tesla
1. **Official Fleet API:**
   - Requires a Tesla Developer account or community integration configured with Fleet API keys.
2. **Tesla Custom Integration (via HACS):**
   - Exposes SoC, location, door states, tire pressure, temperatures, and charging metrics.
   - **Crucial sleep setting:** Enable **"Polling only when awake"** and set a **Sleep interval** of at least 15-21 minutes to allow the vehicle to enter *Deep Sleep*.

#### 🚗 VAG Group (Volkswagen ID, Cupra, Škoda, Audi)
1. Install **Volkswagen We Connect ID** or **MyCupra / Skoda Connect** (available in HACS).
2. Authenticate using your official mobile app credentials.
3. Exposes battery percentage, estimated range, plug connection status, and charging rate.

#### 🚗 Renault / Dacia (Zoe, Megane E-Tech, Spring, 5 E-Tech)
1. Install the native **Renault** integration in Home Assistant.
2. Provide your *My Renault* credentials and select your vehicle VIN.

#### 🚗 Direct OBD-II / BLE Hardware
- For vehicles without cloud APIs or for cell-level voltages and temperatures:
  - Use a Bluetooth Low Energy (BLE) or WiFi OBD-II adapter (e.g. vLinker MC+, OBDLink CX).
  - Stream data via Webhook to Home Assistant or Node-RED using apps like **Torque Pro** or **ABRP**.

---

## 5. Step 2: InfluxDB 2.7 Configuration (Buckets & Tokens)

1. Open InfluxDB at: **`http://<YOUR-SERVER-IP>:8086`**.
2. Log in using the credentials defined in your `.env` file.
3. Verify that the bucket `ev_telemetry` and organization `lavera` are active.

### 5.1 Generate an API Token
1. In the left navigation menu, go to **Load Data** > **API Tokens**.
2. Click **Generate API Token** > **Custom API Token** (or *All-Access Token* for testing).
3. Grant **Read / Write** permissions for the `ev_telemetry` bucket.
4. Copy and store this token for client applications and scripts.

---

## 6. Step 3: Telemetry Pipeline (Direct or via Node-RED)

### Direct Home Assistant to InfluxDB Ingestion
Add this configuration snippet to your `configuration.yaml` in Home Assistant:

```yaml
influxdb:
  api_version: 2
  ssl: false
  host: influxdb
  port: 8086
  token: !secret influxdb_token
  organization: lavera
  bucket: ev_telemetry
  tags:
    source: homeassistant
    vehicle_type: electric
  include:
    domains:
      - sensor
      - device_tracker
    entity_globs:
      - sensor.*battery*
      - sensor.*soc*
      - sensor.*range*
      - sensor.*charging*
      - sensor.*odometer*
      - sensor.*energy*
      - sensor.*power*
      - sensor.*temperature*
      - device_tracker.*
```

---

## 7. Step 4: Real-Time Hybrid Gateway (Tesla Fleet & Tessie)

LaVera includes a standalone gateway module located in [`ev-telemetry-hub/gateway/`](ev-telemetry-hub/gateway/):

1. **Tesla Fleet Provider (`tesla_fleet_provider.py`):**
   - Connects to Tesla's official fleet endpoint with OAuth2 authentication.
   - Signs vehicle command payloads using **ECDSA NIST P-256 / secp256r1**.
2. **Tessie Live Provider (`tessie_provider.py`):**
   - High-resolution drive state capture and real-time waypoint streaming.
3. **Adaptive Sleep Manager (`polling_manager.py`):**
   - Suspends polling when the vehicle is parked to guarantee deep sleep.
4. **InfluxDB Streaming Injector (`scripts/influx_telemetry_injector.py`):**
   - Ingests batch and streaming telemetry records directly into InfluxDB v2:
   ```bash
   python ev-telemetry-hub/scripts/influx_telemetry_injector.py
   ```

---

## 8. Step 5: Geographic Routes & Exports (GPX, KML & Google Maps)

Every drive session logged or imported into LaVera stores precise coordinate pairs (`start_latitude`, `start_longitude`, `end_latitude`, `end_longitude`):

### 1. GPX 1.1 Route Export
- **Endpoint:** `/api/drives/export?id=<ID>&format=gpx`
- Generates standard XML tracks with `<trk>`, `<trkseg>`, and `<trkpt lat="..." lon="...">` elements.
- Compatible with **Garmin Connect / BaseCamp**, **Strava**, **Komoot**, and **OsmAnd**.

### 2. KML 2.2 Route Export
- **Endpoint:** `/api/drives/export?id=<ID>&format=kml`
- Generates OpenGIS KML strings with `<LineString><coordinates>lon,lat,0 ...</coordinates></LineString>`.
- Open directly in **Google Earth Pro** or spatial GIS tools.

### 3. Google Maps Instant Route Link
- Drive table rows include a direct action button launching Google Maps with exact route coordinates:
  `https://www.google.com/maps/dir/?api=1&origin=LAT,LON&destination=LAT,LON`

---

## 9. Step 6: Grafana Dashboards & Metrics

1. Open Grafana at: **`http://<YOUR-SERVER-IP>:3000`**.
2. Log in with user `admin` and the password configured in `.env`.

### Sample Flux Queries

#### Current Battery SoC (Gauge)
```flux
from(bucket: "ev_telemetry")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "%" and r["entity_id"] =~ /.*battery.*/)
  |> filter(fn: (r) => r["_field"] == "value")
  |> last()
```

#### Charging Power Profile (kW)
```flux
from(bucket: "ev_telemetry")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r["_field"] == "value")
  |> filter(fn: (r) => r["entity_id"] =~ /.*charging_power.*/ or r["entity_id"] =~ /.*charger_power.*/)
  |> aggregateWindow(every: 1m, fn: mean, createEmpty: false)
  |> yield(name: "charging_kw")
```

---

## 10. Step 7: Vampire Drain Prevention

### Core Rules Against Phantom Drain:
1. **Never force wake-ups:** Read vehicle status from cached cloud endpoints rather than sending active wake commands.
2. **Adaptive Polling Intervals:**
   - **Driving or Charging:** Fast interval (every 30 to 60 seconds).
   - **Parked and Sleeping:** Pause requests or poll every 4 to 8 hours.
3. The [`polling_manager.py`](ev-telemetry-hub/gateway/polling_manager.py) module handles this state machine automatically.

---

## 11. Step 8: Maintenance, Backups & SSL Security

### Full Data Backup
All persistent state is stored under `ev-telemetry-hub/data/`. To take a consistent snapshot:

```bash
# 1. Stop services temporarily
cd LaVera/ev-telemetry-hub
docker compose stop

# 2. Archive data directory and .env
tar -czvf "backup_lavera_$(date +%Y%m%d_%H%M%S).tar.gz" data/ .env

# 3. Resume services
docker compose start
```

### Hot InfluxDB Backup
```bash
docker exec -it telemetry_influxdb influx backup /var/lib/influxdb2/backup -t "YOUR_INFLUX_TOKEN"
```

---

## 12. Troubleshooting & FAQ

### ❓ InfluxDB returns "401 Unauthorized"
- Verify that your token has Read & Write access to the `ev_telemetry` bucket inside the `lavera` organization.

### ❓ Grafana displays "No Data"
- Ensure the time picker range (top right in Grafana) covers your recording period (e.g. `Last 24 hours`).
- Check that the `entity_id` filter matches the exact sensor name in Home Assistant.

### ❓ How do I export a drive to GPX or KML?
- On the web dashboard (`http://localhost:8088`), go to the Drives section. Click the **📍 GPX** or **🌐 KML** button on any trip row to download the file instantly.
