"""
PRAGYAM — Metrics & Observability Module
══════════════════════════════════════════════════════════════════════════════

Production-grade execution metrics tracking and performance monitoring.

Features:
- Phase-level timing tracking
- Resource utilization monitoring
- Error tracking and reporting
- Performance benchmarks
- Execution summary generation

Author: @thebullishvalue
"""

import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class PhaseMetrics:
    """Metrics for a single execution phase."""
    name: str
    start_time: float = 0.0
    end_time: float = 0.0
    duration: float = 0.0
    status: str = "pending"  # pending, running, success, error
    error_message: Optional[str] = None
    items_processed: int = 0
    memory_mb: float = 0.0
    
    def start(self):
        """Mark phase as started."""
        self.start_time = time.time()
        self.status = "running"
    
    def end(self, success: bool = True, error_msg: Optional[str] = None):
        """Mark phase as completed."""
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time
        self.status = "success" if success else "error"
        self.error_message = error_msg
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "duration_sec": round(self.duration, 3),
            "status": self.status,
            "items_processed": self.items_processed,
            "memory_mb": round(self.memory_mb, 2),
            "error": self.error_message
        }


@dataclass
class ExecutionMetrics:
    """
    Comprehensive execution metrics tracker.
    
    Usage:
        metrics = ExecutionMetrics()
        metrics.start_phase("data_fetching")
        # ... do work ...
        metrics.end_phase("data_fetching", success=True, items=50)
        
        # Get summary
        summary = metrics.to_dict()
    """
    
    # Metadata
    run_id: str = field(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S"))
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0
    
    # Phase tracking
    phases: Dict[str, PhaseMetrics] = field(default_factory=dict)
    current_phase: Optional[str] = None
    
    # Counters
    symbols_count: int = 0
    days_count: int = 0
    strategies_count: int = 0
    portfolios_generated: int = 0
    rebalances: int = 0
    
    # Performance
    total_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    
    # Errors
    errors: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    # Data quality — what the batch download missed and what the per-symbol
    # second pass got back (see backdata._recover_missing_symbols). Kept here
    # rather than logged and forgotten so the UI can state which symbols the
    # book was built WITHOUT.
    data_recovery: Dict[str, Any] = field(default_factory=dict)
    
    # System
    memory_peak_mb: float = 0.0
    cpu_percent: float = 0.0
    
    def start_phase(self, name: str):
        """Start tracking a phase."""
        if name in self.phases:
            self.warnings.append(f"Phase '{name}' already exists - overwriting")
        
        phase = PhaseMetrics(name=name)
        phase.start()
        self.phases[name] = phase
        self.current_phase = name
    
    def end_phase(self, name: str, success: bool = True, 
                  error_msg: Optional[str] = None,
                  items: int = 0):
        """End tracking a phase."""
        if name not in self.phases:
            raise ValueError(f"Phase '{name}' not started")
        
        phase = self.phases[name]
        phase.end(success=success, error_msg=error_msg)
        phase.items_processed = items
        self.current_phase = None
    
    def add_error(self, error_type: str, message: str, location: str = ""):
        """Record an error."""
        self.errors.append({
            "type": error_type,
            "message": message,
            "location": location,
            "timestamp": time.time()
        })
    
    def add_warning(self, message: str):
        """Record a warning."""
        self.warnings.append(message)
    
    def get_phase_duration(self, name: str) -> float:
        """Get duration of a specific phase."""
        if name not in self.phases:
            return 0.0
        return self.phases[name].duration
    
    def get_total_duration(self) -> float:
        """Get total execution time."""
        if self.end_time > 0:
            return self.end_time - self.start_time
        return time.time() - self.start_time
    
    def get_slowest_phases(self, n: int = 3) -> List[Dict[str, Any]]:
        """Get the N slowest phases."""
        sorted_phases = sorted(
            self.phases.values(),
            key=lambda p: p.duration,
            reverse=True
        )[:n]
        return [p.to_dict() for p in sorted_phases]
    
    def get_error_summary(self) -> Dict[str, int]:
        """Get error counts by type."""
        error_counts = {}
        for error in self.errors:
            error_type = error["type"]
            error_counts[error_type] = error_counts.get(error_type, 0) + 1
        return error_counts
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert all metrics to dictionary."""
        phase_summaries = {name: phase.to_dict() for name, phase in self.phases.items()}
        
        return {
            "run_id": self.run_id,
            "total_duration_sec": round(self.get_total_duration(), 3),
            "phases": phase_summaries,
            "slowest_phases": self.get_slowest_phases(),
            "counters": {
                "symbols": self.symbols_count,
                "days": self.days_count,
                "strategies": self.strategies_count,
                "portfolios": self.portfolios_generated,
                "rebalances": self.rebalances
            },
            "performance": {
                "total_return": round(self.total_return, 4),
                "sharpe_ratio": round(self.sharpe_ratio, 2),
                "max_drawdown": round(self.max_drawdown, 4)
            },
            "errors": {
                "count": len(self.errors),
                "by_type": self.get_error_summary()
            },
            "warnings_count": len(self.warnings),
            "data_recovery": {
                "missing": len(self.data_recovery.get("missing", [])),
                "recovered": len(self.data_recovery.get("recovered", [])),
                "failed": len(self.data_recovery.get("failed", [])),
            },
            "system": {
                "memory_peak_mb": round(self.memory_peak_mb, 2),
                "cpu_percent": round(self.cpu_percent, 1)
            }
        }
    
    def print_summary(self, console=None):
        """Print execution summary to console."""
        if console is None:
            from logger_config import console

        console.line()

        # Timing summary
        console.section("Timing")
        console.item("Total Duration", f"{self.get_total_duration():.2f}s")

        for phase_name, phase in self.phases.items():
            if phase_name == "total_execution":
                # Already reported as Total Duration above — repeating the
                # whole run inside its own phase breakdown double-counts it.
                continue
            status_icon = "✓" if phase.status == "success" else "✗"
            console.detail(f"{phase_name.replace('_', ' ').title()}: {phase.duration:.2f}s [{status_icon}]")

        # Counters
        console.section("Counters")
        console.item("Symbols", self.symbols_count)
        console.item("Days", self.days_count)
        console.item("Strategies", self.strategies_count)
        console.item("Portfolios Generated", self.portfolios_generated)
        if self.rebalances:
            # Backtest-only counter — printing "Rebalances: 0" on every live
            # curation run states a fact about a process that never ran.
            console.item("Rebalances", self.rebalances)
        
        # Performance
        if self.total_return != 0:
            console.section("Performance")
            console.item("Total Return", f"{self.total_return*100:.2f}%")
            console.item("Sharpe Ratio", f"{self.sharpe_ratio:.2f}")
            console.item("Max Drawdown", f"{self.max_drawdown*100:.2f}%")
        
        # Errors
        if self.errors:
            console.section("Errors")
            for error in self.errors[:5]:  # Show first 5
                console.error(f"[{error['type']}] {error['message']}")
            if len(self.errors) > 5:
                console.detail(f"... and {len(self.errors) - 5} more errors")
        
        # Warnings
        if self.warnings:
            console.section("Warnings")
            for warning in self.warnings[:5]:  # Show first 5
                console.warning(warning)
            if len(self.warnings) > 5:
                console.detail(f"... and {len(self.warnings) - 5} more warnings")
        
        console.line()


# Module-level fallback instance — used only when Streamlit's session state
# is unavailable (e.g. backdata.py's standalone CLI/script entry point,
# imports at module load time before a session exists). Under Streamlit,
# get_metrics() below returns a PER-SESSION tracker instead: Streamlit serves
# all connected users from one process, so a single shared module-level
# instance let two concurrent users interleave each other's phase timings,
# error lists, and run IDs (see AUDIT_DIRECTIVES.md B5).
metrics = ExecutionMetrics()


def get_metrics() -> ExecutionMetrics:
    """Get the execution metrics tracker for the current context.

    Under Streamlit, returns a tracker scoped to st.session_state so
    concurrent users/sessions never share or interleave metrics. Falls back
    to the module-level singleton when no Streamlit runtime is active (CLI
    usage, e.g. backdata.py run as a script).
    """
    try:
        import streamlit as st
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        if get_script_run_ctx() is not None:
            if "_pragyam_metrics" not in st.session_state:
                st.session_state["_pragyam_metrics"] = ExecutionMetrics()
            return st.session_state["_pragyam_metrics"]
    except Exception:
        pass
    return metrics


def track_phase(name: str):
    """
    Decorator for tracking function execution time.
    
    Usage:
        @track_phase("data_fetching")
        def fetch_data():
            # ... implementation ...
    """
    from functools import wraps
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            m = get_metrics()
            m.start_phase(name)
            try:
                result = func(*args, **kwargs)
                m.end_phase(name, success=True)
                return result
            except Exception as e:
                m.end_phase(name, success=False, error_msg=str(e))
                m.add_error(type(e).__name__, str(e), location=func.__name__)
                raise
        return wrapper
    return decorator
