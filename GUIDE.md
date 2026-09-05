# 📘 Comprehensive Deployment, Integration & Operation Guide
## LaVera - Universal EV Telemetry Hub ⚡🚗

🌐 **Language / Idioma:** **English** | [Español (GUIA.md)](GUIA.md)

This guide provides step-by-step instructions for deploying, integrating multi-brand Electric Vehicles (EV), ingesting time-series telemetry, and building analytical Grafana dashboards using the **LaVera** Docker stack.

---

## 📑 Table of Contents
1. [Architecture & Core Concepts](#1-architecture--core-concepts)
2. [Prerequisites & System Requirements](#2-prerequisites--system-requirements)
3. [Stack Installation & Deployment](#3-stack-installation--deployment)
4. [Step 1: Vehicle Telemetry Extraction with Home Assistant](#4-step-1-vehicle-telemetry-extraction-with-home-assistant)
5. [Step 2: InfluxDB 2.7 Configuration (Buckets & Tokens)](#5-step-2-influxdb-27-configuration-buckets--tokens)
6. [Step 3: Telemetry Ingestion (Direct vs. Node-RED ETL)](#6-step-3-telemetry-ingestion-direct-vs-node-red-etl)
7. [Step 4: Analytical Dashboards in Grafana](#7-step-4-analytical-dashboards-in-grafana)
8. [Step 5: Mitigating Vampire Drain (Parasitic Battery Draw)](#8-step-5-mitigating-vampire-drain-parasitic-battery-draw)
9. [Step 6: Maintenance, Backups & SSL Security](#9-step-6-maintenance-backups--ssl-security)
10. [Troubleshooting & FAQ](#10-troubleshooting--faq)

---

## 1. Architecture & Core Concepts

The system operates on a modular data pipeline:
1. **Extraction:** Home Assistant serves as a multi-brand gateway, connecting to OEM cloud APIs (Tesla Fleet, Renault Gigya, VAG We Connect, BYD, etc.) or local OBD-II hardware dongles.
2. **Time-Series Storage:** InfluxDB records high-precision metrics (timestamps, values, and contextual tags) with configurable data retention and downsampling.
3. **ETL & Orchestration:** Node-RED handles complex data transformations, unit normalization (Wh to kWh), and merges telemetry with electricity rates (e.g., dynamic hourly pricing) for session cost calculation.
4. **Visualization & Alerting:** Grafana queries InfluxDB via Flux or InfluxQL to render responsive dashboards and trigger notifications.

### Fundamental EV Metrics Glossary
- **SoC (State of Charge):** Current battery pack percentage (0 - 100%).
- **SOH (State of Health):** Battery degradation percentage relative to factory capacity.
- **Charging Power (kW):** Real-time charging rate entering the vehicle pack.
- **Average Consumption (Wh/km or kWh/100 km):** Driving efficiency.
- **Vampire / Phantom Drain:** Energy consumed by vehicle computers and electronics while parked and idle.

---

## 2. Prerequisites & System Requirements

### Recommended Hardware
- **Host System:** Mini PC (x86-64, e.g. Intel N100 / Celeron / Ryzen), Raspberry Pi 4 / 5 (minimum 4 GB RAM), or a home NAS (Synology, QNAP, TrueNAS).
- **Storage:** Solid State Drive (SSD) recommended. Frequent time-series database writes rapidly wear out microSD cards.
- **Operating System:** Linux (Debian, Ubuntu, DietPi, Alpine) or Windows/macOS using Docker Desktop.

### Host Network Ports
Ensure the following ports are free on your host:
- `8123` (Home Assistant)
- `8086` (InfluxDB)
- `1880` (Node-RED)
- `3000` (Grafana)

> [!TIP]
> **Native Linux Hosts:** If you want Home Assistant to auto-discover local chargers (Wallbox, go-eCharger, OCPP) or smart plugs via mDNS/SSDP, you can uncomment `network_mode: host` in `ev-telemetry-hub/docker-compose.yml`. On Windows/macOS with Docker Desktop, keep the default `bridge` networking.

---

## 3. Stack Installation & Deployment

### Step 3.1: Clone and Enter the Directory
```bash
git clone https://github.com/cast0rtech/LaVera.git
cd LaVera/ev-telemetry-hub
```

### Step 3.2: Configure Environment Variables
Copy the `.env.example` file:
```bash
cp .env.example .env
```

Edit `.env` using your preferred editor:
```ini
# InfluxDB 2.x Configuration
INFLUX_USER=admin
INFLUX_PASS=ChooseAStrongPassword2026!
INFLUX_ORG=EV_Telemetry
INFLUX_BUCKET=vehicle_data

# Initial Grafana Configuration
GRAFANA_PASS=StrongGrafanaPassword2026!
```

> [!IMPORTANT]
> Avoid problematic characters like quotes or raw dollar signs (`$`) in `.env` passwords to prevent interpretation issues in Docker Compose.

### Step 3.3: Start the Containers
Launch the stack in detached mode:
```bash
docker compose up -d
```

Verify that all containers are healthy:
```bash
docker compose ps
```

To tail the logs:
```bash
docker compose logs -f
```

---

## 4. Step 1: Vehicle Telemetry Extraction with Home Assistant

Access Home Assistant at: **`http://<YOUR-SERVER-IP>:8123`** and complete the initial onboarding to create your administrator account.

### Brand-Specific Vehicle Integrations

#### 🚗 Option A: Tesla
1. **Official Fleet API Integration:**
   - Requires a Tesla Developer account or third-party proxy compatible with the Fleet API.
2. **Tesla Custom Integration (via HACS):**
   - The most popular community integration for Home Assistant.
   - Provides SoC, location, door states, tire pressure, cabin/exterior temperature, and charging state.
   - **Crucial Sleep Setting:** Under integration options, enable **"Polling only when awake"** and set a sleep threshold of at least 15–21 minutes to allow the vehicle to transition into *Deep Sleep*.

#### 🚗 Option B: VAG Group (Volkswagen ID, Cupra, Škoda, Audi)
1. Install **Volkswagen We Connect ID** or **MyCupra / Skoda Connect** (via HACS).
2. Enter your credentials from the official manufacturer mobile application.
3. Exposed entities: Battery level (%), remaining range (km), charging cable status, and charge speed (kW).

#### 🚗 Option C: Renault / Dacia (Zoe, Megane E-Tech, Spring, 5 E-Tech)
1. Install the official **Renault** integration (built natively into Home Assistant core).
2. Enter your *My Renault* account credentials and select your vehicle by VIN.
3. Available metrics: SoC, estimated range, plug status, charger state, and remote climate controls.

#### 🚗 Option D: BYD (Atto 3, Dolphin, Seal, Tang, Han)
- Community HACS integrations communicate with the BYD cloud or local ESP32 hardware dongles reading CAN bus frames.

#### 🚗 Option E: OBD-II / BLE & Direct Cell Monitoring
- If your EV lacks an active cloud API or you want millisecond-level telemetry (per-cell voltage, exact pack temperature):
  - Connect a Bluetooth Low Energy (BLE) or WiFi OBD-II adapter (e.g., vLinker MC+, OBDLink CX).
  - Use mobile apps like **Torque Pro** or **ABRP** to stream telemetry via Webhook to Home Assistant or Node-RED.
  - Alternatively, use an ESP32 connected to the OBD-II port publishing decoded CAN frames over MQTT.

#### 🔌 Home EVSE / Wall Charger (Wallbox, OCPP, Shelly EM)
Integrating your charger into Home Assistant lets you track true charging efficiency:
$$\text{Charging Loss (\%)} = \left(1 - \frac{\Delta \text{Energy Added to Battery (kWh)}}{\text{Energy Supplied by EVSE (kWh)}}\right) \times 100$$

---

## 5. Step 2: InfluxDB 2.7 Configuration (Buckets & Tokens)

1. Open InfluxDB at: **`http://<YOUR-SERVER-IP>:8086`**.
2. Sign in using `INFLUX_USER` and `INFLUX_PASS` from your `.env` file.
3. Confirm that the default bucket `vehicle_data` and organization `EV_Telemetry` are present.

### 5.1 Generate an API Access Token
1. In the left navigation menu, go to **Load Data** > **API Tokens**.
2. Click **Generate API Token** > **Custom API Token** (or *All-Access Token* for testing).
3. Grant permissions:
   - **Read / Write** on the `vehicle_data` bucket.
4. Set a description (e.g. `HomeAssistant-LaVera-Token`) and click **Generate**.
5. **Copy and save this Token securely:** You will need it in the following steps.

### 5.2 Retention Policy
- By default, `vehicle_data` retains data indefinitely.
- To prevent unbounded disk growth over several years, configure retention:
  - **Load Data** > **Buckets** > `vehicle_data` > **Settings** > **Delete data older than** > e.g., `90 days` or `180 days`.

---

## 6. Step 3: Telemetry Ingestion (Direct vs. Node-RED ETL)

### Option A: Direct Home Assistant to InfluxDB Ingestion (Recommended)

1. Open the Home Assistant configuration file in the host volume:
   `ev-telemetry-hub/data/homeassistant/configuration.yaml`
2. Add the following block:

```yaml
# InfluxDB v2 Connection for Electric Vehicle Telemetry
influxdb:
  api_version: 2
  ssl: false
  host: influxdb
  port: 8086
  token: !secret influxdb_token
  organization: EV_Telemetry
  bucket: vehicle_data
  tags:
    source: homeassistant
    vehicle_type: electric
  tags_attributes:
    - friendly_name
  # Filter only relevant EV telemetry to optimize disk space and query performance
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

3. In `ev-telemetry-hub/data/homeassistant/secrets.yaml`, add the token generated in Step 5.1:
```yaml
influxdb_token: "YOUR_INFLUXDB_API_TOKEN_HERE"
```

4. Restart Home Assistant (**Settings** > **System** > **Restart**) or via Docker:
```bash
docker compose restart homeassistant
```

---

### Option B: Advanced ETL & Routing with Node-RED

If you want to preprocess data (convert units, classify charge sessions by electricity tariff window, or calculate monetary cost):

1. Access Node-RED at: **`http://<YOUR-SERVER-IP>:1880`**.
2. Go to the menu (top right) > **Manage palette** > **Install** tab.
3. Install the following nodes:
   - `node-red-contrib-home-assistant-websocket`
   - `node-red-contrib-influxdb`
4. Configure the InfluxDB node:
   - **Version:** `2.0`
   - **URL:** `http://influxdb:8086`
   - **Token:** Your InfluxDB API token.
   - **Organization:** `EV_Telemetry`
   - **Bucket:** `vehicle_data`
5. Create a flow that listens to vehicle state changes and writes clean measurements (e.g. `battery_soc`, `charging_kw`, `session_cost`).

---

## 7. Step 4: Analytical Dashboards in Grafana

1. Open Grafana at: **`http://<YOUR-SERVER-IP>:3000`**.
2. Log in with user `admin` and your `GRAFANA_PASS`.

### 7.1 Add the InfluxDB Data Source
1. Navigate to **Connections** > **Data sources** > **Add data source**.
2. Select **InfluxDB**.
3. Configure the settings:
   - **Query Language:** `Flux`
   - **URL:** `http://influxdb:8086`
   - **Auth:** Disable Basic Auth.
   - **InfluxDB Details:**
     - **Organization:** `EV_Telemetry`
     - **Token:** *(Your InfluxDB API Token)*
     - **Default Bucket:** `vehicle_data`
4. Click **Save & test**. A green confirmation message indicates a successful connection.

---

### 7.2 Example Flux Queries for Panels

Create a new Dashboard (**Dashboards** > **New Dashboard** > **Add visualization**):

#### Panel 1: Current Battery State of Charge (Gauge)
```flux
from(bucket: "vehicle_data")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "%" and r["entity_id"] =~ /.*battery.*/)
  |> filter(fn: (r) => r["_field"] == "value")
  |> last()
```
*Recommended visual:* **Gauge** (Thresholds: Red < 20%, Yellow 20-50%, Green 50-80%, Blue 80-100%).

---

#### Panel 2: Real-Time Charging Power Curve (kW)
```flux
from(bucket: "vehicle_data")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r["_field"] == "value")
  |> filter(fn: (r) => r["entity_id"] =~ /.*charging_power.*/ or r["entity_id"] =~ /.*charger_power.*/)
  |> aggregateWindow(every: 1m, fn: mean, createEmpty: false)
  |> yield(name: "charging_kw")
```
*Recommended visual:* **Time series**.

---

#### Panel 3: Odometer & Daily Distance Driven
```flux
from(bucket: "vehicle_data")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r["_field"] == "value")
  |> filter(fn: (r) => r["entity_id"] =~ /.*odometer.*/)
  |> aggregateWindow(every: 1d, fn: max, createEmpty: false)
```
*Recommended visual:* **Bar chart** or **Stat**.

---

#### Panel 4: Vehicle GPS Location & Trips
When Home Assistant publishes the vehicle's `device_tracker`:
```flux
from(bucket: "vehicle_data")
  |> range(start: -7d)
  |> filter(fn: (r) => r["entity_id"] =~ /.*device_tracker.*/)
  |> filter(fn: (r) => r["_field"] == "latitude" or r["_field"] == "longitude")
  |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
```
*Recommended visual:* **Geomap** panel.

---

## 8. Step 5: Mitigating Vampire Drain (Parasitic Battery Draw)

A common pitfall with connected EVs is **unintentional 12V and high-voltage battery drainage** caused by repetitive cloud API polling that keeps the vehicle's ECUs awake.

### Golden Rules against Vampire Drain:
1. **Never force wake-ups:** Always read cached telemetry from the OEM cloud servers rather than triggering remote wake commands.
2. **Dynamic Polling:**
   - **While driving or charging:** Poll frequently (every 30 to 60 seconds).
   - **While parked and idle:** Stop active polling or throttle to every 4 to 8 hours.
3. **Automate in Home Assistant:** Create an automation that pauses telemetry polling whenever the car reports state `asleep` or `offline`.

---

## 9. Step 6: Maintenance, Backups & SSL Security

### 9.1 Data Backups
All persistent data lives in the `ev-telemetry-hub/data/` directory. To create a full snapshot:

```bash
# 1. Stop containers briefly for snapshot consistency
cd LaVera/ev-telemetry-hub
docker compose stop

# 2. Archive data and environment config
tar -czvf "backup_lavera_$(date +%Y%m%d_%H%M%S).tar.gz" data/ .env

# 3. Restart the containers
docker compose start
```

### 9.2 InfluxDB Hot Backup
To back up InfluxDB while it remains running:
```bash
docker exec -it telemetry_influxdb influx backup /var/lib/influxdb2/backup -t "YOUR_INFLUX_TOKEN"
```

### 9.3 Secure Remote Access with HTTPS
To access dashboards on mobile networks without exposing insecure ports:
- **Recommended:** Set up a **Cloudflare Tunnel (Zero Trust)** or **Tailscale / WireGuard VPN**.
- **Standard:** Use a reverse proxy (Nginx Proxy Manager, Traefik, or Caddy) with automated Let's Encrypt SSL/TLS certificates.

---

## 10. Troubleshooting & FAQ

### ❓ InfluxDB returns "401 Unauthorized"
- **Cause:** The API token used in Home Assistant, Node-RED, or Grafana is incorrect or lacks read/write permissions for bucket `vehicle_data`.
- **Fix:** In the InfluxDB UI (`http://localhost:8086`), generate a new token with explicit permissions for the bucket and organization, then update your secrets.

### ❓ Grafana displays "No Data"
- Verify that the time range selector (top right of Grafana) encompasses active data points (e.g., select `Last 24 hours` or `Last 7 days`).
- Check that the `entity_id` in your Flux query matches the exact name of your sensor in Home Assistant (**Developer Tools** > **States**).

### ❓ Volume permission issues on Linux
- If a container cannot write to the `data/` folder, ensure ownership matches UID `1000`:
  ```bash
  sudo chown -R 1000:1000 data/
  ```

### ❓ Can I add more services (e.g. MQTT Broker or Teslamate)?
- Yes. You can declare additional containers in `ev-telemetry-hub/docker-compose.yml` and attach them to the shared `telemetry_net` bridge network.
