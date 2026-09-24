"""
TeslaFi Data Parser for LaVera EV Telemetry Hub.
Parses TeslaFi CSV exports (drives, charges, idle/sleep, battery degradation reports).
"""

import csv
import io
from typing import Any, Dict, List, Optional, Tuple
from .normalizer import (
    clean_header_key,
    detect_delimiter,
    miles_to_km,
    f_to_c,
    wh_per_mi_to_wh_per_km,
    safe_float,
    safe_int,
    parse_timestamp,
)


def detect_teslafi_type(headers: List[str]) -> str:
    """Detects whether a TeslaFi CSV is drives, charges, idles, or battery report."""
    cleaned = [clean_header_key(h) for h in headers]
    joined = " ".join(cleaned)

    if any(k in joined for k in ["energyadded", "chargeenergy", "chargerate", "supercharger"]):
        return "charges"
    if any(k in joined for k in ["degradation", "maxrange", "range100", "calculatedkwh"]):
        return "battery"
    if any(k in joined for k in ["sleeptime", "idletime", "rangelost", "batterylost"]):
        return "idles"
    if any(k in joined for k in ["startlocation", "endlocation", "efficiency", "rangeused", "distance"]):
        return "drives"
    return "unknown"


def parse_teslafi_drives(csv_text_or_io: Any, vin: str = "TESLA_DEFAULT") -> List[Dict[str, Any]]:
    """
    Parses TeslaFi drives CSV export into normalized records.
    """
    text = csv_text_or_io if isinstance(csv_text_or_io, str) else str(csv_text_or_io)
    text = text.lstrip("\ufeff")
    delim = detect_delimiter(text)
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)

    records = []
    headers = reader.fieldnames or []
    
    # Check if distance is explicitly marked as kilometers
    is_km_distance = any("km" in h.lower() for h in headers if "dist" in h.lower())
    is_celsius_temp = any("c" in h.lower() for h in headers if "temp" in h.lower())
    is_wh_per_km = any("wh/km" in h.lower() for h in headers if "effic" in h.lower())

    for row in reader:
        # Create map of cleaned header -> raw value
        row_map = {clean_header_key(k): v for k, v in row.items() if k}

        # Date / Timestamps
        start_date = row_map.get("date") or row_map.get("startdate") or row_map.get("start")
        start_ts = parse_timestamp(start_date)
        if not start_ts:
            continue

        end_date = row_map.get("enddate") or row_map.get("end")
        end_ts = parse_timestamp(end_date) or start_ts

        duration_s = safe_int(row_map.get("duration") or row_map.get("durationseconds"))
        if duration_s == 0 and "durationminutes" in row_map:
            duration_s = int(safe_float(row_map.get("durationminutes")) * 60)

        # Distance & Efficiency
        raw_dist = safe_float(row_map.get("distance") or row_map.get("distancemi") or row_map.get("distancekm"))
        distance_km = raw_dist if is_km_distance else miles_to_km(raw_dist)

        raw_effic = safe_float(row_map.get("efficiency") or row_map.get("whmi") or row_map.get("whkm"))
        efficiency_wh_km = raw_effic if is_wh_per_km else wh_per_mi_to_wh_per_km(raw_effic)

        energy_kwh = safe_float(row_map.get("energyused") or row_map.get("kwhused") or row_map.get("kwh"))
        if energy_kwh == 0 and distance_km > 0 and efficiency_wh_km > 0:
            energy_kwh = round((distance_km * efficiency_wh_km) / 1000.0, 2)

        # Battery SoC
        start_soc = safe_float(row_map.get("startbattery") or row_map.get("startsoc") or row_map.get("startlevel"))
        end_soc = safe_float(row_map.get("endbattery") or row_map.get("endsoc") or row_map.get("endlevel"))

        # Temperatures
        raw_start_temp = safe_float(row_map.get("starttemp") or row_map.get("insidetemp"))
        raw_end_temp = safe_float(row_map.get("endtemp") or row_map.get("outsidetemp"))
        start_temp_c = raw_start_temp if is_celsius_temp else f_to_c(raw_start_temp)
        end_temp_c = raw_end_temp if is_celsius_temp else f_to_c(raw_end_temp)

        # Odometers
        raw_start_odo = safe_float(row_map.get("startodometer") or row_map.get("odometer"))
        raw_end_odo = safe_float(row_map.get("endodometer"))
        start_odo_km = raw_start_odo if is_km_distance else miles_to_km(raw_start_odo)
        end_odo_km = raw_end_odo if is_km_distance else miles_to_km(raw_end_odo)

        record = {
            "provider": "teslafi",
            "vin": vin,
            "started_at": start_ts,
            "ended_at": end_ts,
            "duration_s": duration_s,
            "distance_km": distance_km,
            "energy_kwh": energy_kwh,
            "efficiency_wh_km": efficiency_wh_km,
            "start_soc": start_soc,
            "end_soc": end_soc,
            "start_temp_c": start_temp_c,
            "end_temp_c": end_temp_c,
            "start_location": row_map.get("startlocation", ""),
            "end_location": row_map.get("endlocation", ""),
            "start_odometer_km": start_odo_km,
            "end_odometer_km": end_odo_km,
            "max_speed_kmh": round(safe_float(row_map.get("maxspeed")) * (1.0 if is_km_distance else 1.60934), 1),
        }
        records.append(record)

    return records


