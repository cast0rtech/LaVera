"""
Tessie Data Parser for LaVera EV Telemetry Hub.
Parses Tessie CSV and JSON exports (drives, charges, battery health analytics, idles).
Supports all Tessie export variations, API responses, and multi-lingual formats.
"""

import csv
import io
import json
from typing import Any, Dict, List, Optional, Tuple, Union
from .normalizer import (
    clean_header_key,
    miles_to_km,
    f_to_c,
    wh_per_mi_to_wh_per_km,
    safe_float,
    safe_int,
    parse_timestamp,
)


def detect_tessie_type(data: Union[str, Dict, List]) -> str:
    """Detects whether Tessie export is drives, charges, battery, or idle data."""
    if isinstance(data, str):
        s = data.strip()
        # If it's a JSON string, parse it to examine structured content
        if s.startswith("{") or s.startswith("["):
            try:
                parsed = json.loads(s)
                return detect_tessie_type(parsed)
            except Exception:
                pass

        # Inspect first 10 lines of CSV
        first_lines = "\n".join(s.splitlines()[:10])
        cleaned = clean_header_key(first_lines)
        if any(k in cleaned for k in ["energyadded", "chargeenergy", "fastcharger", "supercharger", "peakpower", "charges"]):
            return "charges"
        if any(k in cleaned for k in ["degradation", "capacitykwh", "batteryhealth", "usablecapacity", "degradationpercent"]):
            return "battery"
        if any(k in cleaned for k in ["idletime", "vampire", "drain", "idleduration", "socloss"]):
            return "idles"
        if any(k in cleaned for k in ["distance", "energyused", "startingbattery", "startsoc", "odometerstart", "drives", "distancia"]):
            return "drives"
        return "unknown"

    if isinstance(data, (dict, list)):
        if isinstance(data, dict):
            if "drives" in data:
                return "drives"
            if "charges" in data:
                return "charges"
            if "battery" in data or "battery_health" in data:
                return "battery"
            if "idles" in data:
                return "idles"
            # Support {"results": [...]} or {"data": [...]}
            for key in ["results", "data", "items"]:
                if key in data and isinstance(data[key], list) and len(data[key]) > 0:
                    return detect_tessie_type(data[key])
            sample = data
        elif isinstance(data, list):
            sample = data[0] if len(data) > 0 else {}
        else:
            sample = {}

        if any(k in sample for k in ["energy_added", "charge_energy_added", "fast_charger", "max_charge_power", "peak_kw", "peak_power"]):
            return "charges"
        if any(k in sample for k in ["capacity_kwh", "degradation_percent", "battery_health", "original_capacity", "degradation"]):
            return "battery"
        if any(k in sample for k in ["idle_time", "vampire_loss", "soc_loss", "range_loss"]):
            return "idles"
        if any(k in sample for k in ["distance", "energy_used", "starting_battery", "start_soc", "odometer_start", "duration", "speed_max"]):
            return "drives"
        return "unknown"

    return "unknown"


def _extract_list_from_json(data: Any, key_name: str) -> List[Dict[str, Any]]:
    """Helper to extract list of records from various JSON wrapper formats."""
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        if key_name in data and isinstance(data[key_name], list):
            return [item for item in data[key_name] if isinstance(item, dict)]
        for k in ["results", "data", "items", "records"]:
            if k in data and isinstance(data[k], list):
                return [item for item in data[k] if isinstance(item, dict)]
        # If single object
        if "started_at" in data or "date" in data or "timestamp" in data:
            return [data]
    return []


