"""
Tessie Data Parser for LaVera EV Telemetry Hub.
Parses Tessie CSV and JSON exports (drives, charges, battery health analytics, idles).
Supports all Tessie export variations, API responses, multi-lingual formats, and European delimiters.
"""

import csv
import io
import json
from typing import Any, Dict, List, Optional, Tuple, Union
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


def detect_tessie_type(data: Union[str, Dict, List]) -> str:
    """Detects whether Tessie export is drives, charges, battery, or idle data."""
    if isinstance(data, str):
        s = data.strip().lstrip("\ufeff")
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
        if any(k in cleaned for k in ["energyadded", "chargeenergy", "fastcharger", "supercharger", "peakpower", "charges", "cargador", "energiaagregada", "cargas"]):
            return "charges"
        if any(k in cleaned for k in ["degradation", "capacitykwh", "batteryhealth", "usablecapacity", "degradationpercent", "degradacion", "saludbateria", "capacidadkwh"]):
            return "battery"
        if any(k in cleaned for k in ["idletime", "vampire", "drain", "idleduration", "socloss", "inactividad"]):
            return "idles"
        if any(k in cleaned for k in ["distance", "energyused", "startingbattery", "startsoc", "odometerstart", "drives", "distancia", "viajes", "conduccion", "horadeinicio", "started", "startedat"]):
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
            for key in ["results", "data", "items", "records"]:
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
        if any(k in sample for k in ["idle_duration", "vampire_loss", "drain_rate"]):
            return "idles"
        if any(k in sample for k in ["distance", "energy_used", "duration", "starting_battery", "start_soc", "odometer_start", "efficiency"]):
            return "drives"

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
        if "started_at" in data or "date" in data or "timestamp" in data or "start_time" in data:
            return [data]
    return []


