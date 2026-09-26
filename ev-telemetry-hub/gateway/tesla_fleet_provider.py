"""
Official Tesla Fleet API Telemetry Provider Implementation.
Supports OAuth 2.0 Partner/Refresh Token auth, multi-region routing (NA, EU, CN),
endpoint data extraction (/vehicle_data), and canonical normalization.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from .base import BaseTelemetryProvider
from .models import CanonicalVehicleState, CanonicalDrive, CanonicalCharge, ProviderHealth, ProviderError
from .security import TeslaSecurityManager
from importer.normalizer import safe_float, safe_int, miles_to_km, parse_timestamp


class TeslaFleetProvider(BaseTelemetryProvider):
    """
    Adapter for official Tesla Fleet API (https://fleet-api.prd.{region}.vn.cloud.tesla.com).
    """

    def __init__(self, security_manager: TeslaSecurityManager, timeout: int = 15):
        super().__init__(name="tesla_fleet", timeout=timeout)
        self.security = security_manager
        self.health = ProviderHealth(name="tesla_fleet")
        self._latencies: List[float] = []

    def _request(self, endpoint: str, method: str = "GET", payload: Optional[Dict[str, Any]] = None) -> Any:
        token = self.security.get_valid_access_token()
        url = f"{self.security.fleet_base_url}/{endpoint.lstrip('/')}"

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "LaVera-EV-FleetGateway/1.2",
        }

        data_bytes = None
        if payload is not None:
            data_bytes = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)

        t0 = time.time()
        self.health.total_requests += 1

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                elapsed_ms = (time.time() - t0) * 1000.0
                self._record_latency(elapsed_ms)
                raw_bytes = resp.read()
                data = json.loads(raw_bytes.decode("utf-8"))

                self.health.total_successes += 1
                self.health.consecutive_failures = 0
                self.health.last_success_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                return data.get("response", data)
        except urllib.error.HTTPError as e:
            elapsed_ms = (time.time() - t0) * 1000.0
            self._record_latency(elapsed_ms)
            self._record_error(str(e))
            if e.code == 429:
                retry_after = e.headers.get("Retry-After")
                raise ProviderError(f"Tesla Fleet Rate Limit (429): {e.reason}", status_code=429, is_rate_limit=True)
            elif e.code == 401:
                # Invalidate cached token so next attempt re-authenticates
                self.security.access_token = None
                raise ProviderError("Tesla Fleet Token expirado/invalido (401)", status_code=401, is_auth_error=True)
            elif e.code in (408, 504):
                raise ProviderError(f"Tesla Fleet Gateway Timeout ({e.code})", status_code=e.code, is_timeout=True)
            elif e.code >= 500:
                raise ProviderError(f"Tesla Fleet Server Error ({e.code}): {e.reason}", status_code=e.code, is_server_error=True)
            elif e.code == 408:
                raise ProviderError("Vehículo no responde (Asleep / Timeout 408)", status_code=408, is_timeout=True)
            else:
                raise ProviderError(f"Tesla Fleet HTTP Error ({e.code}): {e.reason}", status_code=e.code)
        except (urllib.error.URLError, TimeoutError) as e:
            elapsed_ms = (time.time() - t0) * 1000.0
            self._record_latency(elapsed_ms)
            self._record_error(str(e))
            raise ProviderError(f"Tesla Fleet Connection Timeout: {str(e)}", is_timeout=True)
        except Exception as e:
            self._record_error(str(e))
            raise ProviderError(f"Tesla Fleet unexpected error: {str(e)}")

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

    def get_vehicles(self) -> List[Dict[str, Any]]:
        res = self._request("api/1/vehicles")
        if isinstance(res, list):
            return res
        if isinstance(res, dict):
            return res.get("results") or res.get("vehicles") or []
        return []

    def get_vehicle_state(self, vin: str) -> CanonicalVehicleState:
        # Request full vehicle data
        endpoint = f"api/1/vehicles/{vin}/vehicle_data?endpoints=location_data;charge_state;climate_state;drive_state;vehicle_state"
        res = self._request(endpoint)

        charge_st = res.get("charge_state", {}) if isinstance(res, dict) else {}
        drive_st = res.get("drive_state", {}) if isinstance(res, dict) else {}
        climate_st = res.get("climate_state", {}) if isinstance(res, dict) else {}
        vehicle_st = res.get("vehicle_state", {}) if isinstance(res, dict) else {}

        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        odo_raw = safe_float(vehicle_st.get("odometer"))
        odo_km = miles_to_km(odo_raw) if odo_raw > 0 else 0.0

        spd_raw = safe_float(drive_st.get("speed"))
        spd_kmh = round(spd_raw * 1.60934, 1) if spd_raw > 0 else 0.0

        pwr_raw = safe_float(charge_st.get("charger_power"))

        return CanonicalVehicleState(
            vin=vin,
            provider="tesla_fleet",
            timestamp=parse_timestamp(res.get("timestamp")) or now_iso,
            soc=safe_float(charge_st.get("battery_level")),
            battery_range_km=miles_to_km(safe_float(charge_st.get("battery_range"))),
            is_charging=bool(charge_st.get("charging_state") == "Charging"),
            charging_state=charge_st.get("charging_state", "STANDBY"),
            charger_power_kw=pwr_raw,
            charge_rate_kmh=miles_to_km(safe_float(charge_st.get("charge_rate"))),
            energy_added_kwh=safe_float(charge_st.get("charge_energy_added")),
            time_to_full_charge_hours=safe_float(charge_st.get("time_to_full_charge")),
            speed_kmh=spd_kmh,
            power_kw=pwr_raw,
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
            shift_state=drive_st.get("shift_state"),
            raw_payload=res,
        )

    def get_drives(self, vin: str, from_ts: Optional[int] = None, to_ts: Optional[int] = None) -> List[CanonicalDrive]:
        # Tesla Fleet Data Exchange / Drives endpoint
        try:
            params = {}
            if from_ts:
                params["from"] = from_ts
            if to_ts:
                params["to"] = to_ts
            query_str = f"?{urllib.parse.urlencode(params)}" if params else ""
            res = self._request(f"api/1/dx/vehicles/{vin}/drives{query_str}")
            raw_list = res if isinstance(res, list) else (res.get("results") or res.get("drives") or [])
            result = []
            for d in raw_list:
                result.append(CanonicalDrive(
                    vin=vin,
                    provider="tesla_fleet",
                    started_at=parse_timestamp(d.get("started_at")) or "",
                    ended_at=parse_timestamp(d.get("ended_at")) or "",
                    duration_s=safe_int(d.get("duration_s")),
                    distance_km=safe_float(d.get("distance_km") or miles_to_km(safe_float(d.get("distance")))),
                    energy_kwh=safe_float(d.get("energy_kwh")),
                    efficiency_wh_km=safe_float(d.get("efficiency_wh_km")),
                    start_soc=safe_float(d.get("start_soc")),
                    end_soc=safe_float(d.get("end_soc")),
                    start_location=str(d.get("start_location") or "Origen").strip(),
                    end_location=str(d.get("end_location") or "Destino").strip(),
                    start_odometer_km=safe_float(d.get("start_odometer_km")),
                    end_odometer_km=safe_float(d.get("end_odometer_km")),
                    start_latitude=d.get("start_latitude"),
                    start_longitude=d.get("start_longitude"),
                    end_latitude=d.get("end_latitude"),
                    end_longitude=d.get("end_longitude"),
                    max_speed_kmh=safe_float(d.get("max_speed_kmh")),
                    autopilot_km=safe_float(d.get("autopilot_km")),
                    autopilot_pct=safe_float(d.get("autopilot_pct")),
                    raw_payload=d,
                ))
            return result
        except Exception:
            # If fleet drive history endpoint not provisioned for partner tier, return empty
            return []

    def get_charges(self, vin: str, from_ts: Optional[int] = None, to_ts: Optional[int] = None) -> List[CanonicalCharge]:
        try:
            params = {}
            if from_ts:
                params["from"] = from_ts
            if to_ts:
                params["to"] = to_ts
            query_str = f"?{urllib.parse.urlencode(params)}" if params else ""
            res = self._request(f"api/1/dx/vehicles/{vin}/charges{query_str}")
            raw_list = res if isinstance(res, list) else (res.get("results") or res.get("charges") or [])
            result = []
            for c in raw_list:
                result.append(CanonicalCharge(
                    vin=vin,
                    provider="tesla_fleet",
                    started_at=parse_timestamp(c.get("started_at")) or "",
                    ended_at=parse_timestamp(c.get("ended_at")) or "",
                    duration_s=safe_int(c.get("duration_s")),
                    energy_added_kwh=safe_float(c.get("energy_added_kwh")),
                    start_soc=safe_float(c.get("start_soc")),
                    end_soc=safe_float(c.get("end_soc")),
                    range_added_km=safe_float(c.get("range_added_km")),
                    peak_kw=safe_float(c.get("peak_kw")),
                    cost=safe_float(c.get("cost")),
                    location=str(c.get("location") or "Cargador").strip(),
                    is_fast_charge=bool(c.get("is_fast_charge", False)),
                    raw_payload=c,
                ))
            return result
        except Exception:
            return []

    def wake_up(self, vin: str) -> bool:
        try:
            res = self._request(f"api/1/vehicles/{vin}/wake_up", method="POST")
            state = res.get("state") if isinstance(res, dict) else str(res)
            return state == "online"
        except Exception:
            return False

    def health_check(self) -> ProviderHealth:
        return self.health
