# 📘 Guía Exhaustiva de Despliegue, Integración y Operación
## LaVera - Universal EV Telemetry Hub ⚡🚗

🌐 **Idioma / Language:** [English (GUIDE.md)](GUIDE.md) | **Español**

Esta guía describe detalladamente la puesta en marcha, integración multimarca de vehículos, ingesta de telemetría en series temporales y construcción de dashboards analíticos utilizando el stack Docker de **LaVera**.

---

## 📑 Tabla de Contenidos
1. [Arquitectura y Conceptos Clave](#1-arquitectura-y-conceptos-clave)
2. [Requisitos Previos y Entorno](#2-requisitos-previos-y-entorno)
3. [Instalación y Despliegue del Stack](#3-instalación-y-despliegue-del-stack)
4. [Paso 1: Extracción de Telemetría con Home Assistant](#4-paso-1-extracción-de-telemetría-con-home-assistant)
5. [Paso 2: Configuración de InfluxDB 2.7 (Buckets y Tokens)](#5-paso-2-configuración-de-influxdb-27-buckets-y-tokens)
6. [Paso 3: Ingesta de Telemetría (Directa o vía Node-RED)](#6-paso-3-ingesta-de-telemetría-directa-o-vía-node-red)
7. [Paso 4: Dashboards y Métricas en Grafana](#7-paso-4-dashboards-y-métricas-en-grafana)
8. [Paso 5: Mitigación del Vampire Drain (Consumo Parásito)](#8-paso-5-mitigación-del-vampire-drain-consumo-parásito)
9. [Paso 6: Mantenimiento, Copias de Seguridad y Seguridad SSL](#9-paso-6-mantenimiento-copias-de-seguridad-y-seguridad-ssl)
10. [Solución de Problemas Frecuentes (FAQ / Troubleshooting)](#10-solución-de-problemas-frecuentes-faq--troubleshooting)

---

## 1. Arquitectura y Conceptos Clave

El sistema opera bajo un pipeline modular de datos:
1. **Extracción:** Home Assistant actúa como gateway multimarca. Se conecta a las APIs de los fabricantes (Tesla Fleet, Renault Gigya, VAG We Connect, BYD, etc.) o a dongles OBD-II locales.
2. **Almacenamiento en Series Temporales:** InfluxDB almacena cada métrica con marca de tiempo precisa en nanosegundos, optimizado para consultas de alta resolución y downsampling.
3. **ETL y Orquestación:** Node-RED se encarga de transformaciones complejas de unidades, cruces con tarifas de electricidad (ej. precio por hora) y cálculos de coste por sesión.
4. **Visualización y Alertas:** Grafana consulta InfluxDB mediante Flux o InfluxQL y presenta métricas operativas y de salud de la batería.

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
- `8123` (Home Assistant)
- `8086` (InfluxDB)
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
INFLUX_USER=admin
INFLUX_PASS=EligeUnaContrasenaMuySegura2026!
INFLUX_ORG=EV_Telemetry
INFLUX_BUCKET=vehicle_data

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

Comprueba que todos los contenedores estén en estado `Up`:
```bash
docker compose ps
```

Para ver los registros en tiempo real:
```bash
docker compose logs -f
```

---

## 4. Paso 1: Extracción de Telemetría con Home Assistant

Accede a Home Assistant en: **`http://<IP-DE-TU-SERVIDOR>:8123`** y completa la creación del usuario administrador inicial.

### Instalación de Integraciones según la Marca de tu Vehículo

#### 🚗 Opción A: Tesla
1. **Integración Oficial (Tesla Fleet API):**
   - Requiere cuenta en el portal de desarrolladores de Tesla o usar integraciones comunitarias compatibles con Fleet API.
2. **Tesla Custom Integration (vía HACS):**
   - Es la integración comunitaria más popular para Home Assistant.
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

#### 🚗 Opción D: BYD (Atto 3, Dolphin, Seal, Tang, Han)
- Existen integraciones en HACS que interactúan con la nube de BYD o mediante módulos hardware locales (dongles con microcontroladores ESP32 con lectura CAN bus).

#### 🚗 Opción E: Dongle OBD-II / BLE y Lectura Directa de Celdas
- Si tu vehículo no cuenta con API en la nube o deseas leer datos directos de alta frecuencia (voltaje celda por celda, temperatura del pack en tiempo real):
  - Utiliza un dongle OBD-II Bluetooth Low Energy (BLE) o WiFi (ej. vLinker MC+, OBDLink CX).
  - Mediante apps como **Torque Pro** o **ABRP (A Better Routeplanner)**, puedes reenviar telemetría por Webhook a Home Assistant o Node-RED.
  - Alternativamente, un módulo ESP32 conectado al puerto OBD2 puede publicar las tramas CAN decodificadas directamente a un broker MQTT conectado con Home Assistant.

#### 🔌 Cargador Doméstico (Wallbox, OCPP, Shelly EM)
Integrar tu punto de recarga en Home Assistant permite calcular pérdidas de eficiencia:
$$\text{Pérdida en recarga (\%)} = \left(1 - \frac{\Delta \text{Energía almacenada en batería}}{\text{Energía entregada por el cargador}}\right) \times 100$$

---

## 5. Paso 2: Configuración de InfluxDB 2.7 (Buckets y Tokens)

1. Accede a InfluxDB en: **`http://<IP-DE-TU-SERVIDOR>:8086`**.
2. Inicia sesión con el usuario y contraseña definidos en tu archivo `.env` (`INFLUX_USER` y `INFLUX_PASS`).
3. Comprueba que el Bucket inicial `vehicle_data` y la Organización `EV_Telemetry` ya existen.

### 5.1 Generar un API Token de Acceso
1. En el menú lateral izquierdo de InfluxDB, ve a **Load Data** > **API Tokens**.
2. Haz clic en **Generate API Token** > **Custom API Token** (o *All-Access Token* para entornos de pruebas).
3. Asigna permisos:
   - **Read / Write** en el bucket `vehicle_data`.
4. Añade una descripción (ej. `HomeAssistant-LaVera-Token`) y pulsa **Generate**.
5. **Copia y guarda este Token:** Lo necesitarás en los siguientes pasos.

### 5.2 Política de Retención (Retention Policies)
- Por defecto, el bucket `vehicle_data` almacena datos de forma indefinida.
- Para evitar que la base de datos crezca sin control a lo largo de varios años, puedes configurar la retención en:
  - **Load Data** > **Buckets** > En `vehicle_data` haz clic en **Settings** > **Delete data older than** > ej. `90 days` o `180 days`.

---

## 6. Paso 3: Ingesta de Telemetría (Directa o vía Node-RED)

### Opción A: Ingesta Directa de Home Assistant a InfluxDB (Recomendada)

1. Abre el archivo de configuración de Home Assistant ubicado en el volumen del host:
   `ev-telemetry-hub/data/homeassistant/configuration.yaml`
2. Agrega el siguiente bloque al final del archivo:

```yaml
# Conexión InfluxDB v2 para Telemetría de Vehículo Eléctrico
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
  # Filtrar solo entidades relevantes de telemetría para optimizar espacio y rendimiento
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

3. Crea o edita el archivo `ev-telemetry-hub/data/homeassistant/secrets.yaml` y añade el token generado en el paso 5.1:
```yaml
influxdb_token: "TU_API_TOKEN_DE_INFLUXDB_AQUI"
```

4. Reinicia Home Assistant desde la interfaz web (**Ajustes** > **Sistema** > **Reiniciar**) o mediante Docker:
```bash
docker compose restart homeassistant
```

---

### Opción B: Ingesta y Lógica Avanzada con Node-RED

Si deseas manipular las métricas antes de guardarlas (convertir unidades, clasificar sesiones de carga por tramos horarios de electricidad o calcular costes monetarios):

1. Accede a Node-RED en: **`http://<IP-DE-TU-SERVIDOR>:1880`**.
2. En el menú de hamburguesa (arriba a la derecha), ve a **Manage palette** > pestaña **Install**.
3. Instala los paquetes:
   - `node-red-contrib-home-assistant-websocket`
   - `node-red-contrib-influxdb`
4. Configura el nodo de InfluxDB con:
   - **Version:** `2.0`
   - **URL:** `http://influxdb:8086`
   - **Token:** Tu token de InfluxDB.
   - **Organization:** `EV_Telemetry`
   - **Bucket:** `vehicle_data`
5. Diseña un flujo que escuche los eventos de cambio de estado de tu vehículo y escriba mediciones etiquetadas (*measurements*) con nombres limpios como `battery_soc`, `charging_kw`, `session_cost`.

---

## 7. Paso 4: Dashboards y Métricas en Grafana

1. Accede a Grafana en: **`http://<IP-DE-TU-SERVIDOR>:3000`**.
2. Inicia sesión con el usuario `admin` y la contraseña `GRAFANA_PASS` que configuraste en tu `.env`.

### 7.1 Configurar el Data Source de InfluxDB
1. Ve a **Connections** > **Data sources** > **Add data source**.
2. Selecciona **InfluxDB**.
3. Completa los campos:
   - **Query Language:** `Flux`
   - **URL:** `http://influxdb:8086` *(nombre del servicio en la red Docker)*
   - **Custom HTTP Headers:** Desactivado.
   - **Auth:** Desactivar Basic Auth.
   - **InfluxDB Details:**
     - **Organization:** `EV_Telemetry`
     - **Token:** *(Tu API Token generado en InfluxDB)*
     - **Default Bucket:** `vehicle_data`
4. Haz clic en **Save & test**. Debe mostrar una notificación verde confirmando la conexión exitosa.

---

### 7.2 Consultas Flux de Ejemplo para tus Paneles

Crea un nuevo Dashboard (**Dashboards** > **New Dashboard** > **Add visualization**):

#### Panel 1: Estado de Batería Actual (Gauge / Indicador)
```flux
from(bucket: "vehicle_data")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "%" and r["entity_id"] =~ /.*battery.*/)
  |> filter(fn: (r) => r["_field"] == "value")
  |> last()
```
*Visualización recomendada:* **Gauge** (Umbrales: Rojo < 20%, Amarillo 20-50%, Verde 50-80%, Azul 80-100%).

---

#### Panel 2: Curva de Potencia de Carga en Tiempo Real (kW)
```flux
from(bucket: "vehicle_data")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r["_field"] == "value")
  |> filter(fn: (r) => r["entity_id"] =~ /.*charging_power.*/ or r["entity_id"] =~ /.*charger_power.*/)
  |> aggregateWindow(every: 1m, fn: mean, createEmpty: false)
  |> yield(name: "potencia_kw")
```
*Visualización recomendada:* **Time series**.

---

#### Panel 3: Evolución del Odómetro y Kilómetros Recorridos
```flux
from(bucket: "vehicle_data")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r["_field"] == "value")
  |> filter(fn: (r) => r["entity_id"] =~ /.*odometer.*/)
  |> aggregateWindow(every: 1d, fn: max, createEmpty: false)
```
*Visualización recomendada:* **Bar chart** o **Stat**.

---

#### Panel 4: Mapa de Ubicación y Trayectorias
Si Home Assistant envía la entidad `device_tracker` del vehículo:
```flux
from(bucket: "vehicle_data")
  |> range(start: -7d)
  |> filter(fn: (r) => r["entity_id"] =~ /.*device_tracker.*/)
  |> filter(fn: (r) => r["_field"] == "latitude" or r["_field"] == "longitude")
  |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
```
*Visualización recomendada:* Panel **Geomap**.

---

## 8. Paso 5: Mitigación del Vampire Drain (Consumo Parásito)

Uno de los problemas más frecuentes al monitorizar un vehículo eléctrico mediante llamadas a API en la nube es el **agotamiento innecesario de la batería auxiliar de 12V y del paquete principal**. Si un script consulta al vehículo cada minuto, la centralita del coche nunca puede entrar en reposo (*Deep Sleep*).

### Reglas de Oro contra el Vampire Drain:
1. **Dormir es sagrado:** Consulta la API del coche únicamente para leer los datos que la nube ya tiene almacenados (*Cached status*), sin forzar un comando de despertar (*Wake Up*).
2. **Polling dinámico según estado:**
   - **Vehículo cargando o en movimiento:** Intervalo de lectura frecuente (cada 30 a 60 segundos).
   - **Vehículo estacionado y durmiendo:** Detener las peticiones periódicas o aumentar el intervalo a 4 - 8 horas.
3. **Automatización en Home Assistant:** Puedes crear una automatización que desactive la entidad de sondeo o aumente su tiempo de espera cuando el sensor `is_asleep` o `car_state` sea `asleep`.

---

## 9. Paso 6: Mantenimiento, Copias de Seguridad y Seguridad SSL

### 9.1 Copias de Seguridad de los Datos
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

### 9.2 Copia Nativa de InfluxDB
Para realizar un backup en caliente sin detener InfluxDB:
```bash
docker exec -it telemetry_influxdb influx backup /var/lib/influxdb2/backup -t "TU_INFLUX_TOKEN"
```

### 9.3 Acceso Remoto Seguro con HTTPS
Para acceder de forma segura a tus paneles de Grafana o Home Assistant desde el móvil sin abrir puertos inseguros en tu router:
- **Opción recomendada:** Instala **Cloudflare Tunnel (cloudflared)** o **Tailscale**.
- **Opción estándar:** Configura un Proxy Inverso (Nginx Proxy Manager, Caddy o Traefik) con certificados SSL gratuitos emitidos por Let's Encrypt.

---

## 10. Solución de Problemas Frecuentes (FAQ / Troubleshooting)

### ❓ InfluxDB responde con "401 Unauthorized"
- **Causa:** El token utilizado en Home Assistant, Node-RED o Grafana es incorrecto o no tiene permisos de lectura/escritura en el bucket `vehicle_data`.
- **Solución:** Entra a la interfaz de InfluxDB (`http://localhost:8086`) con el usuario administrador, genera un nuevo token con permisos explícitos sobre la organización y el bucket, y actualiza la configuración.

### ❓ Grafana muestra "No Data" en los paneles
- Verifica que el rango temporal seleccionado (arriba a la derecha en Grafana) contenga mediciones (ej. selecciona `Last 24 hours` o `Last 7 days`).
- Comprueba que el nombre del `entity_id` en la consulta Flux coincida con el nombre real de tu sensor en Home Assistant (ve a **Herramientas para desarrolladores** > **Estados** en Home Assistant para verificar el identificador exacto).

### ❓ Error de permisos en la carpeta `data/` en sistemas Linux
- Si algún contenedor no puede escribir datos en disco, ajusta la propiedad del directorio al usuario UID `1000`:
  ```bash
  sudo chown -R 1000:1000 data/
  ```

### ❓ ¿Cómo añadir más servicios (ej. Mosquitto MQTT o Teslamate)?
- Puedes incorporar fácilmente un servicio adicional en [docker-compose.yml](file:///c:/Users/castor/Documents/GitHub/LaVera/ev-telemetry-hub/docker-compose.yml) conectándolo a la misma red `telemetry_net`.
