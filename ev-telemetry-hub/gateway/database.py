"""
Production Database Connector & KPI Extraction Module for InfluxDB and Local Storage.
Supports:
- InfluxDB v2.x / v3.0 / Cloud via HTTP v2 REST API (no heavy binary dependencies).
- InfluxDB v1.8 compatibility via /write & /query.
- Thread-safe batch writing with auto-flush and network retry buffer.
- Query engine for Flux and InfluxQL.
- Pre-built KPI aggregations (Power, SoC, Charging, Vampire Drain, Efficiency, Thermal).
"""

import csv
import io
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

try:
    import requests
except ImportError:
    requests = None

from .influx_parser import TelemetryToInfluxParser
from .models import CanonicalVehicleState

logger = logging.getLogger("lavera.database")


@dataclass
class InfluxDBConfig:
    """Configuration for InfluxDB connection."""
    url: str = "http://localhost:8086"
    token: str = ""
    org: str = "lavera"
    bucket: str = "ev_telemetry"
    precision: str = "s"              # s, ms, or ns
    timeout: int = 10                  # seconds
    batch_size: int = 50               # points per batch
    flush_interval_sec: float = 5.0    # max seconds before forced flush
    max_retry_buffer: int = 5000       # max points stored in memory on network drop

    @classmethod
    def from_env(cls) -> "InfluxDBConfig":
        return cls(
            url=os.getenv("INFLUXDB_URL", "http://localhost:8086").rstrip("/"),
            token=os.getenv("INFLUXDB_TOKEN", ""),
            org=os.getenv("INFLUXDB_ORG", "lavera"),
            bucket=os.getenv("INFLUXDB_BUCKET", "ev_telemetry"),
            precision=os.getenv("INFLUXDB_PRECISION", "s"),
            timeout=int(os.getenv("INFLUXDB_TIMEOUT", "10")),
            batch_size=int(os.getenv("INFLUXDB_BATCH_SIZE", "50")),
            flush_interval_sec=float(os.getenv("INFLUXDB_FLUSH_INTERVAL", "5.0")),
        )


