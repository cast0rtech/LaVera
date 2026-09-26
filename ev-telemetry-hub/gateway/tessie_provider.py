"""
Tessie Telemetry Provider Implementation.
Integrates Tessie REST API into the Unified Gateway with Sleep-Aware Vampire Drain Protection
and robust HTTP 4xx/5xx / Network fault handling.
"""

import email.utils
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from .base import BaseTelemetryProvider
from .models import (
    CanonicalVehicleState,
    CanonicalDrive,
    CanonicalCharge,
    ProviderHealth,
    ProviderError,
    CircuitState,
)
from importer.normalizer import (
    safe_float,
    safe_int,
    miles_to_km,
    f_to_c,
    wh_per_mi_to_wh_per_km,
    parse_timestamp,
)

logger = logging.getLogger("lavera.tessie")


class TessieProvider(BaseTelemetryProvider):
    """
    Adapter for https://api.tessie.com/ REST API.
    Features:
    - Zero-wake status checking (prevents vampire drain).
    - Cache-only retrieval when vehicle is sleeping or waiting to sleep.
    - Comprehensive HTTP 4xx/5xx error classification (429, 401/403, 408, 5xx).
    - Network timeout and drop resiliency.
    """

    BASE_URL = "https://api.tessie.com"

    def __init__(self, token: str = "", timeout: int = 12):
        super().__init__(name="tessie", timeout=timeout)
        self.token = token.strip() if token else ""
        self.health = ProviderHealth(name="tessie")
        self._latencies: List[float] = []
        self._cached_states: Dict[str, CanonicalVehicleState] = {}

    def set_token(self, token: str):
        self.token = token.strip()

    def _request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        method: str = "GET",
        data: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Executes an HTTP request to Tessie API with detailed exception handling for
        network failures, timeouts, rate limits (429), auth issues (401/403), and server errors (5xx).
        """
        if not self.token:
            raise ProviderError("Token de Tessie no configurado.", is_auth_error=True)

        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"

        payload_bytes = None
        if data is not None:
            payload_bytes = json.dumps(data).encode("utf-8")

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "User-Agent": "LaVera-EV-Gateway/1.2",
        }
        if payload_bytes:
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(
            url,
            data=payload_bytes,
            headers=headers,
            method=method,
        )

        t0 = time.time()
        self.health.total_requests += 1

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                elapsed_ms = (time.time() - t0) * 1000.0
                self._record_latency(elapsed_ms)
                raw_bytes = resp.read()
                parsed = json.loads(raw_bytes.decode("utf-8"))

                self.health.total_successes += 1
                self.health.consecutive_failures = 0
                self.health.last_success_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                return parsed

        except urllib.error.HTTPError as e:
            elapsed_ms = (time.time() - t0) * 1000.0
            self._record_latency(elapsed_ms)
            self._record_error(f"HTTP {e.code}: {e.reason}")

            # 1. HTTP 429 Too Many Requests
            if e.code == 429:
                retry_after_hdr = e.headers.get("Retry-After")
                retry_sec = self._parse_retry_after(retry_after_hdr) or 60
                logger.warning(f"[Tessie] HTTP 429 Rate Limit alcanzado. Retry-After: {retry_sec}s")
                raise ProviderError(
                    f"Tessie Rate Limit (429) excedido. Reintento en {retry_sec}s",
                    status_code=429,
                    is_rate_limit=True,
                )

            # 2. HTTP 401 / 403 Authentication & Permissions
            elif e.code in (401, 403):
                msg = "Token de Tessie no autorizado o revocado (401)" if e.code == 401 else "Acceso prohibido o suscripción inactiva en Tessie (403)"
                logger.error(f"[Tessie] Error de credenciales: {msg}")
                raise ProviderError(msg, status_code=e.code, is_auth_error=True)

            # 3. HTTP 408 Request Timeout / Vehicle Asleep
            elif e.code == 408:
                logger.info(f"[Tessie] HTTP 408: Vehículo dormido o sin cobertura LTE.")
                raise ProviderError("Vehículo en reposo profundo o sin cobertura (408)", status_code=408, is_timeout=True)

            # 4. HTTP 404 Not Found
            elif e.code == 404:
                raise ProviderError(f"Vehículo o recurso no encontrado en Tessie (404): {endpoint}", status_code=404)

            # 5. HTTP 5xx Server Errors (Tessie o Tesla Upstream caídos)
            elif e.code >= 500:
                logger.warning(f"[Tessie] Error de servidor upstream HTTP {e.code}: {e.reason}")
                raise ProviderError(
                    f"Tessie Upstream Server Error ({e.code}): {e.reason}",
                    status_code=e.code,
                    is_server_error=True,
                )
            else:
                raise ProviderError(f"Tessie HTTP Error ({e.code}): {e.reason}", status_code=e.code)

        # Manejo de caídas de red, resets y timeouts de socket
        except (urllib.error.URLError, TimeoutError, ConnectionResetError, ConnectionRefusedError, OSError) as e:
            elapsed_ms = (time.time() - t0) * 1000.0
            self._record_latency(elapsed_ms)
            err_msg = str(e)
            self._record_error(f"Network drop: {err_msg}")
            logger.warning(f"[Tessie] Caída de red o timeout ({type(e).__name__}): {err_msg}")
            raise ProviderError(f"Error de red al conectar con Tessie: {err_msg}", is_timeout=True)

        except json.JSONDecodeError as e:
            self._record_error("Invalid JSON")
            raise ProviderError(f"Respuesta inválida no JSON de Tessie: {str(e)}")

        except Exception as e:
            self._record_error(str(e))
            raise ProviderError(f"Error inesperado en cliente Tessie: {str(e)}")

    @staticmethod
    def _parse_retry_after(header_val: Optional[str]) -> Optional[int]:
        """Parses Retry-After header as either seconds integer or HTTP-date."""
        if not header_val:
            return None
        try:
            return int(header_val.strip())
        except ValueError:
            try:
                date_tuple = email.utils.parsedate_tz(header_val)
                if date_tuple:
                    target_ts = email.utils.mktime_tz(date_tuple)
                    return max(1, int(target_ts - time.time()))
            except Exception:
                pass
        return None

    def _record_latency(self, ms: float):
        self._latencies.append(ms)
        if len(self._latencies) > 20:
            self._latencies.pop(0)
        self.health.average_latency_ms = round(sum(self._latencies) / len(self._latencies), 1)

    def _record_error(self, reason: str):
        self.health.total_failures += 1
        self.health.consecutive_failures += 1
        self.health.last_error_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.health.last_error_reason = reason

    # -------------------------------------------------------------------------
    # GESTIÓN ANTI-VAMPIRE DRAIN & SLEEP CHECK
    # -------------------------------------------------------------------------

    def get_status(self, vin: str) -> str:
        """
        Consulta el estado operacional del vehículo SIN DESPERTARLO.
        Endpoint Tessie: GET /{vin}/status
        Posibles retornos: 'online', 'asleep', 'waiting_for_sleep'
        """
        try:
            data = self._request(f"{vin}/status")
            status = data.get("status") if isinstance(data, dict) else str(data)
            return status.lower() if status else "unknown"
        except ProviderError as e:
            if e.status_code == 408:
                return "asleep"
            raise

    def get_vehicles(self) -> List[Dict[str, Any]]:
        data = self._request("vehicles")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("results") or data.get("vehicles") or []
        return []

    def get_vehicle_state(
        self,
        vin: str,
        allow_wake: bool = False,
        use_cache: bool = True
    ) -> CanonicalVehicleState:
        """
        Obtiene la telemetría del vehículo con protección activa contra vampire drain:
        1. Si allow_wake=False, comprueba primero el estado rápido sin despertar (/{vin}/status).
        2. Si el coche está dormido ('asleep') o en proceso de reposo ('waiting_for_sleep'):
           - NO despierta la MCU ni las computadoras de a bordo.
           - Solicita el estado con '?use_cache=true' o retorna el último estado cacheado marcando is_asleep=True.
        3. Si está 'online', obtiene la telemetría viva.
        """
        # Paso 1: Verificación de estado de reposo si no se permite despertar
        is_asleep = False
        if not allow_wake:
            status = self.get_status(vin)
            if status in ("asleep", "waiting_for_sleep"):
                logger.info(f"[Tessie] Vehículo {vin} en reposo ({status}). Modo Anti-Vampire Drain activado (use_cache=true).")
                is_asleep = True
                use_cache = True

        # Paso 2: Petición de telemetría (con use_cache si el coche duerme)
        params = {"use_cache": "true"} if use_cache else None
        data = self._request(f"{vin}/state", params=params)

        charge_st = data.get("charge_state", {}) if isinstance(data, dict) else {}
        drive_st = data.get("drive_state", {}) if isinstance(data, dict) else {}
        climate_st = data.get("climate_state", {}) if isinstance(data, dict) else {}
        vehicle_st = data.get("vehicle_state", {}) if isinstance(data, dict) else {}

        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        odo_raw = safe_float(vehicle_st.get("odometer"))
        odo_km = miles_to_km(odo_raw) if odo_raw > 0 else 0.0

        spd_raw = safe_float(drive_st.get("speed"))
        spd_kmh = round(spd_raw * 1.609344, 1) if spd_raw > 0 else 0.0

        pwr_raw = safe_float(charge_st.get("charger_power"))

        state = CanonicalVehicleState(
            vin=vin,
            provider="tessie",
            timestamp=parse_timestamp(data.get("timestamp")) or now_iso,
            soc=safe_float(charge_st.get("battery_level")),
            battery_range_km=miles_to_km(safe_float(charge_st.get("battery_range"))),
            is_charging=bool(charge_st.get("charging_state") == "Charging"),
            charging_state=charge_st.get("charging_state", "STANDBY"),
            charger_power_kw=pwr_raw,
            charge_rate_kmh=miles_to_km(safe_float(charge_st.get("charge_rate"))),
            energy_added_kwh=safe_float(charge_st.get("charge_energy_added")),
            time_to_full_charge_hours=safe_float(charge_st.get("time_to_full_charge")),
            speed_kmh=0.0 if is_asleep else spd_kmh,
            power_kw=0.0 if is_asleep else pwr_raw,
            odometer_km=odo_km,
            latitude=drive_st.get("latitude"),
            longitude=drive_st.get("longitude"),
            heading=drive_st.get("heading"),
            inside_temp_c=climate_st.get("inside_temp"),
            outside_temp_c=climate_st.get("outside_temp"),
            battery_temp_c=climate_st.get("inside_temp"),
            is_locked=bool(vehicle_st.get("locked", True)),
            is_sentry_active=bool(vehicle_st.get("sentry_mode", False)),
            is_climate_on=bool(climate_st.get("is_climate_on", False)),
            is_asleep=is_asleep,
            shift_state=None if is_asleep else drive_st.get("shift_state"),
            raw_payload=data,
        )

        self._cached_states[vin] = state
        return state

    def get_drives(self, vin: str, from_ts: Optional[int] = None, to_ts: Optional[int] = None) -> List[CanonicalDrive]:
        params = {}
        if from_ts:
            params["from"] = from_ts
        if to_ts:
            params["to"] = to_ts
        data = self._request(f"{vin}/drives", params=params if params else None)
        raw_list = data if isinstance(data, list) else (data.get("results") or data.get("drives") or [])

        result = []
        for d in raw_list:
            start_ts = parse_timestamp(d.get("started_at") or d.get("start_time") or d.get("date")) or ""
            end_ts = parse_timestamp(d.get("ended_at") or d.get("end_time")) or start_ts
            dist_km = safe_float(d.get("distance_km") or miles_to_km(safe_float(d.get("distance"))))
            dur_s = safe_int(d.get("duration_s") or d.get("duration") or d.get("duration_seconds"))

            result.append(CanonicalDrive(
                vin=vin,
                provider="tessie",
                started_at=start_ts,
                ended_at=end_ts,
                duration_s=dur_s,
                distance_km=dist_km,
                energy_kwh=safe_float(d.get("energy_used") or d.get("energy_kwh")),
                efficiency_wh_km=safe_float(d.get("wh_per_km") or wh_per_mi_to_wh_per_km(safe_float(d.get("efficiency")))),
                start_soc=safe_float(d.get("starting_battery") or d.get("start_soc")),
                end_soc=safe_float(d.get("ending_battery") or d.get("end_soc")),
                start_location=str(d.get("start_location") or d.get("start_address") or "Origen").strip(),
                end_location=str(d.get("end_location") or d.get("end_address") or "Destino").strip(),
                start_odometer_km=safe_float(d.get("odometer_start") or miles_to_km(safe_float(d.get("starting_odometer")))),
                end_odometer_km=safe_float(d.get("odometer_end") or miles_to_km(safe_float(d.get("ending_odometer")))),
                start_latitude=d.get("starting_latitude") or d.get("start_latitude"),
                start_longitude=d.get("starting_longitude") or d.get("start_longitude"),
                end_latitude=d.get("ending_latitude") or d.get("end_latitude"),
                end_longitude=d.get("ending_longitude") or d.get("end_longitude"),
                max_speed_kmh=safe_float(d.get("speed_max") or d.get("max_speed")),
                autopilot_km=safe_float(d.get("autopilot_distance") or d.get("autopilot_km")),
                autopilot_pct=safe_float(d.get("autopilot_percent") or d.get("autopilot_pct")),
                raw_payload=d,
            ))
        return result

    def get_charges(self, vin: str, from_ts: Optional[int] = None, to_ts: Optional[int] = None) -> List[CanonicalCharge]:
        params = {}
        if from_ts:
            params["from"] = from_ts
        if to_ts:
            params["to"] = to_ts
        data = self._request(f"{vin}/charges", params=params if params else None)
        raw_list = data if isinstance(data, list) else (data.get("results") or data.get("charges") or [])

        result = []
        for c in raw_list:
            start_ts = parse_timestamp(c.get("started_at") or c.get("start_time") or c.get("date")) or ""
            end_ts = parse_timestamp(c.get("ended_at") or c.get("end_time")) or start_ts
            result.append(CanonicalCharge(
                vin=vin,
                provider="tessie",
                started_at=start_ts,
                ended_at=end_ts,
                duration_s=safe_int(c.get("duration_s") or c.get("duration")),
                energy_added_kwh=safe_float(c.get("energy_added") or c.get("charge_energy_added")),
                start_soc=safe_float(c.get("starting_battery") or c.get("start_soc")),
                end_soc=safe_float(c.get("ending_battery") or c.get("end_soc")),
                range_added_km=safe_float(c.get("range_added_km") or miles_to_km(safe_float(c.get("range_added")))),
                peak_kw=safe_float(c.get("max_charge_power") or c.get("peak_kw")),
                cost=safe_float(c.get("cost")),
                location=str(c.get("location") or "Cargador").strip(),
                is_fast_charge=bool(c.get("fast_charger", False) or safe_float(c.get("peak_kw", 0)) > 40.0),
                raw_payload=c,
            ))
        return result

    def wake_up(self, vin: str) -> bool:
        """Envía comando explícito para despertar el vehículo (MCU + contactores de alta tensión)."""
        try:
            logger.info(f"[Tessie] Enviando comando wake_up a {vin}...")
            data = self._request(f"{vin}/wake", method="POST")
            return bool(data.get("result") or data.get("state") == "online")
        except Exception as e:
            logger.error(f"[Tessie] Error al despertar {vin}: {e}")
            return False

    def health_check(self) -> ProviderHealth:
        return self.health
