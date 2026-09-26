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
from gateway import (
    HybridTelemetryGateway,
    TeslaSecurityManager,
    TeslaFleetProvider,
    TessieProvider,
    CircuitBreaker,
    CanonicalVehicleState,
)

DB_PATH = os.getenv("LAVERA_DB_PATH", os.path.join(current_dir, "data", "lavera.db"))
WEB_DIR = os.path.join(current_dir, "web")
PORT = int(os.getenv("PORT", "8088"))

storage = OfflineStorage(db_path=DB_PATH)


def init_gateway(storage_instance) -> HybridTelemetryGateway:
    """Initializes the Hybrid Telemetry Gateway with persistent configuration."""
    primary = storage_instance.get_setting("telemetry_primary_provider", "tessie")
    fallback = storage_instance.get_setting("telemetry_fallback_enabled", "1") == "1"

    tessie_token = storage_instance.get_setting("tessie_token", "")
    tesla_client_id = storage_instance.get_setting("tesla_client_id", "")
    tesla_client_secret = storage_instance.get_setting("tesla_client_secret", "")
    tesla_refresh_token = storage_instance.get_setting("tesla_refresh_token", "")
    tesla_region = storage_instance.get_setting("tesla_region", "eu")
    tesla_priv_pem = storage_instance.get_setting("tesla_private_key_pem", None)

    gw = HybridTelemetryGateway(primary_provider_name=primary, fallback_enabled=fallback)

    # Register Tessie Provider
    tessie_prov = TessieProvider(token=tessie_token)
    gw.register_provider(tessie_prov)

    # Register Tesla Fleet Provider
    tesla_sec = TeslaSecurityManager(
        client_id=tesla_client_id,
        client_secret=tesla_client_secret,
        refresh_token=tesla_refresh_token,
        region=tesla_region,
        private_key_pem=tesla_priv_pem
    )
    fleet_prov = TeslaFleetProvider(security_manager=tesla_sec)
    gw.register_provider(fleet_prov)

    try:
        gw.set_primary_provider(primary)
    except Exception:
        pass

    return gw

gateway = init_gateway(storage)


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


def xml_escape(s) -> str:
    """Safely escapes text for inclusion in XML/KML/GPX documents."""
    if s is None:
        return ""
    text = str(s)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _parse_coord(lat_val, lon_val):
    """Safely validates and normalizes latitude and longitude."""
    try:
        lat = float(lat_val)
        lon = float(lon_val)
        if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0 and (lat != 0.0 or lon != 0.0):
            return lat, lon
    except (TypeError, ValueError):
        pass
    return None


def _parse_coord_string(s):
    """Tries to extract (lat, lon) from a coordinate string (e.g. '40.4168, -3.7038')."""
    if not s:
        return None
    st = str(s).strip()
    for sep in [",", ";", "/"]:
        if sep in st:
            parts = st.split(sep)
            if len(parts) >= 2:
                c = _parse_coord(parts[0].strip(), parts[1].strip())
                if c:
                    return c
    return None


