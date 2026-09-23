"""
LaVera EV Telemetry Hub - Normalization Utilities
Handles unit conversions, timestamp parsing, and telemetry standardizations.
"""

from datetime import datetime, timezone
import re
from typing import Any, Optional


def miles_to_km(miles: float) -> float:
    """Converts miles to kilometers."""
    return round(float(miles) * 1.609344, 2)


def km_to_miles(km: float) -> float:
    """Converts kilometers to miles."""
    return round(float(km) / 1.609344, 2)


def f_to_c(fahrenheit: float) -> float:
    """Converts Fahrenheit to Celsius."""
    return round((float(fahrenheit) - 32.0) * 5.0 / 9.0, 1)


def c_to_f(celsius: float) -> float:
    """Converts Celsius to Fahrenheit."""
    return round((float(celsius) * 9.0 / 5.0) + 32.0, 1)


def wh_per_mi_to_wh_per_km(wh_mi: float) -> float:
    """Converts Wh/mile to Wh/km."""
    if wh_mi <= 0:
        return 0.0
    return round(float(wh_mi) / 1.609344, 1)


def safe_float(val: Any, default: float = 0.0) -> float:
    """Safely converts string/number to float, handling currencies, % and separators."""
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace("$", "").replace("?", "").replace("%", "").replace(",", "")
    if not s or s.lower() in ("null", "none", "nan", "-"):
        return default
    try:
        return float(s)
    except (ValueError, TypeError):
        return default


def safe_int(val: Any, default: int = 0) -> int:
    """Safely converts string/number to integer."""
    if val is None:
        return default
    if isinstance(val, int):
        return val
    try:
        return int(round(safe_float(val, float(default))))
    except (ValueError, TypeError):
        return default


def parse_timestamp(val: Any) -> Optional[str]:
    """
    Parses various timestamp formats (ISO8601, TeslaFi, Tessie, Epoch)
    into standard ISO 8601 UTC string (YYYY-MM-DDTHH:MM:SSZ).
    """
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ("null", "none", ""):
        return None

    # Check Unix epoch (seconds or milliseconds)
    if re.match(r"^\d{10}(\d{3})?$", s):
        try:
            ts = float(s)
            if len(s) > 10:
                ts = ts / 1000.0
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            pass

    formats = [
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%d",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue

    return None


def clean_header_key(key: str) -> str:
    """Normalizes CSV header key for flexible matching (lowercase, alphanumeric only)."""
    return re.sub(r"[^a-z0-9]", "", str(key).lower())
