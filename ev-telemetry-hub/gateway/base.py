"""
Abstract Base Telemetry Provider.
Standardizes provider interactions (Tesla Fleet API, Tessie, Demo).
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from .models import CanonicalVehicleState, CanonicalDrive, CanonicalCharge, ProviderHealth


class BaseTelemetryProvider(ABC):
    """Abstract interface that all EV telemetry providers must implement."""

    def __init__(self, name: str, timeout: int = 12):
        self.name = name
        self.timeout = timeout

    @abstractmethod
    def get_vehicles(self) -> List[Dict[str, Any]]:
        """Retrieves list of vehicles linked to this provider account."""
        pass

    @abstractmethod
    def get_vehicle_state(self, vin: str) -> CanonicalVehicleState:
        """Retrieves live vehicle telemetry normalized to CanonicalVehicleState."""
        pass

    @abstractmethod
    def get_drives(self, vin: str, from_ts: Optional[int] = None, to_ts: Optional[int] = None) -> List[CanonicalDrive]:
        """Retrieves historical drive sessions normalized to CanonicalDrive."""
        pass

    @abstractmethod
    def get_charges(self, vin: str, from_ts: Optional[int] = None, to_ts: Optional[int] = None) -> List[CanonicalCharge]:
        """Retrieves historical charging sessions normalized to CanonicalCharge."""
        pass

    @abstractmethod
    def wake_up(self, vin: str) -> bool:
        """Sends wake command to vehicle if asleep."""
        pass

    @abstractmethod
    def health_check(self) -> ProviderHealth:
        """Returns health metrics and status of this provider."""
        pass
