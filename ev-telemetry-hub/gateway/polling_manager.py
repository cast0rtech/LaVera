"""
Adaptive Polling Manager & Vampire Drain Protector.
Controls telemetry polling cadence based on vehicle state (Driving, Charging, Parked, Asleep)
to prevent phantom battery drain, and manages exponential backoff for network drops and HTTP 4xx/5xx.
"""

import logging
import random
import time
from enum import Enum
from typing import Any, Callable, Dict, Optional, Tuple

from .base import BaseTelemetryProvider
from .models import CanonicalVehicleState, ProviderError
from .orchestrator import HybridTelemetryGateway

logger = logging.getLogger("lavera.polling")


class VehicleOperationalState(str, Enum):
    DRIVING = "driving"
    CHARGING = "charging"
    PARKED = "parked"
    WAITING_FOR_SLEEP = "waiting_for_sleep"
    ASLEEP = "asleep"
    OFFLINE = "offline"


class AdaptivePollingConfig:
    """Configurable polling intervals and timeouts (in seconds)."""
    def __init__(
        self,
        driving_interval: float = 10.0,
        charging_interval: float = 30.0,
        parked_recent_interval: float = 60.0,
        waiting_for_sleep_interval: float = 300.0,   # 5 min (non-waking status only)
        asleep_interval: float = 1800.0,             # 30 min check (zero-wake)
        sleep_eligibility_delay: float = 900.0,      # 15 min parked before entering waiting_for_sleep
        base_error_backoff: float = 15.0,
        max_error_backoff: float = 600.0,            # 10 min cap
    ):
        self.driving_interval = driving_interval
        self.charging_interval = charging_interval
        self.parked_recent_interval = parked_recent_interval
        self.waiting_for_sleep_interval = waiting_for_sleep_interval
        self.asleep_interval = asleep_interval
        self.sleep_eligibility_delay = sleep_eligibility_delay
        self.base_error_backoff = base_error_backoff
        self.max_error_backoff = max_error_backoff


class VehicleSessionTracker:
    """Tracks state and timers for an individual VIN."""
    def __init__(self, vin: str, config: AdaptivePollingConfig):
        self.vin = vin
        self.config = config
        self.current_state = VehicleOperationalState.PARKED
        self.last_poll_time: float = 0.0
        self.next_poll_time: float = 0.0
        self.parked_since: Optional[float] = time.time()
        self.consecutive_errors: int = 0
        self.last_known_state: Optional[CanonicalVehicleState] = None
        self.is_asleep: bool = False

    def time_until_next_poll(self) -> float:
        now = time.time()
        return max(0.0, self.next_poll_time - now)

    def is_due(self) -> bool:
        return time.time() >= self.next_poll_time


