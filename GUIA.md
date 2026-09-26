# 📘 Guía Exhaustiva de Despliegue, Integración y Operación
## LaVera - Universal EV Telemetry Hub ⚡🚗

🌐 **Idioma / Language:** [English (GUIDE.md)](GUIDE.md) | **Español**

Esta guía describe detalladamente la puesta en marcha, integración multimarca de vehículos, ingesta de telemetría en series temporales, diccionario completo de métricas en tiempo real, exportación de rutas geográficas y construcción de dashboards analíticos utilizando el stack Docker de **LaVera**.

---

## 📑 Tabla de Contenidos
1. [Arquitectura y Conceptos Clave](#1-arquitectura-y-conceptos-clave)
2. [Requisitos Previos y Entorno](#2-requisitos-previos-y-entorno)
3. [Instalación y Despliegue del Stack](#3-instalación-y-despliegue-del-stack)
4. [Paso 1: Extracción de Telemetría con Home Assistant](#4-paso-1-extracción-de-telemetría-con-home-assistant)
5. [Paso 2: Configuración de InfluxDB 2.7 (Buckets y Tokens)](#5-paso-2-configuración-de-influxdb-27-buckets-y-tokens)
6. [Paso 3: Diccionario de Datos de Telemetría en Tiempo Real (Tags vs Fields)](#6-paso-3-diccionario-de-datos-de-telemetría-en-tiempo-real-tags-vs-fields)
7. [Paso 4: Ingesta de Telemetría (Directa o vía Node-RED)](#7-paso-4-ingesta-de-telemetría-directa-o-vía-node-red)
8. [Paso 5: Pasarela Híbrida en Tiempo Real (Tesla Fleet & Tessie)](#8-paso-5-pasarela-híbrida-en-tiempo-real-tesla-fleet--tessie)
9. [Paso 6: Rutas y Exportación Geográfica (GPX, KML y Google Maps)](#9-paso-6-rutas-y-exportación-geográfica-gpx-kml-y-google-maps)
10. [Paso 7: Dashboards y Métricas en Grafana](#10-paso-7-dashboards-y-métricas-en-grafana)
11. [Paso 8: Mitigación del Vampire Drain (Consumo Parásito)](#11-paso-8-mitigación-del-vampire-drain-consumo-parásito)
12. [Paso 9: Mantenimiento, Copias de Seguridad y Seguridad SSL](#12-paso-9-mantenimiento-copias-de-seguridad-y-seguridad-ssl)
13. [Solución de Problemas Frecuentes (FAQ / Troubleshooting)](#13-solución-de-problemas-frecuentes-faq--troubleshooting)

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
1. **Integración Oficial (Tesla Fleet API):** Requiere cuenta en el portal de desarrolladores de Tesla o usar integraciones comunitarias compatibles con Fleet API.
2. **Tesla Custom Integration (vía HACS):** Permite consultar SoC, ubicación, estado de las puertas, presión de neumáticos, temperatura interna/externa y estado de carga. Configura un intervalo de descanso (*Sleep interval*) de al menos 15-21 minutos.

#### 🚗 Opción B: Grupo VAG (Volkswagen ID, Cupra, Škoda, Audi)
1. Instala la integración **Volkswagen We Connect ID** o **MyCupra / Skoda Connect** (disponibles en HACS).
2. Entidades expuestas: Nivel de batería, autonomía restante en km, estado del conector de carga, velocidad de carga (km/h y kW).

#### 🚗 Opción C: Renault / Dacia (Zoe, Megane E-Tech, Spring, 5 E-Tech)
1. Instala la integración **Renault** (integrada de forma nativa en el núcleo de Home Assistant).
2. Introduce tus credenciales de *My Renault* y selecciona tu vehículo por VIN.

#### 🚗 Opción D: Dongle OBD-II / BLE y Lectura Directa de Celdas
- Utiliza un dongle OBD-II Bluetooth Low Energy (BLE) o WiFi (ej. vLinker MC+, OBDLink CX) para reenviar telemetría por Webhook a Home Assistant o Node-RED.

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

## 6. Paso 3: Diccionario de Datos de Telemetría en Tiempo Real (Tags vs Fields)

Para estructurar de manera óptima la base de datos de series temporales (InfluxDB v2 / TimescaleDB) y habilitar consultas de alto rendimiento en Grafana, LaVera aplica una separación estricta:

> [!TIP]
> **Regla de Diseño para Series Temporales:**
> - **Tags (Índices):** Valores de tipo `string` y `boolean` de baja cardinalidad (ej. `shift_state`, `charging_state`, `locked`, `sentry_mode`, `is_climate_on`). Se almacenan en el índice invertido de InfluxDB para filtrado instantáneo por facetas y agrupaciones (`group by`).
> - **Fields (Valores de Series Temporales):** Todos los valores numéricos `int` o `float` (ej. `power`, `speed`, `odometer`, `inside_temp`, `charger_voltage`). Permiten generar gráficos continuos de líneas, agregaciones temporales (`mean`, `max`, `min`), derivadas de velocidad e integrales de consumo energético en el tiempo.

### 1. 🔋 `charge_state` (Energía y Batería)
Engloba todo lo relacionado con el Battery Management System (BMS), recargas y autonomías:

| Parámetro | Tipo | Clasificación | Unidad | Descripción |
| :--- | :--- | :--- | :--- | :--- |
| `battery_level` | `int` | **Field** | `%` | Porcentaje actual de carga de la batería (SoC reportado). |
| `usable_battery_level` | `int` | **Field** | `%` | Porcentaje real utilizable (descuenta la energía bloqueada por batería fría). |
| `charge_limit_soc` | `int` | **Field** | `%` | Límite de carga configurado en la pantalla del coche (ej. 80% o 100%). |
| `battery_range` | `float` | **Field** | `km` / `mi` | Autonomía estimada basada en el estándar oficial del vehículo. |
| `charging_state` | `string` | **Tag** | — | Estado de carga (`Disconnected`, `Charging`, `Complete`, `Stopped`, `NoPower`). |
| `charge_port_door_open` | `boolean` | **Tag** | — | Tapa del puerto de carga abierta (`true` / `false`). |
| `charge_port_latch` | `string` | **Tag** | — | Bloqueo físico de seguridad del cable (`Engaged`, `Disengaged`). |
| `conn_charge_cable` | `string` | **Tag** | — | Tipo de conector o cable acoplado (`SAE`, `IEC`, `CCS`, `<none>`). |
| `charger_voltage` | `int` | **Field** | `V` | Voltaje de entrada de la red eléctrica. |
| `charger_actual_current` | `int` | **Field** | `A` | Amperaje real que está fluyendo en este momento hacia el vehículo. |
| `charge_current_request` | `int` | **Field** | `A` | Amperaje solicitado por el usuario o centralita. |
| `charge_current_request_max` | `int` | **Field** | `A` | Amperaje máximo permitido por la instalación eléctrica. |
| `charger_power` | `int` | **Field** | `kW` | Potencia instantánea de carga entregada. |
| `charge_energy_added` | `float` | **Field** | `kWh` | Total de energía inyectada en la sesión de carga actual. |
| `time_to_full_charge` | `float` | **Field** | `h` | Horas estimadas restantes para alcanzar el límite configurado. |
| `battery_heater_on` | `boolean` | **Tag** | — | Preacondicionamiento térmico de la batería en curso (`true` / `false`). |
| `fast_charger_present` | `boolean` | **Tag** | — | Conexión activa a una estación de carga en corriente continua (DC / Supercharger). |

---

### 2. 🌡️ `climate_state` (Climatización y Sensores)
Monitoriza temperaturas y estado del HVAC del habitáculo:

| Parámetro | Tipo | Clasificación | Unidad | Descripción |
| :--- | :--- | :--- | :--- | :--- |
| `inside_temp` | `float` | **Field** | `°C` | Temperatura ambiente medida en el interior de la cabina. |
| `outside_temp` | `float` | **Field** | `°C` | Temperatura exterior medida por el termómetro frontal del coche. |
| `driver_temp_setting` | `float` | **Field** | `°C` | Temperatura consigna configurada para el conductor. |
| `passenger_temp_setting` | `float` | **Field** | `°C` | Temperatura consigna configurada para el acompañante. |
| `is_climate_on` | `boolean` | **Tag** | — | Sistema global de climatización en funcionamiento (`true` / `false`). |
| `is_auto_conditioning_on` | `boolean` | **Tag** | — | Climatizador operando en modo automático (`true` / `false`). |
| `fan_status` | `int` | **Field** | `0 - 7` | Velocidad actual del ventilador de la cabina. |
| `climate_keeper_mode` | `string` | **Tag** | — | Modo de mantenimiento del clima (`off`, `keep`, `dog`, `camp`). |
| `defrost_mode` | `int` | **Field** | `0 - 2` | Nivel de desempañado/descongelación activo (0=off, 1=normal, 2=max). |
| `seat_heater_left` / `right` | `int` | **Field** | `0 - 3` | Nivel de calefacción en asientos delanteros. |
| `seat_heater_rear_left` / etc. | `int` | **Field** | `0 - 3` | Nivel de calefacción en asientos traseros. |
| `steering_wheel_heater` | `boolean` | **Tag** | — | Calefacción del volante encendida (`true` / `false`). |
| `cabin_overheat_protection` | `string` | **Tag** | — | Protección contra sobrecalentamiento del habitáculo (`On`, `Off`, `FanOnly`). |

---

### 3. 🛣️ `drive_state` (Dinámica y Geolocalización)
Datos posicionales y telemetría de movimiento en tiempo real:

| Parámetro | Tipo | Clasificación | Unidad | Descripción |
| :--- | :--- | :--- | :--- | :--- |
| `shift_state` | `string` | **Tag** | — | Posición de la transmisión (`P`, `R`, `N`, `D`). Nulo si el coche duerme. |
| `speed` | `int` | **Field** | `km/h` | Velocidad instantánea de desplazamiento. |
| `power` | `int` | **Field** | `kW` | Potencia instantánea: positivo al acelerar (consumo), negativo al frenar (regeneración). |
| `latitude` | `float` | **Field** | `deg` | Coordenada GPS de latitud en grados decimales (WGS84). |
| `longitude` | `float` | **Field** | `deg` | Coordenada GPS de longitud en grados decimales (WGS84). |
| `heading` | `int` | **Field** | `0 - 359` | Rumbo de dirección en grados respecto al norte. |
| `gps_as_of` | `int` | **Field** | `UNIX s` | Marca de tiempo UNIX de la última coordenada válida recibida. |
| `active_route_destination` | `string` | **Tag** | — | Nombre del destino si hay navegación activa en el mapa. |
| `active_route_energy_at_arrival` | `int` | **Field** | `%` | Porcentaje estimado de SoC al llegar al destino. |
| `active_route_traffic_minutes_delay` | `float` | **Field** | `min` | Retraso estimado debido al tráfico en la ruta activa. |

---

### 4. 🚘 `vehicle_state` (Hardware, Carrocería y Seguridad)
Sensores físicos, integridad del habitáculo e información estática del vehículo:

| Parámetro | Tipo | Clasificación | Unidad | Descripción |
| :--- | :--- | :--- | :--- | :--- |
| `odometer` | `float` | **Field** | `km` | Kilometraje acumulado histórico total. |
| `locked` | `boolean` | **Tag** | — | Estado de los cierres centralizados (cerrado = `true`, abierto = `false`). |
| `sentry_mode` | `boolean` | **Tag** | — | Vigilancia de seguridad activa del Modo Centinela (`true` / `false`). |
| `is_user_present` | `boolean` | **Tag** | — | Detección de presencia física en el asiento del conductor (`true` / `false`). |
| `df`, `pf`, `dr`, `pr` | `int` | **Field** | `0 / 1` | Apertura física de puertas (Driver Front, Passenger Front, Traseras). |
| `fd_window`, `fp_window`, etc. | `int` | **Field** | `0 / 1` | Estado de apertura de ventanillas individuales. |
| `ft` / `rt` | `int` | **Field** | `0 / 1` | Apertura de maletero delantero (*frunk*) y trasero (*trunk*). |
| `tpms_pressure_fl` / `fr` / `rl` / `rr` | `float` | **Field** | `Bar` | Presión individual de cada neumático (TPMS). |
| `center_display_state` | `int` | **Field** | `0 - 2` | Estado de la pantalla táctil principal (0=off, 2=on). |
| `car_version` | `string` | **Tag** | — | Versión de software embarcada (ej. `2024.14.9`). |
| `software_update.status` | `string` | **Tag** | — | Estado del ciclo de actualización OTA (`available`, `installing`, `""`). |

---

### 5. 📡 Fleet Telemetry / Diagnósticos Avanzados
Parámetros recogidos del flujo de alta frecuencia de Tesla Fleet Telemetry (WebSocket/MQTT) o diagnósticos de Tessie:

| Parámetro | Tipo | Clasificación | Unidad | Descripción |
| :--- | :--- | :--- | :--- | :--- |
| `BmsFullchargecomplete` | `boolean` | **Tag** | — | Indica si el BMS completó el 100% de la carga para balanceo y calibración de celdas. |
| `BrakePedalPos` | `float` | **Field** | `%` | Presión física ejercida en el cilindro del pedal de freno en tiempo real. |
| `ACChargingEnergyIn` | `float` | **Field** | `kWh` | Cómputo exacto de energía AC recibida a nivel de batería desde el cargador. |
| `DCChargingEnergyIn` | `float` | **Field** | `kWh` | Cómputo exacto de energía DC recibida a nivel de batería (carga rápida). |
| `BrickVoltageMax` | `float` | **Field** | `V` | Tensión máxima detectada en los clústers de celdas internas del pack. |
| `BrickVoltageMin` | `float` | **Field** | `V` | Tensión mínima detectada en los clústers (diferencial clave para evaluar desbalanceo). |
| `DiInverterTR` | `float` | **Field** | `°C` | Temperatura del inversor del motor de tracción trasero. |
| `DiInverterTF` | `float` | **Field** | `°C` | Temperatura del inversor del motor de tracción delantero. |

---

## 7. Paso 4: Ingesta de Telemetría (Directa o vía Node-RED)

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

## 8. Paso 5: Pasarela Híbrida en Tiempo Real (Tesla Fleet & Tessie)

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

## 9. Paso 6: Rutas y Exportación Geográfica (GPX, KML y Google Maps)

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

## 10. Paso 7: Dashboards y Métricas en Grafana

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

## 11. Paso 8: Mitigación del Vampire Drain (Consumo Parásito)

### Reglas de Oro contra el Vampire Drain:
1. **Dormir es sagrado:** Consulta la API del coche únicamente para leer los datos que la nube ya tiene almacenados (*Cached status*), sin forzar un comando de despertar (*Wake Up*).
2. **Polling dinámico según estado:**
   - **Vehículo cargando o en movimiento:** Intervalo de lectura frecuente (cada 30 a 60 segundos).
   - **Vehículo estacionado y durmiendo:** Detener las peticiones periódicas o aumentar el intervalo a 4 - 8 horas.
3. El módulo [`polling_manager.py`](ev-telemetry-hub/gateway/polling_manager.py) de LaVera implementa esta lógica de forma nativa.

---

## 12. Paso 9: Mantenimiento, Copias de Seguridad y Seguridad SSL

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

## 13. Solución de Problemas Frecuentes (FAQ / Troubleshooting)

### ❓ InfluxDB responde con "401 Unauthorized"
- Verifica que el token utilizado tenga permisos de lectura y escritura en el bucket `ev_telemetry` de la organización `lavera`.

### ❓ Grafana muestra "No Data" en los paneles
- Verifica que el rango temporal seleccionado (arriba a la derecha en Grafana) contenga mediciones (ej. selecciona `Last 24 hours` o `Last 7 days`).
- Comprueba que el nombre del `entity_id` en la consulta Flux coincida con el nombre real de tu sensor.

### ❓ ¿Cómo exportar un trayecto a GPX o KML?
- En el panel web (`http://localhost:8088`), ve a la sección de trayectos. En la columna de acciones encontrarás los botones **📍 GPX** y **🌐 KML** para descargar la ruta con un solo clic.
