"""
CLI Tool for Importing TeslaFi & Tessie Data into LaVera Hub.
Supports SQLite (local offline), TimescaleDB (PostgreSQL 16), and InfluxDB.

Usage:
  python -m importer.cli --source teslafi --file drives.csv --vin MY_TESLA
  python -m importer.cli --source tessie --file export.json --vin MY_TESLA --timescale-host localhost
"""

import argparse
import os
import sys
from .teslafi_parser import (
    detect_teslafi_type,
    parse_teslafi_drives,
    parse_teslafi_charges,
    parse_teslafi_battery_report,
    parse_teslafi_idles,
)
from .tessie_parser import (
    detect_tessie_type,
    parse_tessie_drives,
    parse_tessie_charges,
    parse_tessie_battery_health,
)
from .writer import TelemetryWriter


def main():
    parser = argparse.ArgumentParser(description="LaVera Tesla Telemetry Importer (TeslaFi & Tessie)")
    parser.add_argument("--source", choices=["auto", "teslafi", "tessie"], default="auto",
                        help="Data source provider (default: auto)")
    parser.add_argument("--type", choices=["auto", "drives", "charges", "battery", "idles"], default="auto",
                        help="Record type (default: auto detect)")
    parser.add_argument("--file", required=True, help="Path to CSV or JSON file to import")
    parser.add_argument("--vin", default="TESLA_MODEL", help="Vehicle VIN or Identifier")
    parser.add_argument("--db", default="data/lavera.db", help="Path to local SQLite database")
    
    # TimescaleDB / PostgreSQL parameters
    parser.add_argument("--timescale-host", default=os.getenv("POSTGRES_HOST"), help="TimescaleDB / PostgreSQL Host")
    parser.add_argument("--timescale-port", type=int, default=int(os.getenv("POSTGRES_PORT", "5432")), help="TimescaleDB Port")
    parser.add_argument("--timescale-user", default=os.getenv("POSTGRES_USER", "lavera"), help="TimescaleDB User")
    parser.add_argument("--timescale-password", default=os.getenv("POSTGRES_PASSWORD", "LaVeraSecurePass2026!"), help="TimescaleDB Password")
    parser.add_argument("--timescale-db", default=os.getenv("POSTGRES_DB", "lavera_telemetry"), help="TimescaleDB Database")

    # InfluxDB legacy parameters (optional)
    parser.add_argument("--influx-url", default=os.getenv("INFLUX_URL"), help="InfluxDB URL (optional)")
    parser.add_argument("--influx-token", default=os.getenv("INFLUX_TOKEN"), help="InfluxDB API Token")
    parser.add_argument("--influx-org", default=os.getenv("INFLUX_ORG", "lavera"), help="InfluxDB Org")
    parser.add_argument("--influx-bucket", default=os.getenv("INFLUX_BUCKET", "telemetry"), help="InfluxDB Bucket")

    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"Error: File '{args.file}' not found.")
        sys.exit(1)

    with open(args.file, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    from .normalizer import clean_header_key

    source = args.source
    content_stripped = content.strip()
    is_json = content_stripped.startswith("{") or content_stripped.startswith("[")

    if source == "auto":
        if is_json or "tessie" in args.file.lower():
            source = "tessie"
        else:
            first_line = content.splitlines()[0] if content else ""
            headers = first_line.split(",")
            cleaned = [clean_header_key(h) for h in headers]
            is_teslafi = any(k in cleaned for k in [
                "startrange", "endrange", "rangeused", "chargerate", "maxchargerate",
                "datecharging", "dateidling", "dateparked", "batteryrange",
                "timetofullcharge", "rangelost", "batterylost", "sleeptime", "startbattery"
            ]) or (cleaned and cleaned[0] == "date" and ("duration" in cleaned or "efficiency" in cleaned or "maxrange" in cleaned))
            source = "teslafi" if is_teslafi else "tessie"

    rec_type = args.type
    if rec_type == "auto":
        if source == "tessie":
            rec_type = detect_tessie_type(content)
        else:
            first_line = content.splitlines()[0] if content else ""
            rec_type = detect_teslafi_type(first_line.split(","))

    print(f"[*] Importing {source.upper()} file: '{args.file}' as '{rec_type}' for VIN: {args.vin}")

    writer = TelemetryWriter(
        db_path=args.db,
        timescale_host=args.timescale_host,
        timescale_port=args.timescale_port,
        timescale_user=args.timescale_user,
        timescale_password=args.timescale_password,
        timescale_db=args.timescale_db,
        influx_url=args.influx_url,
        influx_token=args.influx_token,
        influx_org=args.influx_org,
        influx_bucket=args.influx_bucket,
    )

    count = 0
    if source == "teslafi":
        if rec_type == "drives":
            records = parse_teslafi_drives(content, vin=args.vin)
            count = writer.write_drives(records)
        elif rec_type == "charges":
            records = parse_teslafi_charges(content, vin=args.vin)
            count = writer.write_charges(records)
        elif rec_type == "battery":
            records = parse_teslafi_battery_report(content, vin=args.vin)
            count = writer.write_battery_health(records)
        elif rec_type == "idles":
            records = parse_teslafi_idles(content, vin=args.vin)
            count = writer.write_idles(records)
        else:
            print("[-] Unable to identify TeslaFi record type. Specify with --type")
            sys.exit(1)
    else:  # tessie
        if rec_type == "drives":
            records = parse_tessie_drives(content, vin=args.vin)
            count = writer.write_drives(records)
        elif rec_type == "charges":
            records = parse_tessie_charges(content, vin=args.vin)
            count = writer.write_charges(records)
        elif rec_type == "battery":
            records = parse_tessie_battery_health(content, vin=args.vin)
            count = writer.write_battery_health(records)
        else:
            print("[-] Unable to identify Tessie record type. Specify with --type")
            sys.exit(1)

    print(f"[+] Successfully processed and imported {count} records into '{args.db}'.")


if __name__ == "__main__":
    main()
