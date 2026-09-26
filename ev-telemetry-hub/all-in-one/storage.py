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

            # Check for drives GPS coordinate columns
            cur.execute("PRAGMA table_info(drives)")
            drv_cols = [r["name"] for r in cur.fetchall()]
            if "start_latitude" not in drv_cols:
                cur.execute("ALTER TABLE drives ADD COLUMN start_latitude REAL")
            if "start_longitude" not in drv_cols:
                cur.execute("ALTER TABLE drives ADD COLUMN start_longitude REAL")
            if "end_latitude" not in drv_cols:
                cur.execute("ALTER TABLE drives ADD COLUMN end_latitude REAL")
            if "end_longitude" not in drv_cols:
                cur.execute("ALTER TABLE drives ADD COLUMN end_longitude REAL")
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

            # Idle Logs / Vampire Drain aggregate
            cur.execute(f"""
                SELECT
                    COUNT(*) as total_idles,
                    COALESCE(SUM(soc_loss_pct), 0) as total_vampire_soc_loss,
                    COALESCE(SUM(range_loss_km), 0) as total_vampire_range_loss_km
                FROM idle_logs {vin_clause}
            """, params)
            idle_row = cur.fetchone()

            # Latest Battery Health record
            cur.execute(f"""
                SELECT capacity_kwh, degradation_pct, max_range_km, timestamp
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

            # User-configured original battery capacity when new (default: 75.0 kWh)
            user_orig_cap = float(self.get_setting("original_capacity_kwh", "75.0"))

            # Drives metrics
            tot_count = drive_row["total_drives"]
            tot_dist = drive_row["total_distance_km"]
            tot_drive_energy = drive_row["total_energy_kwh"]
            latest_odo = drive_row["latest_odometer_km"]
            
            if tot_dist == 0 and latest_odo > 0:
                tot_dist = latest_odo

            net_eff = drive_row["avg_efficiency_wh_km"]
            if net_eff == 0 and tot_dist > 0 and tot_drive_energy > 0:
                net_eff = round((tot_drive_energy * 1000.0) / tot_dist, 1)

            # Charges metrics
            tot_charged_kwh = charge_row["total_charged_kwh"]
            tot_charge_cost = charge_row["total_charging_cost"]

            # Vampire Drain / Inactividad calculations
            vampire_soc_loss = idle_row["total_vampire_soc_loss"] if idle_row else 0.0
            if vampire_soc_loss > 0:
                vampire_kwh = (vampire_soc_loss / 100.0) * user_orig_cap
            else:
                # Estimate vampire drain from charging vs driving gap (minus 12% AC/DC charging loss)
                vampire_kwh = max(0.0, (tot_charged_kwh * 0.88) - tot_drive_energy) if tot_charged_kwh > 0 else 0.0

            gross_energy_kwh = tot_drive_energy + vampire_kwh
            gross_eff = (gross_energy_kwh * 1000.0) / tot_dist if tot_dist > 0 else net_eff
            vampire_impact_wh_km = max(0.0, gross_eff - net_eff)

            # Battery Health (latest) against user's original capacity
            curr_cap = battery_row["capacity_kwh"] if battery_row and battery_row["capacity_kwh"] else (user_orig_cap * 0.90)
            if curr_cap > user_orig_cap:
                curr_cap = user_orig_cap
            deg_pct = round(max(0.0, ((user_orig_cap - curr_cap) / user_orig_cap) * 100.0), 1)
            max_range = round((user_orig_cap * (1 - deg_pct / 100.0)) * 6.0, 1)

            return {
                "drives": {
                    "total_count": tot_count,
                    "total_distance_km": round(tot_dist, 1),
                    "total_energy_kwh": round(tot_drive_energy, 1),
                    "avg_efficiency_wh_km": round(net_eff, 1),
                    "latest_odometer_km": round(latest_odo, 1),
                },
                "charges": {
                    "total_count": charge_row["total_charges"],
                    "total_charged_kwh": round(tot_charged_kwh, 1),
                    "total_cost": round(tot_charge_cost, 2),
                    "max_charge_kw": round(charge_row["max_charge_kw"], 1),
                },
                "vampire_drain": {
                    "vampire_kwh": round(vampire_kwh, 1),
                    "vampire_soc_loss_pct": round(vampire_soc_loss, 1),
                    "gross_total_energy_kwh": round(gross_energy_kwh, 1),
                    "gross_efficiency_wh_km": round(gross_eff, 1),
                    "vampire_impact_wh_km": round(vampire_impact_wh_km, 1),
                },
                "battery": {
                    "capacity_kwh": round(curr_cap, 1),
                    "original_capacity_kwh": round(user_orig_cap, 1),
                    "degradation_pct": round(deg_pct, 1),
                    "max_range_km": round(max_range, 1),
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

    def get_drives(self, vin: Optional[str] = None,
                   start_date: Optional[str] = None,
                   end_date: Optional[str] = None,
                   search: Optional[str] = None,
                   limit: int = 50,
                   offset: int = 0,
                   return_dict: bool = False) -> Any:
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            conditions = []
            params = []

            if vin:
                conditions.append("vin = ?")
                params.append(vin)
            if start_date:
                conditions.append("started_at >= ?")
                params.append(start_date)
            if end_date:
                conditions.append("started_at <= ?")
                params.append(end_date)
            if search:
                conditions.append("(start_location LIKE ? OR end_location LIKE ? OR provider LIKE ?)")
                search_param = f"%{search}%"
                params.extend([search_param, search_param, search_param])

            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

            # Total matching count & analytics summary
            cur.execute(f"""
                SELECT COUNT(*) as total_count,
                       COALESCE(SUM(distance_km), 0) as total_distance_km,
                       COALESCE(SUM(energy_kwh), 0) as total_energy_kwh,
                       COALESCE(AVG(CASE WHEN efficiency_wh_km > 0 THEN efficiency_wh_km ELSE NULL END), 0) as avg_efficiency_wh_km,
                       COALESCE(SUM(autopilot_km), 0) as total_autopilot_km
                FROM drives {where_clause}
            """, params)
            agg_row = cur.fetchone()
            total_count = agg_row["total_count"] if agg_row else 0

            # Fetch paginated rows
            query = f"""
                SELECT id, provider, vin, started_at, ended_at, duration_s, distance_km,
                       energy_kwh, efficiency_wh_km, start_soc, end_soc, start_location,
                       end_location, start_odometer_km, end_odometer_km,
                       autopilot_km, autopilot_pct, start_latitude, start_longitude,
                       end_latitude, end_longitude, raw_json
                FROM drives {where_clause}
                ORDER BY started_at DESC
            """
            if limit > 0:
                query += " LIMIT ? OFFSET ?"
                fetch_params = params + [limit, offset]
            else:
                fetch_params = params

            cur.execute(query, fetch_params)
            items = [dict(r) for r in cur.fetchall()]

            if return_dict:
                return {
                    "items": items,
                    "total": total_count,
                    "limit": limit,
                    "offset": offset,
                    "analytics": {
                        "total_distance_km": round(agg_row["total_distance_km"], 1) if agg_row else 0.0,
                        "total_energy_kwh": round(agg_row["total_energy_kwh"], 1) if agg_row else 0.0,
                        "avg_efficiency_wh_km": round(agg_row["avg_efficiency_wh_km"], 1) if agg_row else 0.0,
                        "total_autopilot_km": round(agg_row["total_autopilot_km"], 1) if agg_row else 0.0,
                    }
                }
            return items
        finally:
            conn.close()

    def get_drive_by_id(self, drive_id: int) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, provider, vin, started_at, ended_at, duration_s, distance_km,
                       energy_kwh, efficiency_wh_km, start_soc, end_soc, start_location,
                       end_location, start_odometer_km, end_odometer_km,
                       autopilot_km, autopilot_pct, start_latitude, start_longitude,
                       end_latitude, end_longitude, raw_json
                FROM drives WHERE id = ?
            """, (drive_id,))
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_drive_trackpoints(self, vin: str, started_at: str, ended_at: str) -> List[Dict[str, Any]]:
        """Queries high-resolution GPS trackpoints from live_telemetry for a drive session."""
        if not vin or not started_at:
            return []
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT timestamp, latitude, longitude, speed_kmh, power_kw, battery_temp_c, soc, odometer_km
                FROM live_telemetry
                WHERE vin = ? AND timestamp >= ? AND timestamp <= ?
                  AND latitude IS NOT NULL AND longitude IS NOT NULL
                  AND (latitude != 0.0 OR longitude != 0.0)
                ORDER BY timestamp ASC
            """, (vin, started_at, ended_at or started_at))
            return [dict(r) for r in cur.fetchall()]
        except Exception:
            return []
        finally:
            conn.close()

    def get_charges(self, vin: Optional[str] = None,
                    start_date: Optional[str] = None,
                    end_date: Optional[str] = None,
                    search: Optional[str] = None,
                    limit: int = 50,
                    offset: int = 0,
                    return_dict: bool = False) -> Any:
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            conditions = []
            params = []

            if vin:
                conditions.append("vin = ?")
                params.append(vin)
            if start_date:
                conditions.append("started_at >= ?")
                params.append(start_date)
            if end_date:
                conditions.append("started_at <= ?")
                params.append(end_date)
            if search:
                conditions.append("(location LIKE ? OR provider LIKE ?)")
                search_param = f"%{search}%"
                params.extend([search_param, search_param])

            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

            # Total matching count & analytics summary
            cur.execute(f"""
                SELECT COUNT(*) as total_count,
                       COALESCE(SUM(energy_added_kwh), 0) as total_energy_added_kwh,
                       COALESCE(SUM(cost), 0) as total_cost,
                       SUM(CASE WHEN is_fast_charge = 1 THEN 1 ELSE 0 END) as fast_charges,
                       SUM(CASE WHEN is_fast_charge = 0 THEN 1 ELSE 0 END) as slow_charges
                FROM charges {where_clause}
            """, params)
            agg_row = cur.fetchone()
            total_count = agg_row["total_count"] if agg_row else 0

            # Fetch paginated rows
            query = f"""
                SELECT id, provider, vin, started_at, ended_at, duration_s, energy_added_kwh,
                       start_soc, end_soc, range_added_km, peak_kw, cost, location, is_fast_charge, raw_json
                FROM charges {where_clause}
                ORDER BY started_at DESC
            """
            if limit > 0:
                query += " LIMIT ? OFFSET ?"
                fetch_params = params + [limit, offset]
            else:
                fetch_params = params

            cur.execute(query, fetch_params)
            items = [dict(r) for r in cur.fetchall()]

            if return_dict:
                return {
                    "items": items,
                    "total": total_count,
                    "limit": limit,
                    "offset": offset,
                    "analytics": {
                        "total_energy_added_kwh": round(agg_row["total_energy_added_kwh"], 1) if agg_row else 0.0,
                        "total_cost": round(agg_row["total_cost"], 2) if agg_row else 0.0,
                        "fast_charges": agg_row["fast_charges"] if agg_row else 0,
                        "slow_charges": agg_row["slow_charges"] if agg_row else 0,
                    }
                }
            return items
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

    def get_live_vehicle_state(self, vin: Optional[str] = None) -> Dict[str, Any]:
        """Returns the full digital twin status of the vehicle including cabin interior, climate, closures, and battery."""
        conn = self._get_conn()
        live_raw = {}
        row = None
        try:
            cur = conn.cursor()
            params = []
            vin_clause = ""
            if vin and vin != "ALL":
                vin_clause = "WHERE vin = ?"
                params.append(vin)
            cur.execute(f"""
                SELECT raw_json, soc, speed_kmh, power_kw, battery_temp_c, inside_temp_c, outside_temp_c,
                       odometer_km, charging_state, latitude, longitude, timestamp, vin
                FROM live_telemetry {vin_clause}
                ORDER BY timestamp DESC LIMIT 1
            """, params)
            row = cur.fetchone()
            if row and row["raw_json"]:
                try:
                    parsed = json.loads(row["raw_json"])
                    if isinstance(parsed, dict):
                        live_raw = parsed.get("response", parsed)
                except Exception:
                    live_raw = {}
        finally:
            conn.close()

        # Extract nested structures if present
        charge_st = live_raw.get("charge_state", {}) if isinstance(live_raw.get("charge_state"), dict) else {}
        climate_st = live_raw.get("climate_state", {}) if isinstance(live_raw.get("climate_state"), dict) else {}
        drive_st = live_raw.get("drive_state", {}) if isinstance(live_raw.get("drive_state"), dict) else {}
        vehicle_st = live_raw.get("vehicle_state", {}) if isinstance(live_raw.get("vehicle_state"), dict) else {}

        # Default fallback values representing a realistic healthy Tesla Model 3/Y
        soc_val = row["soc"] if row and row["soc"] is not None else charge_st.get("battery_level", 78)
        chg_state = row["charging_state"] if row and row["charging_state"] else charge_st.get("charging_state", "Disconnected")
        speed_val = row["speed_kmh"] if row and row["speed_kmh"] is not None else drive_st.get("speed", 0)
        pwr_val = row["power_kw"] if row and row["power_kw"] is not None else drive_st.get("power", 0.0)
        odo_val = row["odometer_km"] if row and row["odometer_km"] is not None else vehicle_st.get("odometer", 32750.0)
        lat_val = row["latitude"] if row and row["latitude"] is not None else drive_st.get("latitude", 40.4168)
        lon_val = row["longitude"] if row and row["longitude"] is not None else drive_st.get("longitude", -3.7038)
        ts_val = row["timestamp"] if row and row["timestamp"] else live_raw.get("timestamp", "2026-09-26 19:45:00")
        car_vin = (row["vin"] if row and row["vin"] else (live_raw.get("vin") or "5YJ3E7EB8NF123456"))

        return {
            "vin": car_vin,
            "display_name": "Tesla Model 3/Y Long Range",
            "timestamp": ts_val,
            "charge_state": {
                "battery_level": int(soc_val),
                "usable_battery_level": int(charge_st.get("usable_battery_level", max(0, int(soc_val) - 1))),
                "charge_limit_soc": int(charge_st.get("charge_limit_soc", 80)),
                "battery_range": round(float(charge_st.get("battery_range", 395.2)), 1),
                "charging_state": str(chg_state),
                "charge_port_door_open": bool(charge_st.get("charge_port_door_open", False)),
                "charge_port_latch": str(charge_st.get("charge_port_latch", "Disengaged")),
                "conn_charge_cable": str(charge_st.get("conn_charge_cable", "<none>")),
                "charger_voltage": int(charge_st.get("charger_voltage", 0 if chg_state == "Disconnected" else 230)),
                "charger_actual_current": int(charge_st.get("charger_actual_current", 0 if chg_state == "Disconnected" else 16)),
                "charge_current_request": int(charge_st.get("charge_current_request", 16)),
                "charge_current_request_max": int(charge_st.get("charge_current_request_max", 16)),
                "charger_power": int(charge_st.get("charger_power", 0 if chg_state == "Disconnected" else 11)),
                "charge_energy_added": round(float(charge_st.get("charge_energy_added", 18.5)), 2),
                "time_to_full_charge": round(float(charge_st.get("time_to_full_charge", 0.0)), 1),
                "battery_heater_on": bool(charge_st.get("battery_heater_on", False)),
                "fast_charger_present": bool(charge_st.get("fast_charger_present", False)),
            },
            "climate_state": {
                "inside_temp": round(float(row["inside_temp_c"] if row and row["inside_temp_c"] is not None else climate_st.get("inside_temp", 21.5)), 1),
                "outside_temp": round(float(row["outside_temp_c"] if row and row["outside_temp_c"] is not None else climate_st.get("outside_temp", 17.0)), 1),
                "driver_temp_setting": round(float(climate_st.get("driver_temp_setting", 21.0)), 1),
                "passenger_temp_setting": round(float(climate_st.get("passenger_temp_setting", 21.5)), 1),
                "is_climate_on": bool(climate_st.get("is_climate_on", True)),
                "is_auto_conditioning_on": bool(climate_st.get("is_auto_conditioning_on", True)),
                "fan_status": int(climate_st.get("fan_status", 3)),
                "climate_keeper_mode": str(climate_st.get("climate_keeper_mode", "off")),
                "defrost_mode": int(climate_st.get("defrost_mode", 0)),
                "seat_heater_left": int(climate_st.get("seat_heater_left", 2)),
                "seat_heater_right": int(climate_st.get("seat_heater_right", 1)),
                "seat_heater_rear_left": int(climate_st.get("seat_heater_rear_left", 0)),
                "seat_heater_rear_center": int(climate_st.get("seat_heater_rear_center", 0)),
                "seat_heater_rear_right": int(climate_st.get("seat_heater_rear_right", 0)),
                "steering_wheel_heater": bool(climate_st.get("steering_wheel_heater", True)),
                "cabin_overheat_protection": str(climate_st.get("cabin_overheat_protection", "On")),
            },
            "drive_state": {
                "shift_state": str(drive_st.get("shift_state", "P")),
                "speed": int(speed_val),
                "power": int(pwr_val),
                "latitude": float(lat_val),
                "longitude": float(lon_val),
                "heading": int(drive_st.get("heading", 182)),
                "gps_as_of": int(drive_st.get("gps_as_of", 1727372000)),
                "active_route_destination": str(drive_st.get("active_route_destination", "Paseo de la Castellana 200, Madrid")),
                "active_route_energy_at_arrival": int(drive_st.get("active_route_energy_at_arrival", 64)),
                "active_route_traffic_minutes_delay": round(float(drive_st.get("active_route_traffic_minutes_delay", 4.5)), 1),
            },
            "vehicle_state": {
                "odometer": round(float(odo_val), 1),
                "locked": bool(vehicle_st.get("locked", True)),
                "sentry_mode": bool(vehicle_st.get("sentry_mode", True)),
                "is_user_present": bool(vehicle_st.get("is_user_present", True)),
                "df": int(vehicle_st.get("df", 0)),
                "pf": int(vehicle_st.get("pf", 0)),
                "dr": int(vehicle_st.get("dr", 0)),
                "pr": int(vehicle_st.get("pr", 0)),
                "fd_window": int(vehicle_st.get("fd_window", 0)),
                "fp_window": int(vehicle_st.get("fp_window", 0)),
                "rd_window": int(vehicle_st.get("rd_window", 0)),
                "rp_window": int(vehicle_st.get("rp_window", 0)),
                "ft": int(vehicle_st.get("ft", 0)),
                "rt": int(vehicle_st.get("rt", 0)),
                "tpms_pressure_fl": round(float(vehicle_st.get("tpms_pressure_fl", 2.9)), 2),
                "tpms_pressure_fr": round(float(vehicle_st.get("tpms_pressure_fr", 2.9)), 2),
                "tpms_pressure_rl": round(float(vehicle_st.get("tpms_pressure_rl", 2.8)), 2),
                "tpms_pressure_rr": round(float(vehicle_st.get("tpms_pressure_rr", 2.8)), 2),
                "center_display_state": int(vehicle_st.get("center_display_state", 2)),
                "car_version": str(vehicle_st.get("car_version", "2024.26.8")),
                "software_update": vehicle_st.get("software_update", {"status": "available", "version": "2024.32.4"}),
            },
            "fleet_telemetry": {
                "bms_full_charge_complete": bool(live_raw.get("BmsFullchargecomplete", True)),
                "brake_pedal_pos": round(float(live_raw.get("BrakePedalPos", 0.0)), 2),
                "ac_charging_energy_in": round(float(live_raw.get("ACChargingEnergyIn", 1450.4)), 1),
                "dc_charging_energy_in": round(float(live_raw.get("DCChargingEnergyIn", 420.8)), 1),
                "brick_voltage_max": round(float(live_raw.get("BrickVoltageMax", 4.152)), 3),
                "brick_voltage_min": round(float(live_raw.get("BrickVoltageMin", 4.148)), 3),
                "cell_delta_mv": round(abs(float(live_raw.get("BrickVoltageMax", 4.152)) - float(live_raw.get("BrickVoltageMin", 4.148))) * 1000, 1),
                "di_inverter_tr": round(float(live_raw.get("DiInverterTR", 34.2)), 1),
                "di_inverter_tf": round(float(live_raw.get("DiInverterTF", 31.8)), 1),
            }
        }

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
            {
                "provider": "demo", "vin": vin, "started_at": "2026-06-10 08:30:00", "ended_at": "2026-06-10 09:25:00",
                "duration_s": 3300, "distance_km": 92.4, "energy_kwh": 14.8, "efficiency_wh_km": 160.2,
                "start_soc": 88.0, "end_soc": 68.0, "start_temp_c": 21.0, "end_temp_c": 24.0,
                "start_location": "Madrid Norte (Chamartín)", "end_location": "Segovia Centro (Acueducto)",
                "start_latitude": 40.4721, "start_longitude": -3.6826,
                "end_latitude": 40.9481, "end_longitude": -4.1184,
                "start_odometer_km": 32100.0, "end_odometer_km": 32192.4, "max_speed_kmh": 125.0,
                "autopilot_km": 68.5, "autopilot_pct": 74.1,
            },
            {
                "provider": "demo", "vin": vin, "started_at": "2026-06-12 17:15:00", "ended_at": "2026-06-12 18:10:00",
                "duration_s": 3300, "distance_km": 91.8, "energy_kwh": 13.5, "efficiency_wh_km": 147.1,
                "start_soc": 80.0, "end_soc": 62.0, "start_temp_c": 26.0, "end_temp_c": 28.0,
                "start_location": "Segovia Centro", "end_location": "Madrid (Moncloa)",
                "start_latitude": 40.9481, "start_longitude": -4.1184,
                "end_latitude": 40.4354, "end_longitude": -3.7196,
                "start_odometer_km": 32250.0, "end_odometer_km": 32341.8, "max_speed_kmh": 122.0,
                "autopilot_km": 72.0, "autopilot_pct": 78.4,
            },
            {
                "provider": "demo", "vin": vin, "started_at": "2026-06-15 10:00:00", "ended_at": "2026-06-15 10:50:00",
                "duration_s": 3000, "distance_km": 74.2, "energy_kwh": 11.6, "efficiency_wh_km": 156.3,
                "start_soc": 75.0, "end_soc": 59.0, "start_temp_c": 23.0, "end_temp_c": 25.0,
                "start_location": "Madrid (Atocha)", "end_location": "Toledo (Plaza Zocodover)",
                "start_latitude": 40.4066, "start_longitude": -3.6903,
                "end_latitude": 39.8597, "end_longitude": -4.0208,
                "start_odometer_km": 32400.0, "end_odometer_km": 32474.2, "max_speed_kmh": 120.0,
                "autopilot_km": 50.0, "autopilot_pct": 67.4,
            },
            {
                "provider": "demo", "vin": vin, "started_at": "2026-06-18 08:15:00", "ended_at": "2026-06-18 08:45:00",
                "duration_s": 1800, "distance_km": 24.5, "energy_kwh": 3.7, "efficiency_wh_km": 151.0,
                "start_soc": 70.0, "end_soc": 65.0, "start_temp_c": 20.0, "end_temp_c": 21.0,
                "start_location": "Casa (Majadahonda)", "end_location": "Oficina (Castellana 200)",
                "start_latitude": 40.4735, "start_longitude": -3.8722,
                "end_latitude": 40.4632, "end_longitude": -3.6898,
                "start_odometer_km": 32510.0, "end_odometer_km": 32534.5, "max_speed_kmh": 95.0,
                "autopilot_km": 12.0, "autopilot_pct": 49.0,
            },
            {
                "provider": "demo", "vin": vin, "started_at": "2026-06-20 09:00:00", "ended_at": "2026-06-20 10:15:00",
                "duration_s": 4500, "distance_km": 115.0, "energy_kwh": 19.2, "efficiency_wh_km": 167.0,
                "start_soc": 95.0, "end_soc": 69.0, "start_temp_c": 19.0, "end_temp_c": 22.0,
                "start_location": "Madrid (Moncloa)", "end_location": "Ávila (Murallas)",
                "start_latitude": 40.4354, "start_longitude": -3.7196,
                "end_latitude": 40.6565, "end_longitude": -4.7016,
                "start_odometer_km": 32600.0, "end_odometer_km": 32715.0, "max_speed_kmh": 128.0,
                "autopilot_km": 88.0, "autopilot_pct": 76.5,
            },
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

        # Seed realistic live telemetry trackpoints for Drive 4 (Majadahonda -> Castellana)
        demo_points = [
            ("2026-06-18 08:15:00", 40.4735, -3.8722, 20.0, 70.0, 32510.0),
            ("2026-06-18 08:20:00", 40.4680, -3.8350, 78.0, 69.2, 32515.2),
            ("2026-06-18 08:25:00", 40.4590, -3.7850, 92.0, 68.1, 32521.8),
            ("2026-06-18 08:32:00", 40.4485, -3.7250, 85.0, 66.9, 32527.5),
            ("2026-06-18 08:38:00", 40.4550, -3.6980, 52.0, 65.8, 32531.4),
            ("2026-06-18 08:45:00", 40.4632, -3.6898, 0.0, 65.0, 32534.5),
        ]
        for ts, lat, lon, spd, soc_val, odo_val in demo_points:
            self.insert_live_telemetry({
                "vin": vin,
                "timestamp": ts,
                "soc": soc_val,
                "speed_kmh": spd,
                "power_kw": 18.5 if spd > 0 else 0.0,
                "battery_temp_c": 22.0,
                "odometer_km": odo_val,
                "charging_state": "STANDBY",
                "latitude": lat,
                "longitude": lon
            })

        # Latest vehicle status
        self.insert_live_telemetry({
            "vin": vin,
            "timestamp": "2026-06-22 15:30:00",
            "soc": 74.0,
            "speed_kmh": 0.0,
            "power_kw": 0.0,
            "battery_temp_c": 24.5,
            "odometer_km": 32750.0,
            "charging_state": "STANDBY",
            "latitude": 40.4632,
            "longitude": -3.6898
        })

        return {
            "drives": n_drives,
            "charges": n_charges,
            "battery": n_battery,
            "live": 1
        }
