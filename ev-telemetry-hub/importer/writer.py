"""
Telemetry Writer for LaVera EV Telemetry Hub.
Stores records in SQLite (Offline storage) and/or InfluxDB 2.x.
"""

import json
import sqlite3
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.error


class TelemetryWriter:
    """Manages persistence to SQLite and InfluxDB."""

    def __init__(self, db_path: str = "lavera.db", influx_url: Optional[str] = None,
                 influx_token: Optional[str] = None, influx_org: Optional[str] = None,
                 influx_bucket: Optional[str] = None):
        self.db_path = db_path
        self.influx_url = influx_url.rstrip("/") if influx_url else None
        self.influx_token = influx_token
        self.influx_org = influx_org
        self.influx_bucket = influx_bucket
        self._init_sqlite()

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_sqlite(self):
        """Initializes tables in SQLite database if not present."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
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
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS live_telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vin TEXT,
                    timestamp TEXT,
                    soc REAL,
                    speed_kmh REAL,
                    power_kw REAL,
                    battery_temp_c REAL,
                    odometer_km REAL,
                    charging_state TEXT,
                    latitude REAL,
                    longitude REAL,
                    raw_json TEXT
                );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_drives_time ON drives(started_at);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_charges_time ON charges(started_at);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_battery_time ON battery_health(timestamp);")
            conn.commit()
        finally:
            conn.close()

    def write_drives(self, drives: List[Dict[str, Any]]) -> int:
        """Inserts drives into SQLite and InfluxDB."""
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
                            end_odometer_km, max_speed_kmh, raw_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    inserted += 1
                except sqlite3.Error:
                    continue
            conn.commit()
        finally:
            conn.close()

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
        """Inserts charge sessions into SQLite and InfluxDB."""
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

        if self.influx_url and self.influx_token:
            lines = []
            for c in charges:
                lines.append(f"charges,vin={c.get('vin','DEFAULT')},provider={c.get('provider','unknown')} "
                             f"energy_added_kwh={c.get('energy_added_kwh',0.0)},start_soc={c.get('start_soc',0.0)},"
                             f"end_soc={c.get('end_soc',0.0)},peak_kw={c.get('peak_kw',0.0)},cost={c.get('cost',0.0)}")
            self._send_influx(lines)

        return inserted

    def write_battery_health(self, reports: List[Dict[str, Any]]) -> int:
        """Inserts battery degradation reports into SQLite and InfluxDB."""
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

        if self.influx_url and self.influx_token:
            lines = []
            for b in reports:
                lines.append(f"battery_health,vin={b.get('vin','DEFAULT')},provider={b.get('provider','unknown')} "
                             f"capacity_kwh={b.get('capacity_kwh',0.0)},degradation_pct={b.get('degradation_pct',0.0)},"
                             f"max_range_km={b.get('max_range_km',0.0)},odometer_km={b.get('odometer_km',0.0)}")
            self._send_influx(lines)

        return inserted

    def write_idles(self, idles: List[Dict[str, Any]]) -> int:
        """Inserts idle / vampire drain records into SQLite."""
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
