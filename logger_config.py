"""
PRAGYAM — Direct Console Output System
══════════════════════════════════════════════════════════════════════════════

Bypasses Python logging entirely - writes directly to stdout.
This is the ONLY way to get clean output in Streamlit.

Author: @thebullishvalue
"""

import sys
import time
import uuid
import os
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict

# ══════════════════════════════════════════════════════════════════════════════
# ENABLE ANSI ON WINDOWS - Using colorama for reliability
# ══════════════════════════════════════════════════════════════════════════════

try:
    import colorama
    colorama.init()
except ImportError:
    # Fallback for Windows without colorama
    if os.name == 'nt':
        from ctypes import windll, byref, c_ulong
        STD_OUTPUT_HANDLE = -11
        hConsole = windll.kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
        mode = c_ulong()
        windll.kernel32.GetConsoleMode(hConsole, byref(mode))
        mode.value |= 0x0004  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        windll.kernel32.SetConsoleMode(hConsole, mode)

# ── UTF-8 stdout on Windows ────────────────────────────────────────────────────
# Windows default console encoding (cp1252) cannot represent box-drawing
# characters (═, ─, →, ┌, │, └) used in the logger.  Reconfigure stdout
# to UTF-8 so these render correctly.  Falls back silently if reconfigure
# is unavailable (Python < 3.7) or stdout has been replaced by Streamlit.
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# ══════════════════════════════════════════════════════════════════════════════
# RUN IDENTIFIER - Session-level fallback
# ══════════════════════════════════════════════════════════════════════════════

_SESSION_RUN_ID = datetime.now().strftime('%Y%m%d_%H%M%S')
_SESSION_UUID = str(uuid.uuid4())[:8]
SESSION_RUN_IDENTIFIER = f"{_SESSION_RUN_ID}_{_SESSION_UUID}"

def generate_run_id() -> str:
    """Generate a unique Run ID for each analysis run."""
    run_id = datetime.now().strftime('%Y%m%d_%H%M%S')
    run_uuid = str(uuid.uuid4())[:8]
    return f"{run_id}_{run_uuid}"

def get_run_id() -> str:
    """Get the session-level run identifier (fallback only)."""
    return SESSION_RUN_IDENTIFIER


# ══════════════════════════════════════════════════════════════════════════════
# ANSI COLOR CODES - Windows Compatible
# ══════════════════════════════════════════════════════════════════════════════

class Colors:
    """ANSI color codes that work on Windows 10+."""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    
    # Colors
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GRAY = '\033[90m'
    
    # Symbols
    SUCCESS = '✓'
    WARNING = '⚠'
    ERROR = '✗'
    INFO = 'ℹ'


# ══════════════════════════════════════════════════════════════════════════════
# DIRECT CONSOLE OUTPUT - Bypasses Python logging
# ══════════════════════════════════════════════════════════════════════════════


# Column every line inside a step is written at, header included in the count:
# "  Step 1  Title" starts at 2, its contents sit one level in.
_STEP_COLUMN = 6


class StepHandle:
    """The live step yielded by ConsoleOutput.task.

    Carries the outcome so the closing line can state WHAT the step produced
    rather than only that it finished. Defaults to "ok / done", so a step that
    forgets to report still closes honestly rather than claiming a result.
    """

    def __init__(self, console: "ConsoleOutput"):
        self._console = console
        self.status = "ok"
        self.result = ""

    def detail(self, message: str):
        """A line of working detail, printed as it happens."""
        self._console.detail(message)

    def item(self, label: str, value: Any):
        """A labelled value inside the step."""
        self._console.item(label, value)

    def note(self, message: str):
        """A warning that does NOT change the step's outcome."""
        self._console._write(
            f"{' ' * self._console._indent(4)}"
            f"{Colors.YELLOW}{Colors.WARNING}{Colors.RESET} {message}")

    def ok(self, result: str):
        self.status, self.result = "ok", result

    def warn(self, result: str):
        self.status, self.result = "warn", result

    def fail(self, result: str):
        self.status, self.result = "fail", result