def extract_drive_trackpoints(drive: dict, storage=None):
    """
    Extracts all real GPS points and start/destination waypoints for a drive.
    Returns: (trackpoints, start_waypoint, end_waypoint)
    Each trackpoint dict contains: lat, lon, time, speed (m/s), ele (m).
    """
    pts = []
    vin = drive.get("vin")
    started_at = drive.get("started_at")
    ended_at = drive.get("ended_at") or started_at

    # 1. High fidelity: query recorded GPS points from live_telemetry table
    if storage and vin and started_at and hasattr(storage, "get_drive_trackpoints"):
        raw_tp = storage.get_drive_trackpoints(vin, started_at, ended_at)
        for p in raw_tp:
            c = _parse_coord(p.get("latitude"), p.get("longitude"))
            if c:
                speed_kmh = p.get("speed_kmh")
                speed_mps = round(float(speed_kmh) / 3.6, 2) if speed_kmh is not None and float(speed_kmh) >= 0 else None
                pts.append({
                    "lat": c[0],
                    "lon": c[1],
                    "time": p.get("timestamp") or started_at,
                    "speed": speed_mps,
                    "ele": None
                })

    raw_dict = {}
    raw_data = drive.get("raw_json")
    if isinstance(raw_data, str) and raw_data.strip():
        try:
            raw_dict = json.loads(raw_data)
        except Exception:
            raw_dict = {}
    elif isinstance(raw_data, dict):
        raw_dict = raw_data

    # 2. Check waypoints or path from raw_json
    if not pts and raw_dict:
        for key in ["waypoints", "path", "route", "locations", "coordinates", "coords", "points"]:
            items = raw_dict.get(key)
            if isinstance(items, list) and len(items) > 0:
                for w in items:
                    if isinstance(w, dict):
                        lat = w.get("lat") or w.get("latitude") or w.get("latitud")
                        lon = w.get("lon") or w.get("lng") or w.get("longitude") or w.get("longitud")
                        c = _parse_coord(lat, lon)
                        if c:
                            ts = w.get("timestamp") or w.get("time") or started_at
                            speed = w.get("speed") or w.get("speed_kmh")
                            speed_mps = round(float(speed) / 3.6, 2) if speed is not None else None
                            ele = w.get("ele") or w.get("elevation") or w.get("altitude") or w.get("alt")
                            pts.append({
                                "lat": c[0],
                                "lon": c[1],
                                "time": ts,
                                "speed": speed_mps,
                                "ele": float(ele) if ele is not None else None
                            })
                    elif isinstance(w, (list, tuple)) and len(w) >= 2:
                        try:
                            v1, v2 = float(w[0]), float(w[1])
                            if abs(v1) > 90 and abs(v2) <= 90:
                                lat, lon = v2, v1
                            else:
                                lat, lon = v1, v2
                            c = _parse_coord(lat, lon)
                            if c:
                                ele = float(w[2]) if len(w) >= 3 else None
                                pts.append({"lat": c[0], "lon": c[1], "time": started_at, "speed": None, "ele": ele})
                        except Exception:
                            pass
                if pts:
                    break

    # 3. Resolve start and end coordinates
    start_c = (
        _parse_coord(drive.get("start_latitude"), drive.get("start_longitude")) or
        _parse_coord(raw_dict.get("starting_latitude"), raw_dict.get("starting_longitude")) or
        _parse_coord(raw_dict.get("start_latitude"), raw_dict.get("start_longitude")) or
        _parse_coord(raw_dict.get("start_lat"), raw_dict.get("start_lon") or raw_dict.get("start_lng")) or
        _parse_coord_string(drive.get("start_location"))
    )

    end_c = (
        _parse_coord(drive.get("end_latitude"), drive.get("end_longitude")) or
        _parse_coord(raw_dict.get("ending_latitude"), raw_dict.get("ending_longitude")) or
        _parse_coord(raw_dict.get("end_latitude"), raw_dict.get("end_longitude")) or
        _parse_coord(raw_dict.get("end_lat"), raw_dict.get("end_lon") or raw_dict.get("end_lng")) or
        _parse_coord_string(drive.get("end_location"))
    )

    start_loc_name = str(drive.get("start_location") or "Origen").strip()
    end_loc_name = str(drive.get("end_location") or "Destino").strip()

    start_wpt = None
    if start_c:
        start_wpt = {"lat": start_c[0], "lon": start_c[1], "name": start_loc_name, "time": started_at}
    elif pts:
        start_wpt = {"lat": pts[0]["lat"], "lon": pts[0]["lon"], "name": start_loc_name, "time": pts[0]["time"]}

    end_wpt = None
    if end_c:
        end_wpt = {"lat": end_c[0], "lon": end_c[1], "name": end_loc_name, "time": ended_at}
    elif pts:
        end_wpt = {"lat": pts[-1]["lat"], "lon": pts[-1]["lon"], "name": end_loc_name, "time": pts[-1]["time"]}

    # If no high-frequency points exist but start and end coordinates are known, construct segment
    if not pts:
        if start_c and end_c:
            pts.append({"lat": start_c[0], "lon": start_c[1], "time": started_at, "speed": None, "ele": None})
            pts.append({"lat": end_c[0], "lon": end_c[1], "time": ended_at, "speed": None, "ele": None})
        elif start_c:
            pts.append({"lat": start_c[0], "lon": start_c[1], "time": started_at, "speed": None, "ele": None})
        elif end_c:
            pts.append({"lat": end_c[0], "lon": end_c[1], "time": ended_at, "speed": None, "ele": None})

    return pts, start_wpt, end_wpt


