"""
Tessie Cloud API Client for LaVera EV Telemetry Hub.
Communicates with https://api.tessie.com/ to fetch live vehicle telemetry,
historical drives, charging sessions, and battery health analytics.
Built with standard Python urllib (zero external dependencies).
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("lavera.tessie_api")

BASE_URL = "https://api.tessie.com"


class TessieAPIClient:
    """Client for interacting with the Tessie REST API."""

    def __init__(self, token: str):
        self.token = token.strip() if token else ""

    def _request(self, endpoint: str, params: Optional[Dict[str, Any]] = None, timeout: int = 15) -> Dict[str, Any]:
        """Performs authenticated GET request to Tessie API."""
        if not self.token:
            raise ValueError("Token de acceso de Tessie no configurado.")

        url = f"{BASE_URL}/{endpoint.lstrip('/')}"
        if params:
            query = urllib.parse.urlencode(params)
            url = f"{url}?{query}"

        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "User-Agent": "LaVera-EV-Hub/1.2",
            },
            method="GET",
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                raw_data = response.read().decode(charset)
                return json.loads(raw_data)
        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode("utf-8")
            except Exception:
                pass
            if e.code == 401:
                raise ValueError("Token de Tessie no válido o expirado (401 Unauthorized).")
            elif e.code == 404:
                raise ValueError(f"Recurso no encontrado en Tessie (404 Not Found): {endpoint}")
            elif e.code == 429:
                raise ValueError("Límite de peticiones de Tessie excedido (429 Rate Limit). Intenta de nuevo más tarde.")
            else:
                msg = f"Error de Tessie API ({e.code}): {error_body or e.reason}"
                raise RuntimeError(msg)
        except urllib.error.URLError as e:
            raise ConnectionError(f"No se pudo conectar a api.tessie.com: {e.reason}")
        except Exception as e:
            raise RuntimeError(f"Error inesperado al consultar Tessie API: {str(e)}")

    def get_vehicles(self) -> List[Dict[str, Any]]:
        """Retrieves all Tesla vehicles linked to this Tessie account."""
        data = self._request("vehicles")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            if "results" in data and isinstance(data["results"], list):
                return data["results"]
            if "vehicles" in data and isinstance(data["vehicles"], list):
                return data["vehicles"]
        return []

    def get_state(self, vin: str) -> Dict[str, Any]:
        """Retrieves real-time telemetry state for a specific VIN."""
        return self._request(f"{vin}/state")

    def get_drives(self, vin: str, from_ts: Optional[int] = None, to_ts: Optional[int] = None) -> List[Dict[str, Any]]:
        """Retrieves historical drives for a VIN."""
        params = {}
        if from_ts:
            params["from"] = from_ts
        if to_ts:
            params["to"] = to_ts
        data = self._request(f"{vin}/drives", params=params if params else None)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for k in ["results", "drives", "data"]:
                if k in data and isinstance(data[k], list):
                    return data[k]
        return []

    def get_charges(self, vin: str, from_ts: Optional[int] = None, to_ts: Optional[int] = None) -> List[Dict[str, Any]]:
        """Retrieves historical charging sessions for a VIN."""
        params = {}
        if from_ts:
            params["from"] = from_ts
        if to_ts:
            params["to"] = to_ts
        data = self._request(f"{vin}/charges", params=params if params else None)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for k in ["results", "charges", "data"]:
                if k in data and isinstance(data[k], list):
                    return data[k]
        return []

    def get_battery_health(self, vin: str) -> List[Dict[str, Any]]:
        """Retrieves battery health and degradation history for a VIN from multiple Tessie API endpoints with fallbacks."""
        endpoints = [
            f"{vin}/battery/health",
            f"{vin}/battery",
            f"{vin}/battery/degradation",
            f"{vin}/battery/capacity",
            f"{vin}/battery_health",
            f"{vin}/battery_degradation",
            f"{vin}/state"
        ]
        for ep in endpoints:
            try:
                data = self._request(ep)
                if isinstance(data, list) and len(data) > 0:
                    return data
                if isinstance(data, dict):
                    for k in ["results", "battery_health", "battery", "data", "history", "degradation_history"]:
                        if k in data and isinstance(data[k], list) and len(data[k]) > 0:
                            return data[k]
                    if any(key in data for key in ["capacity_kwh", "degradation_percent", "usable_capacity", "original_capacity", "degradation", "max_range", "charge_state"]):
                        return [data]
            except Exception as e:
                logger.debug(f"Tessie battery endpoint {ep} failed: {e}")
                continue
        return []
