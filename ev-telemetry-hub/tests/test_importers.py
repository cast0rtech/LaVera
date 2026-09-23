"""
Unit Tests for TeslaFi and Tessie Importers.
"""

import os
import sys
import unittest

# Ensure ev-telemetry-hub directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from importer.normalizer import miles_to_km, f_to_c, wh_per_mi_to_wh_per_km
from importer.teslafi_parser import (
    parse_teslafi_drives,
    parse_teslafi_charges,
    parse_teslafi_battery_report,
)
from importer.tessie_parser import (
    parse_tessie_drives,
    parse_tessie_charges,
    parse_tessie_battery_health,
)
from importer.writer import TelemetryWriter


class TestTeslaImporters(unittest.TestCase):

    def test_normalizer_math(self):
        self.assertAlmostEqual(miles_to_km(10.0), 16.09, places=2)
        self.assertAlmostEqual(f_to_c(68.0), 20.0, places=1)
        self.assertAlmostEqual(wh_per_mi_to_wh_per_km(250.0), 155.3, places=1)

    def test_teslafi_drives_parsing(self):
        sample_csv = """Date,Duration,Distance,Start Range,End Range,Range Used,Energy Used,Efficiency,Start Battery,End Battery,Start Temp,End Temp,Start Location,End Location
2026-05-10 14:30:00,1800,25.0,280,245,35,6.5,260,80,70,72,70,Home,Office
"""
        records = parse_teslafi_drives(sample_csv, vin="TEST_VIN_1")
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["vin"], "TEST_VIN_1")
        self.assertEqual(rec["started_at"], "2026-05-10T14:30:00Z")
        self.assertAlmostEqual(rec["distance_km"], 40.23, places=1)
        self.assertEqual(rec["start_soc"], 80.0)
        self.assertEqual(rec["end_soc"], 70.0)
        self.assertAlmostEqual(rec["start_temp_c"], 22.2, places=1)

    def test_teslafi_charges_parsing(self):
        sample_csv = """Date,Duration,Energy Added,Range Added,Start Battery,End Battery,Max Charge Rate,Cost,Location
2026-05-11 22:00:00,7200,32.4,120,40,85,11.0,4.50,Home Charger
"""
        records = parse_teslafi_charges(sample_csv, vin="TEST_VIN_2")
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["energy_added_kwh"], 32.4)
        self.assertEqual(rec["start_soc"], 40.0)
        self.assertEqual(rec["end_soc"], 85.0)
        self.assertEqual(rec["cost"], 4.50)
        self.assertEqual(rec["is_fast_charge"], 0)

    def test_tessie_json_parsing(self):
        sample_json = {
            "drives": [
                {
                    "started_at": "2026-06-01T08:00:00Z",
                    "ended_at": "2026-06-01T08:45:00Z",
                    "distance": 35.5,
                    "distance_unit": "km",
                    "energy_used": 5.2,
                    "starting_battery": 90,
                    "ending_battery": 82,
                    "efficiency": 146.5
                }
            ]
        }
        records = parse_tessie_drives(sample_json, vin="TEST_VIN_3")
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["distance_km"], 35.5)
        self.assertEqual(rec["energy_kwh"], 5.2)
        self.assertEqual(rec["start_soc"], 90.0)
        self.assertEqual(rec["end_soc"], 82.0)

    def test_writer_sqlite(self):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_db = tmp.name
        try:
            writer = TelemetryWriter(db_path=tmp_db)
            drives = [{
                "vin": "V1", "started_at": "2026-01-01T00:00:00Z", "ended_at": "2026-01-01T01:00:00Z",
                "duration_s": 3600, "distance_km": 50.0, "energy_kwh": 8.0, "efficiency_wh_km": 160.0,
                "start_soc": 90.0, "end_soc": 75.0, "provider": "test"
            }]
            count = writer.write_drives(drives)
            self.assertEqual(count, 1)
        finally:
            if os.path.exists(tmp_db):
                os.remove(tmp_db)


if __name__ == "__main__":
    unittest.main()