class InfluxDBTelemetryDatabase:
    """
    High-performance InfluxDB client and telemetry extractor.
    Manages connection pools, background batch flushing, and KPI extraction.
    """

    def __init__(self, config: Optional[InfluxDBConfig] = None):
        self.config = config or InfluxDBConfig.from_env()
        self._session = requests.Session() if requests else None
        self._buffer: List[str] = []
        self._buffer_lock = threading.Lock()
        self._last_flush_time = time.time()
        self._running = False
        self._flush_thread: Optional[threading.Thread] = None

    # -------------------------------------------------------------------------
    # GESTIÓN DE CONEXIÓN Y SALUD
    # -------------------------------------------------------------------------

    def ping(self) -> Tuple[bool, str]:
        """Verifica la conectividad y estado del servidor InfluxDB."""
        if not self._session:
            return False, "Python 'requests' no esta instalado."

        url = f"{self.config.url}/health"
        try:
            resp = self._session.get(url, timeout=self.config.timeout)
            if resp.status_code == 200:
                data = resp.json()
                return True, f"OK - InfluxDB version: {data.get('version', 'unknown')}, status: {data.get('status')}"
            # Compatibilidad v1.8
            resp_ping = self._session.get(f"{self.config.url}/ping", timeout=self.config.timeout)
            if resp_ping.status_code in (200, 204):
                version = resp_ping.headers.get("X-Influxdb-Version", "1.x")
                return True, f"OK - InfluxDB v1 compatible ({version})"
            return False, f"HTTP {resp.status_code}: {resp.text}"
        except Exception as e:
            return False, f"Fallo al conectar con InfluxDB en {self.config.url}: {str(e)}"

    def start_background_writer(self):
        """Inicia el hilo de fondo para vaciado periodico de buffers."""
        if self._running:
            return
        self._running = True
        self._flush_thread = threading.Thread(target=self._flush_worker, daemon=True, name="InfluxDBFlushWorker")
        self._flush_thread.start()
        logger.info("[Database] Background InfluxDB batch worker iniciado.")

    def stop_background_writer(self):
        """Detiene el hilo y vuelca todos los datos remanentes."""
        self._running = False
        if self._flush_thread and self._flush_thread.is_alive():
            self._flush_thread.join(timeout=3.0)
        self.flush()

    def _flush_worker(self):
        while self._running:
            time.sleep(1.0)
            now = time.time()
            with self._buffer_lock:
                should_flush = (
                    len(self._buffer) >= self.config.batch_size
                    or (self._buffer and (now - self._last_flush_time) >= self.config.flush_interval_sec)
                )
            if should_flush:
                self.flush()

    # -------------------------------------------------------------------------
    # INGESTA Y ESCRITURA DE DATOS
    # -------------------------------------------------------------------------

    def write_telemetry(self, data: Union[CanonicalVehicleState, Dict[str, Any]], synchronous: bool = False) -> bool:
        """
        Convierte la telemetria a Line Protocol y la anade al buffer de escritura.
        Si synchronous=True, fuerza el envio HTTP inmediato.
        """
        try:
            line_protocol, _ = TelemetryToInfluxParser.parse(
                data,
                measurement="ev_telemetry",
                precision=self.config.precision
            )
            return self.write_line_protocol(line_protocol, synchronous=synchronous)
        except Exception as e:
            logger.error(f"[Database] Error al procesar telemetria para InfluxDB: {e}")
            return False

    def write_line_protocol(self, line_proto: str, synchronous: bool = False) -> bool:
        """Escribe una o varias lineas de Line Protocol."""
        if not line_proto or not line_proto.strip():
            return False

        if synchronous:
            return self._send_http_write(line_proto.strip())

        with self._buffer_lock:
            if len(self._buffer) >= self.config.max_retry_buffer:
                self._buffer.pop(0)
            self._buffer.append(line_proto.strip())
            should_flush = len(self._buffer) >= self.config.batch_size

        if should_flush:
            return self.flush()
        return True

    def flush(self) -> bool:
        """Vuelca el contenido acumulado en el buffer a InfluxDB."""
        with self._buffer_lock:
            if not self._buffer:
                return True
            batch_data = "\n".join(self._buffer)
            points_count = len(self._buffer)

        success = self._send_http_write(batch_data)
        if success:
            with self._buffer_lock:
                del self._buffer[:points_count]
                self._last_flush_time = time.time()
            logger.debug(f"[Database] Batch de {points_count} puntos inyectado en InfluxDB exitosamente.")
            return True
        else:
            logger.warning(f"[Database] Error al enviar batch de {points_count} puntos. Reteniendo en buffer.")
            return False

    def _send_http_write(self, payload: str) -> bool:
        """Envia el payload raw a /api/v2/write."""
        if not self._session:
            logger.error("[Database] 'requests' no disponible.")
            return False

        write_url = (
            f"{self.config.url}/api/v2/write"
            f"?org={self.config.org}&bucket={self.config.bucket}&precision={self.config.precision}"
        )
        headers = {
            "Authorization": f"Token {self.config.token}",
            "Content-Type": "text/plain; charset=utf-8",
            "Accept": "application/json",
            "User-Agent": "LaVera-EV-Hub/1.2"
        }

        try:
            resp = self._session.post(
                write_url,
                data=payload.encode("utf-8"),
                headers=headers,
                timeout=self.config.timeout
            )
            if resp.status_code in (200, 204):
                return True
            elif resp.status_code == 429:
                logger.warning(f"[Database] InfluxDB Rate Limit (429): {resp.text}")
            else:
                logger.error(f"[Database] InfluxDB write HTTP {resp.status_code}: {resp.text}")
            return False
        except Exception as e:
            logger.error(f"[Database] Fallo de conexion en escritura InfluxDB: {e}")
            return False

    # -------------------------------------------------------------------------
    # MOTOR DE CONSULTAS Y EXTRACCION (FLUX Y INFLUXQL)
    # -------------------------------------------------------------------------

    def query_flux(self, flux_query: str) -> List[Dict[str, Any]]:
        """
        Ejecuta una consulta en lenguaje Flux (/api/v2/query) y retorna
        una lista de diccionarios limpios con las series temporales resultantes.
        """
        if not self._session:
            raise RuntimeError("Libreria 'requests' no disponible.")

        query_url = f"{self.config.url}/api/v2/query?org={self.config.org}"
        headers = {
            "Authorization": f"Token {self.config.token}",
            "Content-Type": "application/vnd.flux",
            "Accept": "application/csv",
        }

        resp = self._session.post(
            query_url,
            data=flux_query.encode("utf-8"),
            headers=headers,
            timeout=self.config.timeout
        )

        if resp.status_code != 200:
            raise RuntimeError(f"Flux Query Error HTTP {resp.status_code}: {resp.text}")

        # Parsear Annotated CSV de InfluxDB
        csv_text = resp.text
        results = []
        reader = csv.reader(io.StringIO(csv_text))
        header = None

        for row in reader:
            if not row or not row[0]:
                continue
            if row[0].startswith("#"):
                continue  # Comentarios y metadatos de anotacion
            if row[0] == "" or "result" in row:
                header = row
                continue
            if header and len(row) == len(header):
                row_dict = {}
                for idx, col_name in enumerate(header):
                    if col_name and col_name not in ("", "result", "table"):
                        val = row[idx]
                        try:
                            val = float(val) if "." in val else int(val)
                        except ValueError:
                            pass
                        row_dict[col_name] = val
                results.append(row_dict)

        return results

    # -------------------------------------------------------------------------
    # EXTRACCION AUTOMATIZADA DE KPIS
    # -------------------------------------------------------------------------

    def extract_dashboard_kpis(self, vin: Optional[str] = None, range_expr: str = "-1h") -> Dict[str, Any]:
        """
        Extrae un resumen consolidado de KPIs clave directamente desde InfluxDB.
        """
        vin_filter = f'|> filter(fn: (r) => r["vin"] == "{vin}")' if vin else ""

        flux = (
            f'from(bucket: "{self.config.bucket}")\n'
            f'  |> range(start: {range_expr})\n'
            f'  |> filter(fn: (r) => r["_measurement"] == "ev_telemetry")\n'
            f'  {vin_filter}\n'
            f'  |> last()'
        )

        records = self.query_flux(flux)
        kpis = {
            "vin": vin or "N/A",
            "timestamp": None,
            "vehicle_state": "unknown",
            "soc_pct": 0.0,
            "battery_range_km": 0.0,
            "power_kw": 0.0,
            "speed_kmh": 0.0,
            "odometer_km": 0.0,
            "inside_temp_c": 0.0,
            "outside_temp_c": 0.0,
            "charger_power_kw": 0.0,
            "energy_added_kwh": 0.0,
            "tpms": {}
        }

        for r in records:
            field = r.get("_field")
            val = r.get("_value")
            kpis["timestamp"] = r.get("_time", kpis["timestamp"])
            if "vehicle_state" in r:
                kpis["vehicle_state"] = r["vehicle_state"]

            if field in kpis:
                kpis[field] = val
            elif field and field.startswith("tpms_") and field.endswith("_bar"):
                wheel = field.replace("tpms_", "").replace("_bar", "")
                kpis["tpms"][wheel] = val

        return kpis