def parse_tessie_drives(data_or_text: Any, vin: str = "TESLA_DEFAULT") -> List[Dict[str, Any]]:
    """
    Parses Tessie drives from either JSON or CSV format.
    Supports auto-detected delimiters, units, accents, and Spanish headers.
    """
    records = []

    # If string, check if it's JSON first
    if isinstance(data_or_text, str):
        stripped = data_or_text.strip().lstrip("\ufeff")
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
                item.get("started_at") or item.get("start_time") or item.get("start") or
                item.get("date") or item.get("start_date") or item.get("timestamp")
            )
            if not start_ts:
                continue
            end_ts = parse_timestamp(
                item.get("ended_at") or item.get("end_time") or item.get("end") or item.get("end_date")
            ) or start_ts

            dist = safe_float(
                item.get("distance") or item.get("distance_km") or item.get("distance_miles") or
                item.get("drive_distance") or item.get("miles") or item.get("km")
            )
            unit = str(item.get("distance_unit") or item.get("unit") or "").lower()
            dist_km = dist if "km" in unit else miles_to_km(dist)

            dur_s = safe_int(
                item.get("duration") or item.get("duration_seconds") or item.get("duration_s") or
                item.get("drive_duration") or item.get("seconds")
            )
            if dur_s == 0 and start_ts and end_ts:
                try:
                    from datetime import datetime
                    t1 = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
                    t2 = datetime.fromisoformat(end_ts.replace("Z", "+00:00"))
                    dur_s = max(0, int((t2 - t1).total_seconds()))
                except Exception:
                    pass

            energy_kwh = safe_float(
                item.get("energy_used") or item.get("energy_kwh") or item.get("energy") or
                item.get("kwh_used") or item.get("kwh")
            )

            raw_eff = safe_float(
                item.get("efficiency") or item.get("wh_per_km") or item.get("wh_per_mile") or
                item.get("avg_efficiency") or item.get("wh_mi") or item.get("wh_km")
            )
            eff_wh_km = raw_eff if "km" in unit else wh_per_mi_to_wh_per_km(raw_eff)

            start_soc = safe_float(item.get("starting_battery") or item.get("start_soc") or item.get("start_battery_level") or item.get("starting_soc"))
            end_soc = safe_float(item.get("ending_battery") or item.get("end_soc") or item.get("end_battery_level") or item.get("ending_soc"))

            start_odo = safe_float(item.get("odometer_start") or item.get("starting_odometer") or item.get("start_odometer") or item.get("start_odo") or item.get("odometer"))
            end_odo = safe_float(item.get("odometer_end") or item.get("ending_odometer") or item.get("end_odometer") or item.get("end_odo"))
            start_odo_km = start_odo if "km" in unit else miles_to_km(start_odo)
            end_odo_km = end_odo if "km" in unit else miles_to_km(end_odo)

            if dist_km == 0 and end_odo_km > start_odo_km > 0:
                dist_km = round(end_odo_km - start_odo_km, 2)

            if dist_km == 0:
                soc_diff = abs(start_soc - end_soc)
                if soc_diff > 0:
                    dist_km = round(soc_diff * 4.5, 2)
                elif energy_kwh > 0:
                    dist_km = round(energy_kwh / 0.145, 2)

            if eff_wh_km == 0 and dist_km > 0 and energy_kwh > 0:
                eff_wh_km = round((energy_kwh * 1000.0) / dist_km, 1)

            # Autopilot / Piloto Automático metrics
            raw_ap_dist = safe_float(
                item.get("autopilot_distance") or item.get("autosteer_distance") or item.get("fsd_distance") or
                item.get("autopilot_km") or item.get("autopilot_miles")
            )
            ap_dist_km = raw_ap_dist if "km" in unit else miles_to_km(raw_ap_dist)

            ap_dur_s = safe_int(
                item.get("autopilot_duration") or item.get("autosteer_duration") or item.get("fsd_duration") or
                item.get("autopilot_seconds") or item.get("autopilot_s")
            )

            ap_pct = safe_float(
                item.get("autopilot_percent") or item.get("autopilot_pct") or item.get("autosteer_percent") or
                item.get("autopilot")
            )
            if ap_pct == 0 and dist_km > 0 and ap_dist_km > 0:
                ap_pct = round((ap_dist_km / dist_km) * 100.0, 1)

            start_loc = str(
                item.get("start_location") or item.get("start_address") or item.get("origin") or
                item.get("starting_location") or item.get("starting_address") or item.get("start_name") or
                item.get("start_city") or item.get("location_start") or item.get("address_start") or ""
            ).strip()
            end_loc = str(
                item.get("end_location") or item.get("end_address") or item.get("destination") or
                item.get("ending_location") or item.get("ending_address") or item.get("end_name") or
                item.get("end_city") or item.get("location_end") or item.get("address_end") or ""
            ).strip()

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
                "start_location": start_loc or "Tessie Drive",
                "end_location": end_loc or "Tesla Destination",
                "start_odometer_km": start_odo_km,
                "end_odometer_km": end_odo_km,
                "max_speed_kmh": round(safe_float(item.get("speed_max") or item.get("max_speed")) * (1.0 if "km" in unit else 1.60934), 1),
                "autopilot_km": ap_dist_km,
                "autopilot_duration_s": ap_dur_s,
                "autopilot_pct": ap_pct,
            })
        return records

    # CSV path
    text_content = data_or_text if isinstance(data_or_text, str) else str(data_or_text)
    text_content = text_content.lstrip("\ufeff")
    delimiter = detect_delimiter(text_content)
    reader = csv.DictReader(io.StringIO(text_content), delimiter=delimiter)

    headers = reader.fieldnames or []
    cleaned_header_list = [clean_header_key(h) for h in headers]
    is_km = any("km" in h for h in cleaned_header_list) or any("distancia" in h for h in cleaned_header_list) or any("autonomia" in h for h in cleaned_header_list) or delimiter == ";" or any("autonomia" in h for h in cleaned_header_list) or delimiter == ";"

    for row in reader:
        row_map = {clean_header_key(k): v for k, v in row.items() if k}

        # Multi-lingual start timestamp
        start_ts = parse_timestamp(
            row_map.get("startedat") or row_map.get("started") or row_map.get("date") or
            row_map.get("startdate") or row_map.get("starttime") or row_map.get("startingtime") or
            row_map.get("start") or row_map.get("horadeinicio") or row_map.get("fechainicio") or
            row_map.get("inicio") or row_map.get("timestamp") or row_map.get("time") or
            row_map.get("fecha") or row_map.get("hora") or row_map.get("startat")
        )
        if not start_ts:
            continue

        end_ts = parse_timestamp(
            row_map.get("endedat") or row_map.get("ended") or row_map.get("enddate") or
            row_map.get("endtime") or row_map.get("endingtime") or row_map.get("end") or
            row_map.get("horadefin") or row_map.get("fechafin") or row_map.get("fin") or
            row_map.get("horadefinalizacion") or row_map.get("endat")
        ) or start_ts

        raw_dist_val = (
            row_map.get("distance") or row_map.get("distancekm") or row_map.get("distancemi") or
            row_map.get("distancia") or row_map.get("miles") or row_map.get("km") or
            row_map.get("kilometros") or row_map.get("recorrido") or ""
        )
        row_is_km = is_km or ("km" in str(raw_dist_val).lower())
        raw_dist = safe_float(raw_dist_val)
        dist_km = raw_dist if row_is_km else miles_to_km(raw_dist)

        dur_s = safe_int(
            row_map.get("duration") or row_map.get("durationseconds") or row_map.get("durations") or
            row_map.get("time") or row_map.get("duracion") or row_map.get("duracionsegundos") or
            row_map.get("tiempo")
        )
        if dur_s == 0 and "durationminutes" in row_map:
            dur_s = int(safe_float(row_map.get("durationminutes")) * 60)
        if dur_s == 0 and "duracionminutos" in row_map:
            dur_s = int(safe_float(row_map.get("duracionminutos")) * 60)

        raw_eff = safe_float(
            row_map.get("efficiency") or row_map.get("whkm") or row_map.get("whmi") or
            row_map.get("eficiencia") or row_map.get("rendimiento") or row_map.get("consumomedio")
        )
        eff_wh_km = raw_eff if is_km else wh_per_mi_to_wh_per_km(raw_eff)
        energy_kwh = safe_float(
            row_map.get("energyused") or row_map.get("energykwh") or row_map.get("energy") or
            row_map.get("energia") or row_map.get("energiausada") or row_map.get("consumo") or
            row_map.get("consumokwh")
        )
        if energy_kwh == 0 and dist_km > 0 and eff_wh_km > 0:
            energy_kwh = round((dist_km * eff_wh_km) / 1000.0, 2)

        start_soc = safe_float(
            row_map.get("startingbattery") or row_map.get("startsoc") or row_map.get("startbattery") or
            row_map.get("startbatterylevel") or row_map.get("batterylevelstart") or
            row_map.get("bateriainicial") or row_map.get("socinicio") or row_map.get("socinicial") or
            row_map.get("bateriaprincipio")
        )
        end_soc = safe_float(
            row_map.get("endingbattery") or row_map.get("endsoc") or row_map.get("endbattery") or
            row_map.get("endbatterylevel") or row_map.get("batterylevelend") or
            row_map.get("bateriafinal") or row_map.get("socfin") or row_map.get("socfinal") or
            row_map.get("bateriadestino")
        )

        raw_start_odo = safe_float(
            row_map.get("odometerstart") or row_map.get("startingodometer") or row_map.get("startodometer") or
            row_map.get("odometroinicio") or row_map.get("odometroinicial") or row_map.get("odometro")
        )
        raw_end_odo = safe_float(
            row_map.get("odometerend") or row_map.get("endingodometer") or row_map.get("endodometer") or
            row_map.get("odometrofin") or row_map.get("odometrofinal")
        )
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
            "start_temp_c": safe_float(
                row_map.get("startingtemperature") or row_map.get("starttemp") or row_map.get("insidetemp") or
                row_map.get("temperaturainicial")
            ),
            "end_temp_c": safe_float(
                row_map.get("endingtemperature") or row_map.get("endtemp") or row_map.get("outsidetemp") or
                row_map.get("temperaturafinal")
            ),
            "start_location": str(
                row_map.get("startlocation") or row_map.get("startaddress") or row_map.get("origin") or
                row_map.get("origen") or row_map.get("ubicacioninicial") or row_map.get("ubicacioninicio") or ""
            ),
            "end_location": str(
                row_map.get("endlocation") or row_map.get("endaddress") or row_map.get("destination") or
                row_map.get("destino") or row_map.get("ubicacionfinal") or row_map.get("ubicacionfin") or ""
            ),
            "start_odometer_km": start_odo_km,
            "end_odometer_km": end_odo_km,
            "max_speed_kmh": round(
                safe_float(row_map.get("maxspeed") or row_map.get("speedmax") or row_map.get("velocidadmaxima") or row_map.get("velocidadmax")) * (1.0 if is_km else 1.60934), 1
            ),
        })

    return records


