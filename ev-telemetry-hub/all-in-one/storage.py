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
        self._ensure_tables()

    def _ensure_tables(self):
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            ''')
            # Check for live_telemetry columns
            cur.execute("PRAGMA table_info(live_telemetry)")
            cols = [r["name"] for r in cur.fetchall()]
            if "odometer_km" not in cols:
                cur.execute("ALTER TABLE live_telemetry ADD COLUMN odometer_km REAL")
            if "charging_state" not in cols:
                cur.execute("ALTER TABLE live_telemetry ADD COLUMN charging_state TEXT")
            conn.commit()
        finally:
            conn.close()


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
            cur.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            ''')

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

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cur.fetchone()
            return row["value"] if row else default
        finally:
            conn.close()

    def set_setting(self, key: str, value: str) -> None:
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
            """, (key, value))
            conn.commit()
        finally:
            conn.close()

    def clear_all_data(self) -> Dict[str, int]:
        """Clears all telemetry, drives, charges, and battery data."""
        conn = self._get_conn()
        deleted = {}
        try:
            cur = conn.cursor()
            for table in ["drives", "charges", "battery_health", "live_telemetry", "idle_logs"]:
                cur.execute(f"DELETE FROM {table}")
                deleted[table] = cur.rowcount
            conn.commit()
            return deleted
        finally:
            conn.close()

    def seed_demo_data(self, vin: str = "TESLA_MODEL_Y_LR") -> Dict[str, int]:
        """Seeds realistic sample drives, charges, battery degradation, and live state."""
        self.clear_all_data()

        demo_drives = [
            {"provider": "demo", "vin": vin, "started_at": "2026-06-10 08:30:00", "ended_at": "2026-06-10 09:25:00", "duration_s": 3300, "distance_km": 92.4, "energy_kwh": 14.8, "efficiency_wh_km": 160.2, "start_soc": 88.0, "end_soc": 68.0, "start_temp_c": 21.0, "end_temp_c": 24.0, "start_location": "Madrid Norte", "end_location": "Segovia Centro", "start_odometer_km": 32100.0, "end_odometer_km": 32192.4, "max_speed_kmh": 125.0},
            {"provider": "demo", "vin": vin, "started_at": "2026-06-12 17:15:00", "ended_at": "2026-06-12 18:10:00", "duration_s": 3300, "distance_km": 91.8, "energy_kwh": 13.5, "efficiency_wh_km": 147.1, "start_soc": 80.0, "end_soc": 62.0, "start_temp_c": 26.0, "end_temp_c": 28.0, "start_location": "Segovia", "end_location": "Madrid", "start_odometer_km": 32250.0, "end_odometer_km": 32341.8, "max_speed_kmh": 122.0},
            {"provider": "demo", "vin": vin, "started_at": "2026-06-15 10:00:00", "ended_at": "2026-06-15 10:50:00", "duration_s": 3000, "distance_km": 74.2, "energy_kwh": 11.6, "efficiency_wh_km": 156.3, "start_soc": 75.0, "end_soc": 59.0, "start_temp_c": 23.0, "end_temp_c": 25.0, "start_location": "Madrid", "end_location": "Toledo", "start_odometer_km": 32400.0, "end_odometer_km": 32474.2, "max_speed_kmh": 120.0},
            {"provider": "demo", "vin": vin, "started_at": "2026-06-18 08:15:00", "ended_at": "2026-06-18 08:45:00", "duration_s": 1800, "distance_km": 24.5, "energy_kwh": 3.7, "efficiency_wh_km": 151.0, "start_soc": 70.0, "end_soc": 65.0, "start_temp_c": 20.0, "end_temp_c": 21.0, "start_location": "Casa", "end_location": "Oficina", "start_odometer_km": 32510.0, "end_odometer_km": 32534.5, "max_speed_kmh": 95.0},
            {"provider": "demo", "vin": vin, "started_at": "2026-06-20 09:00:00", "ended_at": "2026-06-20 10:15:00", "duration_s": 4500, "distance_km": 115.0, "energy_kwh": 19.2, "efficiency_wh_km": 167.0, "start_soc": 95.0, "end_soc": 69.0, "start_temp_c": 19.0, "end_temp_c": 22.0, "start_location": "Madrid", "end_location": "Ávila Murallas", "start_odometer_km": 32600.0, "end_odometer_km": 32715.0, "max_speed_kmh": 128.0},
        ]

        demo_charges = [
            {"provider": "demo", "vin": vin, "started_at": "2026-06-10 12:00:00", "ended_at": "2026-06-10 12:35:00", "duration_s": 2100, "energy_added_kwh": 38.5, "start_soc": 25.0, "end_soc": 78.0, "range_added_km": 255.0, "peak_kw": 175.0, "cost": 16.50, "location": "Tesla Supercharger Torrelodones", "is_fast_charge": 1},
            {"provider": "demo", "vin": vin, "started_at": "2026-06-14 23:00:00", "ended_at": "2026-06-15 06:30:00", "duration_s": 27000, "energy_added_kwh": 22.4, "start_soc": 52.0, "end_soc": 80.0, "range_added_km": 145.0, "peak_kw": 7.4, "cost": 3.80, "location": "Wallbox Doméstico (Tarifa Valle)", "is_fast_charge": 0},
            {"provider": "demo", "vin": vin, "started_at": "2026-06-17 18:30:00", "ended_at": "2026-06-17 19:05:00", "duration_s": 2100, "energy_added_kwh": 31.0, "start_soc": 30.0, "end_soc": 75.0, "range_added_km": 205.0, "peak_kw": 150.0, "cost": 13.20, "location": "Tesla Supercharger Getafe", "is_fast_charge": 1},
            {"provider": "demo", "vin": vin, "started_at": "2026-06-21 14:00:00", "ended_at": "2026-06-21 18:00:00", "duration_s": 14400, "energy_added_kwh": 18.0, "start_soc": 60.0, "end_soc": 85.0, "range_added_km": 120.0, "peak_kw": 11.0, "cost": 0.0, "location": "Cargador Empresa (Gratis)", "is_fast_charge": 0},
        ]

        demo_battery = [
            {"provider": "demo", "vin": vin, "timestamp": "2024-01-15 12:00:00", "capacity_kwh": 75.0, "original_capacity_kwh": 75.0, "degradation_pct": 0.0, "max_range_km": 505.0, "odometer_km": 1200.0},
            {"provider": "demo", "vin": vin, "timestamp": "2024-07-20 12:00:00", "capacity_kwh": 74.3, "original_capacity_kwh": 75.0, "degradation_pct": 0.9, "max_range_km": 500.0, "odometer_km": 9400.0},
            {"provider": "demo", "vin": vin, "timestamp": "2025-01-18 12:00:00", "capacity_kwh": 73.6, "original_capacity_kwh": 75.0, "degradation_pct": 1.9, "max_range_km": 495.0, "odometer_km": 17800.0},
            {"provider": "demo", "vin": vin, "timestamp": "2025-07-22 12:00:00", "capacity_kwh": 73.0, "original_capacity_kwh": 75.0, "degradation_pct": 2.7, "max_range_km": 491.0, "odometer_km": 25100.0},
            {"provider": "demo", "vin": vin, "timestamp": "2026-01-10 12:00:00", "capacity_kwh": 72.3, "original_capacity_kwh": 75.0, "degradation_pct": 3.6, "max_range_km": 486.0, "odometer_km": 30500.0},
            {"provider": "demo", "vin": vin, "timestamp": "2026-06-20 12:00:00", "capacity_kwh": 71.7, "original_capacity_kwh": 75.0, "degradation_pct": 4.4, "max_range_km": 482.0, "odometer_km": 32750.0},
        ]

        n_drives = self.writer.write_drives(demo_drives)
        n_charges = self.writer.write_charges(demo_charges)
        n_battery = self.writer.write_battery_health(demo_battery)

        self.insert_live_telemetry({
            "vin": vin,
            "timestamp": "2026-06-22 15:30:00",
            "soc": 74.0,
            "speed_kmh": 0.0,
            "power_kw": 0.0,
            "battery_temp_c": 24.5,
            "odometer_km": 32750.0,
            "charging_state": "STANDBY",
            "latitude": 40.4168,
            "longitude": -3.7038
        })

        return {
            "drives": n_drives,
            "charges": n_charges,
            "battery": n_battery,
            "live": 1
        }
