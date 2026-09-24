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

    def test_05_import_tessie_csv(self):
        csv_content = """Started,Ended,Duration,Distance,Starting Battery,Ending Battery,Energy Used,Efficiency,Starting Temperature,Ending Temperature,Start Location,End Location
2026-06-16 09:00:00,2026-06-16 09:30:00,1800,15,4,80,72,2,8,160,22,23,Madrid,Toledo
"""
        boundary = "----WebKitFormBoundaryTessieCSVTest"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="tessie_drives.csv"\r\n'
            f"Content-Type: text/csv\r\n\r\n"
            f"{csv_content}\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="vin"\r\n\r\n'
            f"TESLA_TESSIE_CSV\r\n"
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
            self.assertEqual(data["source"], "tessie")
            self.assertEqual(data["type"], "drives")
            self.assertEqual(data["records_imported"], 1)

    def test_06_import_tessie_json(self):
        json_content = json.dumps({
            "results": [
                {
                    "started_at": "2026-06-17T14:00:00.000Z",
                    "ended_at": "2026-06-17T14:45:00.000Z",
                    "duration": 2700,
                    "distance": 35.5,
                    "starting_battery": 90,
                    "ending_battery": 78,
                    "energy_used": 6.8,
                    "efficiency": 185
                }
            ]
        }, indent=2)

        boundary = "----WebKitFormBoundaryTessieJSONTest"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="tessie_export.json"\r\n'
            f"Content-Type: application/json\r\n\r\n"
            f"{json_content}\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="vin"\r\n\r\n'
            f"TESLA_TESSIE_JSON\r\n"
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
            self.assertEqual(data["source"], "tessie")
            self.assertEqual(data["type"], "drives")
            self.assertEqual(data["records_imported"], 1)


    def test_07_demo_seed_and_clear(self):
        # 1. Seed demo
        req_seed = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/demo/seed",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req_seed, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data["status"], "success")
            self.assertEqual(data["seeded"]["drives"], 5)

        # 2. Check stats has data
        url_stats = f"http://127.0.0.1:{self.port}/api/stats"
        with urllib.request.urlopen(url_stats, timeout=3) as resp:
            stats = json.loads(resp.read().decode())
            self.assertEqual(stats["drives"]["total_count"], 5)
            self.assertEqual(stats["charges"]["total_count"], 4)

        # 3. Clear data
        req_clear = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/data/clear",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req_clear, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data["status"], "success")

        # 4. Check stats is 0 again
        with urllib.request.urlopen(url_stats, timeout=3) as resp:
            stats = json.loads(resp.read().decode())
            self.assertEqual(stats["drives"]["total_count"], 0)

    def test_08_sync_config(self):
        body = json.dumps({"tessie_token": "test_token_12345", "tessie_auto_sync": True}).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/sync/config",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            self.assertEqual(resp.status, 200)

        url_get = f"http://127.0.0.1:{self.port}/api/sync/config"
        with urllib.request.urlopen(url_get, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertTrue(data["has_token"])
            self.assertTrue(data["auto_sync"])

    def test_09_db_info(self):
        url = f"http://127.0.0.1:{self.port}/api/db/info"
        with urllib.request.urlopen(url, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertIn("db_path", data)
            self.assertIn("drives_count", data)

    def test_10_import_spanish_semicolon_csv(self):
        csv_content = "\ufeffHora de inicio;Hora de fin;Distancia;Batería inicial;Batería final;Energía usada;Eficiencia;Ubicación inicial;Ubicación final\r\n15/06/2026 10:30;15/06/2026 11:15;42,5 km;80 %;68 %;6,8 kWh;160 Wh/km;Madrid Norte;Guadalajara\r\n"
        boundary = "----WebKitFormBoundarySpanishCSVTest"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="viajes_tessie.csv"\r\n'
            f"Content-Type: text/csv; charset=utf-8\r\n\r\n"
            f"{csv_content}\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="vin"\r\n\r\n'
            f"TESLA_SPAIN_TEST\r\n"
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
            self.assertEqual(data["source"], "tessie")
            self.assertEqual(data["type"], "drives")
            self.assertEqual(data["records_imported"], 1)


if __name__ == "__main__":
    unittest.main()