def parse_tessie_charges(data_or_text: Any, vin: str = "TESLA_DEFAULT") -> List[Dict[str, Any]]:
    """
    Parses Tessie charges from either JSON or CSV format.
    Supports auto-detected delimiters, units, accents, and Spanish headers.
    """
    records = []

    # If string, check if it's JSON first
    if isinstance(data_or_text, str):
        stripped = data_or_text.strip().lstrip("\ufeff")
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

            energy = safe_float(item.get("energy_added") or item.get("charge_energy_added") or item.get("energy_kwh") or item.get("kwh_added"))
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
    text_content = data_or_text if isinstance(data_or_text, str) else str(data_or_text)
    text_content = text_content.lstrip("\ufeff")
    delimiter = detect_delimiter(text_content)
    reader = csv.DictReader(io.StringIO(text_content), delimiter=delimiter)

    headers = reader.fieldnames or []
    cleaned_header_list = [clean_header_key(h) for h in headers]
    is_km = any("km" in h for h in cleaned_header_list) or any("distancia" in h for h in cleaned_header_list) or any("autonomia" in h for h in cleaned_header_list) or delimiter == ";" or any("autonomia" in h for h in cleaned_header_list) or delimiter == ";"

    for row in reader:
        row_map = {clean_header_key(k): v for k, v in row.items() if k}
        start_ts = parse_timestamp(
            row_map.get("startedat") or row_map.get("started") or row_map.get("date") or
            row_map.get("startdate") or row_map.get("starttime") or row_map.get("startingtime") or
            row_map.get("start") or row_map.get("horadeinicio") or row_map.get("fechainicio") or
            row_map.get("inicio") or row_map.get("time") or row_map.get("fecha") or row_map.get("hora")
        )
        if not start_ts:
            continue
        end_ts = parse_timestamp(
            row_map.get("endedat") or row_map.get("ended") or row_map.get("enddate") or
            row_map.get("endtime") or row_map.get("endingtime") or row_map.get("end") or
            row_map.get("horadefin") or row_map.get("fechafin") or row_map.get("fin")
        ) or start_ts

        energy = safe_float(
            row_map.get("energyadded") or row_map.get("chargeenergyadded") or row_map.get("energykwh") or
            row_map.get("energy") or row_map.get("kwhadded") or row_map.get("energiaagregada") or
            row_map.get("energiacargada") or row_map.get("cargakwh") or row_map.get("kwhcargados")
        )
        raw_range_val = (
            row_map.get("rangeadded") or row_map.get("autonomiaagregada") or row_map.get("autonomiaganada") or
            row_map.get("kmagregados") or row_map.get("kmganados") or ""
        )
        row_is_km = is_km or ("km" in str(raw_range_val).lower())
        raw_range = safe_float(raw_range_val)
        range_added_km = raw_range if row_is_km else miles_to_km(raw_range)
        peak_kw = safe_float(
            row_map.get("peakkw") or row_map.get("maxchargepower") or row_map.get("peakpower") or
            row_map.get("maxpower") or row_map.get("potenciamaxima") or row_map.get("potenciamax") or
            row_map.get("kwmax")
        )

        records.append({
            "provider": "tessie",
            "vin": vin,
            "started_at": start_ts,
            "ended_at": end_ts,
            "duration_s": safe_int(
                row_map.get("duration") or row_map.get("durationseconds") or row_map.get("duracion") or
                row_map.get("tiempo")
            ),
            "energy_added_kwh": energy,
            "start_soc": safe_float(
                row_map.get("startingbattery") or row_map.get("startsoc") or row_map.get("startbattery") or
                row_map.get("startbatterylevel") or row_map.get("bateriainicial") or row_map.get("socinicio")
            ),
            "end_soc": safe_float(
                row_map.get("endingbattery") or row_map.get("endsoc") or row_map.get("endbattery") or
                row_map.get("endbatterylevel") or row_map.get("bateriafinal") or row_map.get("socfin")
            ),
            "range_added_km": range_added_km,
            "peak_kw": peak_kw,
            "cost": safe_float(
                row_map.get("cost") or row_map.get("totalcost") or row_map.get("coste") or
                row_map.get("costo") or row_map.get("precio") or row_map.get("importe")
            ),
            "location": str(
                row_map.get("location") or row_map.get("address") or row_map.get("chargername") or
                row_map.get("ubicacion") or row_map.get("cargador") or row_map.get("estacion") or ""
            ),
            "is_fast_charge": 1 if (
                row_map.get("fastcharger") in ("1", "true", "yes", "si", "True", True) or
                row_map.get("supercharger") in ("1", "true", "yes", "si", "True", True) or
                row_map.get("cargadorrapido") in ("1", "true", "yes", "si", "True", True) or
                peak_kw > 40
            ) else 0,
        })

    return records