def parse_tessie_drives(data_or_text: Any, vin: str = "TESLA_DEFAULT") -> List[Dict[str, Any]]:
    """
    Parses Tessie drives from either JSON or CSV format.
    """
    records = []

    # If string, check if it's JSON first
    if isinstance(data_or_text, str):
        stripped = data_or_text.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                parsed_json = json.loads(stripped)
                return parse_tessie_drives(parsed_json, vin)
            except Exception:
                pass

    # JSON path
    if isinstance(data_or_text, (dict, list)):
        raw_list = _extract_list_from_json(data_or_text, "drives")
        for item in raw_list:
            start_ts = parse_timestamp(
                item.get("started_at") or item.get("start_time") or item.get("start") or item.get("date")
            )
            if not start_ts:
                continue
            end_ts = parse_timestamp(
                item.get("ended_at") or item.get("end_time") or item.get("end")
            ) or start_ts

            dist = safe_float(item.get("distance"))
            unit = str(item.get("distance_unit") or item.get("unit") or "").lower()
            dist_km = dist if "km" in unit else miles_to_km(dist)

            dur_s = safe_int(item.get("duration") or item.get("duration_seconds") or item.get("duration_s"))
            energy_kwh = safe_float(item.get("energy_used") or item.get("energy_kwh") or item.get("energy"))
            raw_eff = safe_float(item.get("efficiency") or item.get("wh_per_km") or item.get("wh_per_mile"))
            eff_wh_km = raw_eff if "km" in unit else wh_per_mi_to_wh_per_km(raw_eff)
            if energy_kwh == 0 and dist_km > 0 and eff_wh_km > 0:
                energy_kwh = round((dist_km * eff_wh_km) / 1000.0, 2)

            start_soc = safe_float(item.get("starting_battery") or item.get("start_soc") or item.get("start_battery_level"))
            end_soc = safe_float(item.get("ending_battery") or item.get("end_soc") or item.get("end_battery_level"))

            start_odo = safe_float(item.get("odometer_start") or item.get("starting_odometer") or item.get("start_odometer"))
            end_odo = safe_float(item.get("odometer_end") or item.get("ending_odometer") or item.get("end_odometer"))
            start_odo_km = start_odo if "km" in unit else miles_to_km(start_odo)
            end_odo_km = end_odo if "km" in unit else miles_to_km(end_odo)

            records.append({
                "provider": "tessie",
                "vin": vin,
                "started_at": start_ts,
                "ended_at": end_ts,
                "duration_s": dur_s,
                "distance_km": dist_km,
                "energy_kwh": energy_kwh,
                "efficiency_wh_km": eff_wh_km,
                "start_soc": start_soc,
                "end_soc": end_soc,
                "start_temp_c": safe_float(item.get("starting_temperature") or item.get("start_temp")),
                "end_temp_c": safe_float(item.get("ending_temperature") or item.get("end_temp")),
                "start_location": str(item.get("start_location") or item.get("start_address") or ""),
                "end_location": str(item.get("end_location") or item.get("end_address") or ""),
                "start_odometer_km": start_odo_km,
                "end_odometer_km": end_odo_km,
                "max_speed_kmh": round(safe_float(item.get("speed_max") or item.get("max_speed")) * (1.0 if "km" in unit else 1.60934), 1),
            })
        return records

    # CSV path
    if isinstance(data_or_text, str):
        reader = csv.DictReader(io.StringIO(data_or_text))
    else:
        reader = csv.DictReader(data_or_text)

    headers = reader.fieldnames or []
    is_km = any("km" in h.lower() for h in headers)

    for row in reader:
        row_map = {clean_header_key(k): v for k, v in row.items() if k}
        start_ts = parse_timestamp(
            row_map.get("startedat") or row_map.get("started") or row_map.get("date") or
            row_map.get("startdate") or row_map.get("starttime") or row_map.get("start")
        )
        if not start_ts:
            continue
        end_ts = parse_timestamp(
            row_map.get("endedat") or row_map.get("ended") or row_map.get("enddate") or
            row_map.get("endtime") or row_map.get("end")
        ) or start_ts

        raw_dist = safe_float(
            row_map.get("distance") or row_map.get("distancekm") or row_map.get("distancemi") or
            row_map.get("distancia") or row_map.get("miles") or row_map.get("km")
        )
        dist_km = raw_dist if is_km else miles_to_km(raw_dist)

        dur_s = safe_int(
            row_map.get("duration") or row_map.get("durationseconds") or row_map.get("durations") or
            row_map.get("time") or row_map.get("duracion")
        )
        raw_eff = safe_float(row_map.get("efficiency") or row_map.get("whkm") or row_map.get("whmi") or row_map.get("eficiencia"))
        eff_wh_km = raw_eff if is_km else wh_per_mi_to_wh_per_km(raw_eff)
        energy_kwh = safe_float(row_map.get("energyused") or row_map.get("energykwh") or row_map.get("energy") or row_map.get("energia"))
        if energy_kwh == 0 and dist_km > 0 and eff_wh_km > 0:
            energy_kwh = round((dist_km * eff_wh_km) / 1000.0, 2)

        start_soc = safe_float(
            row_map.get("startingbattery") or row_map.get("startsoc") or row_map.get("startbattery") or
            row_map.get("startbatterylevel") or row_map.get("baterianicial")
        )
        end_soc = safe_float(
            row_map.get("endingbattery") or row_map.get("endsoc") or row_map.get("endbattery") or
            row_map.get("endbatterylevel") or row_map.get("bateriafinal")
        )

        raw_start_odo = safe_float(row_map.get("odometerstart") or row_map.get("startingodometer") or row_map.get("startodometer"))
        raw_end_odo = safe_float(row_map.get("odometerend") or row_map.get("endingodometer") or row_map.get("endodometer"))
        start_odo_km = raw_start_odo if is_km else miles_to_km(raw_start_odo)
        end_odo_km = raw_end_odo if is_km else miles_to_km(raw_end_odo)

        records.append({
            "provider": "tessie",
            "vin": vin,
            "started_at": start_ts,
            "ended_at": end_ts,
            "duration_s": dur_s,
            "distance_km": dist_km,
            "energy_kwh": energy_kwh,
            "efficiency_wh_km": eff_wh_km,
            "start_soc": start_soc,
            "end_soc": end_soc,
            "start_temp_c": safe_float(row_map.get("startingtemperature") or row_map.get("starttemp")),
            "end_temp_c": safe_float(row_map.get("endingtemperature") or row_map.get("endtemp")),
            "start_location": row_map.get("startlocation") or row_map.get("startaddress") or row_map.get("start") or "",
            "end_location": row_map.get("endlocation") or row_map.get("endaddress") or row_map.get("end") or "",
            "start_odometer_km": start_odo_km,
            "end_odometer_km": end_odo_km,
            "max_speed_kmh": round(safe_float(row_map.get("maxspeed") or row_map.get("speedmax")) * (1.0 if is_km else 1.60934), 1),
        })

    return records


