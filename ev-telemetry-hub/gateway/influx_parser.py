"""
Optimized InfluxDB Line Protocol & Point Serializer for EV Telemetry.
Converts CanonicalVehicleState, Tesla Fleet API vehicle_data, and Tessie state payloads
into high-performance InfluxDB time-series records.
"""

import math
import re
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from .models import CanonicalVehicleState
from importer.normalizer import safe_float, miles_to_km, f_to_c, parse_timestamp


def escape_tag(val: Any) -> str:
    """Escapes tag keys and tag values according to InfluxDB Line Protocol spec."""
    s = str(val or "unknown").strip()
    return s.replace(" ", r"\ ").replace(",", r"\,").replace("=", r"\=")


def escape_string_field(val: Any) -> str:
    """Escapes string field values with double quotes."""
    s = str(val)
    return '"' + s.replace('"', '\"') + '"'


class TelemetryToInfluxParser:
    """
    Transforms vehicle telemetry into optimized InfluxDB Line Protocol records.
    Strictly differentiates between low-cardinality indexing TAGS and numeric time-series FIELDS.
    """

    MEASUREMENT_NAME = "ev_telemetry"

    @classmethod
    def parse(cls, data: Union[CanonicalVehicleState, Dict[str, Any]],
              measurement: str = MEASUREMENT_NAME, precision: str = "s") -> Tuple[str, Dict[str, Any]]:
        """
        Parses raw or canonical telemetry into both:
        1. InfluxDB Line Protocol string.
        2. Structured dictionary payload for influxdb-client v2.
        """
        tags: Dict[str, str] = {}
        fields: Dict[str, Union[float, int, bool, str]] = {}
        timestamp_sec: int = int(time.time())

        # If data is CanonicalVehicleState object
        if isinstance(data, CanonicalVehicleState):
            tags["vin"] = data.vin
            tags["provider"] = data.provider
            tags["vehicle_state"] = cls._determine_vehicle_state(data.speed_kmh, data.is_charging, data.shift_state)
            tags["charging_state"] = data.charging_state or "Disconnected"
            tags["shift_state"] = data.shift_state or "P"
            tags["sentry_mode"] = "true" if data.is_sentry_active else "false"
            tags["climate_state"] = "on" if data.is_climate_on else "off"

            fields["soc_pct"] = round(data.soc, 2)
            fields["battery_range_km"] = round(data.battery_range_km, 2)
            fields["speed_kmh"] = round(data.speed_kmh, 1)
            fields["power_kw"] = round(data.power_kw, 2)
            fields["charger_power_kw"] = round(data.charger_power_kw, 2)
            fields["charge_rate_kmh"] = round(data.charge_rate_kmh, 1)
            fields["energy_added_kwh"] = round(data.energy_added_kwh, 2)
            fields["time_to_full_charge_h"] = round(data.time_to_full_charge_hours, 2)
            fields["odometer_km"] = round(data.odometer_km, 2)

            if data.latitude is not None and data.longitude is not None:
                fields["latitude"] = round(float(data.latitude), 6)
                fields["longitude"] = round(float(data.longitude), 6)
            if data.heading is not None:
                fields["heading_deg"] = round(float(data.heading), 1)
            if data.inside_temp_c is not None:
                fields["inside_temp_c"] = round(float(data.inside_temp_c), 1)
            if data.outside_temp_c is not None:
                fields["outside_temp_c"] = round(float(data.outside_temp_c), 1)
            if data.battery_temp_c is not None:
                fields["battery_temp_c"] = round(float(data.battery_temp_c), 1)

            # TPMS
            if data.tpms_pressure_bar:
                for wheel, bar in data.tpms_pressure_bar.items():
                    fields[f"tpms_pressure_{wheel}_bar"] = round(float(bar), 2)

            # Extract timestamp
            if data.timestamp:
                try:
                    from datetime import datetime, timezone
                    t_str = data.timestamp.replace("Z", "+00:00")
                    dt = datetime.fromisoformat(t_str)
                    timestamp_sec = int(dt.timestamp())
                except Exception:
                    pass

        # If data is raw dictionary (Tesla Fleet API response or Tessie state)
        elif isinstance(data, dict):
            # Unwrap nested Tesla response if present
            raw = data.get("response", data) if isinstance(data, dict) else {}

            charge_st = raw.get("charge_state", {}) if isinstance(raw.get("charge_state"), dict) else {}
            drive_st = raw.get("drive_state", {}) if isinstance(raw.get("drive_state"), dict) else {}
            climate_st = raw.get("climate_state", {}) if isinstance(raw.get("climate_state"), dict) else {}
            vehicle_st = raw.get("vehicle_state", {}) if isinstance(raw.get("vehicle_state"), dict) else {}

            vin = raw.get("vin") or drive_st.get("vin") or "DEFAULT_VIN"
            provider = raw.get("provider", "tesla_fleet")
            shift = drive_st.get("shift_state") or "P"
            is_charging = charge_st.get("charging_state") == "Charging"
            spd_raw = safe_float(drive_st.get("speed"))
            speed_kmh = round(spd_raw * 1.60934, 1) if spd_raw > 0 else 0.0

            tags["vin"] = vin
            tags["provider"] = provider
            tags["vehicle_state"] = cls._determine_vehicle_state(speed_kmh, is_charging, shift)
            tags["charging_state"] = charge_st.get("charging_state", "Disconnected")
            tags["shift_state"] = shift
            tags["sentry_mode"] = "true" if vehicle_st.get("sentry_mode") else "false"
            tags["climate_state"] = "on" if climate_st.get("is_climate_on") else "off"

            # Power & Energy fields
            fields["soc_pct"] = round(safe_float(charge_st.get("battery_level")), 2)
            fields["usable_soc_pct"] = round(safe_float(charge_st.get("usable_battery_level") or charge_st.get("battery_level")), 2)

            raw_range = safe_float(charge_st.get("battery_range"))
            fields["battery_range_km"] = round(miles_to_km(raw_range), 2)

            chg_pwr = safe_float(charge_st.get("charger_power"))
            fields["charger_power_kw"] = round(chg_pwr, 2)

            # Instantaneous power in drive (positive = traction, negative = regen)
            pwr_kw = safe_float(drive_st.get("power"))
            if pwr_kw != 0:
                fields["power_kw"] = round(pwr_kw, 2)
            elif chg_pwr > 0:
                fields["power_kw"] = round(chg_pwr, 2)
            else:
                fields["power_kw"] = 0.0

            fields["charge_rate_kmh"] = round(miles_to_km(safe_float(charge_st.get("charge_rate"))), 1)
            fields["energy_added_kwh"] = round(safe_float(charge_st.get("charge_energy_added")), 2)
            fields["time_to_full_charge_h"] = round(safe_float(charge_st.get("time_to_full_charge")), 2)

            raw_voltage = safe_float(charge_st.get("charger_voltage"))
            if raw_voltage > 0:
                fields["charger_voltage_v"] = round(raw_voltage, 1)

            raw_current = safe_float(charge_st.get("charger_actual_current"))
            if raw_current > 0:
                fields["charger_current_a"] = round(raw_current, 1)

            # Vehicle Dynamics & Odometer
            fields["speed_kmh"] = speed_kmh
            raw_odo = safe_float(vehicle_st.get("odometer"))
            fields["odometer_km"] = round(miles_to_km(raw_odo), 2)

            if drive_st.get("latitude") is not None and drive_st.get("longitude") is not None:
                fields["latitude"] = round(float(drive_st["latitude"]), 6)
                fields["longitude"] = round(float(drive_st["longitude"]), 6)

            if drive_st.get("heading") is not None:
                fields["heading_deg"] = round(float(drive_st["heading"]), 1)

            # Temperatures
            if climate_st.get("inside_temp") is not None:
                fields["inside_temp_c"] = round(float(climate_st["inside_temp"]), 1)
            if climate_st.get("outside_temp") is not None:
                fields["outside_temp_c"] = round(float(climate_st["outside_temp"]), 1)
            if climate_st.get("driver_temp_setting") is not None:
                fields["driver_temp_setting_c"] = round(float(climate_st["driver_temp_setting"]), 1)

            # Tire Pressures (TPMS) - Convert bar / psi
            tpms_fl = safe_float(vehicle_st.get("tpms_pressure_fl"))
            tpms_fr = safe_float(vehicle_st.get("tpms_pressure_fr"))
            tpms_rl = safe_float(vehicle_st.get("tpms_pressure_rl"))
            tpms_rr = safe_float(vehicle_st.get("tpms_pressure_rr"))

            # Normalize to bar (Tesla returns bar by default in vehicle_data)
            if tpms_fl > 0:
                fields["tpms_fl_bar"] = round(tpms_fl if tpms_fl < 10 else tpms_fl * 0.0689476, 2)
            if tpms_fr > 0:
                fields["tpms_fr_bar"] = round(tpms_fr if tpms_fr < 10 else tpms_fr * 0.0689476, 2)
            if tpms_rl > 0:
                fields["tpms_rl_bar"] = round(tpms_rl if tpms_rl < 10 else tpms_rl * 0.0689476, 2)
            if tpms_rr > 0:
                fields["tpms_rr_bar"] = round(tpms_rr if tpms_rr < 10 else tpms_rr * 0.0689476, 2)

            ts_raw = raw.get("timestamp") or drive_st.get("timestamp")
            if ts_raw:
                try:
                    num = float(ts_raw)
                    timestamp_sec = int(num / 1000.0) if num > 10000000000 else int(num)
                except Exception:
                    pass

        # Format Line Protocol String
        # Syntax: <measurement>[,<tag_key>=<tag_value>...] <field_key>=<field_value>[,<field_key>=<field_value>...] [<timestamp>]
        tag_str = ",".join(f"{k}={escape_tag(v)}" for k, v in sorted(tags.items()) if v is not None)

        field_parts = []
        for k, v in sorted(fields.items()):
            if isinstance(v, bool):
                field_parts.append(f"{k}={'t' if v else 'f'}")
            elif isinstance(v, (int, float)):
                if math.isnan(v) or math.isinf(v):
                    continue
                # InfluxDB differentiates float (1.0) and integer (1i)
                field_parts.append(f"{k}={float(v)}")
            elif isinstance(v, str):
                field_parts.append(f"{k}={escape_string_field(v)}")

        fields_str = ",".join(field_parts)

        # Multiplier for timestamp precision
        ts_val = timestamp_sec
        if precision == "ns":
            ts_val = timestamp_sec * 1_000_000_000
        elif precision == "ms":
            ts_val = timestamp_sec * 1_000

        line_protocol = f"{measurement},{tag_str} {fields_str} {ts_val}"

        point_dict = {
            "measurement": measurement,
            "tags": tags,
            "fields": fields,
            "time": ts_val
        }

        return line_protocol, point_dict

    @staticmethod
    def _determine_vehicle_state(speed_kmh: float, is_charging: bool, shift: Optional[str]) -> str:
        """Categorizes operational state into low-cardinality tag."""
        if is_charging:
            return "charging"
        if speed_kmh > 1.0 or (shift and shift in ("D", "R")):
            return "driving"
        return "parked"



TelemetryToInfluxParser.to_line_protocol = TelemetryToInfluxParser.parse
TelemetryToInfluxParser.parse_to_line_protocol = TelemetryToInfluxParser.parse