def parse_tessie_battery_health(data_or_text: Any, vin: str = "TESLA_DEFAULT") -> List[Dict[str, Any]]:
    """Parses Tessie battery health history from JSON or CSV."""
    records = []
    if isinstance(data_or_text, str):
        stripped = data_or_text.strip().lstrip("\ufeff")
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                parsed_json = json.loads(stripped)
                return parse_tessie_battery_health(parsed_json, vin)
            except Exception:
                pass

    if isinstance(data_or_text, (dict, list)):
        raw_list = _extract_list_from_json(data_or_text, "battery_health")
        for item in raw_list:
            import datetime
            ts = parse_timestamp(item.get("timestamp") or item.get("date") or item.get("created_at") or item.get("time"))
            if not ts:
                ts = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

            # Support nested charge_state & vehicle_state from Tessie state object
            charge_st = item.get("charge_state", {}) if isinstance(item.get("charge_state"), dict) else {}
            vehicle_st = item.get("vehicle_state", {}) if isinstance(item.get("vehicle_state"), dict) else {}

            cap = safe_float(
                item.get("capacity_kwh") or item.get("usable_capacity") or item.get("battery_capacity") or item.get("capacity")
            )
            orig = safe_float(
                item.get("original_capacity_kwh") or item.get("original_capacity") or item.get("factory_capacity")
            )

            # If capacity not direct, compute from charge_state ideal range & SoC
            if cap == 0 and charge_st:
                soc = safe_float(charge_st.get("battery_level") or charge_st.get("usable_battery_level"))
                b_range = safe_float(charge_st.get("battery_range") or charge_st.get("est_battery_range"))
                if soc > 5 and b_range > 20:
                    ideal_100_range = (b_range / soc) * 100.0
                    cap = round(ideal_100_range * 0.145, 1)

            if orig == 0:
                orig = 75.0 if cap == 0 else cap

            deg = safe_float(
                item.get("degradation_percent") or item.get("degradation_pct") or item.get("degradation") or item.get("battery_degradation")
            )
            if deg == 0 and orig > 0 and cap > 0 and orig >= cap:
                deg = round(((orig - cap) / orig) * 100.0, 1)

            unit = str(item.get("distance_unit") or item.get("unit") or "").lower()
            raw_range = safe_float(item.get("max_range_km") or item.get("range") or item.get("max_range") or charge_st.get("battery_range"))
            range_km = raw_range if "km" in unit else miles_to_km(raw_range)
            raw_odo = safe_float(item.get("odometer") or item.get("odometer_km") or vehicle_st.get("odometer"))
            odo_km = raw_odo if "km" in unit else miles_to_km(raw_odo)

            if cap > 0 or deg > 0 or range_km > 0:
                records.append({
                    "provider": "tessie",
                    "vin": vin,
                    "timestamp": ts,
                    "capacity_kwh": cap,
                    "original_capacity_kwh": orig,
                    "degradation_pct": deg,
                    "max_range_km": range_km,
                    "odometer_km": odo_km,
                })
        return records

    text_content = data_or_text if isinstance(data_or_text, str) else str(data_or_text)
    text_content = text_content.lstrip("\ufeff")
    delimiter = detect_delimiter(text_content)
    reader = csv.DictReader(io.StringIO(text_content), delimiter=delimiter)

    for row in reader:
        row_map = {clean_header_key(k): v for k, v in row.items() if k}
        ts = parse_timestamp(
            row_map.get("timestamp") or row_map.get("date") or row_map.get("fecha") or row_map.get("hora")
        )
        if not ts:
            continue
        cap = safe_float(row_map.get("capacitykwh") or row_map.get("capacidadkwh") or row_map.get("usablecapacity"))
        orig = safe_float(row_map.get("originalcapacitykwh") or row_map.get("capacidadoriginal")) or cap
        deg = safe_float(
            row_map.get("degradationpercent") or row_map.get("degradationpct") or row_map.get("degradation") or
            row_map.get("degradacion") or row_map.get("porcentajedegradacion")
        )
        records.append({
            "provider": "tessie",
            "vin": vin,
            "timestamp": ts,
            "capacity_kwh": cap,
            "original_capacity_kwh": orig,
            "degradation_pct": deg,
            "max_range_km": safe_float(row_map.get("maxrangekm") or row_map.get("autonomia100")),
            "odometer_km": safe_float(row_map.get("odometerkm") or row_map.get("odometro")),
        })

    return records