class VampireDrainProtector:
    """
    Coordinates vehicle polling schedules to protect high-voltage battery from vampire drain
    and gracefully handles network dropouts, rate-limiting (429), and 5xx outages.
    """

    def __init__(
        self,
        gateway: HybridTelemetryGateway,
        config: Optional[AdaptivePollingConfig] = None
    ):
        self.gateway = gateway
        self.config = config or AdaptivePollingConfig()
        self._vehicles: Dict[str, VehicleSessionTracker] = {}
        self._on_telemetry_callbacks = []

    def register_callback(self, cb: Callable[[CanonicalVehicleState], None]):
        """Registers a listener for freshly parsed telemetry (e.g. InfluxDB injector)."""
        self._on_telemetry_callbacks.append(cb)

    def _get_or_create_tracker(self, vin: str) -> VehicleSessionTracker:
        if vin not in self._vehicles:
            self._vehicles[vin] = VehicleSessionTracker(vin, self.config)
        return self._vehicles[vin]

    def poll_vehicle(self, vin: str, force: bool = False) -> Tuple[Optional[CanonicalVehicleState], str]:
        """
        Polls the vehicle using zero-wake logic when asleep, updating cadence dynamically.
        Returns: (CanonicalVehicleState or None, status_message)
        """
        tracker = self._get_or_create_tracker(vin)
        now = time.time()

        if not force and not tracker.is_due():
            wait_s = tracker.time_until_next_poll()
            return tracker.last_known_state, f"Skipped: next poll due in {wait_s:.1f}s (State: {tracker.current_state.value})"

        # Determine if we should allow waking the vehicle
        # CRITICAL RULE: If the car is ASLEEP or WAITING_FOR_SLEEP, allow_wake MUST be False
        allow_wake = False
        if tracker.current_state in (VehicleOperationalState.DRIVING, VehicleOperationalState.CHARGING):
            allow_wake = True

        logger.debug(f"[VampireProtector] Polling {vin} (State: {tracker.current_state.value}, allow_wake={allow_wake})")

        try:
            # Execute with hybrid gateway failover
            state, provider_name = self.gateway.execute_with_failover(
                "get_vehicle_state",
                lambda p: p.get_vehicle_state(vin, allow_wake=allow_wake) if hasattr(p, "get_vehicle_state") else None
            )

            if not state:
                return None, "No data received from provider."

            # Update tracker state
            self._on_poll_success(tracker, state)

            # Notify listeners (InfluxDB, Storage, WebSockets)
            for cb in self._on_telemetry_callbacks:
                try:
                    cb(state)
                except Exception as ex:
                    logger.error(f"[VampireProtector] Error in telemetry callback: {ex}")

            return state, f"Success ({provider_name}) - State: {tracker.current_state.value} (Next poll in {tracker.time_until_next_poll():.0f}s)"

        except ProviderError as pe:
            backoff_s = self._on_poll_error(tracker, pe)
            return tracker.last_known_state, f"ProviderError: {pe} (Backing off for {backoff_s:.1f}s)"

        except Exception as e:
            backoff_s = self._on_poll_error(tracker, e)
            return tracker.last_known_state, f"Unexpected error: {e} (Backing off for {backoff_s:.1f}s)"

    def _on_poll_success(self, tracker: VehicleSessionTracker, state: CanonicalVehicleState):
        """Calculates state transitions and schedules the next poll interval."""
        now = time.time()
        tracker.last_poll_time = now
        tracker.consecutive_errors = 0
        tracker.last_known_state = state

        # 1. Check if vehicle reported sleeping
        if state.is_asleep or state.charging_state == "ASLEEP":
            tracker.current_state = VehicleOperationalState.ASLEEP
            tracker.is_asleep = True
            interval = self.config.asleep_interval
            tracker.next_poll_time = now + interval
            logger.info(
                f"[VampireProtector] 💤 {tracker.vin} está DORMIDO. Cadencia relajada a {interval/60:.0f} min "
                "para evitar vampire drain."
            )
            return

        tracker.is_asleep = False

        # 2. Check Driving
        if state.speed_kmh > 1.0 or (state.shift_state and state.shift_state in ("D", "R")):
            tracker.current_state = VehicleOperationalState.DRIVING
            tracker.parked_since = None
            interval = self.config.driving_interval
            tracker.next_poll_time = now + interval
            logger.debug(f"[VampireProtector] 🚗 {tracker.vin} EN MARCHA ({state.speed_kmh} km/h). Polling cada {interval}s.")
            return

        # 3. Check Charging
        if state.is_charging or state.charging_state == "Charging":
            tracker.current_state = VehicleOperationalState.CHARGING
            tracker.parked_since = None
            interval = self.config.charging_interval
            tracker.next_poll_time = now + interval
            logger.debug(f"[VampireProtector] ⚡ {tracker.vin} CARGANDO ({state.charger_power_kw} kW). Polling cada {interval}s.")
            return

        # 4. Parked & Idle Management (The critical sleep-opportunity logic)
        if tracker.parked_since is None:
            tracker.parked_since = now

        parked_duration = now - tracker.parked_since

        if parked_duration >= self.config.sleep_eligibility_delay:
            # The vehicle has been parked long enough to enter deep sleep (~15 min)
            # We MUST STOP frequent active polls to allow the Tesla MCU bus to enter sleep!
            tracker.current_state = VehicleOperationalState.WAITING_FOR_SLEEP
            interval = self.config.waiting_for_sleep_interval
            tracker.next_poll_time = now + interval
            logger.info(
                f"[VampireProtector] ⏳ {tracker.vin} estacionado hace {parked_duration/60:.1f} min. "
                f"Entrando en ventana WAITING_FOR_SLEEP. Próximo chequeo pasivo en {interval/60:.1f} min."
            )
        else:
            # Parked recently (< 15 min)
            tracker.current_state = VehicleOperationalState.PARKED
            interval = self.config.parked_recent_interval
            tracker.next_poll_time = now + interval
            logger.debug(f"[VampireProtector] 🅿️ {tracker.vin} ESTACIONADO (reciente). Polling cada {interval}s.")

    def _on_poll_error(self, tracker: VehicleSessionTracker, error: Exception) -> float:
        """
        Computes exponential backoff with jitter on network drops or HTTP 4xx/5xx errors.
        """
        now = time.time()
        tracker.consecutive_errors += 1

        # Check for specific Rate Limit retry-after
        if isinstance(error, ProviderError) and error.is_rate_limit:
            backoff = 60.0 + random.uniform(1.0, 5.0)
            logger.warning(f"[VampireProtector] HTTP 429 en {tracker.vin}. Backoff forzado de {backoff:.1f}s.")
        else:
            # Exponential Backoff with Jitter: base * 2^(errors - 1) + jitter
            exp = min(tracker.consecutive_errors - 1, 6)
            backoff = min(
                self.config.max_error_backoff,
                self.config.base_error_backoff * (2 ** exp)
            )
            jitter = random.uniform(1.0, 5.0)
            backoff += jitter

        tracker.next_poll_time = now + backoff
        logger.warning(
            f"[VampireProtector] Error en {tracker.vin} ({error}). "
            f"Fallo #{tracker.consecutive_errors}. Próximo reintento en {backoff:.1f}s."
        )
        return backoff

    def get_status_summary(self) -> Dict[str, Any]:
        """Provides status report for all tracked vehicles."""
        now = time.time()
        report = {}
        for vin, t in self._vehicles.items():
            report[vin] = {
                "state": t.current_state.value,
                "is_asleep": t.is_asleep,
                "consecutive_errors": t.consecutive_errors,
                "seconds_until_next_poll": round(t.time_until_next_poll(), 1),
                "parked_duration_minutes": round((now - t.parked_since) / 60.0, 1) if t.parked_since else 0.0,
                "last_poll_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t.last_poll_time)) if t.last_poll_time else None
            }
        return report
