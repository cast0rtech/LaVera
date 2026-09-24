"""
Telemetry Writer for LaVera EV Telemetry Hub.
Stores records in SQLite (Offline storage), TimescaleDB (PostgreSQL 16),
and/or InfluxDB 2.x.
"""

import json
import sqlite3
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.error

try:
    import psycopg2
    from psycopg2.extras import execute_batch
except ImportError:
    psycopg2 = None


class TelemetryWriter:
    """Manages persistence to SQLite, TimescaleDB (PostgreSQL), and InfluxDB."""

    def __init__(self, db_path: str = "lavera.db",
                 timescale_host: Optional[str] = None,
                 timescale_port: int = 5432,
                 timescale_user: Optional[str] = None,
                 timescale_password: Optional[str] = None,
                 timescale_db: Optional[str] = None,
                 influx_url: Optional[str] = None,
                 influx_token: Optional[str] = None,
                 influx_org: Optional[str] = None,
                 influx_bucket: Optional[str] = None):
        self.db_path = db_path
        self.timescale_host = timescale_host
        self.timescale_port = timescale_port
        self.timescale_user = timescale_user
        self.timescale_password = timescale_password
        self.timescale_db = timescale_db
        
        self.influx_url = influx_url.rstrip("/") if influx_url else None
        self.influx_token = influx_token
        self.influx_org = influx_org
        self.influx_bucket = influx_bucket
        
        self._init_sqlite()
        self.pg_conn = None
        if psycopg2 and self.timescale_host and self.timescale_user and self.timescale_db:
            try:
                self.pg_conn = psycopg2.connect(
                    host=self.timescale_host,
                    port=self.timescale_port,
                    user=self.timescale_user,
                    password=self.timescale_password,
                    dbname=self.timescale_db
                )
                self.pg_conn.autocommit = True
            except Exception as e:
                print(f"[!] Warning: Could not connect to TimescaleDB: {e}")
                self.pg_conn = None

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_sqlite(self):
        """Initializes tables in SQLite database if not present."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS drives (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT,
                    vin TEXT,
                    started_at TEXT,
                    ended_at TEXT,
                    duration_s INTEGER,
                    distance_km REAL,
                    energy_kwh REAL,
                    efficiency_wh_km REAL,
                    start_soc REAL,
                    end_soc REAL,
                    start_temp_c REAL,
                    end_temp_c REAL,
                    start_location TEXT,
                    end_location TEXT,
                    start_odometer_km REAL,
                    end_odometer_km REAL,
                    max_speed_kmh REAL,
                    autopilot_km REAL,
                    autopilot_duration_s INTEGER,
                    autopilot_pct REAL,
                    raw_json TEXT,
                    UNIQUE(vin, started_at)
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS charges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT,
                    vin TEXT,
                    started_at TEXT,
                    ended_at TEXT,
                    duration_s INTEGER,
                    energy_added_kwh REAL,
                    start_soc REAL,
                    end_soc REAL,
                    range_added_km REAL,
                    peak_kw REAL,
                    cost REAL,
                    location TEXT,
                    is_fast_charge INTEGER,
                    raw_json TEXT,
                    UNIQUE(vin, started_at)
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS battery_health (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT,
                    vin TEXT,
                    timestamp TEXT,
                    capacity_kwh REAL,
                    original_capacity_kwh REAL,
                    degradation_pct REAL,
                    max_range_km REAL,
                    odometer_km REAL,
                    raw_json TEXT,
                    UNIQUE(vin, timestamp)
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS live_telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vin TEXT DEFAULT 'DEFAULT',
                    timestamp TEXT,
                    soc REAL,
                    speed_kmh REAL,
                    power_kw REAL,
                    battery_temp_c REAL,
                    inside_temp_c REAL,
                    outside_temp_c REAL,
                    odometer_km REAL,
                    charging_state TEXT,
                    latitude REAL,
                    longitude REAL,
                    raw_json TEXT
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS idle_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT,
                    vin TEXT,
                    started_at TEXT,
                    ended_at TEXT,
                    duration_s INTEGER,
                    soc_loss_pct REAL,
                    range_loss_km REAL,
                    raw_json TEXT,
                    UNIQUE(vin, started_at)
                );
            """)

            # Run column migrations for existing SQLite databases
            for col, col_type in [("autopilot_km", "REAL"), ("autopilot_duration_s", "INTEGER"), ("autopilot_pct", "REAL")]:
                try:
                    cursor.execute(f"ALTER TABLE drives ADD COLUMN {col} {col_type};")
                except sqlite3.Error:
                    pass

            conn.commit()
        finally:
            conn.close()

    def write_drives(self, drives: List[Dict[str, Any]]) -> int:
        """Inserts drive sessions into SQLite, TimescaleDB, and InfluxDB."""
        if not drives:
            return 0
        inserted = 0
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            for d in drives:
                try:
                    cursor.execute("""
                        INSERT OR REPLACE INTO drives (
                            provider, vin, started_at, ended_at, duration_s, distance_km,
                            energy_kwh, efficiency_wh_km, start_soc, end_soc, start_temp_c,
                            end_temp_c, start_location, end_location, start_odometer_km,
                            end_odometer_km, max_speed_kmh, autopilot_km, autopilot_duration_s,
                            autopilot_pct, raw_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        d.get("provider", "unknown"),
                        d.get("vin", "DEFAULT"),
                        d.get("started_at"),
                        d.get("ended_at"),
                        d.get("duration_s", 0),
                        d.get("distance_km", 0.0),
                        d.get("energy_kwh", 0.0),
                        d.get("efficiency_wh_km", 0.0),
                        d.get("start_soc", 0.0),
                        d.get("end_soc", 0.0),
                        d.get("start_temp_c", 0.0),
                        d.get("end_temp_c", 0.0),
                        d.get("start_location", ""),
                        d.get("end_location", ""),
                        d.get("start_odometer_km", 0.0),
                        d.get("end_odometer_km", 0.0),
                        d.get("max_speed_kmh", 0.0),
                        d.get("autopilot_km", 0.0),
                        d.get("autopilot_duration_s", 0),
                        d.get("autopilot_pct", 0.0),
                        json.dumps(d)
                    ))
                    inserted += 1
                except sqlite3.Error:
                    continue
            conn.commit()
        finally:
            conn.close()

        if self.pg_conn:
            try:
                pg_cur = self.pg_conn.cursor()
                for d in drives:
                    pg_cur.execute("""
                        INSERT INTO drives (
                            provider, vin, started_at, ended_at, duration_s, distance_km,
                            energy_kwh, efficiency_wh_km, start_soc, end_soc, start_temp_c,
                            end_temp_c, start_location, end_location, start_odometer_km,
                            end_odometer_km, max_speed_kmh, raw_json
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        d.get("provider", "unknown"),
                        d.get("vin", "DEFAULT"),
                        d.get("started_at"),
                        d.get("ended_at"),
                        d.get("duration_s", 0),
                        d.get("distance_km", 0.0),
                        d.get("energy_kwh", 0.0),
                        d.get("efficiency_wh_km", 0.0),
                        d.get("start_soc", 0.0),
                        d.get("end_soc", 0.0),
                        d.get("start_temp_c", 0.0),
                        d.get("end_temp_c", 0.0),
                        d.get("start_location", ""),
                        d.get("end_location", ""),
                        d.get("start_odometer_km", 0.0),
                        d.get("end_odometer_km", 0.0),
                        d.get("max_speed_kmh", 0.0),
                        json.dumps(d)
                    ))
                pg_cur.close()
            except Exception as e:
                print(f"[!] Error writing drives to TimescaleDB: {e}")

        if self.influx_url and self.influx_token:
            lines = []
            for d in drives:
                lines.append(f"drives,vin={d.get('vin','DEFAULT')},provider={d.get('provider','unknown')} "
                             f"distance_km={d.get('distance_km',0.0)},energy_kwh={d.get('energy_kwh',0.0)},"
                             f"efficiency_wh_km={d.get('efficiency_wh_km',0.0)},start_soc={d.get('start_soc',0.0)},"
                             f"end_soc={d.get('end_soc',0.0)}")
            self._send_influx(lines)

        return inserted

    def write_charges(self, charges: List[Dict[str, Any]]) -> int:
        """Inserts charge sessions into SQLite, TimescaleDB, and InfluxDB."""
        if not charges:
            return 0
        inserted = 0
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            for c in charges:
                try:
                    cursor.execute("""
                        INSERT OR REPLACE INTO charges (
                            provider, vin, started_at, ended_at, duration_s, energy_added_kwh,
                            start_soc, end_soc, range_added_km, peak_kw, cost, location,
                            is_fast_charge, raw_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        c.get("provider", "unknown"),
                        c.get("vin", "DEFAULT"),
                        c.get("started_at"),
                        c.get("ended_at"),
                        c.get("duration_s", 0),
                        c.get("energy_added_kwh", 0.0),
                        c.get("start_soc", 0.0),
                        c.get("end_soc", 0.0),
                        c.get("range_added_km", 0.0),
                        c.get("peak_kw", 0.0),
                        c.get("cost", 0.0),
                        c.get("location", ""),
                        c.get("is_fast_charge", 0),
                        json.dumps(c)
                    ))
                    inserted += 1
                except sqlite3.Error:
                    continue
            conn.commit()
        finally:
            conn.close()

        if self.pg_conn:
            try:
                pg_cur = self.pg_conn.cursor()
                for c in charges:
                    pg_cur.execute("""
                        INSERT INTO charges (
                            provider, vin, started_at, ended_at, duration_s, energy_added_kwh,
                            start_soc, end_soc, range_added_km, peak_kw, cost, location,
                            is_fast_charge, raw_json
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        c.get("provider", "unknown"),
                        c.get("vin", "DEFAULT"),
                        c.get("started_at"),
                        c.get("ended_at"),
                        c.get("duration_s", 0),
                        c.get("energy_added_kwh", 0.0),
                        c.get("start_soc", 0.0),
                        c.get("end_soc", 0.0),
                        c.get("range_added_km", 0.0),
                        c.get("peak_kw", 0.0),
                        c.get("cost", 0.0),
                        c.get("location", ""),
                        c.get("is_fast_charge", 0),
                        json.dumps(c)
                    ))
                pg_cur.close()
            except Exception as e:
                print(f"[!] Error writing charges to TimescaleDB: {e}")

        if self.influx_url and self.influx_token:
            lines = []
            for c in charges:
                lines.append(f"charges,vin={c.get('vin','DEFAULT')},provider={c.get('provider','unknown')} "
                             f"energy_added_kwh={c.get('energy_added_kwh',0.0)},start_soc={c.get('start_soc',0.0)},"
                             f"end_soc={c.get('end_soc',0.0)},peak_kw={c.get('peak_kw',0.0)},cost={c.get('cost',0.0)}")
            self._send_influx(lines)

        return inserted

    def write_battery_health(self, reports: List[Dict[str, Any]]) -> int:
        """Inserts battery degradation reports into SQLite, TimescaleDB, and InfluxDB."""
        if not reports:
            return 0
        inserted = 0
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            for b in reports:
                try:
                    cursor.execute("""
                        INSERT OR REPLACE INTO battery_health (
                            provider, vin, timestamp, capacity_kwh, original_capacity_kwh,
                            degradation_pct, max_range_km, odometer_km, raw_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        b.get("provider", "unknown"),
                        b.get("vin", "DEFAULT"),
                        b.get("timestamp"),
                        b.get("capacity_kwh", 0.0),
                        b.get("original_capacity_kwh", 0.0),
                        b.get("degradation_pct", 0.0),
                        b.get("max_range_km", 0.0),
                        b.get("odometer_km", 0.0),
                        json.dumps(b)
                    ))
                    inserted += 1
                except sqlite3.Error:
                    continue
            conn.commit()
        finally:
            conn.close()

        if self.pg_conn:
            try:
                pg_cur = self.pg_conn.cursor()
                for b in reports:
                    pg_cur.execute("""
                        INSERT INTO battery_health (
                            provider, vin, reported_at, capacity_kwh, original_capacity_kwh,
                            degradation_pct, max_range_km, odometer_km, raw_json
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        b.get("provider", "unknown"),
                        b.get("vin", "DEFAULT"),
                        b.get("timestamp"),
                        b.get("capacity_kwh", 0.0),
                        b.get("original_capacity_kwh", 0.0),
                        b.get("degradation_pct", 0.0),
                        b.get("max_range_km", 0.0),
                        b.get("odometer_km", 0.0),
                        json.dumps(b)
                    ))
                pg_cur.close()
            except Exception as e:
                print(f"[!] Error writing battery health to TimescaleDB: {e}")

        if self.influx_url and self.influx_token:
            lines = []
            for b in reports:
                lines.append(f"battery_health,vin={b.get('vin','DEFAULT')},provider={b.get('provider','unknown')} "
                             f"capacity_kwh={b.get('capacity_kwh',0.0)},degradation_pct={b.get('degradation_pct',0.0)},"
                             f"max_range_km={b.get('max_range_km',0.0)},odometer_km={b.get('odometer_km',0.0)}")
            self._send_influx(lines)

        return inserted

    def write_idles(self, idles: List[Dict[str, Any]]) -> int:
        """Inserts idle / vampire drain records into SQLite and TimescaleDB."""
        if not idles:
            return 0
        inserted = 0
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            for i in idles:
                try:
                    cursor.execute("""
                        INSERT OR REPLACE INTO idle_logs (
                            provider, vin, started_at, ended_at, duration_s, soc_loss_pct,
                            range_loss_km, raw_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        i.get("provider", "unknown"),
                        i.get("vin", "DEFAULT"),
                        i.get("started_at"),
                        i.get("ended_at"),
                        i.get("duration_s", 0),
                        i.get("soc_loss_pct", 0.0),
                        i.get("range_loss_km", 0.0),
                        json.dumps(i)
                    ))
                    inserted += 1
                except sqlite3.Error:
                    continue
            conn.commit()
        finally:
            conn.close()

        if self.pg_conn:
            try:
                pg_cur = self.pg_conn.cursor()
                for i in idles:
                    pg_cur.execute("""
                        INSERT INTO idle_logs (
                            provider, vin, started_at, ended_at, duration_s, soc_loss_pct,
                            range_loss_km, raw_json
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        i.get("provider", "unknown"),
                        i.get("vin", "DEFAULT"),
                        i.get("started_at"),
                        i.get("ended_at"),
                        i.get("duration_s", 0),
                        i.get("soc_loss_pct", 0.0),
                        i.get("range_loss_km", 0.0),
                        json.dumps(i)
                    ))
                pg_cur.close()
            except Exception as e:
                print(f"[!] Error writing idles to TimescaleDB: {e}")

        return inserted

    def _send_influx(self, lines: List[str]):
        """Transmits line protocol batches to InfluxDB HTTP endpoint."""
        if not self.influx_url or not self.influx_token or not self.influx_bucket or not lines:
            return
        url = f"{self.influx_url}/api/v2/write?org={self.influx_org}&bucket={self.influx_bucket}&precision=s"
        data = "\n".join(lines).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Token {self.influx_token}",
                "Content-Type": "text/plain; charset=utf-8",
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                pass
        except Exception:
            pass
