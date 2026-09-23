"""
Tessie Data Parser for LaVera EV Telemetry Hub.
Parses Tessie CSV and JSON exports (drives, charges, battery health analytics).
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
    """Detects whether Tessie export is drives, charges, or battery data."""
    if isinstance(data, (dict, list)):
        sample = data[0] if isinstance(data, list) and len(data) > 0 else (data if isinstance(data, dict) else {})
        if "drives" in data:
            return "drives"
        if "charges" in data:
            return "charges"
        if any(k in sample for k in ["energy_added", "charge_energy_added", "fast_charger"]):
            return "charges"
        if any(k in sample for k in ["capacity_kwh", "degradation_percent", "battery_health"]):
            return "battery"
        if any(k in sample for k in ["distance", "energy_used", "starting_battery"]):
            return "drives"
        return "unknown"

    # CSV string
    first_line = data.splitlines()[0] if isinstance(data, str) and data else ""
    cleaned = clean_header_key(first_line)
    if any(k in cleaned for k in ["energyadded", "chargeenergy", "fastcharger"]):
        return "charges"
    if any(k in cleaned for k in ["degradation", "capacitykwh", "batteryhealth"]):
        return "battery"
    if any(k in cleaned for k in ["distance", "energyused", "startingbattery", "odometerstart"]):
        return "drives"
    return "unknown"


def parse_tessie_drives(data_or_text: Any, vin: str = "TESLA_DEFAULT") -> List[Dict[str, Any]]:
    """
    Parses Tessie drives from either JSON or CSV format.
    """
    records = []

    # If JSON
    if isinstance(data_or_text, (dict, list)):
        raw_list = data_or_text.get("drives", []) if isinstance(data_or_text, dict) else data_or_text
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            start_ts = parse_timestamp(item.get("started_at") or item.get("start_time") or item.get("start"))
            if not start_ts:
                continue
            end_ts = parse_timestamp(item.get("ended_at") or item.get("end_time") or item.get("end")) or start_ts

            dist = safe_float(item.get("distance"))
            # Tessie distance is typically in miles if not specified, or kilometers if unit="km"
            unit = str(item.get("distance_unit", "")).lower()
            dist_km = dist if unit == "km" else miles_to_km(dist)

            dur_s = safe_int(item.get("duration") or item.get("duration_seconds"))
            energy_kwh = safe_float(item.get("energy_used") or item.get("energy_kwh"))
            raw_eff = safe_float(item.get("efficiency") or item.get("wh_per_km") or item.get("wh_per_mile"))
            eff_wh_km = raw_eff if "km" in unit else wh_per_mi_to_wh_per_km(raw_eff)
            if energy_kwh == 0 and dist_km > 0 and eff_wh_km > 0:
                energy_kwh = round((dist_km * eff_wh_km) / 1000.0, 2)

            start_soc = safe_float(item.get("starting_battery") or item.get("start_soc"))
            end_soc = safe_float(item.get("ending_battery") or item.get("end_soc"))

            start_odo = safe_float(item.get("odometer_start") or item.get("starting_odometer"))
            end_odo = safe_float(item.get("odometer_end") or item.get("ending_odometer"))
            start_odo_km = start_odo if unit == "km" else miles_to_km(start_odo)
            end_odo_km = end_odo if unit == "km" else miles_to_km(end_odo)

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
                "start_temp_c": safe_float(item.get("starting_temperature")),
                "end_temp_c": safe_float(item.get("ending_temperature")),
                "start_location": str(item.get("start_location") or item.get("start_address") or ""),
                "end_location": str(item.get("end_location") or item.get("end_address") or ""),
                "start_odometer_km": start_odo_km,
                "end_odometer_km": end_odo_km,
                "max_speed_kmh": round(safe_float(item.get("speed_max") or item.get("max_speed")) * (1.0 if unit == "km" else 1.60934), 1),
            })
        return records

    # CSV path
    if isinstance(data_or_text, str):
        # Try JSON parse first in case a JSON string was passed
        try:
            parsed_json = json.loads(data_or_text)
            return parse_tessie_drives(parsed_json, vin)
        except Exception:
            pass
        reader = csv.DictReader(io.StringIO(data_or_text))
    else:
        reader = csv.DictReader(data_or_text)

    headers = reader.fieldnames or []
    is_km = any("km" in h.lower() for h in headers)

    for row in reader:
        row_map = {clean_header_key(k): v for k, v in row.items() if k}
        start_ts = parse_timestamp(row_map.get("startedat") or row_map.get("date") or row_map.get("starttime"))
        if not start_ts:
            continue
        end_ts = parse_timestamp(row_map.get("endedat") or row_map.get("endtime")) or start_ts

        raw_dist = safe_float(row_map.get("distance") or row_map.get("distancekm") or row_map.get("distancemi"))
        dist_km = raw_dist if is_km else miles_to_km(raw_dist)

        dur_s = safe_int(row_map.get("duration") or row_map.get("durationseconds"))
        raw_eff = safe_float(row_map.get("efficiency") or row_map.get("whkm") or row_map.get("whmi"))
        eff_wh_km = raw_eff if is_km else wh_per_mi_to_wh_per_km(raw_eff)
        energy_kwh = safe_float(row_map.get("energyused") or row_map.get("energykwh") or row_map.get("energy"))
        if energy_kwh == 0 and dist_km > 0 and eff_wh_km > 0:
            energy_kwh = round((dist_km * eff_wh_km) / 1000.0, 2)

        start_soc = safe_float(row_map.get("startingbattery") or row_map.get("startsoc"))
        end_soc = safe_float(row_map.get("endingbattery") or row_map.get("endsoc"))

        raw_start_odo = safe_float(row_map.get("odometerstart") or row_map.get("startingodometer"))
        raw_end_odo = safe_float(row_map.get("odometerend") or row_map.get("endingodometer"))
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
            "start_location": row_map.get("startlocation") or row_map.get("startaddress") or "",
            "end_location": row_map.get("endlocation") or row_map.get("endaddress") or "",
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

    # If JSON
    if isinstance(data_or_text, (dict, list)):
        raw_list = data_or_text.get("charges", []) if isinstance(data_or_text, dict) else data_or_text
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            start_ts = parse_timestamp(item.get("started_at") or item.get("start_time"))
            if not start_ts:
                continue
            end_ts = parse_timestamp(item.get("ended_at") or item.get("end_time")) or start_ts

            energy = safe_float(item.get("energy_added") or item.get("charge_energy_added"))
            unit = str(item.get("distance_unit", "")).lower()
            raw_range = safe_float(item.get("range_added"))
            range_added_km = raw_range if unit == "km" else miles_to_km(raw_range)

            records.append({
                "provider": "tessie",
                "vin": vin,
                "started_at": start_ts,
                "ended_at": end_ts,
                "duration_s": safe_int(item.get("duration") or item.get("duration_seconds")),
                "energy_added_kwh": energy,
                "start_soc": safe_float(item.get("starting_battery") or item.get("start_soc")),
                "end_soc": safe_float(item.get("ending_battery") or item.get("end_soc")),
                "range_added_km": range_added_km,
                "peak_kw": safe_float(item.get("peak_kw") or item.get("max_charge_power")),
                "cost": safe_float(item.get("cost") or item.get("total_cost")),
                "location": str(item.get("location") or item.get("address") or ""),
                "is_fast_charge": 1 if (item.get("fast_charger") or safe_float(item.get("peak_kw")) > 40) else 0,
            })
        return records

    # CSV path
    if isinstance(data_or_text, str):
        try:
            parsed_json = json.loads(data_or_text)
            return parse_tessie_charges(parsed_json, vin)
        except Exception:
            pass
        reader = csv.DictReader(io.StringIO(data_or_text))
    else:
        reader = csv.DictReader(data_or_text)

    headers = reader.fieldnames or []
    is_km = any("km" in h.lower() for h in headers)

    for row in reader:
        row_map = {clean_header_key(k): v for k, v in row.items() if k}
        start_ts = parse_timestamp(row_map.get("startedat") or row_map.get("date"))
        if not start_ts:
            continue
        end_ts = parse_timestamp(row_map.get("endedat")) or start_ts

        energy = safe_float(row_map.get("energyadded") or row_map.get("chargeenergyadded") or row_map.get("energykwh"))
        raw_range = safe_float(row_map.get("rangeadded"))
        range_added_km = raw_range if is_km else miles_to_km(raw_range)
        peak_kw = safe_float(row_map.get("peakkw") or row_map.get("maxchargepower") or row_map.get("maxpower"))

        records.append({
            "provider": "tessie",
            "vin": vin,
            "started_at": start_ts,
            "ended_at": end_ts,
            "duration_s": safe_int(row_map.get("duration") or row_map.get("durationseconds")),
            "energy_added_kwh": energy,
            "start_soc": safe_float(row_map.get("startingbattery") or row_map.get("startsoc")),
            "end_soc": safe_float(row_map.get("endingbattery") or row_map.get("endsoc")),
            "range_added_km": range_added_km,
            "peak_kw": peak_kw,
            "cost": safe_float(row_map.get("cost") or row_map.get("totalcost")),
            "location": row_map.get("location") or row_map.get("address") or "",
            "is_fast_charge": 1 if (row_map.get("fastcharger") in ("1", "true", "True") or peak_kw > 40) else 0,
        })

    return records


def parse_tessie_battery_health(data_or_text: Any, vin: str = "TESLA_DEFAULT") -> List[Dict[str, Any]]:
    """
    Parses Tessie battery health / degradation analytics (CSV or JSON).
    """
    records = []

    if isinstance(data_or_text, (dict, list)):
        raw_list = data_or_text.get("battery_health", []) if isinstance(data_or_text, dict) else data_or_text
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            ts = parse_timestamp(item.get("date") or item.get("timestamp"))
            if not ts:
                continue
            cap = safe_float(item.get("capacity_kwh") or item.get("capacity"))
            orig_cap = safe_float(item.get("original_capacity_kwh") or item.get("original_capacity"))
            deg = safe_float(item.get("degradation_percent") or item.get("degradation"))
            if orig_cap == 0 and cap > 0 and deg > 0 and deg < 50:
                orig_cap = round(cap / (1 - (deg / 100.0)), 2)

            records.append({
                "provider": "tessie",
                "vin": vin,
                "timestamp": ts,
                "capacity_kwh": cap,
                "original_capacity_kwh": orig_cap if orig_cap > 0 else cap,
                "degradation_pct": deg,
                "max_range_km": safe_float(item.get("estimated_range_km") or item.get("max_range")),
                "odometer_km": safe_float(item.get("odometer_km") or item.get("odometer")),
            })
        return records

    # CSV path
    if isinstance(data_or_text, str):
        try:
            parsed_json = json.loads(data_or_text)
            return parse_tessie_battery_health(parsed_json, vin)
        except Exception:
            pass
        reader = csv.DictReader(io.StringIO(data_or_text))
    else:
        reader = csv.DictReader(data_or_text)

    for row in reader:
        row_map = {clean_header_key(k): v for k, v in row.items() if k}
        ts = parse_timestamp(row_map.get("date") or row_map.get("timestamp"))
        if not ts:
            continue
        cap = safe_float(row_map.get("capacitykwh") or row_map.get("capacity"))
        deg = safe_float(row_map.get("degradationpercent") or row_map.get("degradation"))
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
