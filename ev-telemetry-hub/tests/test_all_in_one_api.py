import io
import json
import os
import sys
import unittest
import urllib.request
import urllib.parse
import threading
import time

base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
aio_dir = os.path.join(base_dir, "all-in-one")
sys.path.insert(0, base_dir)
sys.path.insert(0, aio_dir)

from storage import OfflineStorage
import app as app_module

class TestAllInOneAPI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.test_db = os.path.join(base_dir, "tests", "test_lavera_api.db")
        if os.path.exists(cls.test_db):
            try:
                os.remove(cls.test_db)
            except Exception:
                pass
        
        app_module.storage = OfflineStorage(db_path=cls.test_db)
        
        cls.port = 18099
        cls.server = app_module.ThreadedHTTPServer(("127.0.0.1", cls.port), app_module.LaVeraRequestHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        time.sleep(0.2)
        if os.path.exists(cls.test_db):
            try:
                os.remove(cls.test_db)
            except Exception:
                pass

    def test_01_health(self):
        url = f"http://127.0.0.1:{self.port}/api/health"
        with urllib.request.urlopen(url, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data["status"], "ok")

    def test_02_import_teslafi_csv(self):
        csv_content = """Date,Duration,Distance,Start Range,End Range,Range Used,Energy Used,Efficiency,Start Battery,End Battery,Start Temp,End Temp,Start Location,End Location
2026-06-15 10:00:00,1200,20.0,260,230,30,5.2,260,85,75,70,68,Casa,Trabajo
"""
        boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="drives.csv"\r\n'
            f"Content-Type: text/csv\r\n\r\n"
            f"{csv_content}\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="vin"\r\n\r\n'
            f"TESLA_TEST_1\r\n"
            f"--{boundary}--\r\n"
        ).encode("utf-8")

        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/import",
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(body))
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data["status"], "success")
            self.assertEqual(data["source"], "teslafi")
            self.assertEqual(data["type"], "drives")
            self.assertEqual(data["records_imported"], 1)

    def test_03_stats(self):
        url = f"http://127.0.0.1:{self.port}/api/stats"
        with urllib.request.urlopen(url, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertIn("drives", data)
            self.assertEqual(data["drives"]["total_count"], 1)
            self.assertGreater(data["drives"]["total_distance_km"], 30.0)

    def test_04_export(self):
        url = f"http://127.0.0.1:{self.port}/api/export"
        with urllib.request.urlopen(url, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertIn("summary", data)
            self.assertIn("drives", data)
            self.assertEqual(len(data["drives"]), 1)

if __name__ == "__main__":
    unittest.main()
