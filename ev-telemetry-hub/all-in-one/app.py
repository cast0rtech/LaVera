"""
LaVera All-in-One Offline EV Telemetry Hub Server.
Provides local REST API, real-time telemetry ingestion, Tessie/TeslaFi importer,
and offline interactive dashboard.
Runs with standard Python library (zero mandatory external pip dependencies).
"""

import email
import io
import json
import mimetypes
import os
import re
import sys
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import Any, Dict, List, Optional

if sys.platform.startswith("win"):
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from importer.normalizer import parse_timestamp, clean_header_key, decode_file_bytes, detect_delimiter
from importer.teslafi_parser import (
    detect_teslafi_type,
    parse_teslafi_drives,
    parse_teslafi_charges,
    parse_teslafi_battery_report,
    parse_teslafi_idles,
)
from importer.tessie_api import TessieAPIClient
from importer.tessie_parser import (
    detect_tessie_type,
    parse_tessie_drives,
    parse_tessie_charges,
    parse_tessie_battery_health,
)
from storage import OfflineStorage

DB_PATH = os.getenv("LAVERA_DB_PATH", os.path.join(current_dir, "data", "lavera.db"))
WEB_DIR = os.path.join(current_dir, "web")
PORT = int(os.getenv("PORT", "8088"))

storage = OfflineStorage(db_path=DB_PATH)


def parse_multipart_payload(body: bytes, content_type: str) -> dict:
    """Parses multipart/form-data using standard library email module with robust boundary fallback."""
    fields = {}
    try:
        raw = b"MIME-Version: 1.0\r\nContent-Type: " + content_type.encode("utf-8") + b"\r\n\r\n" + body
        msg = email.message_from_bytes(raw)
        for part in msg.walk():
            cd = part.get("Content-Disposition", "")
            if "form-data" in cd:
                match = re.search(r'name=["\']?([^";\r\n\'"]+)["\']?', cd)
                if match:
                    name = match.group(1)
                    payload = part.get_payload(decode=True)
                    if payload is None:
                        payload = part.get_payload()
                        if isinstance(payload, str):
                            payload = payload.encode("utf-8")
                    if payload is not None:
                        fields[name] = payload
    except Exception:
        pass

    # Direct boundary fallback if email parser missed fields or file payload
    if ("file" not in fields or not fields["file"]) and "boundary=" in content_type:
        try:
            boundary_str = content_type.split("boundary=")[-1].split(";")[0].strip().strip('"').strip("'")
            boundary_bytes = ("--" + boundary_str).encode("utf-8")
            parts = body.split(boundary_bytes)
            for part in parts:
                if b"Content-Disposition:" in part:
                    headers_and_body = part.split(b"\r\n\r\n", 1)
                    if len(headers_and_body) == 2:
                        header_text = headers_and_body[0].decode("utf-8", errors="replace")
                        part_body = headers_and_body[1].rstrip(b"\r\n--").rstrip(b"\r\n")
                        match = re.search(r'name=["\']?([^";\r\n\'"]+)["\']?', header_text)
                        if match:
                            name = match.group(1)
                            if name not in fields or not fields[name]:
                                fields[name] = part_body
        except Exception:
            pass

    return fields