def parse_tessie_charges(data_or_text: Any, vin: str = "TESLA_DEFAULT") -> List[Dict[str, Any]]:
    """
    Parses Tessie charge sessions from either JSON or CSV format.
    """
    records = []

    # If string, check if it's JSON first
    if isinstance(data_or_text, str):
        stripped = data_or_text.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                parsed_json = json.loads(stripped)
                return parse_tessie_charges(parsed_json, vin)
            except Exception:
                pass

    # JSON path
    if isinstance(data_or_text, (dict, list)):
        raw_list = _extract_list_from_json(data_or_text, "charges")
        for item in raw_list:
            start_ts = parse_timestamp(
                item.get("started_at") or item.get("start_time") or item.get("start") or item.get("date")
            )
            if not start_ts:
                continue
            end_ts = parse_timestamp(
                item.get("ended_at") or item.get("end_time") or item.get("end")
            ) or start_ts

            energy = safe_float(item.get("energy_added") or item.get("charge_energy_added") or item.get("kwh_added") or item.get("energy"))
            unit = str(item.get("distance_unit") or item.get("unit") or "").lower()
            raw_range = safe_float(item.get("range_added"))
            range_added_km = raw_range if "km" in unit else miles_to_km(raw_range)
            peak_kw = safe_float(item.get("peak_kw") or item.get("max_charge_power") or item.get("peak_power") or item.get("max_power"))

            records.append({
                "provider": "tessie",
                "vin": vin,
                "started_at": start_ts,
                "ended_at": end_ts,
                "duration_s": safe_int(item.get("duration") or item.get("duration_seconds") or item.get("duration_s")),
                "energy_added_kwh": energy,
                "start_soc": safe_float(item.get("starting_battery") or item.get("start_soc") or item.get("start_battery_level")),
                "end_soc": safe_float(item.get("ending_battery") or item.get("end_soc") or item.get("end_battery_level")),
                "range_added_km": range_added_km,
                "peak_kw": peak_kw,
                "cost": safe_float(item.get("cost") or item.get("total_cost")),
                "location": str(item.get("location") or item.get("address") or item.get("charger_name") or ""),
                "is_fast_charge": 1 if (item.get("fast_charger") or item.get("supercharger") or peak_kw > 40) else 0,
            })
        return records

    # CSV path
    if isinstance(data_or_text, str):
        reader = csv.DictReader(io.StringIO(data_or_text))
    else:
        reader = csv.DictReader(data_or_text)

    headers = reader.fieldnames or []
    is_km = any("km" in h.lower() for h in headers)

    for row in reader:
        row_map = {clean_header_key(k): v for k, v in row.items() if k}
        start_ts = parse_timestamp(
            row_map.get("startedat") or row_map.get("started") or row_map.get("date") or
            row_map.get("startdate") or row_map.get("starttime") or row_map.get("start")
        )
        if not start_ts:
            continue
        end_ts = parse_timestamp(
            row_map.get("endedat") or row_map.get("ended") or row_map.get("enddate") or
            row_map.get("endtime") or row_map.get("end")
        ) or start_ts

        energy = safe_float(
            row_map.get("energyadded") or row_map.get("chargeenergyadded") or row_map.get("energykwh") or
            row_map.get("energy") or row_map.get("kwhadded") or row_map.get("energiaagregada")
        )
        raw_range = safe_float(row_map.get("rangeadded") or row_map.get("autonomiaagregada"))
        range_added_km = raw_range if is_km else miles_to_km(raw_range)
        peak_kw = safe_float(
            row_map.get("peakkw") or row_map.get("maxchargepower") or row_map.get("peakpower") or
            row_map.get("maxpower") or row_map.get("potenciamaxima")
        )

        records.append({
            "provider": "tessie",
            "vin": vin,
            "started_at": start_ts,
            "ended_at": end_ts,
            "duration_s": safe_int(row_map.get("duration") or row_map.get("durationseconds") or row_map.get("duracion")),
            "energy_added_kwh": energy,
            "start_soc": safe_float(
                row_map.get("startingbattery") or row_map.get("startsoc") or row_map.get("startbattery") or
                row_map.get("startbatterylevel") or row_map.get("baterianicial")
            ),
            "end_soc": safe_float(
                row_map.get("endingbattery") or row_map.get("endsoc") or row_map.get("endbattery") or
                row_map.get("endbatterylevel") or row_map.get("bateriafinal")
            ),
            "range_added_km": range_added_km,
            "peak_kw": peak_kw,
            "cost": safe_float(row_map.get("cost") or row_map.get("totalcost") or row_map.get("coste")),
            "location": row_map.get("location") or row_map.get("address") or row_map.get("ubicacion") or "",
            "is_fast_charge": 1 if (row_map.get("fastcharger") in ("1", "true", "True", True) or
                                   row_map.get("supercharger") in ("1", "true", "True", True) or
                                   peak_kw > 40) else 0,
        })

    return records


