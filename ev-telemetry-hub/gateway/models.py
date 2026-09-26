"""
Canonical EV Telemetry Data Models for LaVera Hybrid Telemetry Gateway.
Decouples internal storage and streaming consumers from external provider schemas (Tesla Fleet API / Tessie).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class ProviderType(str, Enum):
    TESLA_FLEET = "tesla_fleet"
    TESSIE = "tessie"
    DEMO = "demo"


class CircuitState(str, Enum):
    CLOSED = "CLOSED"        # Normal operation: requests routed to provider
    OPEN = "OPEN"            # Provider failing: calls short-circuited to fallback
    HALF_OPEN = "HALF_OPEN"  # Trial request probing provider recovery


class ProviderError(Exception):
    """Exception raised by telemetry providers with error classification."""
    def __init__(self, message: str, status_code: Optional[int] = None,
                 is_rate_limit: bool = False, is_timeout: bool = False,
                 is_server_error: bool = False, is_auth_error: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.is_rate_limit = is_rate_limit
        self.is_timeout = is_timeout
        self.is_server_error = is_server_error
        self.is_auth_error = is_auth_error


@dataclass
class CanonicalVehicleState:
    """Universal real-time vehicle telemetry state."""
    vin: str
    provider: str
    timestamp: str  # ISO 8601 UTC
    soc: float  # State of Charge % (0-100)
    battery_range_km: float
    is_charging: bool
    charging_state: str  # Charging, Stopped, Complete, Disconnected, Standby
    charger_power_kw: float
    charge_rate_kmh: float
    energy_added_kwh: float
    time_to_full_charge_hours: float
    speed_kmh: float
    power_kw: float
    odometer_km: float
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    heading: Optional[float] = None
    inside_temp_c: Optional[float] = None
    outside_temp_c: Optional[float] = None
    battery_temp_c: Optional[float] = None
    is_locked: bool = True
    is_sentry_active: bool = False
    is_climate_on: bool = False
    is_asleep: bool = False
    shift_state: Optional[str] = None  # P, D, R, N
    tpms_pressure_bar: Dict[str, float] = field(default_factory=dict)
    raw_payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CanonicalDrive:
    """Universal drive session."""
    vin: str
    provider: str
    started_at: str
    ended_at: str
    duration_s: int
    distance_km: float
    energy_kwh: float
    efficiency_wh_km: float
    start_soc: float
    end_soc: float
    start_location: str
    end_location: str
    start_odometer_km: float
    end_odometer_km: float
    start_latitude: Optional[float] = None
    start_longitude: Optional[float] = None
    end_latitude: Optional[float] = None
    end_longitude: Optional[float] = None
    max_speed_kmh: float = 0.0
    autopilot_km: float = 0.0
    autopilot_pct: float = 0.0
    raw_payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CanonicalCharge:
    """Universal charging session."""
    vin: str
    provider: str
    started_at: str
    ended_at: str
    duration_s: int
    energy_added_kwh: float
    start_soc: float
    end_soc: float
    range_added_km: float
    peak_kw: float
    cost: float
    location: str
    is_fast_charge: bool
    raw_payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderHealth:
    """Live health status and telemetry metrics of a specific provider."""
    name: str
    circuit_state: CircuitState = CircuitState.CLOSED
    is_available: bool = True
    last_success_at: Optional[str] = None
    last_error_at: Optional[str] = None
    last_error_reason: Optional[str] = None
    consecutive_failures: int = 0
    total_requests: int = 0
    total_successes: int = 0
    total_failures: int = 0
    rate_limit_resets_at: Optional[str] = None
    average_latency_ms: float = 0.0