def parse_teslafi_charges(csv_text_or_io: Any, vin: str = "TESLA_DEFAULT") -> List[Dict[str, Any]]:
    """
    Parses TeslaFi charging sessions CSV export.
    """
    text = csv_text_or_io if isinstance(csv_text_or_io, str) else str(csv_text_or_io)
    text = text.lstrip("\ufeff")
    delim = detect_delimiter(text)
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)

    records = []
    headers = reader.fieldnames or []
    is_km = any("km" in h.lower() for h in headers)

    for row in reader:
        row_map = {clean_header_key(k): v for k, v in row.items() if k}

        start_date = row_map.get("date") or row_map.get("startdate")
        start_ts = parse_timestamp(start_date)
        if not start_ts:
            continue

        end_date = row_map.get("enddate")
        end_ts = parse_timestamp(end_date) or start_ts

        duration_s = safe_int(row_map.get("duration") or row_map.get("durationseconds"))
        if duration_s == 0 and "durationminutes" in row_map:
            duration_s = int(safe_float(row_map.get("durationminutes")) * 60)

        energy_added = safe_float(row_map.get("energyadded") or row_map.get("kwhadded") or row_map.get("energy"))
        raw_range_added = safe_float(row_map.get("rangeadded"))
        range_added_km = raw_range_added if is_km else miles_to_km(raw_range_added)

        start_soc = safe_float(row_map.get("startbattery") or row_map.get("startsoc"))
        end_soc = safe_float(row_map.get("endbattery") or row_map.get("endsoc"))
        peak_kw = safe_float(row_map.get("maxchargerate") or row_map.get("chargerate") or row_map.get("kw"))
        cost = safe_float(row_map.get("cost") or row_map.get("totalcost"))
        location = row_map.get("location") or row_map.get("superchargername") or ""
        is_supercharger = 1 if ("supercharger" in location.lower() or safe_int(row_map.get("supercharger")) == 1 or peak_kw > 40) else 0

        record = {
            "provider": "teslafi",
            "vin": vin,
            "started_at": start_ts,
            "ended_at": end_ts,
            "duration_s": duration_s,
            "energy_added_kwh": energy_added,
            "start_soc": start_soc,
            "end_soc": end_soc,
            "range_added_km": range_added_km,
            "peak_kw": peak_kw,
            "cost": cost,
            "location": location,
            "is_fast_charge": is_supercharger,
        }
        records.append(record)

    return records


def parse_teslafi_battery_report(csv_text_or_io: Any, vin: str = "TESLA_DEFAULT") -> List[Dict[str, Any]]:
    """
    Parses TeslaFi battery degradation / calendar report CSV.
    """
    text = csv_text_or_io if isinstance(csv_text_or_io, str) else str(csv_text_or_io)
    text = text.lstrip("\ufeff")
    delim = detect_delimiter(text)
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)

    records = []
    headers = reader.fieldnames or []
    is_km = any("km" in h.lower() for h in headers)

    for row in reader:
        row_map = {clean_header_key(k): v for k, v in row.items() if k}
        ts = parse_timestamp(row_map.get("date"))
        if not ts:
            continue

        raw_range = safe_float(row_map.get("range100") or row_map.get("maxrange") or row_map.get("ratedrange"))
        max_range_km = raw_range if is_km else miles_to_km(raw_range)
        capacity_kwh = safe_float(row_map.get("calculatedkwh") or row_map.get("capacitykwh") or row_map.get("usablekwh"))
        degradation_pct = safe_float(row_map.get("degradation") or row_map.get("degradationpct"))
        raw_odo = safe_float(row_map.get("odometer"))
        odo_km = raw_odo if is_km else miles_to_km(raw_odo)

        record = {
            "provider": "teslafi",
            "vin": vin,
            "timestamp": ts,
            "capacity_kwh": capacity_kwh,
            "original_capacity_kwh": round(capacity_kwh / (1 - (degradation_pct / 100.0)), 2) if (degradation_pct > 0 and degradation_pct < 50 and capacity_kwh > 0) else capacity_kwh,
            "degradation_pct": degradation_pct,
            "max_range_km": max_range_km,
            "odometer_km": odo_km,
        }
        records.append(record)

    return records


def parse_teslafi_idles(csv_text_or_io: Any, vin: str = "TESLA_DEFAULT") -> List[Dict[str, Any]]:
    """
    Parses TeslaFi idle/sleep CSV export for vampire drain analysis.
    """
    text = csv_text_or_io if isinstance(csv_text_or_io, str) else str(csv_text_or_io)
    text = text.lstrip("\ufeff")
    delim = detect_delimiter(text)
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)

    records = []
    headers = reader.fieldnames or []
    is_km = any("km" in h.lower() for h in headers)

    for row in reader:
        row_map = {clean_header_key(k): v for k, v in row.items() if k}
        start_ts = parse_timestamp(row_map.get("date") or row_map.get("startdate"))
        if not start_ts:
            continue

        end_ts = parse_timestamp(row_map.get("enddate")) or start_ts
        duration_s = safe_int(row_map.get("duration") or row_map.get("durationseconds"))
        if duration_s == 0 and "durationminutes" in row_map:
            duration_s = int(safe_float(row_map.get("durationminutes")) * 60)

        soc_loss = safe_float(row_map.get("batterylost") or row_map.get("soclost"))
        raw_range_lost = safe_float(row_map.get("rangelost"))
        range_loss_km = raw_range_lost if is_km else miles_to_km(raw_range_lost)

        record = {
            "provider": "teslafi",
            "vin": vin,
            "started_at": start_ts,
            "ended_at": end_ts,
            "duration_s": duration_s,
            "soc_loss_pct": soc_loss,
            "range_loss_km": range_loss_km,
        }
        records.append(record)

    return records
