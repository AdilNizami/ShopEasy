from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")
logger = logging.getLogger("shop_easy.circuit_breaker")


class CircuitOpenError(RuntimeError):
    """Raised when a downstream is failing and the breaker is open."""


class CircuitBreaker:
    """Thread-safe CLOSED/OPEN/HALF-OPEN breaker for synchronous dependencies."""

    def __init__(
        self,
        failure_threshold: int = 3,
        reset_timeout_seconds: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold < 1 or reset_timeout_seconds <= 0:
            raise ValueError("Circuit breaker threshold and reset timeout must be positive.")
        self.failure_threshold = failure_threshold
        self.reset_timeout_seconds = reset_timeout_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._state = "CLOSED"
        self._failures = 0
        self._opened_at = 0.0
        self._probe_in_flight = False

    @property
    def state(self) -> str:
        with self._lock:
            self._refresh_state()
            return self._state

    def _refresh_state(self) -> None:
        if self._state == "OPEN" and self._clock() - self._opened_at >= self.reset_timeout_seconds:
            self._state = "HALF-OPEN"
            logger.info("downstream circuit entered HALF-OPEN")

    def call(self, operation: Callable[[], T]) -> T:
        with self._lock:
            self._refresh_state()
            if self._state == "OPEN":
                raise CircuitOpenError("Downstream circuit is open.")
            if self._state == "HALF-OPEN":
                if self._probe_in_flight:
                    raise CircuitOpenError("Downstream recovery probe is already in flight.")
                self._probe_in_flight = True

        try:
            result = operation()
        except Exception:
            with self._lock:
                self._failures += 1
                if self._state == "HALF-OPEN" or self._failures >= self.failure_threshold:
                    self._state = "OPEN"
                    self._opened_at = self._clock()
                    logger.warning("downstream circuit entered OPEN failures=%d", self._failures)
                self._probe_in_flight = False
            raise
        with self._lock:
            was_open = self._state != "CLOSED"
            self._state = "CLOSED"
            self._failures = 0
            self._probe_in_flight = False
            if was_open:
                logger.info("downstream circuit entered CLOSED")
        return result


_registry_lock = threading.Lock()
_breakers: dict[str, CircuitBreaker] = {}


def breaker_for(
    dependency: str, failure_threshold: int = 3, reset_timeout_seconds: float = 10.0
) -> CircuitBreaker:
    with _registry_lock:
        if dependency not in _breakers:
            _breakers[dependency] = CircuitBreaker(failure_threshold, reset_timeout_seconds)
        return _breakers[dependency]
