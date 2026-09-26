# ⚡ Hub Universal de Telemetría EV

🌐 **Idioma / Language:** [English](README.md) | **Español**

Módulo de despliegue Docker y pasarela de datos para **LaVera**, una plataforma auto-hospedada para la extracción, normalización, almacenamiento en series temporales y visualización de telemetría de vehículos eléctricos multimarca (Tesla, Grupo VAG, Renault/Dacia, BYD, Hyundai/Kia, OBD-II/BLE, etc.).

> 📖 **Documentación Completa:**
> - [📘 README Principal del Proyecto](../README.es.md) | [English](../README.md)
> - [📘 Guía Paso a Paso](../GUIA.md) | [English Guide](../GUIDE.md)

---

## 🚀 Modos de Despliegue

LaVera ofrece dos modalidades según tus requerimientos de hardware e infraestructura:

### Opción A: Hub All-in-One Offline (Zero-Cloud y Optimizado para Raspberry Pi)
Un único contenedor autónomo, ultra ligero (base Python 3.12-slim), sin dependencias de CDNs externas, con base de datos de series temporales SQLite integrada, pasarela híbrida en tiempo real, importador de Tesla (Tessie/TeslaFi), exportador de rutas GPX/KML y panel web offline.

- **Multiplataforma:** Compatible con **Windows (Docker Desktop)**, **Linux (x86_64 / aarch64)** y **Raspberry Pi 3, 4 y 5** (`linux/amd64`, `linux/arm64`, `linux/arm/v7`).
- **Arrancar All-in-One:**
  ```bash
  docker compose -f docker-compose.all-in-one.yml up -d
  ```
- **Acceso al Panel:** `http://localhost:8088` (o `http://localhost:8080`, y `http://lavera.local:8088` en Raspberry Pi).

### Opción B: Stack Modular Distribuido (InfluxDB v2 + TimescaleDB + Node-RED + Grafana + Home Assistant)
El despliegue multi-contenedor con InfluxDB 2.7 para métricas de alta resolución, TimescaleDB (PostgreSQL 16) empresarial, Home Assistant como extractor multimarca, Node-RED y paneles en Grafana.

1. **Configurar credenciales:**
   ```bash
   cp .env.example .env
   ```
2. **Iniciar los contenedores:**
   ```bash
   docker compose up -d
   ```
3. **Acceder a las interfaces web:**
   - **Panel LaVera Hub:** `http://localhost:8088` (o `:8080`)
   - **InfluxDB 2.7:** `http://localhost:8086` *(Org: `lavera`, Bucket: `ev_telemetry`)*
   - **Grafana:** `http://localhost:3000` *(Usuario: `admin` / Contraseña: en `.env`)*
   - **Node-RED:** `http://localhost:1880`
   - **Home Assistant:** `http://localhost:8123`
   - **TimescaleDB:** `localhost:5432` *(Usuario: `lavera`, BD: `lavera_telemetry`)*

---

## 🗺️ Rutas y Exportación Geográfica (GPX y KML)

El hub extrae automáticamente las coordenadas de origen y destino de cada trayecto, permitiendo:
- **Descargar GPX 1.1:** Para Garmin, Strava, OsmAnd y relojes deportivos.
- **Descargar KML 2.2:** Para visualización tridimensional en Google Earth.
- **Abrir en Google Maps:** Enlace directo de navegación desde la tabla de trayectos del panel.

---

## 🔄 Importador Histórico de Tesla (Tessie y TeslaFi)

Migra fácilmente tus registros históricos de trayectos, cargas y degradación de batería desde **Tessie** (CSV / JSON) o **TeslaFi** (CSV):

### 1. Vía Interfaz Web (Arrastrar y Soltar)
Navega a `http://localhost:8088` ➔ Pestaña **Importar Tessie / TeslaFi** y arrastra tus archivos exportados.

### 2. Vía Línea de Comandos (CLI)
```bash
# Importar CSV de viajes de TeslaFi
python -m importer.cli --source teslafi --type drives --file /ruta/a/drives.csv --vin MI_TESLA

# Importar exportación JSON de Tessie
python -m importer.cli --source tessie --file /ruta/a/tessie_export.json --vin MI_TESLA
```

---

## 📊 Perfiles de Contenedores

| Modo | Contenedor | Puerto | Arquitectura | Almacenamiento / Función |
| :--- | :--- | :--- | :--- | :--- |
| **All-in-One** | `lavera_hub` | `8088` / `8080` | `amd64`, `arm64`, `arm/v7` | SQLite Local + Sync InfluxDB / TimescaleDB |
| **Distribuido** | `telemetry_influxdb` | `8086` | `amd64`, `arm64` | InfluxDB 2.7 (Series temporales en nanosegundos) |
| **Distribuido** | `telemetry_timescale` | `5432` | `amd64`, `arm64` | TimescaleDB / PostgreSQL 16 (Datos relacionales) |
| **Distribuido** | `telemetry_ha` | `8123` | `amd64`, `arm64` | Home Assistant (Integraciones multimarca) |
| **Distribuido** | `telemetry_nodered` | `1880` | `amd64`, `arm64`, `arm/v7` | Node-RED (Lógica de flujos y transformaciones) |
| **Distribuido** | `telemetry_grafana` | `3000` | `amd64`, `arm64`, `arm/v7` | Grafana (Dashboards analíticos de degradación) |
