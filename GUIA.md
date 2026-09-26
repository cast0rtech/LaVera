# 📘 Guía Exhaustiva de Despliegue, Integración y Operación
## LaVera - Universal EV Telemetry Hub ⚡🚗

🌐 **Idioma / Language:** [English (GUIDE.md)](GUIDE.md) | **Español**

Esta guía describe detalladamente la puesta en marcha, integración multimarca de vehículos, ingesta de telemetría en series temporales, exportación de rutas geográficas y construcción de dashboards analíticos utilizando el stack Docker de **LaVera**.

---

## 📑 Tabla de Contenidos
1. [Arquitectura y Conceptos Clave](#1-arquitectura-y-conceptos-clave)
2. [Requisitos Previos y Entorno](#2-requisitos-previos-y-entorno)
3. [Instalación y Despliegue del Stack](#3-instalación-y-despliegue-del-stack)
4. [Paso 1: Extracción de Telemetría con Home Assistant](#4-paso-1-extracción-de-telemetría-con-home-assistant)
5. [Paso 2: Configuración de InfluxDB 2.7 (Buckets y Tokens)](#5-paso-2-configuración-de-influxdb-27-buckets-y-tokens)
6. [Paso 3: Ingesta de Telemetría (Directa o vía Node-RED)](#6-paso-3-ingesta-de-telemetría-directa-o-vía-node-red)
7. [Paso 4: Pasarela Híbrida en Tiempo Real (Tesla Fleet & Tessie)](#7-paso-4-pasarela-híbrida-en-tiempo-real-tesla-fleet--tessie)
8. [Paso 5: Rutas y Exportación Geográfica (GPX, KML y Google Maps)](#8-paso-5-rutas-y-exportación-geográfica-gpx-kml-y-google-maps)
9. [Paso 6: Dashboards y Métricas en Grafana](#9-paso-6-dashboards-y-métricas-en-grafana)
10. [Paso 7: Mitigación del Vampire Drain (Consumo Parásito)](#10-paso-7-mitigación-del-vampire-drain-consumo-parásito)
11. [Paso 8: Mantenimiento, Copias de Seguridad y Seguridad SSL](#11-paso-8-mantenimiento-copias-de-seguridad-y-seguridad-ssl)
12. [Solución de Problemas Frecuentes (FAQ / Troubleshooting)](#12-solución-de-problemas-frecuentes-faq--troubleshooting)

---

## 1. Arquitectura y Conceptos Clave

El sistema opera bajo un pipeline modular de datos:
1. **Extracción y Pasarela:** Home Assistant actúa como gateway multimarca. Adicionalmente, el módulo de pasarela híbrida interna ([`ev-telemetry-hub/gateway/`](ev-telemetry-hub/gateway/)) conecta directamente con la **Tesla Fleet API** oficial (firmando comandos mediante curva elíptica ECDSA NIST P-256) y la **Tessie API**, con algoritmos de mitigación de consumo parásito.
2. **Almacenamiento en Series Temporales:** InfluxDB v2 almacena métricas con marca de tiempo precisa en nanosegundos mediante Line Protocol, y TimescaleDB (PostgreSQL 16) proporciona persistencia relacional a gran escala.
3. **ETL y Orquestación:** Node-RED y el inyector continuo de telemetría ([`influx_telemetry_injector.py`](ev-telemetry-hub/scripts/influx_telemetry_injector.py)) transforman unidades, calculan precios y gestionan lotes de telemetría.
4. **Visualización y Exportación:** Grafana y el panel All-in-One presentan métricas operativas, curvas de degradación de batería y exportadores de rutas a formatos estándar **GPX 1.1** y **KML 2.2**.

### Glosario de Métricas Fundamentales
- **SoC (State of Charge):** Porcentaje de carga actual de la batería (0 - 100%).
- **SOH (State of Health):** Porcentaje de degradación de la batería frente a su capacidad original de fábrica.
- **Potencia de Carga (kW):** Velocidad instantánea a la que entra energía a la batería.
- **Consumo Medio (Wh/km o kWh/100 km):** Eficiencia energética de la conducción.
- **Vampire / Phantom Drain:** Energía consumida por los ordenadores y sistemas del vehículo mientras está estacionado.

---

## 2. Requisitos Previos y Entorno

### Hardware Recomendado
- **Equipo:** Mini PC (x86-64, ej. Intel N100 / Celeron / Ryzen), Raspberry Pi 4 / 5 (mínimo 4 GB RAM) o NAS (Synology, QNAP, TrueNAS).
- **Almacenamiento:** Disco SSD recomendado (las escrituras frecuentes de bases de datos de series temporales en tarjetas microSD desgastan rápidamente la memoria flash).
- **Sistema Operativo:** Linux (Debian, Ubuntu, DietPi, Alpine) o Windows/macOS mediante Docker Desktop.

### Puertos de Red
Asegúrate de que los siguientes puertos están disponibles en el host:
- `8088` / `8080` (LaVera All-in-One Web UI & API)
- `8123` (Home Assistant)
- `8086` (InfluxDB v2)
- `5432` (TimescaleDB / PostgreSQL 16)
- `1880` (Node-RED)
- `3000` (Grafana)

> [!TIP]
> **En servidores Linux nativos:** Si deseas que Home Assistant descubra automáticamente cargadores de pared (Wallbox, go-eCharger, OCPP) o dispositivos de red local vía mDNS/SSDP, puedes descomentar la directiva `network_mode: host` en [docker-compose.yml](file:///c:/Users/castor/Documents/GitHub/LaVera/ev-telemetry-hub/docker-compose.yml). En Windows/macOS bajo Docker Desktop, mantén el modo de red `bridge` predeterminado.

---

## 3. Instalación y Despliegue del Stack

### Paso 3.1: Clonar y Navegar al Repositorio
```bash
git clone https://github.com/cast0rtech/LaVera.git
cd LaVera/ev-telemetry-hub
```

### Paso 3.2: Configurar las Variables de Entorno
Crea tu archivo `.env` a partir de la plantilla:
```bash
cp .env.example .env
```

Edita `.env` con un editor de texto:
```ini
# Configuración InfluxDB 2.x
INFLUXDB_URL=http://influxdb:8086
INFLUXDB_TOKEN=LaVeraSuperSecretAdminToken2026!
INFLUXDB_ORG=lavera
INFLUXDB_BUCKET=ev_telemetry

# Configuración Inicial Grafana
GRAFANA_PASS=PasswordAdminGrafana2026!
```

> [!IMPORTANT]
> No utilices caracteres especiales problemáticos como comillas o signos de dólar (`$`) en las contraseñas del archivo `.env` para evitar errores de interpretación en Docker Compose.

### Paso 3.3: Iniciar los Contenedores
Ejecuta el stack en segundo plano:
```bash
docker compose up -d
```

Comprueba que todos los contenedores estén en estado `healthy` o `Up`:
```bash
docker compose ps
```

---

## 4. Paso 1: Extracción de Telemetría con Home Assistant

Accede a Home Assistant en: **`http://<IP-DE-TU-SERVIDOR>:8123`** y completa la creación del usuario administrador inicial.

### Instalación de Integraciones según la Marca de tu Vehículo

#### 🚗 Opción A: Tesla
1. **Integración Oficial (Tesla Fleet API):**
   - Requiere cuenta en el portal de desarrolladores de Tesla o usar integraciones comunitarias compatibles con Fleet API.
2. **Tesla Custom Integration (vía HACS):**
   - Permite consultar SoC, ubicación, estado de las puertas, presión de neumáticos, temperatura interna/externa y estado de carga.
   - **Ajuste crítico de descanso:** En las opciones de la integración, activa el parámetro **"Polling only when awake"** y configura un intervalo de descanso (*Sleep interval*) de al menos 15-21 minutos para permitir que el vehículo entre en modo *Deep Sleep*.

#### 🚗 Opción B: Grupo VAG (Volkswagen ID, Cupra, Škoda, Audi)
1. Instala la integración **Volkswagen We Connect ID** o **MyCupra / Skoda Connect** (disponibles en HACS).
2. Proporciona tus credenciales de la aplicación móvil oficial de la marca.
3. Entidades expuestas: Nivel de batería, autonomía restante en km, estado del conector de carga, velocidad de carga (km/h y kW).

#### 🚗 Opción C: Renault / Dacia (Zoe, Megane E-Tech, Spring, 5 E-Tech)
1. Instala la integración **Renault** (integrada de forma nativa en el núcleo de Home Assistant).
2. Introduce tus credenciales de *My Renault* y selecciona tu vehículo por VIN.
3. Métricas disponibles: SoC, autonomía estimada, estado del cable, estado del cargador y control de climatización remota.

#### 🚗 Opción D: Dongle OBD-II / BLE y Lectura Directa de Celdas
- Si tu vehículo no cuenta con API en la nube o deseas leer datos directos de alta frecuencia (voltaje celda por celda, temperatura del pack en tiempo real):
  - Utiliza un dongle OBD-II Bluetooth Low Energy (BLE) o WiFi (ej. vLinker MC+, OBDLink CX).
  - Mediante apps como **Torque Pro** o **ABRP (A Better Routeplanner)**, puedes reenviar telemetría por Webhook a Home Assistant o Node-RED.

---

## 5. Paso 2: Configuración de InfluxDB 2.7 (Buckets y Tokens)

1. Accede a InfluxDB en: **`http://<IP-DE-TU-SERVIDOR>:8086`**.
2. Inicia sesión con el usuario y contraseña definidos en tu archivo `.env`.
3. Comprueba que el Bucket inicial `ev_telemetry` y la Organización `lavera` existen.

### 5.1 Generar un API Token de Acceso
1. En el menú lateral izquierdo de InfluxDB, ve a **Load Data** > **API Tokens**.
2. Haz clic en **Generate API Token** > **Custom API Token** (o *All-Access Token* para entornos de pruebas).
3. Asigna permisos: **Read / Write** en el bucket `ev_telemetry`.
4. Copia y guarda este Token para tus clientes externos y scripts.

---

## 6. Paso 3: Ingesta de Telemetría (Directa o vía Node-RED)

### Ingesta Directa de Home Assistant a InfluxDB
Agrega el siguiente bloque a tu archivo `configuration.yaml` de Home Assistant:

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

## 7. Paso 4: Pasarela Híbrida en Tiempo Real (Tesla Fleet & Tessie)

LaVera incluye un módulo independiente en [`ev-telemetry-hub/gateway/`](ev-telemetry-hub/gateway/) diseñado para ingesta continua de alta frecuencia:

1. **Tesla Fleet Provider (`tesla_fleet_provider.py`):**
   - Utiliza OAuth2 para autenticación contra `fleet-api.prd.na.vn.cloud.tesla.com` o endpoints europeos.
   - Implementa firma criptográfica de comandos mediante curva elíptica **ECDSA NIST P-256 / secp256r1**.
2. **Tessie Live Provider (`tessie_provider.py`):**
   - Extrae telemetría instantánea y sesiones de conducción con resolución de waypoints GPS.
3. **Gestor de Reposo Inteligente (`polling_manager.py`):**
   - Detecta si el coche está estacionado y reduce la cadencia de peticiones para permitir el reposo profundo (*Deep Sleep*).
4. **Inyector InfluxDB (`scripts/influx_telemetry_injector.py`):**
   - Permite inyectar flujos de telemetría continuos o por lotes hacia InfluxDB v2 mediante HTTP Line Protocol:
   ```bash
   python ev-telemetry-hub/scripts/influx_telemetry_injector.py
   ```

---

## 8. Paso 5: Rutas y Exportación Geográfica (GPX, KML y Google Maps)

Cada trayecto registrado o importado en LaVera almacena sus coordenadas de inicio y fin (`start_latitude`, `start_longitude`, `end_latitude`, `end_longitude`):

### 1. Exportación GPX 1.1
- **Endpoint:** `/api/drives/export?id=<ID>&format=gpx`
- Genera un archivo estándar XML con etiquetas `<trk>`, `<trkseg>` y `<trkpt lat="..." lon="...">`.
- Compatible con **Garmin BaseCamp / Connect**, **Strava**, **Komoot**, **OsmAnd** y pulsómetros deportivos.

### 2. Exportación KML 2.2
- **Endpoint:** `/api/drives/export?id=<ID>&format=kml`
- Genera un archivo OpenGIS KML con estructura `<LineString><coordinates>lon,lat,0 ...</coordinates></LineString>`.
- Permite abrir la trayectoria directamente en **Google Earth Pro** o visores GIS.

### 3. Enlace Directo a Google Maps
- Cada fila de la tabla de trayectos del panel web incluye un botón directo que abre Google Maps con la ruta exacta entre las coordenadas:
  `https://www.google.com/maps/dir/?api=1&origin=LAT,LON&destination=LAT,LON`

---

## 9. Paso 6: Dashboards y Métricas en Grafana

1. Accede a Grafana en: **`http://<IP-DE-TU-SERVIDOR>:3000`**.
2. Inicia sesión con el usuario `admin` y la contraseña de `.env`.

### Consultas Flux de Ejemplo

#### Estado de Batería Actual (Gauge)
```flux
from(bucket: "ev_telemetry")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "%" and r["entity_id"] =~ /.*battery.*/)
  |> filter(fn: (r) => r["_field"] == "value")
  |> last()
```

#### Curva de Potencia de Carga (kW)
```flux
from(bucket: "ev_telemetry")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r["_field"] == "value")
  |> filter(fn: (r) => r["entity_id"] =~ /.*charging_power.*/ or r["entity_id"] =~ /.*charger_power.*/)
  |> aggregateWindow(every: 1m, fn: mean, createEmpty: false)
  |> yield(name: "potencia_kw")
```

---

## 10. Paso 7: Mitigación del Vampire Drain (Consumo Parásito)

### Reglas de Oro contra el Vampire Drain:
1. **Dormir es sagrado:** Consulta la API del coche únicamente para leer los datos que la nube ya tiene almacenados (*Cached status*), sin forzar un comando de despertar (*Wake Up*).
2. **Polling dinámico según estado:**
   - **Vehículo cargando o en movimiento:** Intervalo de lectura frecuente (cada 30 a 60 segundos).
   - **Vehículo estacionado y durmiendo:** Detener las peticiones periódicas o aumentar el intervalo a 4 - 8 horas.
3. El módulo [`polling_manager.py`](ev-telemetry-hub/gateway/polling_manager.py) de LaVera implementa esta lógica de forma nativa.

---

## 11. Paso 8: Mantenimiento, Copias de Seguridad y Seguridad SSL

### Copias de Seguridad de los Datos
Todos los datos persistentes residen en el directorio `ev-telemetry-hub/data/`. Para crear un respaldo integral:

```bash
# 1. Detener los contenedores momentáneamente para garantizar consistencia
cd LaVera/ev-telemetry-hub
docker compose stop

# 2. Crear archivo comprimido con marca de tiempo
tar -czvf "backup_lavera_$(date +%Y%m%d_%H%M%S).tar.gz" data/ .env

# 3. Reanudar los contenedores
docker compose start
```

### Copia Nativa de InfluxDB
```bash
docker exec -it telemetry_influxdb influx backup /var/lib/influxdb2/backup -t "TU_INFLUX_TOKEN"
```

---

## 12. Solución de Problemas Frecuentes (FAQ / Troubleshooting)

### ❓ InfluxDB responde con "401 Unauthorized"
- Verifica que el token utilizado tenga permisos de lectura y escritura en el bucket `ev_telemetry` de la organización `lavera`.

### ❓ Grafana muestra "No Data" en los paneles
- Verifica que el rango temporal seleccionado (arriba a la derecha en Grafana) contenga mediciones (ej. selecciona `Last 24 hours` o `Last 7 days`).
- Comprueba que el nombre del `entity_id` en la consulta Flux coincida con el nombre real de tu sensor.

### ❓ ¿Cómo exportar un trayecto a GPX o KML?
- En el panel web (`http://localhost:8088`), ve a la sección de trayectos. En la columna de acciones encontrarás los botones **📍 GPX** y **🌐 KML** para descargar la ruta con un solo clic.
