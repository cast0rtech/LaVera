# ? Hub Universal de Telemetr?a EV

?? **Idioma / Language:** [English](README.md) | **Espa?ol**

M?dulo de despliegue Docker para **LaVera**, una arquitectura auto-hospedada para la extracci?n, normalizaci?n y visualizaci?n de telemetr?a de veh?culos el?ctricos multimarca (Tesla, Grupo VAG, Renault/Dacia, BYD, Hyundai/Kia, OBD-II/BLE, etc.).

> ?? **Documentaci?n Completa:**
> - [?? README Principal del Proyecto](../README.md) | [Espa?ol](../README.es.md)
> - [?? Gu?a Paso a Paso](../GUIDE.md) | [Gu?a en Espa?ol](../GUIA.md)

---

## ?? Modos de Despliegue

LaVera ofrece dos modalidades seg?n tus requerimientos de hardware e infraestructura:

### Opci?n A: Hub All-in-One Offline (Zero-Cloud y Listo para Raspberry Pi)
Un ?nico contenedor aut?nomo, ultra ligero, sin dependencias de CDNs externas, con base de datos de series temporales SQLite integrada, importador de Tesla (Tessie/TeslaFi) y panel web offline.

- **Multiplataforma:** Compatible con **Windows (Docker Desktop)**, **Linux (x86_64 / aarch64)** y **Raspberry Pi 3, 4 y 5** (`linux/amd64`, `linux/arm64`, `linux/arm/v7`).
- **Arrancar All-in-One:**
  ```bash
  docker compose -f docker-compose.all-in-one.yml up -d
  ```
- **Acceso al Panel:** `http://localhost:8080` (o `http://lavera.local:8080` en Raspberry Pi).

### Opci?n B: Stack Modular Distribuido (Home Assistant + InfluxDB + Node-RED + Grafana)
El despliegue multi-contenedor con InfluxDB 2.7 empresarial, Home Assistant como extractor multimarca, Node-RED y paneles en Grafana.

1. **Configurar credenciales:**
   ```bash
   cp .env.example .env
   ```
2. **Iniciar los contenedores:**
   ```bash
   docker compose up -d
   ```
3. **Acceder a las interfaces web:**
   - **Home Assistant:** `http://localhost:8123`
   - **Grafana:** `http://localhost:3000` *(Usuario: `admin` / Contrase?a: en `.env`)*
   - **Node-RED:** `http://localhost:1880`
   - **InfluxDB 2.7:** `http://localhost:8086`

---

## ?? Importador Hist?rico de Tesla (Tessie y TeslaFi)

Migra f?cilmente tus registros hist?ricos de trayectos, cargas y degradaci?n de bater?a desde **Tessie** (CSV / JSON) o **TeslaFi** (CSV):

### 1. V?a Interfaz Web (Arrastrar y Soltar)
Navega a `http://localhost:8080` ? Pesta?a **Importar Tessie / TeslaFi** y arrastra tus archivos exportados.

### 2. V?a L?nea de Comandos (CLI)
```bash
# Importar CSV de viajes de TeslaFi
python -m importer.cli --source teslafi --type drives --file /ruta/a/drives.csv --vin MI_TESLA

# Importar exportaci?n JSON de Tessie
python -m importer.cli --source tessie --file /ruta/a/tessie_export.json --vin MI_TESLA
```

---

## ?? Perfiles de Contenedores

| Modo | Contenedor | Puerto | Arquitectura | Almacenamiento |
| :--- | :--- | :--- | :--- | :--- |
| **All-in-One** | `lavera_hub` | `8080` | `amd64`, `arm64`, `arm/v7` | SQLite Local + Sync InfluxDB |
| **Distribuido** | `telemetry_ha` | `8123` | `amd64`, `arm64` | Volumen local de configuraci?n |
| **Distribuido** | `telemetry_influxdb` | `8086` | `amd64`, `arm64` | Motor persistente InfluxDB 2.7 |
| **Distribuido** | `telemetry_nodered` | `1880` | `amd64`, `arm64`, `arm/v7` | Flujos de Node-RED |
| **Distribuido** | `telemetry_grafana` | `3000` | `amd64`, `arm64`, `arm/v7` | Datos y dashboards Grafana |
