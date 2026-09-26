"""
InfluxDB Telemetry Injector for LaVera EV Telemetry Hub.
Demonstrates batch and streaming ingestion to InfluxDB v2 (or v1.8 compatibility).
"""

import os
import sys
import json
import time
import logging
from typing import Dict, Any, Optional

try:
    import requests
except ImportError:
    requests = None

# Ensure path to gateway module
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from gateway.influx_parser import TelemetryToInfluxParser
from gateway.models import CanonicalVehicleState

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("InfluxInjector")


class InfluxDBClientHttp:
    """Lightweight HTTP writer for InfluxDB v2 / InfluxDB Cloud / InfluxDB 1.8 compatibility."""

    def __init__(
        self,
        url: Optional[str] = None,
        token: Optional[str] = None,
        org: Optional[str] = None,
        bucket: Optional[str] = None,
        precision: str = "s"
    ):
        self.url = (url or os.getenv("INFLUXDB_URL", "http://localhost:8086")).rstrip("/")
        self.token = token or os.getenv("INFLUXDB_TOKEN", "")
        self.org = org or os.getenv("INFLUXDB_ORG", "lavera")
        self.bucket = bucket or os.getenv("INFLUXDB_BUCKET", "ev_telemetry")
        self.precision = precision

    def write_line_protocol(self, lines: str) -> bool:
        """Sends raw Line Protocol to InfluxDB v2 /api/v2/write endpoint."""
        if not requests:
            logger.error("The 'requests' package is required. Run: pip install requests")
            return False

        write_url = f"{self.url}/api/v2/write?org={self.org}&bucket={self.bucket}&precision={self.precision}"
        headers = {
            "Authorization": f"Token {self.token}",
            "Content-Type": "text/plain; charset=utf-8",
            "Accept": "application/json"
        }

        try:
            resp = requests.post(write_url, data=lines.encode("utf-8"), headers=headers, timeout=10)
            if resp.status_code in (200, 204):
                logger.info(f"Successfully wrote telemetry to InfluxDB bucket '{self.bucket}'")
                return True
            else:
                logger.error(f"InfluxDB HTTP error {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            logger.error(f"Failed to connect to InfluxDB at {self.url}: {e}")
            return False


def test_pipeline():
    sample_payload = {
        "vin": "5YJ3E7EB8NF123456",
        "provider": "tesla_fleet",
        "charge_state": {
            "battery_level": 74,
            "usable_battery_level": 73,
            "battery_range": 284.5,
            "charging_state": "Charging",
            "charger_power": 11.2,
            "charger_voltage": 230,
            "charger_actual_current": 16,
            "charge_rate": 65.0,
            "charge_energy_added": 14.8,
            "time_to_full_charge": 1.5
        },
        "drive_state": {
            "speed": 0,
            "shift_state": "P",
            "power": 0,
            "latitude": 40.416775,
            "longitude": -3.703790,
            "heading": 182
        },
        "climate_state": {
            "inside_temp": 21.5,
            "outside_temp": 14.0,
            "is_climate_on": True,
            "driver_temp_setting": 21.0
        },
        "vehicle_state": {
            "odometer": 42150.8,
            "sentry_mode": False,
            "tpms_pressure_fl": 2.9,
            "tpms_pressure_fr": 2.9,
            "tpms_pressure_rl": 2.85,
            "tpms_pressure_rr": 2.85
        }
    }

    line_proto, point_dict = TelemetryToInfluxParser.to_line_protocol(
        sample_payload,
        measurement="ev_telemetry",
        precision="s"
    )

    print("=== INFLUXDB POINT DICT (PYTHON SDK) ===")
    print(json.dumps(point_dict, indent=2))
    print("\n=== INFLUXDB LINE PROTOCOL PAYLOAD ===")
    print(line_proto)


if __name__ == "__main__":
    test_pipeline()
