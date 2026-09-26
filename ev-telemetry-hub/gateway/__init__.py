"""
LaVera Hybrid EV Telemetry Gateway.
Provides high-availability telemetry ingestion with failover and circuit breaker protection
across official Tesla Fleet API and Tessie Cloud API.
"""

from .models import (
    ProviderType,
    CircuitState,
    ProviderError,
    CanonicalVehicleState,
    CanonicalDrive,
    CanonicalCharge,
    ProviderHealth,
)
from .security import TeslaSecurityManager
from .circuit_breaker import CircuitBreaker
from .base import BaseTelemetryProvider
from .tessie_provider import TessieProvider
from .tesla_fleet_provider import TeslaFleetProvider
from .orchestrator import HybridTelemetryGateway

__all__ = [
    "ProviderType",
    "CircuitState",
    "ProviderError",
    "CanonicalVehicleState",
    "CanonicalDrive",
    "CanonicalCharge",
    "ProviderHealth",
    "TeslaSecurityManager",
    "CircuitBreaker",
    "BaseTelemetryProvider",
    "TessieProvider",
    "TeslaFleetProvider",
    "HybridTelemetryGateway",
]
