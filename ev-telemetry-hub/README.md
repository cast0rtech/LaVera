# ? Universal EV Telemetry Hub

?? **Language / Idioma:** **English** | [Espa?ol](README.es.md)

Docker deployment module for **LaVera**, a self-hosted architecture for extracting, normalizing, and visualizing multi-brand electric vehicle telemetry (Tesla, VAG Group, Renault/Dacia, BYD, Hyundai/Kia, OBD-II/BLE, etc.).

> ?? **Complete Documentation:**
> - [?? Main Project README](../README.md) | [Espa?ol](../README.es.md)
> - [?? Step-by-Step Setup Guide](../GUIDE.md) | [Gu?a en Espa?ol](../GUIA.md)

---

## ?? Deployment Modes

LaVera offers two distinct deployment modes to match your infrastructure requirements:

### Option A: All-in-One Offline Hub (Zero-Cloud & Raspberry Pi Ready)
A single, lightweight, self-contained container with zero external CDN dependencies, built-in SQLite time-series storage, Tesla importer (Tessie/TeslaFi), and offline web dashboard.

- **Cross-Platform:** Runs on **Windows (Docker Desktop)**, **Linux (x86_64 / aarch64)**, and **Raspberry Pi 3, 4, 5** (`linux/amd64`, `linux/arm64`, `linux/arm/v7`).
- **Start All-in-One:**
  ```bash
  docker compose -f docker-compose.all-in-one.yml up -d
  ```
- **Access Dashboard:** `http://localhost:8080` (or `http://lavera.local:8080` on Raspberry Pi).

### Option B: Distributed Modular Stack (Home Assistant + InfluxDB + Node-RED + Grafana)
The complete multi-container setup with enterprise InfluxDB 2.7, Home Assistant multi-brand extractor, Node-RED ETL, and Grafana dashboards.

1. **Configure credentials:**
   ```bash
   cp .env.example .env
   ```
2. **Start the containers:**
   ```bash
   docker compose up -d
   ```
3. **Access Web Interfaces:**
   - **Home Assistant:** `http://localhost:8123`
   - **Grafana:** `http://localhost:3000` *(User: `admin` / Password: in `.env`)*
   - **Node-RED:** `http://localhost:1880`
   - **InfluxDB 2.7:** `http://localhost:8086`

---

## ?? Tesla Historical Importer (Tessie & TeslaFi)

Migrate your historical driving, charging, and battery degradation logs from **Tessie** (CSV / JSON) or **TeslaFi** (CSV):

### 1. Via Web Interface (Drag & Drop)
Navigate to `http://localhost:8080` ? Tab **Importar Tessie / TeslaFi** and drop your exported files.

### 2. Via Command Line (CLI)
```bash
# Import TeslaFi drives CSV
python -m importer.cli --source teslafi --type drives --file /path/to/drives.csv --vin MY_TESLA

# Import Tessie JSON export
python -m importer.cli --source tessie --file /path/to/tessie_export.json --vin MY_TESLA
```

---

## ?? Container Profiles

| Mode | Container | Port | Architecture | Storage |
| :--- | :--- | :--- | :--- | :--- |
| **All-in-One** | `lavera_hub` | `8080` | `amd64`, `arm64`, `arm/v7` | Local SQLite + InfluxDB Sync |
| **Distributed** | `telemetry_ha` | `8123` | `amd64`, `arm64` | Local config volume |
| **Distributed** | `telemetry_influxdb` | `8086` | `amd64`, `arm64` | InfluxDB 2.7 Persistent Engine |
| **Distributed** | `telemetry_nodered` | `1880` | `amd64`, `arm64`, `arm/v7` | Node-RED flow data |
| **Distributed** | `telemetry_grafana` | `3000` | `amd64`, `arm64`, `arm/v7` | Grafana data & dashboards |
