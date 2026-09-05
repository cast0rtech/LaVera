# ⚡ Universal EV Telemetry Hub

Módulo de despliegue Docker de **LaVera**, una arquitectura autohospedada para la extracción, normalización y visualización de telemetría de vehículos eléctricos multimarca (Tesla, Grupo VAG, Renault/Dacia, BYD, Hyundai/Kia, OBD-II/BLE, etc.).

> 💡 **Documentación completa:**
> - [📘 README Principal del Proyecto](../README.md)
> - [📖 Guía Completa de Configuración Paso a Paso](../GUIA.md)

---

## 🚀 Despliegue Rápido

1. **Configurar credenciales:**
   ```bash
   cp .env.example .env
   ```
   *(Edita el archivo `.env` con tus contraseñas y parámetros).*

2. **Levantar los contenedores:**
   ```bash
   docker compose up -d
   ```

3. **Verificar el estado:**
   ```bash
   docker compose ps
   ```

4. **Acceso a los Servicios:**
   - **Home Assistant:** `http://localhost:8123`
   - **Grafana:** `http://localhost:3000` *(Usuario: `admin` / Password: en `.env`)*
   - **Node-RED:** `http://localhost:1880`
   - **InfluxDB 2.7:** `http://localhost:8086`

---

## 📦 Servicios Incluidos

| Contenedor | Imagen | Puerto | Descripción |
| :--- | :--- | :--- | :--- |
| `telemetry_ha` | `linuxserver/homeassistant` | `8123` | Conexión con vehículos (APIs cloud y dongles) |
| `telemetry_influxdb` | `influxdb:2.7` | `8086` | Base de datos de series temporales |
| `telemetry_nodered` | `nodered/node-red` | `1880` | Normalización, flujos ETL y cálculo de costes |
| `telemetry_grafana` | `grafana/grafana` | `3000` | Dashboards interactivos y analítica |

Para la configuración avanzada de integraciones por vehículo, tokens de InfluxDB y paneles de Grafana, consulta la [Guía Completa (GUIA.md)](../GUIA.md).
