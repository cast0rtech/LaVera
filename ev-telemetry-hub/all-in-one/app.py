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

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from importer.normalizer import parse_timestamp
from importer.teslafi_parser import (
    detect_teslafi_type,
    parse_teslafi_drives,
    parse_teslafi_charges,
    parse_teslafi_battery_report,
    parse_teslafi_idles,
)
from importer.tessie_parser import (
    detect_tessie_type,
    parse_tessie_drives,
    parse_tessie_charges,
    parse_tessie_battery_health,
)
from storage import OfflineStorage

DB_PATH = os.getenv("LAVERA_DB_PATH", os.path.join(current_dir, "data", "lavera.db"))
WEB_DIR = os.path.join(current_dir, "web")
PORT = int(os.getenv("PORT", "8080"))

storage = OfflineStorage(db_path=DB_PATH)


def parse_multipart_payload(body: bytes, content_type: str) -> dict:
    """Parses multipart/form-data using standard library email module."""
    raw = b"Content-Type: " + content_type.encode("utf-8") + b"\r\n\r\n" + body
    msg = email.message_from_bytes(raw)
    fields = {}
    for part in msg.walk():
        cd = part.get("Content-Disposition", "")
        if "form-data" in cd:
            match = re.search(r'name="([^"]+)"', cd)
            if match:
                name = match.group(1)
                payload = part.get_payload(decode=True)
                fields[name] = payload
    return fields


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
            limit = int(query.get("limit", [50])[0])
            offset = int(query.get("offset", [0])[0])
            drives = storage.get_drives(vin=vin, limit=limit, offset=offset)
            self._send_json(drives)
            return

        if path == "/api/charges":
            vin = query.get("vin", [None])[0]
            limit = int(query.get("limit", [50])[0])
            offset = int(query.get("offset", [0])[0])
            charges = storage.get_charges(vin=vin, limit=limit, offset=offset)
            self._send_json(charges)
            return

        if path == "/api/battery":
            vin = query.get("vin", [None])[0]
            limit = int(query.get("limit", [100])[0])
            history = storage.get_battery_history(vin=vin, limit=limit)
            self._send_json(history)
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
        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

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
                content_str = file_bytes.decode("utf-8", errors="replace")

                vin = fields.get("vin", b"TESLA_IMPORTED")
                if isinstance(vin, bytes):
                    vin = vin.decode("utf-8", errors="replace").strip() or "TESLA_IMPORTED"

                # Auto-detect source & type
                is_json = content_str.strip().startswith("{") or content_str.strip().startswith("[")
                source = "tessie" if is_json or "tessie" in content_str[:200].lower() else "teslafi"

                imported_count = 0
                detected_type = "unknown"

                if source == "tessie":
                    detected_type = detect_tessie_type(content_str)
                    if detected_type == "drives":
                        recs = parse_tessie_drives(content_str, vin=vin)
                        imported_count = storage.writer.write_drives(recs)
                    elif detected_type == "charges":
                        recs = parse_tessie_charges(content_str, vin=vin)
                        imported_count = storage.writer.write_charges(recs)
                    elif detected_type == "battery":
                        recs = parse_tessie_battery_health(content_str, vin=vin)
                        imported_count = storage.writer.write_battery_health(recs)
                else:
                    first_line = content_str.splitlines()[0] if content_str else ""
                    headers = first_line.split(",")
                    detected_type = detect_teslafi_type(headers)

                    if detected_type == "drives":
                        recs = parse_teslafi_drives(content_str, vin=vin)
                        imported_count = storage.writer.write_drives(recs)
                    elif detected_type == "charges":
                        recs = parse_teslafi_charges(content_str, vin=vin)
                        imported_count = storage.writer.write_charges(recs)
                    elif detected_type == "battery":
                        recs = parse_teslafi_battery_report(content_str, vin=vin)
                        imported_count = storage.writer.write_battery_health(recs)
                    elif detected_type == "idles":
                        recs = parse_teslafi_idles(content_str, vin=vin)
                        imported_count = storage.writer.write_idles(recs)

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


def run_server():
    server_address = ("0.0.0.0", PORT)
    httpd = ThreadedHTTPServer(server_address, LaVeraRequestHandler)
    print(f"? LaVera All-in-One Offline Hub running on http://0.0.0.0:{PORT}")
    print(f"?? Database: {DB_PATH}")
    print(f"?? Web UI: {WEB_DIR}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down LaVera Hub...")
        httpd.server_close()


if __name__ == "__main__":
    run_server()