def parse_tessie_battery_health(data_or_text: Any, vin: str = "TESLA_DEFAULT") -> List[Dict[str, Any]]:
    """
    Parses Tessie battery health / degradation analytics (CSV or JSON).
    """
    records = []

    # If string, check if it's JSON first
    if isinstance(data_or_text, str):
        stripped = data_or_text.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                parsed_json = json.loads(stripped)
                return parse_tessie_battery_health(parsed_json, vin)
            except Exception:
                pass

    if isinstance(data_or_text, (dict, list)):
        raw_list = _extract_list_from_json(data_or_text, "battery_health")
        if not raw_list and isinstance(data_or_text, dict):
            raw_list = _extract_list_from_json(data_or_text, "battery")
        for item in raw_list:
            ts = parse_timestamp(item.get("date") or item.get("timestamp") or item.get("reported_at"))
            if not ts:
                continue
            cap = safe_float(item.get("capacity_kwh") or item.get("capacity") or item.get("usable_capacity"))
            orig_cap = safe_float(item.get("original_capacity_kwh") or item.get("original_capacity"))
            deg = safe_float(item.get("degradation_percent") or item.get("degradation") or item.get("degradation_pct"))
            if orig_cap == 0 and cap > 0 and deg > 0 and deg < 50:
                orig_cap = round(cap / (1 - (deg / 100.0)), 2)

            records.append({
                "provider": "tessie",
                "vin": vin,
                "timestamp": ts,
                "capacity_kwh": cap,
                "original_capacity_kwh": orig_cap if orig_cap > 0 else cap,
                "degradation_pct": deg,
                "max_range_km": safe_float(item.get("estimated_range_km") or item.get("max_range") or item.get("range")),
                "odometer_km": safe_float(item.get("odometer_km") or item.get("odometer")),
            })
        return records

    # CSV path
    if isinstance(data_or_text, str):
        reader = csv.DictReader(io.StringIO(data_or_text))
    else:
        reader = csv.DictReader(data_or_text)

    for row in reader:
        row_map = {clean_header_key(k): v for k, v in row.items() if k}
        ts = parse_timestamp(row_map.get("date") or row_map.get("timestamp") or row_map.get("fecha"))
        if not ts:
            continue
        cap = safe_float(row_map.get("capacitykwh") or row_map.get("capacity") or row_map.get("capacidad"))
        deg = safe_float(row_map.get("degradationpercent") or row_map.get("degradation") or row_map.get("degradacion"))
        orig_cap = safe_float(row_map.get("originalcapacitykwh") or row_map.get("originalcapacity"))
        if orig_cap == 0 and cap > 0 and deg > 0 and deg < 50:
            orig_cap = round(cap / (1 - (deg / 100.0)), 2)

        records.append({
            "provider": "tessie",
            "vin": vin,
            "timestamp": ts,
            "capacity_kwh": cap,
            "original_capacity_kwh": orig_cap if orig_cap > 0 else cap,
            "degradation_pct": deg,
            "max_range_km": safe_float(row_map.get("estimatedrangekm") or row_map.get("maxrange")),
            "odometer_km": safe_float(row_map.get("odometerkm") or row_map.get("odometer")),
        })

    return records
