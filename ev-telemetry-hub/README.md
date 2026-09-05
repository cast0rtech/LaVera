# ⚡ Universal EV Telemetry Hub

🌐 **Language / Idioma:** **English** | [Español](README.es.md)

Docker deployment module for **LaVera**, a self-hosted architecture for extracting, normalizing, and visualizing multi-brand electric vehicle telemetry (Tesla, VAG Group, Renault/Dacia, BYD, Hyundai/Kia, OBD-II/BLE, etc.).

> 💡 **Complete Documentation:**
> - [📘 Main Project README](../README.md) | [Español](../README.es.md)
> - [📖 Step-by-Step Setup Guide](../GUIDE.md) | [Guía en Español](../GUIA.md)

---

## 🚀 Quickstart

1. **Configure credentials:**
   ```bash
   cp .env.example .env
   ```
   *(Edit the `.env` file with your secure credentials and parameters).*

2. **Start the containers:**
   ```bash
   docker compose up -d
   ```

3. **Check container status:**
   ```bash
   docker compose ps
   ```

4. **Access Web Interfaces:**
   - **Home Assistant:** `http://localhost:8123`
   - **Grafana:** `http://localhost:3000` *(User: `admin` / Password: defined in `.env`)*
   - **Node-RED:** `http://localhost:1880`
   - **InfluxDB 2.7:** `http://localhost:8086`

---

## 📦 Included Services

| Container | Image | Port | Description |
| :--- | :--- | :--- | :--- |
| `telemetry_ha` | `linuxserver/homeassistant` | `8123` | Vehicle connectivity (cloud APIs & local dongles) |
| `telemetry_influxdb` | `influxdb:2.7` | `8086` | High-performance time-series database |
| `telemetry_nodered` | `nodered/node-red` | `1880` | Flow-based ETL, normalization & tariff logic |
| `telemetry_grafana` | `grafana/grafana` | `3000` | Real-time analytics and telemetry dashboards |

For brand-specific vehicle configurations, InfluxDB tokens, and Grafana panels, see the [Comprehensive Guide (GUIDE.md)](../GUIDE.md).
