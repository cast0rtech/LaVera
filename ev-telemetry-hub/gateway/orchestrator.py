"""
Hybrid Telemetry Gateway & Failover Orchestrator.
Manages primary/secondary provider routing, transparent failover on 429/5xx/timeout,
circuit breaker state synchronization, and data ingest dispatcher.
"""

import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .base import BaseTelemetryProvider
from .circuit_breaker import CircuitBreaker
from .models import CanonicalVehicleState, CanonicalDrive, CanonicalCharge, CircuitState, ProviderError
from .security import TeslaSecurityManager
from .tesla_fleet_provider import TeslaFleetProvider
from .tessie_provider import TessieProvider

logger = logging.getLogger("lavera.gateway")


class HybridTelemetryGateway:
    """
    High-availability EV telemetry gateway with active-passive failover and circuit breaker protection.
    """

    def __init__(self, primary_provider_name: str = "tessie", fallback_enabled: bool = True):
        self.primary_name = primary_provider_name.lower()
        self.fallback_enabled = fallback_enabled

        self.providers: Dict[str, BaseTelemetryProvider] = {}
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}

        # Failover telemetry metrics
        self.metrics = {
            "total_calls": 0,
            "primary_successes": 0,
            "fallback_successes": 0,
            "total_failures": 0,
            "last_failover_at": None,
            "last_failover_reason": None,
            "active_provider": self.primary_name,
        }

    def register_provider(self, provider: BaseTelemetryProvider, failure_threshold: int = 3, recovery_timeout: float = 45.0):
        """Registers a telemetry provider with its own dedicated Circuit Breaker."""
        name = provider.name.lower()
        self.providers[name] = provider
        self.circuit_breakers[name] = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )
        logger.info(f"[Gateway] Registered provider: {name} (CircuitBreaker initialized)")

    def set_primary_provider(self, name: str):
        """Switches the prioritized primary provider."""
        norm_name = name.lower()
        if norm_name not in self.providers:
            raise ValueError(f"Proveedor '{name}' no registrado. Disponibles: {list(self.providers.keys())}")
        self.primary_name = norm_name
        self.metrics["active_provider"] = norm_name
        logger.info(f"[Gateway] Primary provider set to: {norm_name}")

    def get_secondary_provider_name(self) -> Optional[str]:
        """Returns the fallback provider name."""
        for name in self.providers:
            if name != self.primary_name:
                return name
        return None

    def execute_with_failover(self, operation_name: str, func: Callable[[BaseTelemetryProvider], Any]) -> Tuple[Any, str]:
        """
        Executes an operation against the primary provider. If the primary fails
        due to 429 rate limit, 5xx server error, timeout, or an open circuit,
        it transparently falls back to the secondary provider.

        Returns: (result, executing_provider_name)
        """
        self.metrics["total_calls"] += 1
        primary = self.providers.get(self.primary_name)
        primary_cb = self.circuit_breakers.get(self.primary_name)
        saved_primary_err = None
        primary_failure_reason = None

        if not primary:
            raise RuntimeError(f"Proveedor primario '{self.primary_name}' no disponible.")

        # Check Circuit Breaker of Primary
        primary_allowed = primary_cb.can_execute() if primary_cb else True

        if primary_allowed:
            try:
                result = func(primary)
                if primary_cb:
                    primary_cb.record_success()
                self.metrics["primary_successes"] += 1
                self.metrics["active_provider"] = self.primary_name
                return result, self.primary_name
            except Exception as primary_err:
                saved_primary_err = primary_err
                if primary_cb:
                    retry_after = getattr(primary_err, "retry_after", None)
                    primary_cb.record_failure(primary_err, retry_after=retry_after)
                logger.warning(f"[Gateway] Primary '{self.primary_name}' failed on '{operation_name}': {primary_err}")
                primary_failure_reason = str(primary_err)
        else:
            primary_failure_reason = f"Circuit Breaker para '{self.primary_name}' en estado OPEN"
            logger.warning(f"[Gateway] Primary '{self.primary_name}' circuit is OPEN. Short-circuiting to fallback.")

        # Fallback evaluation
        if not self.fallback_enabled:
            self.metrics["total_failures"] += 1
            raise RuntimeError(f"Fallo en proveedor primario '{self.primary_name}' y fallback deshabilitado: {primary_failure_reason}")

        secondary_name = self.get_secondary_provider_name()
        if not secondary_name:
            self.metrics["total_failures"] += 1
            if saved_primary_err is not None:
                raise saved_primary_err
            raise RuntimeError("No hay proveedor secundario configurado para conmutacion por error.")

        secondary = self.providers.get(secondary_name)
        secondary_cb = self.circuit_breakers.get(secondary_name)

        if secondary_cb and not secondary_cb.can_execute():
            self.metrics["total_failures"] += 1
            raise RuntimeError(f"Ambos proveedores están degradados. Primario ({self.primary_name}) falló: {primary_failure_reason}; Secundario ({secondary_name}) circuit is OPEN.")

        # Record failover event
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.metrics["last_failover_at"] = now_iso
        self.metrics["last_failover_reason"] = f"Primario '{self.primary_name}' falló ({primary_failure_reason}). Conmutado a '{secondary_name}'."
        self.metrics["active_provider"] = secondary_name

        try:
            logger.info(f"[Gateway Failover] Routing '{operation_name}' to secondary: '{secondary_name}'")
            result = func(secondary)
            if secondary_cb:
                secondary_cb.record_success()
            self.metrics["fallback_successes"] += 1
            return result, secondary_name
        except Exception as sec_err:
            if secondary_cb:
                secondary_cb.record_failure(sec_err)
            self.metrics["total_failures"] += 1
            raise RuntimeError(f"Fallo total en pasarela híbrida. Primario ({self.primary_name}): {primary_failure_reason} | Secundario ({secondary_name}): {str(sec_err)}")

    # --- High-level telemetry operations ---

    def get_vehicles(self) -> Tuple[List[Dict[str, Any]], str]:
        return self.execute_with_failover("get_vehicles", lambda p: p.get_vehicles())

    def get_vehicle_state(self, vin: str) -> Tuple[CanonicalVehicleState, str]:
        return self.execute_with_failover("get_vehicle_state", lambda p: p.get_vehicle_state(vin))

    def get_drives(self, vin: str, from_ts: Optional[int] = None, to_ts: Optional[int] = None) -> Tuple[List[CanonicalDrive], str]:
        return self.execute_with_failover("get_drives", lambda p: p.get_drives(vin, from_ts=from_ts, to_ts=to_ts))

    def get_charges(self, vin: str, from_ts: Optional[int] = None, to_ts: Optional[int] = None) -> Tuple[List[CanonicalCharge], str]:
        return self.execute_with_failover("get_charges", lambda p: p.get_charges(vin, from_ts=from_ts, to_ts=to_ts))

    def wake_up(self, vin: str) -> Tuple[bool, str]:
        return self.execute_with_failover("wake_up", lambda p: p.wake_up(vin))

    def get_gateway_status(self) -> Dict[str, Any]:
        """Provides full operational telemetry metrics of the gateway and registered providers."""
        providers_status = {}
        for name, p in self.providers.items():
            cb = self.circuit_breakers.get(name)
            h = p.health_check()
            providers_status[name] = {
                "name": name,
                "circuit_state": cb.state.value if cb else "CLOSED",
                "can_execute": cb.can_execute() if cb else True,
                "consecutive_failures": cb.failure_count if cb else 0,
                "total_requests": h.total_requests,
                "total_successes": h.total_successes,
                "total_failures": h.total_failures,
                "average_latency_ms": h.average_latency_ms,
                "last_success_at": h.last_success_at,
                "last_error_at": h.last_error_at,
                "last_error_reason": h.last_error_reason,
            }

        return {
            "primary_provider": self.primary_name,
            "secondary_provider": self.get_secondary_provider_name(),
            "fallback_enabled": self.fallback_enabled,
            "active_provider": self.metrics["active_provider"],
            "metrics": self.metrics,
            "providers": providers_status,
        }
