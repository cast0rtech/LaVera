# ⚡ Universal EV Telemetry Hub

🌐 **Language / Idioma:** **English** | [Español](README.es.md)

Docker deployment module and data gateway for **LaVera**, a self-hosted platform for extracting, normalizing, storing time-series data, and visualizing multi-brand electric vehicle telemetry (Tesla, VAG Group, Renault/Dacia, BYD, Hyundai/Kia, OBD-II/BLE, etc.).

> 📖 **Complete Documentation:**
> - [📘 Main Project README](../README.md) | [Español](../README.es.md)
> - [📘 Step-by-Step Setup Guide](../GUIDE.md) | [Guía en Español](../GUIA.md)

---

## 🚀 Deployment Modes

LaVera offers two distinct deployment modes to match your infrastructure requirements:

### Option A: All-in-One Offline Hub (Zero-Cloud & Raspberry Pi Ready)
A single, lightweight, self-contained container (Python 3.12-slim base) with zero external CDN dependencies, built-in SQLite time-series storage, real-time hybrid telemetry gateway, Tesla importer (Tessie/TeslaFi), GPX/KML route generator, and offline web dashboard.

- **Cross-Platform:** Runs on **Windows (Docker Desktop)**, **Linux (x86_64 / aarch64)**, and **Raspberry Pi 3, 4, 5** (`linux/amd64`, `linux/arm64`, `linux/arm/v7`).
- **Start All-in-One:**
  ```bash
  docker compose -f docker-compose.all-in-one.yml up -d
  ```
- **Access Dashboard:** `http://localhost:8088` (or `http://localhost:8080`, and `http://lavera.local:8088` on Raspberry Pi).

### Option B: Distributed Modular Stack (InfluxDB v2 + TimescaleDB + Node-RED + Grafana + Home Assistant)
The complete multi-container setup with InfluxDB 2.7 for high-resolution time-series metrics, enterprise TimescaleDB (PostgreSQL 16), Home Assistant multi-brand extractor, Node-RED ETL, and Grafana dashboards.

1. **Configure credentials:**
   ```bash
   cp .env.example .env
   ```
2. **Start the containers:**
   ```bash
   docker compose up -d
   ```
3. **Access Web Interfaces:**
   - **LaVera Hub Dashboard:** `http://localhost:8088` (or `:8080`)
   - **InfluxDB 2.7:** `http://localhost:8086` *(Org: `lavera`, Bucket: `ev_telemetry`)*
   - **Grafana:** `http://localhost:3000` *(User: `admin` / Password: in `.env`)*
   - **Node-RED:** `http://localhost:1880`
   - **Home Assistant:** `http://localhost:8123`
   - **TimescaleDB:** `localhost:5432` *(User: `lavera`, DB: `lavera_telemetry`)*

---

## 🗺️ Route Tracking & Geographic Exporters (GPX & KML)

The hub automatically extracts origin and destination GPS coordinates from each trip:
- **Download GPX 1.1:** Ready for Garmin Connect, Strava, Komoot, and OsmAnd.
- **Download KML 2.2:** Ready for 3D trajectory rendering in Google Earth.
- **Open in Google Maps:** Instant route direction preview link directly from the web dashboard.

---

## 🔄 Tesla Historical Importer (Tessie & TeslaFi)

Migrate your historical driving, charging, and battery degradation logs from **Tessie** (CSV / JSON) or **TeslaFi** (CSV):

### 1. Via Web Interface (Drag & Drop)
Navigate to `http://localhost:8088` ➔ Tab **Importar Tessie / TeslaFi** and drop your exported files.

### 2. Via Command Line (CLI)
```bash
# Import TeslaFi drives CSV
python -m importer.cli --source teslafi --type drives --file /path/to/drives.csv --vin MY_TESLA

# Import Tessie JSON export
python -m importer.cli --source tessie --file /path/to/tessie_export.json --vin MY_TESLA
```

---

## 📊 Container Profiles

| Mode | Container | Port | Architecture | Storage / Function |
| :--- | :--- | :--- | :--- | :--- |
| **All-in-One** | `lavera_hub` | `8088` / `8080` | `amd64`, `arm64`, `arm/v7` | Local SQLite + InfluxDB / TimescaleDB Sync |
| **Distributed** | `telemetry_influxdb` | `8086` | `amd64`, `arm64` | InfluxDB 2.7 (Nanosecond time-series engine) |
| **Distributed** | `telemetry_timescale` | `5432` | `amd64`, `arm64` | TimescaleDB / PostgreSQL 16 (Relational & analytics) |
| **Distributed** | `telemetry_ha` | `8123` | `amd64`, `arm64` | Home Assistant (Multi-brand cloud integrations) |
| **Distributed** | `telemetry_nodered` | `1880` | `amd64`, `arm64`, `arm/v7` | Node-RED (Flow logic and ETL transformations) |
| **Distributed** | `telemetry_grafana` | `3000` | `amd64`, `arm64`, `arm/v7` | Grafana (Analytical and degradation dashboards) |