def generate_drive_gpx(drive: dict) -> str:
    started_at = drive.get("started_at", "N/A")
    start_loc = drive.get("start_location") or "Origen"
    end_loc = drive.get("end_location") or "Destino"
    dist = drive.get("distance_km", 0)

    pts = []
    if drive.get("raw_json"):
        try:
            raw = json.loads(drive["raw_json"]) if isinstance(drive["raw_json"], str) else drive["raw_json"]
            if isinstance(raw, dict):
                if "waypoints" in raw and isinstance(raw["waypoints"], list):
                    for w in raw["waypoints"]:
                        lat = w.get("lat") or w.get("latitude")
                        lon = w.get("lon") or w.get("lng") or w.get("longitude")
                        ts = w.get("timestamp") or w.get("time") or started_at
                        if lat and lon:
                            pts.append((lat, lon, ts))
                elif "start_latitude" in raw and "end_latitude" in raw:
                    pts.append((raw["start_latitude"], raw.get("start_longitude"), started_at))
                    pts.append((raw["end_latitude"], raw.get("end_longitude"), drive.get("ended_at", started_at)))
        except Exception:
            pass

    if not pts:
        def parse_coord_str(s):
            if s and "," in str(s):
                parts = str(s).split(",")
                try:
                    return float(parts[0]), float(parts[1])
                except Exception:
                    return None
            return None

        p1 = parse_coord_str(start_loc)
        p2 = parse_coord_str(end_loc)
        if p1:
            pts.append((p1[0], p1[1], started_at))
        else:
            pts.append((40.4168, -3.7038, started_at))

        if p2:
            pts.append((p2[0], p2[1], drive.get("ended_at", started_at)))
        else:
            pts.append((40.4500, -3.6900, drive.get("ended_at", started_at)))

    trkpts_xml = ""
    for lat, lon, ts in pts:
        trkpts_xml += f'      <trkpt lat="{lat}" lon="{lon}"><time>{ts}</time></trkpt>\n'

    return f"""<?xml version="1.1" encoding="UTF-8"?>
<gpx version="1.1" creator="LaVera EV Telemetry Hub" xmlns="http://www.topografix.com/GPX/1/1">
  <metadata>
    <name>Trayecto {started_at}: {start_loc} -&gt; {end_loc}</name>
    <desc>Distancia: {dist} km | Consumo: {drive.get('energy_kwh', 0)} kWh</desc>
    <time>{started_at}</time>
  </metadata>
  <trk>
    <name>{start_loc} -&gt; {end_loc}</name>
    <trkseg>
{trkpts_xml}    </trkseg>
  </trk>
</gpx>"""


def generate_drive_kml(drive: dict) -> str:
    started_at = drive.get("started_at", "N/A")
    start_loc = drive.get("start_location") or "Origen"
    end_loc = drive.get("end_location") or "Destino"
    dist = drive.get("distance_km", 0)

    pts = []
    if drive.get("raw_json"):
        try:
            raw = json.loads(drive["raw_json"]) if isinstance(drive["raw_json"], str) else drive["raw_json"]
            if isinstance(raw, dict):
                if "waypoints" in raw and isinstance(raw["waypoints"], list):
                    for w in raw["waypoints"]:
                        lat = w.get("lat") or w.get("latitude")
                        lon = w.get("lon") or w.get("lng") or w.get("longitude")
                        if lat and lon:
                            pts.append(f"{lon},{lat},0")
                elif "start_latitude" in raw and "end_latitude" in raw:
                    pts.append(f"{raw.get('start_longitude')},{raw['start_latitude']},0")
                    pts.append(f"{raw.get('end_longitude')},{raw['end_latitude']},0")
        except Exception:
            pass

    if not pts:
        pts = ["-3.7038,40.4168,0", "-3.6900,40.4500,0"]

    coords_str = " ".join(pts)

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Trayecto {started_at}</name>
    <description>{start_loc} a {end_loc} ({dist} km, {drive.get('energy_kwh', 0)} kWh)</description>
    <Placemark>
      <name>{start_loc} → {end_loc}</name>
      <LineString>
        <tessellate>1</tessellate>
        <coordinates>{coords_str}</coordinates>
      </LineString>
    </Placemark>
  </Document>
