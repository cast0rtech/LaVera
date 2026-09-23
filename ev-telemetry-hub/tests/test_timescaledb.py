import os
import unittest
import yaml

from importer.writer import TelemetryWriter


class TestTimescaleDBIntegration(unittest.TestCase):
    """Validates TimescaleDB schema, Grafana provisioning, and writer integration."""

    def test_sql_schema_file(self):
        sql_path = os.path.join(os.path.dirname(__file__), "..", "sql", "init-timescaledb.sql")
        self.assertTrue(os.path.exists(sql_path), "init-timescaledb.sql must exist")
        with open(sql_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("CREATE EXTENSION IF NOT EXISTS timescaledb", content)
        self.assertIn("CREATE TABLE IF NOT EXISTS telemetry", content)
        self.assertIn("create_hypertable('telemetry', 'time'", content)
        self.assertIn("CREATE TABLE IF NOT EXISTS drives", content)
        self.assertIn("CREATE TABLE IF NOT EXISTS charges", content)
        self.assertIn("CREATE TABLE IF NOT EXISTS battery_health", content)

    def test_grafana_datasource_provisioning(self):
        ds_path = os.path.join(os.path.dirname(__file__), "..", "grafana", "provisioning", "datasources", "datasource.yml")
        self.assertTrue(os.path.exists(ds_path), "datasource.yml must exist")
        with open(ds_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        self.assertEqual(data.get("apiVersion"), 1)
        datasources = data.get("datasources", [])
        self.assertGreaterEqual(len(datasources), 1)
        ds = datasources[0]
        self.assertEqual(ds.get("type"), "postgres")
        self.assertEqual(ds.get("url"), "timescaledb:5432")
        self.assertEqual(ds.get("user"), "lavera")
        self.assertTrue(ds.get("jsonData", {}).get("timescaledb"))
        self.assertEqual(ds.get("jsonData", {}).get("database"), "lavera_telemetry")

    def test_writer_with_timescale_params(self):
        tmp_db = os.path.join(os.path.dirname(__file__), "test_timescale_writer.db")
        if os.path.exists(tmp_db):
            os.remove(tmp_db)
        try:
            writer = TelemetryWriter(
                db_path=tmp_db,
                timescale_host="dummy_host",
                timescale_port=5432,
                timescale_user="lavera",
                timescale_password="secret",
                timescale_db="lavera_telemetry"
            )
            self.assertIsNotNone(writer)
            inserted = writer.write_drives([{"vin": "TEST_VIN", "started_at": "2026-09-24T00:00:00Z"}])
            self.assertEqual(inserted, 1)
        finally:
            if os.path.exists(tmp_db):
                os.remove(tmp_db)


if __name__ == "__main__":
    unittest.main()