def generate_drive_gpx(drive: dict, storage=None) -> str:
    """
    Generates a valid, standards-compliant GPX 1.1 file (XML 1.0) for a drive session.
    Compatible with Strava, Garmin, Google Earth, OsmAnd, Komoot, and all standard GPS parsers.
    """
    started_at = drive.get("started_at", "")
    ended_at = drive.get("ended_at", started_at)
    start_loc = drive.get("start_location") or "Origen"
    end_loc = drive.get("end_location") or "Destino"
    dist = drive.get("distance_km", 0.0)
    energy = drive.get("energy_kwh", 0.0)
    efficiency = drive.get("efficiency_wh_km", 0.0)

    pts, start_wpt, end_wpt = extract_drive_trackpoints(drive, storage=storage)

    def format_iso_time(ts_str):
        if not ts_str:
            return ""
        s = str(ts_str).strip().replace(" ", "T")
        if not s.endswith("Z") and "+" not in s:
            s += "Z"
        return s

    started_iso = format_iso_time(started_at)

    wpts_xml = ""
    if start_wpt:
        wpts_xml += f'  <wpt lat="{start_wpt["lat"]:.6f}" lon="{start_wpt["lon"]:.6f}">\n'
        wpts_xml += f'    <name>{xml_escape(start_wpt["name"])}</name>\n'
        wpts_xml += f'    <desc>Punto de inicio ({xml_escape(started_at)})</desc>\n'
        wpts_xml += f'    <time>{format_iso_time(start_wpt.get("time"))}</time>\n'
        wpts_xml += '  </wpt>\n'
    if end_wpt and (not start_wpt or (end_wpt["lat"] != start_wpt["lat"] or end_wpt["lon"] != start_wpt["lon"])):
        wpts_xml += f'  <wpt lat="{end_wpt["lat"]:.6f}" lon="{end_wpt["lon"]:.6f}">\n'
        wpts_xml += f'    <name>{xml_escape(end_wpt["name"])}</name>\n'
        wpts_xml += f'    <desc>Punto de destino ({xml_escape(ended_at)})</desc>\n'
        wpts_xml += f'    <time>{format_iso_time(end_wpt.get("time"))}</time>\n'
        wpts_xml += '  </wpt>\n'

    trkpts_xml = ""
    for p in pts:
        p_time = format_iso_time(p.get("time") or started_at)
        p_extra = ""
        if p.get("ele") is not None:
            p_extra += f'<ele>{p["ele"]:.1f}</ele>'
        if p.get("speed") is not None:
            p_extra += f'<speed>{p["speed"]:.2f}</speed>'
        trkpts_xml += f'      <trkpt lat="{p["lat"]:.6f}" lon="{p["lon"]:.6f}"><time>{p_time}</time>{p_extra}</trkpt>\n'

    if pts:
        trk_content = f"""  <trk>
    <name>{xml_escape(start_loc)} -&gt; {xml_escape(end_loc)}</name>
    <desc>Distancia: {dist} km | Consumo: {energy} kWh | Eficiencia: {efficiency} Wh/km</desc>
    <trkseg>
{trkpts_xml}    </trkseg>
  </trk>"""
    else:
        trk_content = f"""  <trk>
    <name>{xml_escape(start_loc)} -&gt; {xml_escape(end_loc)}</name>
    <desc>Trayecto registrado sin coordenadas GPS disponibles</desc>
  </trk>"""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="LaVera EV Telemetry Hub"
  xmlns="http://www.topografix.com/GPX/1/1"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd">
  <metadata>
    <name>Trayecto {xml_escape(started_at)}: {xml_escape(start_loc)} -&gt; {xml_escape(end_loc)}</name>
    <desc>Distancia: {dist} km | Consumo: {energy} kWh | Eficiencia: {efficiency} Wh/km</desc>
    <time>{started_iso}</time>
  </metadata>
{wpts_xml}{trk_content}
</gpx>"""


def generate_drive_kml(drive: dict, storage=None) -> str:
    """
    Generates a valid KML 2.2 file for a drive session, compatible with Google Earth and GIS tools.
    """
    started_at = drive.get("started_at", "")
    ended_at = drive.get("ended_at", started_at)
    start_loc = drive.get("start_location") or "Origen"
    end_loc = drive.get("end_location") or "Destino"
    dist = drive.get("distance_km", 0.0)
    energy = drive.get("energy_kwh", 0.0)
    efficiency = drive.get("efficiency_wh_km", 0.0)

    pts, start_wpt, end_wpt = extract_drive_trackpoints(drive, storage=storage)

    coords_list = []
    for p in pts:
        ele = p.get("ele") if p.get("ele") is not None else 0
        coords_list.append(f"{p['lon']:.6f},{p['lat']:.6f},{ele}")
    coords_str = " ".join(coords_list)

    placemarks_xml = ""

    if start_wpt:
        placemarks_xml += f"""    <Placemark>
      <name>{xml_escape(start_wpt['name'])} (Origen)</name>
      <description>Inicio del trayecto: {xml_escape(started_at)}</description>
      <styleUrl>#startPin</styleUrl>
      <Point>
        <coordinates>{start_wpt['lon']:.6f},{start_wpt['lat']:.6f},0</coordinates>
      </Point>
    </Placemark>\n"""

    if end_wpt and (not start_wpt or (end_wpt["lat"] != start_wpt["lat"] or end_wpt["lon"] != start_wpt["lon"])):
        placemarks_xml += f"""    <Placemark>
      <name>{xml_escape(end_wpt['name'])} (Destino)</name>
      <description>Destino del trayecto: {xml_escape(ended_at)}</description>
      <styleUrl>#endPin</styleUrl>
      <Point>
        <coordinates>{end_wpt['lon']:.6f},{end_wpt['lat']:.6f},0</coordinates>
      </Point>
    </Placemark>\n"""

    if coords_str:
        placemarks_xml += f"""    <Placemark>
      <name>{xml_escape(start_loc)} -&gt; {xml_escape(end_loc)}</name>
      <description>Distancia: {dist} km | Consumo: {energy} kWh | Eficiencia: {efficiency} Wh/km</description>
      <styleUrl>#routeLine</styleUrl>
      <LineString>
        <extrude>1</extrude>
        <tessellate>1</tessellate>
        <altitudeMode>clampToGround</altitudeMode>
        <coordinates>{coords_str}</coordinates>
      </LineString>
    </Placemark>\n"""
    else:
        placemarks_xml += f"""    <Placemark>
      <name>{xml_escape(start_loc)} -&gt; {xml_escape(end_loc)}</name>
      <description>Trayecto registrado sin coordenadas GPS disponibles ({dist} km, {energy} kWh)</description>
    </Placemark>\n"""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Trayecto {xml_escape(started_at)}: {xml_escape(start_loc)} -&gt; {xml_escape(end_loc)}</name>
    <description>Distancia: {dist} km | Consumo: {energy} kWh | Eficiencia: {efficiency} Wh/km</description>
    <Style id="routeLine">
      <LineStyle>
        <color>ffd97400</color>
        <width>4</width>
      </LineStyle>
    </Style>
    <Style id="startPin">
      <IconStyle>
        <color>ff00ff00</color>
        <scale>1.1</scale>
        <Icon>
          <href>http://maps.google.com/mapfiles/kml/paddle/grn-circle.png</href>
        </Icon>
      </IconStyle>
    </Style>
    <Style id="endPin">
      <IconStyle>
        <color>ff0000ff</color>
        <scale>1.1</scale>
        <Icon>
          <href>http://maps.google.com/mapfiles/kml/paddle/red-circle.png</href>
        </Icon>
      </IconStyle>
    </Style>
{placemarks_xml}  </Document>
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
                content = generate_drive_kml(drive, storage=storage)
                mime = "application/vnd.google-earth.kml+xml"
                filename = f"lavera_drive_{drive['id']}.kml"
            else:
                content = generate_drive_gpx(drive, storage=storage)
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

        # Serve Tesla Fleet 3rd Party Public Key for domain verification (.well-known)
        if path == "/.well-known/appspecific/com.tesla.3p.public-key.pem":
            pub_pem = storage.get_setting("tesla_public_key_pem", "")
            if not pub_pem:
                self.send_response(404)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"Tesla Fleet public key not yet generated. Use /api/gateway/tesla/generate-keys")
                return
            body = pub_pem.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
            return

        # Vampire Drain & Polling Lifecycle Status
        if path == "/api/gateway/vampire-status":
            summary = gateway.vampire_protector.get_status_summary() if hasattr(gateway, "vampire_protector") else {}
            self._send_json({
                "status": "success",
                "vehicles": summary
            })
            return

        # Gateway live status & metrics
        if path == "/api/gateway/status":
            gw_status = gateway.get_gateway_status()
            gw_status["has_tesla_credentials"] = bool(storage.get_setting("tesla_client_id") and storage.get_setting("tesla_refresh_token"))
            gw_status["has_tessie_token"] = bool(storage.get_setting("tessie_token"))
            gw_status["has_keypair"] = bool(storage.get_setting("tesla_private_key_pem"))
            gw_status["public_key_pem"] = storage.get_setting("tesla_public_key_pem", "")
            gw_status["tesla_region"] = storage.get_setting("tesla_region", "eu")
            self._send_json(gw_status)
            return

        # Gateway configuration details
        if path == "/api/gateway/config":
            saved_tesla_id = storage.get_setting("tesla_client_id", "")
            saved_tessie = storage.get_setting("tessie_token", "")
            masked_tesla_id = (saved_tesla_id[:6] + "..." + saved_tesla_id[-4:]) if len(saved_tesla_id) > 10 else ("*" * len(saved_tesla_id))
            masked_tessie = (saved_tessie[:6] + "..." + saved_tessie[-4:]) if len(saved_tessie) > 10 else ("*" * len(saved_tessie))
            self._send_json({
                "primary_provider": storage.get_setting("telemetry_primary_provider", "tessie"),
                "fallback_enabled": storage.get_setting("telemetry_fallback_enabled", "1") == "1",
                "tesla_client_id": masked_tesla_id,
                "has_tesla_secret": bool(storage.get_setting("tesla_client_secret")),
                "has_tesla_refresh_token": bool(storage.get_setting("tesla_refresh_token")),
                "tesla_region": storage.get_setting("tesla_region", "eu"),
                "tessie_token": masked_tessie,
                "has_keypair": bool(storage.get_setting("tesla_private_key_pem")),
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

        # Configure Gateway Providers & Failover
        if path == "/api/gateway/config":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            try:
                payload = json.loads(post_data.decode("utf-8")) if post_data else {}
            except Exception:
                payload = {}

            if "primary_provider" in payload:
                storage.set_setting("telemetry_primary_provider", str(payload["primary_provider"]).lower())
            if "fallback_enabled" in payload:
                storage.set_setting("telemetry_fallback_enabled", "1" if payload["fallback_enabled"] else "0")
            if "tesla_client_id" in payload and payload["tesla_client_id"]:
                storage.set_setting("tesla_client_id", str(payload["tesla_client_id"]).strip())
            if "tesla_client_secret" in payload and payload["tesla_client_secret"]:
                storage.set_setting("tesla_client_secret", str(payload["tesla_client_secret"]).strip())
            if "tesla_refresh_token" in payload and payload["tesla_refresh_token"]:
                storage.set_setting("tesla_refresh_token", str(payload["tesla_refresh_token"]).strip())
            if "tesla_region" in payload:
                storage.set_setting("tesla_region", str(payload["tesla_region"]).strip().lower())
            if "tessie_token" in payload and payload["tessie_token"]:
                storage.set_setting("tessie_token", str(payload["tessie_token"]).strip())

            # Re-initialize gateway with newly updated credentials
            global gateway
            gateway = init_gateway(storage)

            self._send_json({
                "status": "success",
                "message": "Configuración de pasarela de telemetría actualizada.",
                "gateway": gateway.get_gateway_status()
            })
            return

        # Generate or retrieve Tesla Fleet ECDSA NIST P-256 Keypair
        if path == "/api/gateway/tesla/generate-keys":
            existing_pub = storage.get_setting("tesla_public_key_pem")
            existing_priv = storage.get_setting("tesla_private_key_pem")
            if existing_pub and existing_priv:
                self._send_json({
                    "status": "success",
                    "created": False,
                    "public_key_pem": existing_pub,
                    "message": "Clave pública existente recuperada."
                })
                return

            try:
                priv_pem, pub_pem = TeslaSecurityManager.generate_fleet_keypair()
                storage.set_setting("tesla_private_key_pem", priv_pem)
                storage.set_setting("tesla_public_key_pem", pub_pem)

                # Update running gateway security manager
                gateway = init_gateway(storage)

                self._send_json({
                    "status": "success",
                    "created": True,
                    "public_key_pem": pub_pem,
                    "message": "Nuevo par de claves ECDSA NIST P-256 generado con éxito."
                })
            except Exception as e:
                self._send_json({"status": "error", "message": f"Error generando claves: {str(e)}"}, status=500)
            return

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

                # 1. Live State via Hybrid Gateway (Primary with automatic Failover)
                active_source = "tessie"
                fallback_engaged = False
                try:
                    # Attempt state acquisition through Hybrid Telemetry Gateway
                    state_obj, executing_prov = gateway.get_vehicle_state(vin)
                    active_source = executing_prov
                    fallback_engaged = (executing_prov != gateway.primary_name)

                    storage.insert_live_telemetry({
                        "vin": vin,
                        "timestamp": state_obj.timestamp,
                        "soc": state_obj.soc,
                        "speed_kmh": state_obj.speed_kmh,
                        "power_kw": state_obj.power_kw,
                        "battery_temp_c": state_obj.battery_temp_c,
                        "odometer_km": state_obj.odometer_km,
                        "charging_state": state_obj.charging_state,
                        "latitude": state_obj.latitude,
                        "longitude": state_obj.longitude,
                        "raw_json": json.dumps(state_obj.raw_payload) if isinstance(state_obj.raw_payload, dict) else "{}"
                    })
                except Exception as gw_err:
                    print(f"[!] Gateway state fetch fallback attempt to direct client: {gw_err}")
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
                        print(f"[!] Warning fetching direct live state: {live_err}")

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
