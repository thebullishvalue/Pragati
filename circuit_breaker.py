"""
PRAGYAM — Circuit Breaker Pattern Implementation
══════════════════════════════════════════════════════════════════════════════

Fault tolerance pattern for handling external service failures gracefully.

Features:
- Automatic failure detection
- Graceful degradation
- Recovery testing
- Configurable thresholds
- Retry with exponential backoff

Author: @thebullishvalue
"""

import time
from typing import Callable, Any, Optional
from enum import Enum
from functools import wraps
import threading


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"       # Normal operation - requests allowed
    OPEN = "open"           # Failing - requests blocked
    HALF_OPEN = "half_open" # Testing - limited requests allowed


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open."""
    pass


class CircuitBreaker:
    """
    Circuit Breaker implementation for fault tolerance.
    
    State Machine:
    CLOSED → OPEN: When failure count >= threshold
    OPEN → HALF_OPEN: After recovery timeout
    HALF_OPEN → CLOSED: On successful request
    HALF_OPEN → OPEN: On failed request
    
    Usage:
        breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)
        
        @breaker.protect
        def fetch_data():
            return yf.download(...)
        
        # Or manually:
        result = breaker.call(fetch_data)
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 1,
        name: str = "default"
    ):
        """
        Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before testing recovery
            half_open_max_calls: Max calls allowed in half-open state
            name: Breaker name for logging
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        
        self.name = name
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.last_success_time: Optional[float] = None
        self.half_open_calls = 0
        
        self._lock = threading.Lock()
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.
        
        Args:
            func: Function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Function result
            
        Raises:
            CircuitBreakerError: If circuit is open
        """
        with self._lock:
            if self.state == CircuitState.OPEN:
                # Check if recovery timeout has passed
                if self.last_failure_time is None:
                    raise CircuitBreakerError(
                        f"Circuit '{self.name}' is OPEN - no failure time recorded"
                    )
                
                time_since_failure = time.time() - self.last_failure_time
                if time_since_failure > self.recovery_timeout:
                    # Transition to half-open
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_calls = 0
                else:
                    # Still in recovery timeout
                    remaining = self.recovery_timeout - time_since_failure
                    raise CircuitBreakerError(
                        f"Circuit '{self.name}' is OPEN - retry in {remaining:.1f}s"
                    )
            
            # Allow call in CLOSED or HALF_OPEN state
            if self.state == CircuitState.HALF_OPEN:
                self.half_open_calls += 1
                if self.half_open_calls > self.half_open_max_calls:
                    raise CircuitBreakerError(
                        f"Circuit '{self.name}' HALF_OPEN - max calls ({self.half_open_max_calls}) exceeded"
                    )
        
        # Execute function outside lock
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception:
            self._on_failure()
            raise
    
    def _on_success(self):
        """Handle successful call."""
        with self._lock:
            self.success_count += 1
            self.last_success_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                # Recovery successful
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_calls = 0
            elif self.state == CircuitState.CLOSED:
                # The threshold counts CONSECUTIVE failures, not cumulative
                # ones. Without this reset the counter only ever grew, and
                # since the breaker is a process-lifetime singleton, five
                # unrelated transients spread over hours of successful calls
                # would trip it — the opposite of what a failure threshold is
                # meant to detect. A success means the service is up, so the
                # run of failures is over.
                self.failure_count = 0
        
        # Log success (import here to avoid circular dependency)
        try:
            from logger_config import console
            if self.state == CircuitState.CLOSED and self.success_count == 1:
                console.success(f"Circuit '{self.name}' CLOSED - service recovered")
        except Exception:
            pass
    
    def _on_failure(self):
        """Handle failed call."""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.state == CircuitState.HALF_OPEN:
                # Recovery failed - back to open
                self.state = CircuitState.OPEN
            elif self.state == CircuitState.CLOSED:
                # Check if threshold reached
                if self.failure_count >= self.failure_threshold:
                    self.state = CircuitState.OPEN
        
        # Log failure
        try:
            from logger_config import console
            if self.state == CircuitState.OPEN:
                console.error(
                    f"Circuit '{self.name}' OPEN - {self.failure_count} failures "
                    f"(threshold: {self.failure_threshold})"
                )
            elif self.state == CircuitState.HALF_OPEN:
                console.warning(f"Circuit '{self.name}' recovery failed - back to OPEN")
        except Exception:
            pass
    
    def protect(self, func: Callable) -> Callable:
        """
        Decorator for protecting functions.
        
        Usage:
            @breaker.protect
            def fetch_data():
                return yf.download(...)
        """
        @wraps(func)
        def wrapper(*args, **kwargs):
            return self.call(func, *args, **kwargs)
        return wrapper
    
    def get_state(self) -> dict:
        """Get current circuit state."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "last_failure": self.last_failure_time,
            "last_success": self.last_success_time
        }
    
    def reset(self):
        """Reset circuit breaker to initial state."""
        with self._lock:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            self.last_failure_time = None
            self.last_success_time = None
            self.half_open_calls = 0
        
        try:
            from logger_config import console
            console.success(f"Circuit '{self.name}' manually reset")
        except Exception:
            pass


class RetryWithBackoff:
    """
    Retry decorator with exponential backoff.
    
    Usage:
        @RetryWithBackoff(max_retries=3, backoff_factor=2)
        def fetch_data():
            return yf.download(...)
    """
    
    def __init__(
        self,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        exceptions: tuple = (Exception,)
    ):
        """
        Initialize retry decorator.
        
        Args:
            max_retries: Maximum retry attempts
            backoff_factor: Multiplier for delay (exponential)
            initial_delay: Initial delay in seconds
            max_delay: Maximum delay cap
            exceptions: Exception types to catch
        """
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exceptions = exceptions
    
    def __call__(self, func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            delay = self.initial_delay
            
            for attempt in range(self.max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except self.exceptions as e:
                    last_exception = e
                    
                    if attempt < self.max_retries:
                        # Log retry
                        try:
                            from logger_config import console
                            console.warning(
                                f"Attempt {attempt + 1}/{self.max_retries + 1} failed: {type(e).__name__}. "
                                f"Retrying in {delay:.1f}s..."
                            )
                        except Exception:
                            pass
                        
                        time.sleep(delay)
                        delay = min(delay * self.backoff_factor, self.max_delay)
                    else:
                        # All retries exhausted
                        try:
                            from logger_config import console
                            console.error(
                                f"All {self.max_retries + 1} attempts failed. Last error: {str(e)}"
                            )
                        except Exception:
                            pass
            
            raise last_exception
        return wrapper


# ══════════════════════════════════════════════════════════════════════════════
# GLOBAL CIRCUIT BREAKERS
# ══════════════════════════════════════════════════════════════════════════════

# yfinance API circuit breaker — used by backdata.py for fault-tolerant fetches
yfinance_circuit = CircuitBreaker(
    name="yfinance",
    failure_threshold=5,
    recovery_timeout=60.0,
)
