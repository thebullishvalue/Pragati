"""
PRAGYAM — Eight-factor market regime, as context and never as an instruction.

Nothing downstream is conditioned on the regime. It is here so a reader can
see what kind of market the book was curated into, not so the book changes.

Author: @thebullishvalue
"""

from __future__ import annotations

import html as html_module
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st

from ui.components import (
    panel,
    render_chart_panel,
    render_empty_state,
    render_kpi_strip,
    render_note,
    render_section_header,
)
from ui.shared import NCO_STYLES, REGIME_FACTOR_ORDER, STYLE_LABELS, num, style_spec
from regime import FACTOR_WEIGHTS, get_regime_history_series

# Charts are optional: a missing plotly must degrade this tab to its tables
# and readouts rather than take the whole app down on import.
try:
    from charts import (create_regime_history_chart)
    CHARTS_AVAILABLE = True
except ImportError:                                     # pragma: no cover
    CHARTS_AVAILABLE = False


def _render_regime_tab(regime_result: Dict, regime_series: List, training_data: Optional[List] = None):
    """Tab 2 — Market regime analysis."""
    if not regime_result:
        render_empty_state(
            "No regime reading",
            "The eight-factor composite is computed as part of a run. It is context "
            "for reading the book — nothing in the curation is conditioned on it.",
            action_label="Run Analysis in the rail",
        )
        return

    regime_name = regime_result.get("regime", "UNKNOWN")
    mix_name = regime_result.get("mix_name", "—")
    confidence = regime_result.get("confidence", 0.0)
    score = regime_result.get("composite_score", 0.0)
    color = regime_result.get("color", "#888888")
    icon_key = regime_result.get("icon", "help-circle")
    factors_raw = regime_result.get("factors", {})

    # Current Regime Banner
    render_section_header("Current Reading", "Eight factors over a 10-day window", icon="eye")

    # NOTE: the badge + factor scores are rendered as ONE self-contained HTML flex
    # row (not st.columns), so vertical centring is under our control — Streamlit's
    # column wrappers made the badge impossible to centre reliably. The flex row's
    # `align-items:center` centres the badge card against the factor list, period.

    # The regime detector uses FIXED factor weights (not calibrated); display them
    # so the percentages match what the composite actually used.
    _fw = FACTOR_WEIGHTS
    factor_order = REGIME_FACTOR_ORDER
    # Each factor score is a SIGNED value in [-2, +2] (bearish ↔ bullish), rendered
    # as a CENTER-ANCHORED diverging bar: a zero line in the middle, the fill
    # growing RIGHT (emerald) for a positive score or LEFT (rose) for a negative
    # one, with magnitude = |score| / 2. A 0→100% fill would misread a signed value.
    _rows = []
    for fkey, fbase, label_key in factor_order:
        fd = factors_raw.get(fkey, {})
        fs = float(fd.get("score", 0.0))
        fl = str(fd.get(label_key, "—")).replace("_", " ").lower()
        _wpct = _fw.get(fkey)
        fname = f"{fbase} ({_wpct*100:.0f}%)" if _wpct is not None else fbase
        # |score| / 2 of the half-track. A factor at the extreme fills its side
        # exactly, never past the zero rule.
        half = min(50.0, abs(fs) / 2.0 * 50.0)
        tone = "pos" if fs > 0.05 else "neg" if fs < -0.05 else "flat"
        fill = (f'<i class="{tone}" style="width:{half:.1f}%"></i>'
                if tone != "flat" else "")
        _rows.append(
            f'<div class="factor-row">'
            f'<div class="factor-head">'
            f'<span class="factor-name">{html_module.escape(fname)}</span>'
            f'<span class="factor-verdict">{html_module.escape(fl)}'
            f'<span class="factor-score {tone}">{fs:+.1f}</span></span>'
            f'</div>'
            f'<div class="factor-track">{fill}</div>'
            f'</div>'
        )
    _factors_html = "".join(_rows)

    # THE REGIME IN THE APP'S OWN GRAMMAR.
    #
    # This was a bespoke component — `render_regime_badge`, a tinted readout
    # with its own class family — for a reading the rest of the product would
    # have expressed as numbers in a KPI strip. It was the only place in the
    # app where four headline figures were drawn by a component that existed
    # nowhere else, which is precisely the thing this design system is for.
    #
    # Now: a KPI strip for the reading, a panel for its inputs, a note for what
    # it means. Identical anatomy to the Holdings page, the Performance page
    # and the landing — the regime stops being a special case and starts being
    # a page.
    _regime_tone = {
        "STRONG_BULL": "success", "BULL": "success", "WEAK_BULL": "success",
        "CHOP": "neutral", "UNKNOWN": "neutral",
        "WEAK_BEAR": "warning", "BEAR": "danger", "CRISIS": "danger",
    }.get(regime_name.upper().replace("-", "_"), "neutral")
    render_kpi_strip([
        {"label": "Regime", "value": regime_name.replace("_", " "),
         "subtext": mix_name, "color_class": _regime_tone, "icon": icon_key},
        {"label": "Composite Score", "value": f"{float(score):+.2f}",
         "subtext": "Weighted sum of eight factors · −2 to +2",
         "color_class": "neutral"},
        {"label": "Confidence", "value": f"{float(confidence):.0%}",
         "subtext": "Agreement across the eight",
         "color_class": "info" if confidence >= 0.6 else "warning"},
        {"label": "Window", "value": "10d",
         "subtext": "Trailing indicator window", "color_class": "neutral"},
    ], max_cols=4, key="regime-current")

    # The eight inputs, inside the same panel chrome every other data surface
    # in the app uses — header stating what it is, body carrying the data.
    with panel("regime-factors", context="8 factors · fixed weights · −2 to +2"):
        st.markdown(
            f'<div class="factor-block">'
            f'<div class="factor-scale">'
            f'<span>−2 Bearish</span><span>0 Neutral</span><span>+2 Bullish</span></div>'
            f'{_factors_html}'
            f'</div>',
            unsafe_allow_html=True,
        )
    render_note(
        "Each bar is one factor's signed contribution, drawn from the centre so the "
        "**side** carries the direction and the **length** carries the strength. The "
        "percentage after each name is the weight it takes into the composite above — "
        "**fixed**, never calibrated, so the same conditions always produce the same "
        "reading. Nothing downstream is conditioned on any of it: the regime is context "
        "for reading the book, not an input to it."
    )

    # ── Full-width METHOD card (Obsidian Quant fidelity) — mirrors the
    #    Intelligence tab's method card: header + pill + lede + tile grid.
    method_html = (
        '<div class="intel-method-card">'
            '<div class="intel-method-header">'
                '<div class="intel-method-title">How the Regime Is Read</div>'
                '<div class="intel-method-pill">'
                '8-factor composite · fixed weights'
                '</div>'
            '</div>'
            '<div class="intel-method-lede">'
                'The market regime is a <strong>weighted composite</strong> of eight measured '
                'factors, each scored on a signed <code>[-2, +2]</code> scale (bearish ↔ bullish). '
                'The weighted sum places the market on the regime hierarchy from '
                '<strong>Strong Bull</strong> down to <strong>Crisis</strong>. The eight factor '
                'weights are <strong>fixed</strong> (regime.FACTOR_WEIGHTS) regardless of mode — '
                'the regime detector is not calibrated. Only the four-signal '
                'regime read is <strong>context only</strong> — the allocator is not conditioned on it.'
            '</div>'
            '<div class="intel-method-grid">'

                '<div class="intel-method-tile">'
                    '<div class="tile-label">Momentum &amp; Trend</div>'
                    '<div class="tile-body">'
                        'RSI trajectory, oscillator direction, price/MA alignment and the share of '
                        'names above their 200-DMA — the primary directional drivers (largest weights).'
                    '</div>'
                '</div>'

                '<div class="intel-method-tile">'
                    '<div class="tile-label">Breadth &amp; Velocity</div>'
                    '<div class="tile-body">'
                        'Cross-sectional participation and the first/second derivative of momentum '
                        '(is the move accelerating or decaying) — confirmation and turning-point cues.'
                    '</div>'
                '</div>'

                '<div class="intel-method-tile">'
                    '<div class="tile-label">Extremes, Volatility &amp; Acceptance</div>'
                    '<div class="tile-body">'
                        'Z-score crowding, Bollinger band-width regime, and the volume-profile '
                        'value distribution (discount vs premium) — stress and mean-reversion context.'
                    '</div>'
                '</div>'

                '<div class="intel-method-tile">'
                    '<div class="tile-label">Reading the bars</div>'
                    '<div class="tile-body">'
                        'Each factor bar is <strong>centre-anchored</strong>: it grows right (green) '
                        'when bullish, left (red) when bearish, from a zero line — the magnitude is '
                        'how far the factor leans, not a simple fill.'
                    '</div>'
                '</div>'

            '</div>'
        '</div>'
    )
    st.markdown(method_html, unsafe_allow_html=True)

    # Regime History
    regime_series_to_use = regime_series
    if regime_series_to_use is None and training_data and len(training_data) >= 10:
        with st.spinner("Computing regime history…"):
            regime_series_to_use = get_regime_history_series(training_data, window_size=10, step=1)
        st.session_state.regime_history_series = regime_series_to_use

    if regime_series_to_use and len(regime_series_to_use) > 0:
        render_section_header("Score History", "Composite over rolling 10-day windows",
                              icon="activity", accent="emerald")

        regimes_seq = [r.regime for r in regime_series_to_use]
        transitions = sum(1 for i in range(1, len(regimes_seq)) if regimes_seq[i] != regimes_seq[i-1])
        # The chart and the cards share the same underlying panel as the sidebar
        # regime card (see _detect_regime_cached + _load_historical_data), so the
        # last bar of the chart is the canonical regime by construction.
        last_regime = regimes_seq[-1] if regimes_seq else "—"
        prev_regime = regimes_seq[-2] if len(regimes_seq) > 1 else "—"

        if CHARTS_AVAILABLE:
            fig_rh = create_regime_history_chart(regime_series_to_use)
            render_chart_panel(fig_rh, "regime-history",
                               context="rolling 10-day windows · composite score")
            render_note(
                "The composite score blends eight factors with **fixed** weights, so the same "
                "market conditions always produce the same reading. The shaded band is "
                "confidence: wider means the factors disagree. This is **context only** — the "
                "portfolio is curated from the return covariance and is not conditioned on the "
                "regime, so a bearish reading does not move a single weight."
            )

        # Map regime names to semantic metric card colors
        def regime_color(regime: str) -> str:
            r = regime.upper().replace("-", "_")
            if r in ("STRONG_BULL", "BULL", "WEAK_BULL"):
                return "success"
            elif r in ("BEAR", "CRISIS"):
                return "danger"
            elif r == "WEAK_BEAR":
                return "warning"
            elif r in ("CHOP", "UNKNOWN"):
                return "info"
            return "neutral"

        render_kpi_strip([
            {"label": "Transitions", "value": str(transitions),
             "subtext": "Over the analysis window", "color_class": "info"},
            {"label": "Current", "value": last_regime.replace("_", " "),
             "subtext": "Latest reading", "color_class": regime_color(last_regime)},
            {"label": "Prior", "value": prev_regime.replace("_", " "),
             "subtext": "Previous reading", "color_class": regime_color(prev_regime)},
        ], max_cols=3, key="regime-history-kpi")
