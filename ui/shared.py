"""
PRAGYAM — Presentation helpers shared by the app shell and every tab.
प्रज्ञम् (Pragyam) — "Discernment / Wisdom"

The pieces of the UI layer that need to know something about the DOMAIN — how
a style is named, what an undefined figure looks like, which order the regime
factors are read in. They live here rather than in app.py because the tab
modules need them too, and a tab importing the shell it is rendered by is a
cycle waiting to happen.

Nothing here renders. Anything that emits markup belongs in ui/components.py.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from nco import METHOD_ORDER, METHOD_SPECS, method_spec

# Portfolio styles, derived from nco.METHOD_SPECS rather than hardcoded here.
# Every style travels the identical pipeline — same clustering diagnostics,
# same risk decomposition — so any difference on screen is the allocator and
# nothing else. Built from the registry so adding or retiring a style is a
# one-line change in nco.py.
NCO_STYLES = {str(METHOD_SPECS[k]["label"]): k for k in METHOD_ORDER}
STYLE_LABELS = list(NCO_STYLES.keys())

# The eight regime factors, in the order they are read: registry key, display
# name, and the key holding that factor's own verdict ("STRONG_UPTREND",
# "EXPANSION", …). Shared by the Regime tab and the run log so the terminal
# trace and the screen cannot drift into naming or ordering the same eight
# factors differently.
REGIME_FACTOR_ORDER = [
    ("momentum", "Momentum", "strength"),
    ("trend", "Trend", "quality"),
    ("breadth", "Breadth", "quality"),
    ("velocity", "Velocity", "acceleration"),
    ("extremes", "Extremes", "type"),
    ("volatility", "Volatility", "regime"),
    ("acceptance", "Acceptance", "state"),
    ("correlation", "Correlation", "regime"),
]


def style_spec(ctx_or_method) -> dict:
    """Registry record for a run context, a method code, or a style label."""
    if isinstance(ctx_or_method, dict):
        key = ctx_or_method.get("curation", "EQUAL")
    else:
        key = ctx_or_method
    key = NCO_STYLES.get(str(key), str(key))
    return method_spec(key)


def num(value) -> Optional[float]:
    """A finite float, or None — NaN and non-numeric both read as 'no value'.

    The allocator emits NaN wherever a figure is genuinely undefined (a holding
    with no covariance estimate, a book with no estimable covariance at all).
    Formatting those straight into an f-string prints "nan%", which reads as a
    broken number rather than an absent one, so every display path funnels
    through here and renders an em dash instead.
    """
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if np.isfinite(f) else None