</kml>"""


class LaVeraRequestHandler(SimpleHTTPRequestHandler):
    """HTTP Request Handler for LaVera All-in-One Server."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # API Endpoints
        if path == "/api/health":
            self._send_json({"status": "ok", "mode": "offline", "version": "1.2.0"})
            return

        if path == "/api/stats":
            vin = query.get("vin", [None])[0]
            summary = storage.get_summary(vin=vin)
            self._send_json(summary)
            return

        if path == "/api/drives":
            vin = query.get("vin", [None])[0]
            start_date = query.get("start_date", [None])[0]
            end_date = query.get("end_date", [None])[0]
            search = query.get("search", [None])[0]
            limit = int(query.get("limit", [50])[0])
            offset = int(query.get("offset", [0])[0])
            res = storage.get_drives(
                vin=vin, start_date=start_date, end_date=end_date,
                search=search, limit=limit, offset=offset, return_dict=True
            )
            self._send_json(res)
            return

        if path == "/api/drives/export":
            drive_id_str = query.get("id", [None])[0]
            fmt = (query.get("format", ["gpx"])[0]).lower()
            if not drive_id_str:
                self._send_json({"error": "Parámetro 'id' requerido"}, status=400)
                return

            drive = storage.get_drive_by_id(int(drive_id_str))
            if not drive:
                self._send_json({"error": "Trayecto no encontrado"}, status=404)
                return

            if fmt == "kml":
                content = generate_drive_kml(drive)
                mime = "application/vnd.google-earth.kml+xml"
                filename = f"lavera_drive_{drive['id']}.kml"
            else:
                content = generate_drive_gpx(drive)
                mime = "application/gpx+xml"
                filename = f"lavera_drive_{drive['id']}.gpx"

            body = content.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/charges":
            vin = query.get("vin", [None])[0]
            start_date = query.get("start_date", [None])[0]
            end_date = query.get("end_date", [None])[0]
            search = query.get("search", [None])[0]
            limit = int(query.get("limit", [50])[0])
            offset = int(query.get("offset", [0])[0])
            res = storage.get_charges(
                vin=vin, start_date=start_date, end_date=end_date,
                search=search, limit=limit, offset=offset, return_dict=True
            )
            self._send_json(res)
            return

        if path == "/api/battery":
            vin = query.get("vin", [None])[0]
            limit = int(query.get("limit", [100])[0])
            history = storage.get_battery_history(vin=vin, limit=limit)
            self._send_json(history)
            return

        if path == "/api/sync/tessie/test":
            token = query.get("token", [None])[0] or storage.get_setting("tessie_token", "")
            if not token:
                self._send_json({"status": "error", "message": "No se ha proporcionado ningún token de Tessie."}, status=400)
                return
            try:
                client = TessieAPIClient(token)
                vehicles = client.get_vehicles()
                self._send_json({"status": "success", "vehicles": vehicles})
            except Exception as e:
                self._send_json({"status": "error", "message": str(e)}, status=400)
            return

        if path == "/api/sync/config":
            saved_token = storage.get_setting("tessie_token", "")
            masked_token = (saved_token[:8] + "..." + saved_token[-4:]) if len(saved_token) > 12 else ("*" * len(saved_token))
            self._send_json({
                "has_token": bool(saved_token),
                "masked_token": masked_token if saved_token else "",
                "selected_vin": storage.get_setting("tessie_vin", ""),
                "auto_sync": storage.get_setting("tessie_auto_sync", "0") == "1",
                "last_sync": storage.get_setting("tessie_last_sync", None),
            })
            return

        if path == "/api/settings/vehicle":
            orig_cap = float(storage.get_setting("original_capacity_kwh", "75.0"))
            self._send_json({"original_capacity_kwh": orig_cap})
            return

        if path == "/api/db/info":
            summary = storage.get_summary()
            self._send_json({
                "db_path": DB_PATH,
                "drives_count": summary["drives"]["total_count"],
                "charges_count": summary["charges"]["total_count"],
                "battery_records": 1 if summary["battery"]["last_checked"] else 0,
                "live_soc": summary["live"]["soc"],
            })
            return

        if path == "/api/export":
            vin = query.get("vin", [None])[0]
            export_data = storage.export_all_json(vin=vin)
            body = json.dumps(export_data, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Disposition", 'attachment; filename="lavera_backup.json"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # Serve static web files
        if path == "/":
            self.path = "/index.html"
        else:
            self.path = path
        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/sync/tessie":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            try:
                payload = json.loads(post_data.decode("utf-8")) if post_data else {}
            except Exception:
                payload = {}

            token = payload.get("token") or storage.get_setting("tessie_token", "")
            if not token:
                self._send_json({"status": "error", "message": "Introduce tu Token de Acceso de Tessie."}, status=400)
                return

            vin = payload.get("vin") or storage.get_setting("tessie_vin", "")
            sync_drives = payload.get("sync_drives", True)
            sync_charges = payload.get("sync_charges", True)
            sync_battery = payload.get("sync_battery", True)
            save_token = payload.get("save_token", True)

            try:
                client = TessieAPIClient(token)
                vehicles = client.get_vehicles()
                if not vin and vehicles:
                    v0 = vehicles[0]
                    vin = v0.get("vin") if isinstance(v0, dict) else str(v0)

                if not vin:
                    vin = "TESLA_DEFAULT"

                if save_token:
                    storage.set_setting("tessie_token", token)
                    storage.set_setting("tessie_vin", vin)

                imported_stats = {"drives": 0, "charges": 0, "battery": 0}

                # 1. Live State
                try:
                    state = client.get_state(vin)
                    if state and isinstance(state, dict):
                        charge_st = state.get("charge_state", {})
                        drive_st = state.get("drive_state", {})
                        climate_st = state.get("climate_state", {})
                        vehicle_st = state.get("vehicle_state", {})

                        storage.insert_live_telemetry({
                            "vin": vin,
                            "timestamp": state.get("timestamp"),
                            "soc": charge_st.get("battery_level"),
                            "speed_kmh": (float(drive_st.get("speed") or 0) * 1.60934) if drive_st.get("speed") is not None else 0,
                            "power_kw": charge_st.get("charger_power") or 0,
                            "battery_temp_c": climate_st.get("inside_temp"),
                            "odometer_km": (float(vehicle_st.get("odometer") or 0) * 1.60934) if vehicle_st.get("odometer") else 0,
                            "charging_state": charge_st.get("charging_state", "STANDBY"),
                            "latitude": drive_st.get("latitude"),
                            "longitude": drive_st.get("longitude"),
                            "raw_json": json.dumps(state)
                        })
                except Exception as live_err:
                    print(f"[!] Warning fetching live state: {live_err}")

                # 2. Historical Drives
                if sync_drives:
                    try:
                        raw_drives = client.get_drives(vin)
                        if raw_drives:
                            drives_records = parse_tessie_drives(raw_drives, vin=vin)
                            imported_stats["drives"] = storage.writer.write_drives(drives_records)
                    except Exception as drv_err:
                        print(f"[!] Warning fetching drives: {drv_err}")

                # 3. Historical Charges
                if sync_charges:
                    try:
                        raw_charges = client.get_charges(vin)
                        if raw_charges:
                            charges_records = parse_tessie_charges(raw_charges, vin=vin)
                            imported_stats["charges"] = storage.writer.write_charges(charges_records)
                    except Exception as chg_err:
                        print(f"[!] Warning fetching charges: {chg_err}")

                # 4. Battery Health
                if sync_battery:
                    try:
                        raw_battery = client.get_battery_health(vin)
                        if raw_battery:
                            battery_records = parse_tessie_battery_health(raw_battery, vin=vin)
                            imported_stats["battery"] = storage.writer.write_battery_health(battery_records)
                    except Exception as bat_err:
                        print(f"[!] Warning fetching battery: {bat_err}")

                    # Fallback / Complementary Battery Calculation from state & user configured factory capacity
                    user_orig_cap = float(storage.get_setting("original_capacity_kwh", "75.0"))
                    if 'state' in locals() and state:
                        try:
                            charge_st = state.get("charge_state", {}) if isinstance(state, dict) else {}
                            vehicle_st = state.get("vehicle_state", {}) if isinstance(state, dict) else {}
                            soc = safe_float(charge_st.get("battery_level") or charge_st.get("usable_battery_level"))
                            range_ideal = safe_float(charge_st.get("battery_range") or charge_st.get("est_battery_range"))
                            odo = safe_float(vehicle_st.get("odometer")) * 1.60934

                            calc_cap = user_orig_cap * 0.96
                            calc_100_range = round(user_orig_cap * 6.0, 1)

                            if soc > 5 and range_ideal > 20:
                                calc_100_range = round((range_ideal / soc) * 100.0, 1)
                                calc_cap = round(min(user_orig_cap, calc_100_range * 0.145), 1)

                            deg_pct = round(max(0.0, ((user_orig_cap - calc_cap) / user_orig_cap) * 100.0), 1)
                            import datetime
                            now_ts = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                            gen_record = [{
                                "provider": "tessie",
                                "vin": vin,
                                "timestamp": now_ts,
                                "capacity_kwh": calc_cap,
                                "original_capacity_kwh": user_orig_cap,
                                "degradation_pct": deg_pct,
                                "max_range_km": calc_100_range,
                                "odometer_km": odo,
                            }]
                            n_written = storage.writer.write_battery_health(gen_record)
                            if imported_stats["battery"] == 0:
                                imported_stats["battery"] = n_written
                        except Exception as gen_err:
                            print(f"[!] Battery auto-calc error: {gen_err}")

                import datetime
                storage.set_setting("tessie_last_sync", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

                self._send_json({
                    "status": "success",
                    "vin": vin,
                    "imported": imported_stats,
                    "message": f"Sincronizados {imported_stats['drives']} viajes, {imported_stats['charges']} cargas y métricas de batería."
                })
            except Exception as e:
                self._send_json({"status": "error", "message": str(e)}, status=400)
            return

        if path == "/api/sync/config":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            try:
                payload = json.loads(post_data.decode("utf-8"))
                if "tessie_token" in payload:
                    storage.set_setting("tessie_token", payload["tessie_token"].strip())
                if "tessie_vin" in payload:
                    storage.set_setting("tessie_vin", payload["tessie_vin"].strip())
                if "tessie_auto_sync" in payload:
                    storage.set_setting("tessie_auto_sync", "1" if payload["tessie_auto_sync"] else "0")
                self._send_json({"status": "success"})
            except Exception as e:
                self._send_json({"error": str(e)}, status=400)
            return

        if path == "/api/settings/vehicle":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            try:
                payload = json.loads(post_data.decode("utf-8"))
                val = float(payload.get("original_capacity_kwh", 75.0))
                if val <= 0 or val > 300:
                    raise ValueError("Capacidad no válida (10 - 300 kWh).")
                storage.set_setting("original_capacity_kwh", str(val))
                self._send_json({"status": "success", "original_capacity_kwh": val})
            except Exception as e:
                self._send_json({"error": str(e)}, status=400)
            return

        if path == "/api/demo/seed":
            try:
                res = storage.seed_demo_data()
                self._send_json({"status": "success", "seeded": res})
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
            return

        if path == "/api/data/clear":
            try:
                deleted = storage.clear_all_data()
                self._send_json({"status": "success", "deleted": deleted})
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
            return

        if path == "/api/telemetry":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            try:
                payload = json.loads(post_data.decode("utf-8"))
                row_id = storage.insert_live_telemetry(payload)
                self._send_json({"status": "received", "id": row_id})
            except Exception as e:
                self._send_json({"error": str(e)}, status=400)
            return

        if path == "/api/import":
            content_type = self.headers.get("Content-Type", "")
            if not content_type.startswith("multipart/form-data"):
                self._send_json({"detail": "Invalid content-type; multipart/form-data required"}, status=400)
                return

            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                fields = parse_multipart_payload(body, content_type)

                file_bytes = fields.get("file", b"")
                content_str = decode_file_bytes(file_bytes).lstrip("\ufeff")

                vin = fields.get("vin", b"TESLA_IMPORTED")
                if isinstance(vin, bytes):
                    vin = vin.decode("utf-8", errors="replace").strip() or "TESLA_IMPORTED"

                # Auto-detect source & type
                is_json = content_str.strip().startswith("{") or content_str.strip().startswith("[")
                imported_count = 0
                detected_type = "unknown"

                if is_json:
                    source = "tessie"
                    detected_type = detect_tessie_type(content_str)
                    if detected_type == "charges":
                        recs = parse_tessie_charges(content_str, vin=vin)
                        imported_count = storage.writer.write_charges(recs)
                    elif detected_type == "battery":
                        recs = parse_tessie_battery_health(content_str, vin=vin)
                        imported_count = storage.writer.write_battery_health(recs)
                    else:
                        recs = parse_tessie_drives(content_str, vin=vin)
                        imported_count = storage.writer.write_drives(recs)
                        if imported_count > 0:
                            detected_type = "drives"
                        else:
                            recs = parse_tessie_charges(content_str, vin=vin)
                            imported_count = storage.writer.write_charges(recs)
                            if imported_count > 0:
                                detected_type = "charges"
                            else:
                                recs = parse_tessie_battery_health(content_str, vin=vin)
                                imported_count = storage.writer.write_battery_health(recs)
                                if imported_count > 0:
                                    detected_type = "battery"
                else:
                    first_line = content_str.splitlines()[0] if content_str else ""
                    delim = detect_delimiter(content_str)
                    headers = [h.strip() for h in first_line.split(delim)]
                    cleaned_headers = [clean_header_key(h) for h in headers]
                    is_teslafi = any(k in cleaned_headers for k in [
                        "startrange", "endrange", "rangeused", "chargerate", "maxchargerate",
                        "datecharging", "dateidling", "dateparked", "batteryrange",
                        "timetofullcharge", "rangelost", "batterylost", "sleeptime", "startbattery"
                    ]) or (cleaned_headers and cleaned_headers[0] == "date" and ("duration" in cleaned_headers or "efficiency" in cleaned_headers or "maxrange" in cleaned_headers))

                    if is_teslafi:
                        source = "teslafi"
                        detected_type = detect_teslafi_type(headers)
                        if detected_type == "charges":
                            recs = parse_teslafi_charges(content_str, vin=vin)
                            imported_count = storage.writer.write_charges(recs)
                        elif detected_type == "battery":
                            recs = parse_teslafi_battery_report(content_str, vin=vin)
                            imported_count = storage.writer.write_battery_health(recs)
                        elif detected_type == "idles":
                            recs = parse_teslafi_idles(content_str, vin=vin)
                            imported_count = storage.writer.write_idles(recs)
                        else:
                            recs = parse_teslafi_drives(content_str, vin=vin)
                            imported_count = storage.writer.write_drives(recs)
                            detected_type = "drives"

                        # Universal fallback if 0 imported
                        if imported_count == 0:
                            recs = parse_tessie_drives(content_str, vin=vin)
                            imported_count = storage.writer.write_drives(recs)
                            if imported_count > 0:
                                source = "tessie"
                                detected_type = "drives"
                            else:
                                recs = parse_tessie_charges(content_str, vin=vin)
                                imported_count = storage.writer.write_charges(recs)
                                if imported_count > 0:
                                    source = "tessie"
                                    detected_type = "charges"
                    else:
                        source = "tessie"
                        detected_type = detect_tessie_type(content_str)
                        if detected_type == "charges":
                            recs = parse_tessie_charges(content_str, vin=vin)
                            imported_count = storage.writer.write_charges(recs)
                        elif detected_type == "battery":
                            recs = parse_tessie_battery_health(content_str, vin=vin)
                            imported_count = storage.writer.write_battery_health(recs)
                        else:
                            recs = parse_tessie_drives(content_str, vin=vin)
                            imported_count = storage.writer.write_drives(recs)
                            if imported_count > 0:
                                detected_type = "drives"
                            else:
                                recs = parse_tessie_charges(content_str, vin=vin)
                                imported_count = storage.writer.write_charges(recs)
                                if imported_count > 0:
                                    detected_type = "charges"
                                else:
                                    recs = parse_tessie_battery_health(content_str, vin=vin)
                                    imported_count = storage.writer.write_battery_health(recs)
                                    if imported_count > 0:
                                        detected_type = "battery"

                        # Universal fallback if 0 imported
                        if imported_count == 0:
                            recs = parse_teslafi_drives(content_str, vin=vin)
                            imported_count = storage.writer.write_drives(recs)
                            if imported_count > 0:
                                source = "teslafi"
                                detected_type = "drives"
                            else:
                                recs = parse_teslafi_charges(content_str, vin=vin)
                                imported_count = storage.writer.write_charges(recs)
                                if imported_count > 0:
                                    source = "teslafi"
                                    detected_type = "charges" 

                self._send_json({
                    "status": "success",
                    "source": source,
                    "type": detected_type,
                    "records_imported": imported_count
                })
            except Exception as e:
                self._send_json({"detail": f"Failed to parse file: {str(e)}"}, status=400)
            return

        self._send_json({"detail": "Not found"}, status=404)


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def run_server(initial_port: Optional[int] = None):
    preferred_port = initial_port or PORT
    candidate_ports = [preferred_port, 8088, 8080, 8000, 8888]
    candidate_ports = list(dict.fromkeys(candidate_ports))

    httpd = None
    active_port = preferred_port
    for port in candidate_ports:
        try:
            server_address = ("0.0.0.0", port)
            httpd = ThreadedHTTPServer(server_address, LaVeraRequestHandler)
            active_port = port
            break
        except OSError as e:
            print(f"[*] Puerto {port} ocupado o no disponible ({e}). Probando siguiente...")

    if not httpd:
        print("[ERROR] No se pudo vincular el servidor a ningún puerto disponible.")
        return

    print("==================================================================")
    print(f"[*] LaVera EV Telemetry Hub iniciado correctamente!")
    print(f"[*] Panel Web:      http://localhost:{active_port}")
    print(f"[*] En red local:   http://0.0.0.0:{active_port}")
    print(f"[*] Base de Datos:  {DB_PATH}")
    print(f"[*] Directorio Web: {WEB_DIR}")
    print("==================================================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nDeteniendo servidor LaVera Hub...")
        httpd.server_close()


if __name__ == "__main__":
    run_server()
