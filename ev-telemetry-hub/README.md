# ⚡ Universal EV Telemetry Hub

Una arquitectura autohospedada basada en Docker para la extracción, normalización y visualización de telemetría de vehículos eléctricos (Tesla, VW, BYD, Renault, etc.).

## 🚀 Cómo ejecutar (Despliegue Rápido)

1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/tu-usuario/ev-telemetry-hub.git
   cd ev-telemetry-hub
   ```

2. **Configurar credenciales:**
   ```bash
   cp .env.example .env
   ```
   *(Edita el archivo `.env` con tus contraseñas preferidas).*

3. **Levantar los contenedores:**
   ```bash
   docker compose up -d
   ```

4. **Acceso a los Servicios:**
   - Home Assistant: `http://localhost:8123`
   - Grafana: `http://localhost:3000`
   - Node-RED: `http://localhost:1880`
   - InfluxDB: `http://localhost:8086`
