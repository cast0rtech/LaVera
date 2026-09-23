"""
Storage and Analytical Queries for LaVera All-in-One Offline Hub.
"""

import json
import os
import sqlite3
import sys
from typing import Any, Dict, List, Optional

# Ensure importer writer tables can be shared
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from importer.writer import TelemetryWriter


class OfflineStorage:
    """Handles SQLite queries and aggregations for the offline dashboard."""

    def __init__(self, db_path: str = "data/lavera.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self.writer = TelemetryWriter(db_path=self.db_path)

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_summary(self, vin: Optional[str] = None) -> Dict[str, Any]:
        """Calculates aggregate KPIs across drives, charges, and battery health."""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            vin_clause = "WHERE vin = ?" if vin else ""
            params = (vin,) if vin else ()

            # Drives aggregate
            cur.execute(f"""
                SELECT
                    COUNT(*) as total_drives,
                    COALESCE(SUM(distance_km), 0) as total_distance_km,
                    COALESCE(SUM(energy_kwh), 0) as total_energy_kwh,
                    COALESCE(AVG(CASE WHEN efficiency_wh_km > 0 THEN efficiency_wh_km ELSE NULL END), 0) as avg_efficiency_wh_km,
                    COALESCE(MAX(end_odometer_km), 0) as latest_odometer_km
                FROM drives {vin_clause}
            """, params)
            drive_row = cur.fetchone()

            # Charges aggregate
            cur.execute(f"""
                SELECT
                    COUNT(*) as total_charges,
                    COALESCE(SUM(energy_added_kwh), 0) as total_charged_kwh,
                    COALESCE(SUM(cost), 0) as total_charging_cost,
                    COALESCE(MAX(peak_kw), 0) as max_charge_kw
                FROM charges {vin_clause}
            """, params)
            charge_row = cur.fetchone()

            # Battery Health (latest)
            cur.execute(f"""
                SELECT
                    capacity_kwh,
                    original_capacity_kwh,
                    degradation_pct,
                    max_range_km,
                    timestamp
                FROM battery_health {vin_clause}
                ORDER BY timestamp DESC LIMIT 1
            """, params)
            battery_row = cur.fetchone()

            # Latest Live Telemetry
            cur.execute(f"""
                SELECT soc, speed_kmh, power_kw, battery_temp_c, timestamp
                FROM live_telemetry {vin_clause}
                ORDER BY timestamp DESC LIMIT 1
            """, params)
            live_row = cur.fetchone()

            return {
                "drives": {
                    "total_count": drive_row["total_drives"],
                    "total_distance_km": round(drive_row["total_distance_km"], 1),
                    "total_energy_kwh": round(drive_row["total_energy_kwh"], 1),
                    "avg_efficiency_wh_km": round(drive_row["avg_efficiency_wh_km"], 1),
                    "latest_odometer_km": round(drive_row["latest_odometer_km"], 1),
                },
                "charges": {
                    "total_count": charge_row["total_charges"],
                    "total_charged_kwh": round(charge_row["total_charged_kwh"], 1),
                    "total_cost": round(charge_row["total_charging_cost"], 2),
                    "max_charge_kw": round(charge_row["max_charge_kw"], 1),
                },
                "battery": {
                    "capacity_kwh": round(battery_row["capacity_kwh"], 1) if battery_row else 0.0,
                    "original_capacity_kwh": round(battery_row["original_capacity_kwh"], 1) if battery_row else 0.0,
                    "degradation_pct": round(battery_row["degradation_pct"], 1) if battery_row else 0.0,
                    "max_range_km": round(battery_row["max_range_km"], 1) if battery_row else 0.0,
                    "last_checked": battery_row["timestamp"] if battery_row else None,
                },
                "live": {
                    "soc": live_row["soc"] if live_row else None,
                    "power_kw": live_row["power_kw"] if live_row else 0.0,
                    "battery_temp_c": live_row["battery_temp_c"] if live_row else None,
                    "timestamp": live_row["timestamp"] if live_row else None,
                }
            }
        finally:
            conn.close()

    def get_drives(self, vin: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            vin_clause = "WHERE vin = ?" if vin else ""
            params = (vin, limit, offset) if vin else (limit, offset)
            cur.execute(f"""
                SELECT id, provider, vin, started_at, ended_at, duration_s, distance_km,
                       energy_kwh, efficiency_wh_km, start_soc, end_soc, start_location,
                       end_location, start_odometer_km, end_odometer_km
                FROM drives {vin_clause}
                ORDER BY started_at DESC
                LIMIT ? OFFSET ?
            """, params)
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def get_charges(self, vin: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            vin_clause = "WHERE vin = ?" if vin else ""
            params = (vin, limit, offset) if vin else (limit, offset)
            cur.execute(f"""
                SELECT id, provider, vin, started_at, ended_at, duration_s, energy_added_kwh,
                       start_soc, end_soc, range_added_km, peak_kw, cost, location, is_fast_charge
                FROM charges {vin_clause}
                ORDER BY started_at DESC
                LIMIT ? OFFSET ?
            """, params)
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def get_battery_history(self, vin: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            vin_clause = "WHERE vin = ?" if vin else ""
            params = (vin, limit) if vin else (limit,)
            cur.execute(f"""
                SELECT timestamp, capacity_kwh, degradation_pct, max_range_km, odometer_km
                FROM battery_health {vin_clause}
                ORDER BY timestamp ASC
                LIMIT ?
            """, params)
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def insert_live_telemetry(self, data: Dict[str, Any]) -> int:
        # Flexible key extraction supporting standard, Tessie, ScanMyTesla, and OBD
        vin = data.get("vin") or data.get("vehicle_id") or data.get("car_id") or "DEFAULT"
        timestamp = data.get("timestamp") or data.get("time") or data.get("date")
        
        # State of Charge (%)
        soc = data.get("soc")
        if soc is None:
            soc = data.get("battery_level") or data.get("state_of_charge") or data.get("usable_battery_level")
        
        # Speed (km/h)
        speed = data.get("speed_kmh")
        if speed is None:
            speed = data.get("speed")
            # If in mph, convert
            if data.get("speed_mph"):
                speed = float(data.get("speed_mph")) * 1.60934
        
        # Power (kW)
        power = data.get("power_kw")
        if power is None:
            power = data.get("power")
        
        # Battery Temperature (C)
        bat_temp = data.get("battery_temp_c")
        if bat_temp is None:
            bat_temp = data.get("battery_temp") or data.get("temp_battery")
        
        # Odometer (km)
        odo = data.get("odometer_km")
        if odo is None:
            odo = data.get("odometer")
            if data.get("odometer_mi"):
                odo = float(data.get("odometer_mi")) * 1.60934
        
        charging_state = data.get("charging_state") or ("CHARGING" if data.get("is_charging") else "STANDBY")
        lat = data.get("latitude") or data.get("lat")
        lon = data.get("longitude") or data.get("lon") or data.get("lng")

        conn = self._get_conn()
        row_id = 0
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO live_telemetry (
                    vin, timestamp, soc, speed_kmh, power_kw, battery_temp_c,
                    odometer_km, charging_state, latitude, longitude, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                vin,
                timestamp,
                float(soc) if soc is not None else None,
                float(speed) if speed is not None else None,
                float(power) if power is not None else None,
                float(bat_temp) if bat_temp is not None else None,
                float(odo) if odo is not None else None,
                str(charging_state),
                float(lat) if lat is not None else None,
                float(lon) if lon is not None else None,
                json.dumps(data)
            ))
            conn.commit()
            row_id = cur.lastrowid
        finally:
            conn.close()

        # Also write to TimescaleDB if connected
        if hasattr(self.writer, "pg_conn") and self.writer.pg_conn:
            try:
                pg_cur = self.writer.pg_conn.cursor()
                pg_cur.execute("""
                    INSERT INTO telemetry (
                        time, vin, provider, speed_kmh, soc_percent, power_kw,
                        odometer_km, battery_temp_c, latitude, longitude,
                        is_charging, is_driving, raw_payload
                    ) VALUES (
                        COALESCE(%s::timestamptz, NOW()), %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s
                    )
                """, (
                    timestamp,
                    vin,
                    data.get("provider", "direct_live"),
                    float(speed) if speed is not None else None,
                    float(soc) if soc is not None else None,
                    float(power) if power is not None else None,
                    float(odo) if odo is not None else None,
                    float(bat_temp) if bat_temp is not None else None,
                    float(lat) if lat is not None else None,
                    float(lon) if lon is not None else None,
                    charging_state in ("Charging", "CHARGING", True),
                    (float(speed) > 0) if speed is not None else False,
                    json.dumps(data)
                ))
                pg_cur.close()
            except Exception:
                pass

        return row_id

    def export_all_json(self, vin: Optional[str] = None) -> Dict[str, Any]:
        return {
            "summary": self.get_summary(vin),
            "drives": self.get_drives(vin, limit=10000),
            "charges": self.get_charges(vin, limit=10000),
            "battery_health": self.get_battery_history(vin, limit=10000),
        }