class ConsoleOutput:
    """Direct console output - no logging module."""
    
    def __init__(self):
        self._section_depth: int = 0
        self._step_num: int = 0
        # Depth of the enclosing `task` blocks. Every indent below is derived
        # from this rather than hard-coded, so a module that logs from inside a
        # step (backdata during a fetch, say) nests correctly without having to
        # know it is inside one — or having to pass an indent through three
        # call layers to find out.
        self._task_depth: int = 0

    def _indent(self, base: int) -> int:
        """Indent for a line, given its indent outside any step.

        Inside a step every line shares one column regardless of what printed it
        — an item, a detail, a warning raised three call layers down — so the
        step reads as a single block instead of a ragged edge. Outside a step the
        caller's own indent stands.
        """
        depth: int = self._task_depth
        if not depth:
            return base
        return _STEP_COLUMN + 2 * (depth - 1)
    
    def _write(self, message: str = '', end: str = '\n'):
        """Write directly to stdout, safe on narrow-encoding Windows consoles."""
        text = f"{message}{end}"
        try:
            sys.stdout.write(text)
        except (UnicodeEncodeError, UnicodeDecodeError):
            # Encode to UTF-8 bytes then decode with 'replace' so box-drawing
            # characters become '?' rather than raising on cp1252 consoles.
            safe = text.encode('utf-8', errors='replace').decode(
                sys.stdout.encoding or 'utf-8', errors='replace'
            )
            sys.stdout.write(safe)
        sys.stdout.flush()
    
    def _timestamp(self) -> str:
        """Get current timestamp."""
        return datetime.now().strftime('%H:%M:%S')
    
    def _run_id_short(self) -> str:
        """Get short run ID."""
        return SESSION_RUN_IDENTIFIER[-12:]

    def line(self, char: str = '─', length: int = 60):
        """Print a separator line."""
        self._write(f"{Colors.GRAY}{char * length}{Colors.RESET}")

    def header(self, title: str, version: str = ""):
        """Print run header."""
        self._write()
        self.line('═', 70)
        self._write(f"  {Colors.BOLD}{Colors.CYAN}{title} {version}{Colors.RESET}")
        self._write(f"  {Colors.GRAY}Run ID: {SESSION_RUN_IDENTIFIER}{Colors.RESET}")
        self._write(f"  {Colors.GRAY}Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.RESET}")
        self.line('═', 70)
        self._write()

    def main_header(self, title: str, details: Dict[str, Any]):
        """Print main run header with title and key details."""
        self.reset_steps()
        self._write()
        self.line('═', 70)
        self._write(f"  {Colors.BOLD}{Colors.CYAN}{title}{Colors.RESET}")
        self.line('─', 70)
        for key, value in details.items():
            self._write(f"  {Colors.GRAY}{key}:{Colors.RESET} {value}")
        self.line('═', 70)
        self._write()
    
    def section(self, title: str, phase: str = ""):
        """Print section header."""
        self._write()
        if phase:
            self.line('═', 60)
            self._write(f"  {Colors.BOLD}{Colors.BLUE}{phase}: {title}{Colors.RESET}")
            self.line('═', 60)
        else:
            self._write(f"{Colors.BOLD}{title}{Colors.RESET}")
            self._write(Colors.GRAY + '─' * len(title) + Colors.RESET)
        self._section_depth += 1
    
    def step(self, num: int, title: str):
        """Print numbered step."""
        self._write(f"  {Colors.BOLD}Step {num}:{Colors.RESET} {title}")
    
    def item(self, label: str, value: Any, indent: int = 4):
        """Print labeled item."""
        self._write(f"{' ' * self._indent(indent)}{Colors.GRAY}{label}:{Colors.RESET} {value}")
    
    def detail(self, message: str):
        """Print detailed information."""
        self._write(f"{' ' * self._indent(4)}{Colors.CYAN}→{Colors.RESET} {message}")
    
    def success(self, message: str):
        """Print success message."""
        self._write(f"{' ' * self._indent(2)}{Colors.GREEN}{Colors.SUCCESS} SUCCESS:{Colors.RESET} {message}")
    
    def warning(self, message: str):
        """Print warning message."""
        self._write(f"{' ' * self._indent(2)}{Colors.YELLOW}{Colors.WARNING} WARNING:{Colors.RESET} {message}")
    
    def error(self, message: str):
        """Print error message."""
        self._write(f"{' ' * self._indent(2)}{Colors.RED}{Colors.ERROR} ERROR:{Colors.RESET} {message}")
    
    def failure(self, step: str, error: str):
        """Print failure with context."""
        self._write(f"  {Colors.RED}{Colors.ERROR} FAILURE:{Colors.RESET} {step}")
        self._write(f"      {Colors.GRAY}Reason:{Colors.RESET} {error}")
    
    def issue(self, issue_type: str, location: str, description: str):
        """Flag an issue."""
        self._write(f"  {Colors.YELLOW}{Colors.WARNING} ISSUE [{issue_type}]{Colors.RESET} at {location}")
        self._write(f"      {Colors.GRAY}{description}{Colors.RESET}")
    
    def checkpoint(self, name: str, status: str = "OK"):
        """Print checkpoint."""
        symbol = Colors.GREEN + Colors.SUCCESS if status == "OK" else Colors.RED + Colors.ERROR
        self._write(f"  {symbol} Checkpoint:{Colors.RESET} {name} {Colors.GRAY}[{status}]{Colors.RESET}")
    

    def text(self, message: str = "", indent: int = 4):
        """Print a verbatim line — tracebacks, quoted output — undecorated."""
        self._write(f"{' ' * self._indent(indent)}{Colors.GRAY}{message}{Colors.RESET}")

    def info(self, message: str):
        """Print an informational message."""
        self._write(f"{' ' * self._indent(2)}{Colors.BLUE}{Colors.INFO} INFO:{Colors.RESET} {message}")

    # ── Steps ─────────────────────────────────────────────────────────────────
    # A run is a sequence of steps, and the terminal should read like that
    # sequence: what is starting, what it found while it worked, how it ended and
    # how long it took. `task` is the one entry point for that shape, so no
    # caller has to hand-format a step header or time itself.
    #
    # Numbering is automatic and continues across sections within a run
    # (`reset_steps` starts a new run), so a step that is skipped on one path
    # cannot leave a hole in the sequence or force a renumber in the code.

    def reset_steps(self):
        """Restart step numbering — called at the top of each run."""
        self._step_num = 0

    @contextmanager
    def task(self, title: str, detail: str = ""):
        """Run a step, printing its header, outcome and elapsed time.

            with console.task("Historical panel", "100-file lookback") as t:
                t.detail("cache MISS - downloading")
                t.ok(f"{len(rows)} trading days")

        The handle's `ok` / `warn` / `fail` set how the closing line reads. An
        uncaught exception closes the step as a failure and propagates, so a
        crashed step can never be reported as a completed one.
        """
        self._step_num += 1
        num = self._step_num
        # Printed before the depth is incremented, so a nested step's header
        # lands in its parent's content column.
        head = (f"{' ' * self._indent(2)}{Colors.BOLD}Step {num}{Colors.RESET}"
                f"  {Colors.BOLD}{title}{Colors.RESET}")
        if detail:
            head += f"  {Colors.GRAY}{detail}{Colors.RESET}"
        self._write(head)
        handle = StepHandle(self)
        started = time.perf_counter()
        self._task_depth += 1
        try:
            yield handle
        except BaseException as exc:
            # Streamlit ends a script by RAISING (st.stop, st.rerun). Those are
            # control flow, not failures, and marking them with a red cross would
            # put one under every deliberate early exit.
            if type(exc).__name__ in ("StopException", "RerunException"):
                self._task_depth -= 1
                raise
            # Written BEFORE the depth is unwound, so the closing line sits in
            # the same column as the step's own lines rather than the caller's.
            self._write(
                f"{' ' * self._indent(4)}{Colors.RED}{Colors.ERROR}{Colors.RESET} "
                f"{type(exc).__name__}: {exc}"
                f"  {Colors.GRAY}({self._elapsed(started)}){Colors.RESET}"
            )
            self._task_depth -= 1
            raise
        colour, symbol = {
            "ok": (Colors.GREEN, Colors.SUCCESS),
            "warn": (Colors.YELLOW, Colors.WARNING),
            "fail": (Colors.RED, Colors.ERROR),
        }[handle.status]
        self._write(
            f"{' ' * self._indent(4)}{colour}{symbol}{Colors.RESET} "
            f"{handle.result or 'done'}"
            f"  {Colors.GRAY}({self._elapsed(started)}){Colors.RESET}"
        )
        self._task_depth -= 1

    @staticmethod
    def _elapsed(started: float) -> str:
        """Elapsed time in the unit that makes it readable at a glance."""
        secs = time.perf_counter() - started
        return f"{secs*1000:.0f}ms" if secs < 1.0 else f"{secs:.2f}s"

    def summary(self, title: str, data: Dict[str, Any]):
        """Print summary box."""
        self._write()
        self._write(f"  {Colors.GRAY}┌─ {title}{Colors.RESET}")
        for key, value in data.items():
            self._write(f"  {Colors.GRAY}│   {key}:{Colors.RESET} {value}")
        self._write(f"  {Colors.GRAY}└─{Colors.RESET}")


# ══════════════════════════════════════════════════════════════════════════════
# GLOBAL INSTANCE
# ══════════════════════════════════════════════════════════════════════════════

# Single global instance
console = ConsoleOutput()


def get_console() -> ConsoleOutput:
    """Get the global console instance."""
    return console
