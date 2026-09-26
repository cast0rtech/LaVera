"""
Circuit Breaker Pattern Implementation for EV Telemetry Gateway.
Prevents cascading failures, rate-limit bans (HTTP 429), and unneeded wake-ups.
"""

import time
from typing import Optional
from .models import CircuitState, ProviderError


class CircuitBreaker:
    """
    Monitors provider calls and short-circuits execution when failure thresholds are reached.
    Automatically transitions from CLOSED -> OPEN -> HALF_OPEN -> CLOSED.
    """
    def __init__(self, name: str, failure_threshold: int = 3,
                 recovery_timeout: float = 45.0, half_open_success_threshold: int = 1):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_success_threshold = half_open_success_threshold

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.last_state_change: float = time.time()
        self.backoff_until: Optional[float] = None

    def can_execute(self) -> bool:
        """Determines whether a call is permitted to proceed to the provider."""
        now = time.time()

        # Respect explicit backoff (e.g. HTTP 429 Retry-After)
        if self.backoff_until and now < self.backoff_until:
            return False

        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            if self.last_failure_time and (now - self.last_failure_time) >= self.recovery_timeout:
                self._transition_to(CircuitState.HALF_OPEN)
                return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            # Allow limited probe request
            return True

        return False

    def record_success(self):
        """Records a successful call and recovers circuit if probing."""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.half_open_success_threshold:
                self._transition_to(CircuitState.CLOSED)
                self.failure_count = 0
                self.success_count = 0
        elif self.state == CircuitState.CLOSED:
            self.failure_count = 0

    def record_failure(self, error: Exception, retry_after: Optional[int] = None):
        """
        Records a failed call. Trips the circuit breaker if thresholds or rate limits are met.
        """
        now = time.time()
        self.last_failure_time = now

        # Handle rate-limit specific backoff
        if retry_after and retry_after > 0:
            self.backoff_until = now + retry_after
        elif isinstance(error, ProviderError) and error.is_rate_limit:
            self.backoff_until = now + 60.0  # Default 60s cooldown for 429

        self.failure_count += 1

        is_429 = False
        if isinstance(error, ProviderError) and error.is_rate_limit:
            is_429 = True
            cooldown = float(retry_after) if (retry_after and retry_after > 0) else 60.0
            self.backoff_until = now + cooldown

        # Trip to OPEN if threshold reached or explicit 429
        if is_429 or self.failure_count >= self.failure_threshold:
            if self.state != CircuitState.OPEN:
                self._transition_to(CircuitState.OPEN)

    def _transition_to(self, new_state: CircuitState):
        self.state = new_state
        self.last_state_change = time.time()
        if new_state == CircuitState.HALF_OPEN:
            self.success_count = 0
