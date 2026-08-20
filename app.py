"""
PRAGYAM — Portfolio Intelligence (Streamlit App)
══════════════════════════════════════════════════════════════════════════════

Covariance-based portfolio curation over a fixed ETF universe.

Architecture:
  nco.py            → HRP / Equal Weight curation (selection AND weighting)
  regime.py         → MarketRegimeDetector (fixed 8-factor) — context only
  backdata.py       → generate_historical_data(), compute_volume_profile()
  analytics.py      → portfolio-vs-benchmark performance metrics
  charts.py         → Plotly chart builders
  universe.py       → universe resolution

What this system does NOT do, and why
─────────────────────────────────────
It carries no conviction score, no strategy library and no weight calibration.
All three were removed after measurement, not preference:

  · the conviction blend had no cross-sectional predictive power on this
    universe (IC ~0.00-0.04, sign unstable across horizons);
  · the 95-strategy library was 97.2% self-correlated — an effective count of
    1.03 independent strategies out of 92, because long-only baskets of assets
    that are themselves 52% correlated cannot decorrelate;
  · per-regime weight calibration could not clear its own significance gate.

Grinold's Fundamental Law bounds excess return from FORECASTING at
IR = IC x sqrt(BR) x TC — roughly 1%/yr here, since 30 ETFs at rho 0.517 are
only ~1.9 effective independent bets. Rather than keep chasing that bound, the
system allocates from the covariance structure, which is estimable where
expected returns are not. It targets RISK, and is honest that it does not
deliver excess return: measured across two disjoint periods, HRP gives up
~1%/yr against equal weight and buys a ~20% cut in volatility and drawdown.

Pipeline:
  Phase 1: Data fetching + regime detection (context)
  Phase 2: Covariance curation (HRP or Equal Weight)

Result tabs: Portfolio (holdings + risk profile + cluster structure) ·
Analytics (book vs benchmark vs equal-weight shadow) · Regime ·
Broker Sync (curated units → broker JSONs) · System.

Author: @thebullishvalue
"""

import streamlit as st
import pandas as pd
import numpy as np
import warnings
from datetime import datetime, date, timedelta, timezone
from typing import List, Dict, Tuple, Optional, Any

# Suppress warnings
warnings.filterwarnings("ignore", category=RuntimeWarning)

import html as html_module

# ── Imports ────────────────────────────────────────────────────────────────────
from logger_config import get_console
log = get_console()

from metrics import get_metrics
from ui.theme import inject_css, VERSION, PRODUCT_NAME, COMPANY, progress_bar
from ui.shared import NCO_STYLES, REGIME_FACTOR_ORDER, STYLE_LABELS, num, style_spec
from ui.tabs import (
    render_analytics_tab,
    render_broker_sync_tab,
    render_portfolio_tab,
    render_regime_tab,
    render_system_tab,
)
from ui.components import (
    panel,
    render_empty_state,
    render_header,
    render_kpi_strip,
    render_nav_brand,
    render_notice_rail,
    render_rail_readout,
    render_section_header,
    render_ticker,
    render_top_bar,
    render_warning_box,
)
import streamlit.components.v1 as components
from regime import (
    MarketRegimeDetector,
    REGIME_COLORS,
    FACTOR_WEIGHTS,
    get_regime_history_series,
)
from backdata import (
    generate_historical_data,
    get_default_universe,
    MAX_INDICATOR_PERIOD,
)
from universe import (
    resolve_universe,
    render_universe_selector,
)
from nco import (compute_nco_portfolio, METHOD_SPECS, METHOD_ORDER, method_spec,
                 MIN_COVERAGE, MOMENTUM_LOOKBACK, MOMENTUM_SKIP)

try:
    from charts import (
        COLORS,
        create_risk_allocation_heatmap,
        create_risk_contribution_chart,
        create_cluster_correlation_heatmap,
        create_regime_history_chart,
    )
    CHARTS_AVAILABLE = True
except ImportError:
    CHARTS_AVAILABLE = False
    COLORS = {
        "primary": "#FFC300",
        "success": "#10b981",
        "danger": "#ef4444",
        "warning": "#f59e0b",
        "info": "#06b6d4",
        "muted": "#888888",
        "card": "#1A1A1A",
        "border": "#2A2A2A",
        "text": "#EAEAEA",
    }


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

# VERSION / PRODUCT_NAME / COMPANY are imported from ui.theme above — that is
# the single source of truth. They were previously redefined here, so the
# version could drift between the footer and the System tab.
st.set_page_config(
    page_title="PRAGYAM | Portfolio Intelligence",
    page_icon="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI+PGNpcmNsZSBjeD0iMTIiIGN5PSIxMiIgcj0iMTAiIGZpbGw9Im5vbmUiIHN0cm9rZT0iIzRDN0RGMCIgc3Ryb2tlLXdpZHRoPSIyIi8+PHBhdGggZD0iTTggMTRsMy01IDIgMyAzLTQiIGZpbGw9Im5vbmUiIHN0cm9rZT0iIzRDN0RGMCIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiLz48L3N2Zz4=",
    layout="wide",
    # Start EXPANDED: the landing page explicitly instructs "Configure via
    # the Sidebar", so a first-time visitor should see the sidebar controls
    # immediately rather than discover they're collapsed (see
    # AUDIT_DIRECTIVES.md C5.5).
    initial_sidebar_state="expanded",
)

#: The two appearances. Both are reading surfaces — Paper is the light one you
#: read a result on and print from, Slate the dark one you work on.
#:
#: PAPER LEADS, and the order is the default: `theme_choice()` falls back to
#: APPEARANCES[0] for any unset or unrecognised value, so first-in-tuple IS
#: first-run. Kept as one fact rather than a separate DEFAULT_ constant, so the
#: toggle's left-to-right order and the default can never disagree.
#:
#: Two other places track this and must be flipped with it — both are asserted
#: by the audit in theme.py's docstring rather than left to memory:
#:   * `.streamlit/config.toml` sets the colour of the FIRST PAINT, before this
#:     app's stylesheet arrives. Pointing it at the other ramp ships a flash of
#:     the wrong theme on every cold load.
#:   * `ui.theme._active_theme()` falls back for callers that reach the palette
#:     without a session (the headless render tests), and a fallback that
#:     disagrees with the product default is a second default.
APPEARANCES = ("Paper", "Slate")
_THEME_CHOICE = "theme_choice"


def theme_choice() -> str:
    """The appearance the user last chose, always one of ``APPEARANCES``.

    A value that is not in the list is treated as unset. That matters across a
    rename: a session opened before this list changed still holds the old
    string in the durable key, and handing an unknown option to the segmented
    control as its default is an error rather than a fallback.
    """
    choice = st.session_state.get(_THEME_CHOICE)
    return choice if choice in APPEARANCES else APPEARANCES[0]


# Resolve the theme BEFORE anything is styled, and read the DURABLE choice
# rather than the widget key — the widget's state is discarded by Streamlit on
# any run that does not reach it. Deriving it here, first, makes the whole
# script agree on one value for the whole run: chrome, charts and tables all
# resolve their palette from st.session_state["theme"], and a page whose CSS
# and whose plots disagree about the theme is exactly what "some elements show
# up, some do not" looks like.
st.session_state["theme"] = "light" if theme_choice() == "Paper" else "dark"
inject_css(theme=st.session_state["theme"])


# ══════════════════════════════════════════════════════════════════════════════
# SESSION STATE
# ══════════════════════════════════════════════════════════════════════════════

def _init_session_state():
    """Initialize session state with defaults."""
    defaults = {
        "portfolio": None,
        "current_df": None,
        "selected_date": None,
        "regime_result_dict": None,
        "training_data_window": None,
        "regime_history_series": None,
        "min_pos_pct": 0.01,
        "max_pos_pct": 0.10,
        # Effective bounds actually applied by the last curation run (may
        # differ from the nominal min/max_pos_pct above when num_positions
        "min_pos_pct_eff": 0.01,
        "max_pos_pct_eff": 0.10,
        "selected_universe": None,
        "selected_index": None,
        # Frozen (universe, index, regime, mode, anchor_date) the CURRENT
        # portfolio was curated under — see _intel_context()'s docstring.
        "run_context": None,
        "debug_info": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# ══════════════════════════════════════════════════════════════════════════════
# CACHED DATA FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

# Counts how many times the cached fetch below actually EXECUTED. Streamlit
# exposes no hit/miss signal, and inferring one from elapsed time is a guess; a
# caller that reads this counter either side of the call knows for certain
# whether it paid for a download or reused the session's panel. That distinction
# is the difference between a 12-second step and a 12-millisecond one, and the
# terminal should say which happened rather than leave it to be inferred.
_PANEL_FETCHES = {"n": 0}


def _panel_fetch_count() -> int:
    """How many historical-panel downloads have run in this session."""
    return _PANEL_FETCHES["n"]


def _log_recovery(step, previous) -> None:
    """Report a re-fetch on the step that triggered it.

    `metrics.data_recovery` holds the LAST report, and a run fetches two panels
    (regime and estimation), so identity against the report seen before the call
    is what says whether THIS step re-fetched anything.
    """
    report = getattr(get_metrics(), "data_recovery", None) or {}
    if report is previous or not report.get("missing"):
        return
    step.item("Missing from batch", ", ".join(report["missing"]))
    if report.get("recovered"):
        step.item("Recovered on re-fetch", ", ".join(report["recovered"]))
    if report.get("failed"):
        step.note(f"{len(report['failed'])} symbol(s) still unavailable and dropped "
                  f"from the universe: {', '.join(report['failed'])}")
    if report.get("skipped_reason"):
        step.note(f"second pass skipped ({report['skipped_reason']})")


@st.cache_data(ttl=3600, show_spinner=False)
def _load_historical_data(end_date: datetime, lookback_files: int, symbols_key: str) -> List[Tuple[datetime, pd.DataFrame]]:
    """Fetch and cache historical indicator snapshots from yfinance."""
    _PANEL_FETCHES["n"] += 1
    # Announced here rather than by the caller: reaching this line IS the cache
    # miss, and saying so before the download starts puts the explanation above
    # the work instead of after it.
    log.detail(f"cache MISS — fetching the {lookback_files}-day panel from yfinance")
    # Resolve symbols from the cache key
    try:
        if symbols_key.startswith("UNIVERSE:"):
            universe_name, index = symbols_key.replace("UNIVERSE:", "", 1).split("|", 1)
            index = index if index != "None" else None
            symbols_list, _ = resolve_universe(universe_name, index)
        else:
            symbols_list = get_default_universe()
        
        if not symbols_list:
            raise ValueError("No symbols found in the selected universe.")
    except Exception as e:
        log.error(f"Universe resolution failed inside the panel fetch: {e}")
        st.error(f"Error resolving universe: {e}")
        return []
    
    try:
        return generate_historical_data(
            symbols_to_process=symbols_list,
            start_date=end_date - timedelta(days=int((lookback_files + MAX_INDICATOR_PERIOD) * 1.5) + 30),
            end_date=end_date,
        )
    except Exception as e:
        # Logged as well as surfaced: the browser message disappears on the next
        # rerun, and this is the failure a terminal trace most needs to retain.
        log.error(f"Data fetch failed ({type(e).__name__}): {e}")
        st.error(f"Data fetch failed: {e}")
        return []


# Single LOOKBACK used by both the regime detection cache and the main-flow
# fetch — so the regime card, the Phase 2 curation, and the Regime Score
# History chart all reason about the same historical panel.
_REGIME_LOOKBACK_FILES = 100

# Estimation panel used ONLY by Phase 1.5 calibration — sized from the
# statistics, not from the display. The paired beats-default gate needs
# MIN_PAIRED_VAL_DATES (=8) non-overlapping validation dates at horizon 10
# under a 50/50 split, i.e. >= intelligence.min_calibration_dates() = 142
# usable dates INSIDE the target regime family. The regime family typically
# covers only a fraction of any trailing window, so the window must be a
# multiple of that: at a ~40% family share, 142 / 0.4 + horizon ≈ 365 → 375
# trading days (~18 months). The 100-day _REGIME_LOOKBACK_FILES panel was
# structurally incapable of EVER calibrating: 90 harvest dates → 45
# validation dates → at most 5 non-overlapping paired dates < 8, so every
# run failed the gate before a single Optuna trial ran. Kept separate from
# _REGIME_LOOKBACK_FILES so the regime card / chart / curation stay on the
# fast 100-day panel; this longer panel is fetched (and cached for the
# session) only when a run actually needs it.
_CALIBRATION_LOOKBACK_FILES = 375

# Portfolio styles, derived from nco.METHOD_SPECS rather than hardcoded here.
# Every style travels the identical pipeline — same eligibility filter, same
# clustering diagnostics, same risk decomposition — so any difference on screen
# is the allocator and nothing else.
#
# Built from the registry so adding or retiring a style is a one-line change in
# nco.py. The previous hardcoded dict had to be kept in sync with six other
# `curation == "EQUAL"` checks scattered through this file; those are now all
# registry lookups.
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


def num(value) -> Optional[float]:
    """A finite float, or None — NaN and non-numeric both read as 'no value'.

    The allocator now emits NaN wherever a figure is genuinely undefined (a
    holding with no covariance estimate, a book with no estimable covariance at
    all). Formatting those straight into an f-string prints "nan%", which reads
    as a broken number rather than an absent one, so every display path funnels
    through here and renders an em dash instead.
    """
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if np.isfinite(f) else None


def style_spec(ctx_or_method) -> dict:
    """Registry record for a run context, a method code, or a style label."""
    if isinstance(ctx_or_method, dict):
        key = ctx_or_method.get("curation", "EQUAL")
    else:
        key = ctx_or_method
    key = NCO_STYLES.get(str(key), str(key))
    return method_spec(key)


@st.cache_data(ttl=3600, show_spinner=False)
def _detect_regime_cached(end_date: datetime, symbols_key: str) -> Dict:
    """Detect market regime from the SAME cached panel the main flow uses.

    Reads `_load_historical_data(end_date, _REGIME_LOOKBACK_FILES, symbols_key)`
    so the trailing 10 days the detector consumes are identical to the trailing
    10 days the Regime Score History chart's last bucket consumes. This makes
    the sidebar card, the result page's regime banner, and the chart's last
    bar three views of the SAME computation on the SAME data.
    """
    try:
        hist = _load_historical_data(end_date, _REGIME_LOOKBACK_FILES, symbols_key)
    except Exception as e:
        return {
            "regime": "UNKNOWN",
            "mix_name": "Chop/Consolidate Mix",
            "confidence": 0.30,
            "composite_score": 0.0,
            "explanation": f"Data fetch error: {e}",
            "color": "#6b7280",
            "icon": "help-circle",
            "description": "",
        }

    if not hist or len(hist) < 5:
        return {
            "regime": "UNKNOWN",
            "mix_name": "Chop/Consolidate Mix",
            "confidence": 0.30,
            "composite_score": 0.0,
            "explanation": "Insufficient data for regime classification.",
            "color": REGIME_COLORS["UNKNOWN"],
            "icon": "help-circle",
            "description": "",
        }

    try:
        result = MarketRegimeDetector().detect(hist, analysis_date=end_date)
        return result.to_dict()
    except Exception as e:
        return {
            "regime": "UNKNOWN",
            "mix_name": "Chop/Consolidate Mix",
            "confidence": 0.30,
            "composite_score": 0.0,
            "explanation": f"Regime detection error: {e}",
            "color": "#6b7280",
            "icon": "help-circle",
            "description": "",
        }




# ══════════════════════════════════════════════════════════════════════════════
# TAB RENDERERS
# ══════════════════════════════════════════════════════════════════════════════













def _render_header() -> None:
    """Render the main masthead header."""
    render_header(
        title=f"{PRODUCT_NAME}",
        tagline="Covariance-Based Portfolio Curation · Equal Weight · ERC · HRP · Live NSE Data"
    )


#: The three systems, as the cold-start screen describes them. Data, not
#: markup — the landing page renders them through one template, so the three
#: panels cannot drift apart in structure the way three hand-written HTML
#: blocks did.
_SYSTEM_PANELS = (
    ("portfolio", "PORTFOLIO", "Covariance curation",
     "Capital is allocated from the return covariance. Nothing forecasts a return — "
     "the book spreads risk across distinct exposures rather than picking winners.",
     (("Cluster", "Ward on correlation distance"),
      ("Allocate", "1/N · equal risk · cluster bisection"),
      ("Targets", "Volatility and drawdown"))),
    ("regime", "REGIME", "Eight-factor context",
     "A fixed-weight composite of eight measured factors over a rolling window. "
     "Context for reading the book — no weight changes because of it.",
     (("Factors", "Momentum · trend · breadth · velocity"),
      ("Output", "Score and confidence"),
      ("History", "Rolling-window timeline"))),
    ("structure", "RISK STRUCTURE", "What the allocator saw",
     "The correlation matrix reordered by cluster, so the blocks driving the "
     "allocation are visible — with each holding's variance share against its capital.",
     (("Clusters", "Silhouette-selected"),
      ("Per holding", "Weight · risk · vol · independence"),
      ("Benchmark", "Equal-weight shadow book"))),
)


def _render_landing_page() -> None:
    """Cold start — a description of the product, built from the product's own parts.

    Every block here uses the same components the analysis pages use: a section
    header for each division, `panel()` for each engine, and `render_kpi_strip`
    for the scope numbers.

    The order is an argument, and it runs from the thing to its bounds to its
    product: the claim, then ENGINES (what the system is made of), then INPUTS
    & SCOPE (the bounds those engines run under), then RUN OUTPUTS (what comes
    back). Scope led once, which put the answer to "over what?" in front of any
    reason to ask it.
    """
    # THE CLAIM SAYS WHAT THE PRODUCT DOES.
    #
    # It used to read "Selection and weighting both come from the return
    # covariance structure, and no part of the system forecasts a return" —
    # which is a disclaimer, not a description. It led with an absence, so the
    # first sentence of the product described something the product is not.
    #
    # It was also not true of all three styles: Equal Weight is deliberately no
    # longer confined to the covariance-eligible names (see
    # nco.compute_nco_portfolio), so neither its selection nor its weighting
    # comes from the covariance at all.
    #
    # What IS true of every style, and is the actual product: it measures how
    # the holdings move together, and it puts each holding's share of variance
    # next to its share of capital. The non-forecasting thesis is not lost —
    # the PORTFOLIO panel below states it, and the Coverage strip and the
    # Targets row both carry it — it just stops being the opening line.
    st.markdown(
        """<div class="lede">
  <div class="lede-claim">The system curates a book by measuring how its holdings move
    together, then shows what each one contributes to risk against what it costs
    in capital.</div>
  <div class="lede-cta">Pick a date, a universe and a style in the rail, then
    <strong>Run Analysis</strong>.</div>
</div>""",
        unsafe_allow_html=True,
    )

    # ── Engines — what the thing is, before what it is bounded by ─────────
    # This section leads. The reader has just been told what the system does;
    # the next thing they need is what it is MADE of, not the numbers those
    # parts are bounded by. Scope answers a question — "over what?" — that
    # only exists once you know there is machinery to scope.
    #
    # Accent, not violet: every page in the app gives its LEAD section the
    # primary accent (see "Positions", "Relative Performance"), and the lead
    # here changed.
    render_section_header("Engines", "Three engines, one pipeline · every style "
                          "travels all of it", icon="cpu", accent="accent")
    cols = st.columns(3, gap="small")
    for col, (cls, name, kicker, body, specs) in zip(cols, _SYSTEM_PANELS):
        with col:
            with panel(f"landing-{cls}", name, context=kicker):
                st.markdown(
                    f'<div class="panel-copy">{body}</div>'
                    '<div class="panel-specs">'
                    + "".join(
                        f'<div class="lookback-row"><span class="lbl">{k}</span>'
                        f'<span class="val">{v}</span></div>'
                        for k, v in specs
                    )
                    + "</div>",
                    unsafe_allow_html=True,
                )

    # ── Inputs & Scope — the app's own KPI grammar, not a bespoke number row
    #    Second, because these are the bounds ON the engines above: what they
    #    can be pointed at, how much history they read, and how far any one
    #    holding is allowed to go.
    render_section_header("Inputs & Scope", "Styles, estimation window and position "
                          "cap · fixed before any run", icon="layers", accent="violet")
    render_kpi_strip(
        [
            {"label": "Portfolio Styles", "value": str(len(STYLE_LABELS)),
             "subtext": " · ".join(str(METHOD_SPECS[k]["short"]) for k in METHOD_ORDER)
                        + " — every one travels the identical pipeline"},
            {"label": "Estimation Window", "value": f"{_CALIBRATION_LOOKBACK_FILES}d",
             "subtext": "Daily observations behind the covariance, over a universe that "
                        "must carry 80% of it to be estimated"},
            {"label": "Position Cap", "value": "10%",
             "subtext": "Per holding, relaxed only where it and full allocation are not "
                        "simultaneously satisfiable"},
        ],
        max_cols=3,
        key="landing-coverage",   # key is CSS-visible (st-key-kpi-*); name is not
    )

    # ── Run Outputs — the close of the argument ───────────────────────────
    render_section_header("Run Outputs", "What a run hands back, on the page rather "
                          "than in a log", icon="target", accent="emerald")
    _out = (
        ("A curated book", "Holdings, units and value, with the weight formula that "
                           "produced them and the cap that bounded them."),
        ("Its risk structure", "Each holding's share of variance against its share of "
                               "capital, and the clusters the allocator actually saw."),
        ("An honest comparison", "The same holdings split 1/N, so the weighting decision "
                                 "is isolated from the selection."),
        ("Every constraint named", "What was excluded, what could not be estimated, and "
                                   "which limit is binding — on the page, not in a log."),
    )
    st.markdown(
        '<div class="outcome-grid">'
        + "".join(
            f'<div class="outcome"><div class="o-t">{html_module.escape(t)}</div>'
            f'<div class="o-d">{html_module.escape(d)}</div></div>'
            for t, d in _out
        )
        + "</div>",
        unsafe_allow_html=True,
    )


def _book_notices(portfolio: pd.DataFrame, ctx: dict) -> "list[dict]":
    """Data-quality notices for the rail under the command bar.

    Everything the reader would otherwise have to infer from a blank cell or a
    short table. These used to be scattered as captions inside whichever tab
    happened to show the affected number, which meant a book built on 28 of 30
    names looked complete until you reached the System tab.
    """
    at = portfolio.attrs if hasattr(portfolio, "attrs") else {}
    spec = style_spec(ctx)
    out: "list[dict]" = []

    cov_req = num(at.get("nco_coverage_required")) or 0.8
    uncovered = int(at.get("nco_positions_uncovered", 0) or 0)
    if uncovered:
        rc_cov = num(at.get("nco_rc_coverage"))
        out.append({
            "kind": "info",
            "title": f"{uncovered} holding(s) carry no covariance estimate",
            "body": f"Held at their full weight — {spec['label']} needs no estimate to size "
                    f"them — but every risk figure on this page is computed without them"
                    + (f", over {rc_cov:.0%} of book weight." if rc_cov is not None else "."),
        })
    excluded = at.get("nco_universe_excluded") or {}
    if excluded:
        out.append({
            "kind": "info",
            "title": f"{len(excluded)} symbol(s) excluded from the book",
            "body": f"Below {cov_req:.0%} of the estimation window, so this style has no "
                    f"weight to give them: {', '.join(sorted(excluded))}.",
        })
    if not at.get("nco_cov_estimable", True):
        out.append({
            "kind": "warning",
            "title": "No covariance was estimable for this window",
            "body": "The book is unaffected — this style reads no covariance — but the "
                    "cluster, risk and correlation diagnostics are unavailable.",
        })
    # ONE EVENT, ONE NOTICE.
    #
    # A symbol the data source cannot deliver is dropped from the universe
    # before the allocator ever sees it, so a failed re-fetch and a book that
    # came up short are frequently the SAME event reported twice. The rail was
    # stacking "the eligible universe ran out" directly above "1 symbol(s)
    # unavailable from the data source" and leaving the reader to infer a
    # causal link the code already knows — two warnings for one problem, which
    # reads as two problems. Where they coincide, the shortfall notice names
    # the cause and the second notice stands down.
    recovery = getattr(get_metrics(), "data_recovery", None) or {}
    failed = [str(s) for s in (recovery.get("failed") or [])]
    short = int(at.get("nco_positions_short", 0) or 0)
    short_from_universe = at.get("nco_short_cause") == "universe"
    caused_by_fetch = bool(short and short_from_universe and failed)

    if short:
        if caused_by_fetch:
            # Say "matches exactly" only when it does. A universe short by five
            # with one failed fetch is a contribution, not the whole story, and
            # claiming otherwise would be a worse error than the split notice.
            _lead = ("The eligible universe ran out, and the shortfall is exactly the "
                     "symbol(s) the data source could not deliver"
                     if len(failed) == short else
                     "The eligible universe ran out, and the data source contributed to it")
            _body = (f"{_lead}: {', '.join(sorted(failed))} — dropped before allocation "
                     f"after a dedicated re-fetch also failed.")
        elif short_from_universe:
            _body = "The eligible universe ran out."
        else:
            _body = "The allocator zeroed the remaining names."
        out.append({
            "kind": "warning",
            "title": f"{short} position(s) short of the request",
            "body": _body,
        })
    cap_eff = num(at.get("max_pos_pct_eff"))
    cap_nom = num(st.session_state.get("max_pos_pct"))
    if cap_eff is not None and cap_nom is not None and abs(cap_eff - cap_nom) > 1e-9:
        out.append({
            "kind": "info",
            "title": f"Position cap relaxed to {cap_eff:.0%}",
            "body": f"A {cap_nom:.0%} cap and full allocation are not simultaneously "
                    f"satisfiable at this position count.",
        })
    if failed and not caused_by_fetch:
        # Reached when the drop did not cause the shortfall — either the book is
        # complete, or it is short for an unrelated reason the notice above
        # already names. Only the first of those may claim a full position
        # count, so the closing sentence is gated on the count and not on the
        # branch: a book short because the allocator zeroed names is still short
        # while this fires.
        out.append({
            "kind": "info" if not short else "warning",
            "title": f"{len(failed)} symbol(s) unavailable from the data source",
            "body": f"Dropped from the universe after a dedicated re-fetch: "
                    f"{', '.join(sorted(failed))}."
                    + (" The book still reached its full position count, so nothing "
                       "was lost but the choice." if not short else
                       " The universe was that much smaller before the allocator "
                       "ran, though it is not what the book came up short on."),
        })
    return out


def _render_results(display_capital: float):
    """Render results page with portfolio, regime, and system tabs."""
    portfolio = st.session_state.portfolio
    if portfolio.empty or "value" not in portfolio.columns:
        render_empty_state(
            "No holdings in the curated book",
            "The allocator returned a frame with no priced rows. Adjust the universe, "
            "the date or the position count and run again.",
            action_label="Run Analysis in the rail",
        )
        return

    current_df = st.session_state.current_df
    regime_d = st.session_state.regime_result_dict or {}
    training_window = st.session_state.get("training_data_window", [])
    _ctx = st.session_state.get("run_context") or {}
    _at: Dict[Any, Any] = portfolio.attrs if hasattr(portfolio, "attrs") else {}
    _spec = style_spec(_ctx)
    _vol = num(_at.get("nco_port_vol_ann"))

    total_value = portfolio["value"].sum()
    cash_remaining = display_capital - total_value

    def _chrome() -> None:
        """The chrome every page opens with: tape, command bar, notices, KPIs.

        Reading order is identity → value → trust: what was curated, what it is
        worth, and whether the data behind that is current. The tape sits above
        it because a tape is the one thing on screen that is about the market
        rather than about this book, and the notice rail hangs below so a
        data-quality caveat is never further than one page from the number it
        qualifies.

        The KPI strip closes the block and is part of it, not part of any one
        page. These five numbers describe the BOOK, and the book does not
        change when you move between its holdings, its performance and the
        regime it was curated into — so a reader should not have to navigate
        back to a particular page to see them. They were on Holdings alone,
        which made that page the only one that could answer "how much is
        deployed" and left every other page describing a book whose size was
        off-screen.
        """
        render_ticker(current_df)
        render_top_bar(
            target=f"{_ctx.get('universe', '—')}"
                   + (f" · {_ctx['selected_index']}" if _ctx.get("selected_index") else ""),
            price=float(total_value),
            change_pct=None,
            status_label=_spec["short"],
            status_tone="accent",
            meta_items=[
                ("Anchor", str(_ctx.get("anchor_date", "—"))),
                ("Regime", str(regime_d.get("regime", "—")).replace("_", " ")),
                ("Holdings", str(len(portfolio))),
            ],
        )
        render_notice_rail(_book_notices(portfolio, _ctx))
        render_kpi_strip(_kpis, max_cols=5, key="book-kpi")

    # Cash health, read in the direction the system actually works in: this is a
    # capital-DEPLOYMENT engine, so leftover cash is the defect and a fully
    # invested book is the goal. The thresholds were previously inverted
    # (<5% = danger), which painted the correct outcome red on every single run
    # — integer-lot flooring in the curation leaves ~0.5-2%
    # residual by construction, so "danger" was unreachable-by-design to avoid
    # and "success" required leaving >=15% of the book uninvested.
    cash_pct = (cash_remaining / display_capital * 100) if display_capital > 0 else 0
    cash_color = "success" if cash_pct < 5 else ("info" if cash_pct < 15 else ("warning" if cash_pct < 30 else "danger"))

    # Risk concentration: the share of portfolio variance carried by the single
    # heaviest contributor, against the 1/N share it would carry if risk were
    # perfectly balanced. This is the headline number for a risk-based book —
    # it says in one figure whether the allocator actually spread the risk or
    # merely spread the capital.
    _rc = pd.to_numeric(portfolio.get("risk_contribution", pd.Series(dtype=float)),
                        errors="coerce").dropna()
    _n_pos = max(len(portfolio), 1)
    _eq_rc = 1.0 / _n_pos
    _top_rc = float(_rc.max()) if len(_rc) else float("nan")
    _rc_ratio = (_top_rc / _eq_rc) if (len(_rc) and _eq_rc > 0) else float("nan")
    # 1.0x is perfect balance; below ~1.5x is well spread, above ~3x means one
    # holding dominates the book's variance.
    _rc_color = ("info" if not np.isfinite(_rc_ratio) else
                 "success" if _rc_ratio < 1.5 else
                 "warning" if _rc_ratio < 3.0 else "danger")

    _kpis = [
        {"label": "Deployed", "value": f"₹{total_value:,.0f}",
         "subtext": f"{total_value / display_capital * 100:.0f}% of capital",
         "color_class": "info"},
        {"label": "Cash", "value": f"₹{cash_remaining:,.0f}",
         "subtext": f"{cash_pct:.1f}% remaining", "color_class": cash_color},
        {"label": "Positions", "value": str(len(portfolio)),
         "subtext": f"of {_at.get('nco_positions_requested', len(portfolio))} requested",
         "color_class": "warning" if _at.get("nco_positions_short") else "neutral"},
        {"label": "Ex-ante Volatility",
         "value": f"{_vol:.2%}" if _vol is not None else "—",
         "subtext": "Annualised, from the covariance",
         "color_class": "neutral",
         "tooltip": "The volatility the covariance implies for this book. "
                    "It is what the allocator targets — not a return forecast."},
        {"label": "Risk Concentration",
         "value": f"{_rc_ratio:.2f}x" if np.isfinite(_rc_ratio) else "—",
         "subtext": "Top holding vs equal risk share", "color_class": _rc_color,
         "tooltip": "1.00x is perfect balance. Above 3x, one holding carries "
                    "the book's variance whatever the capital says."},
    ]

    # ── Error boundary ────────────────────────────────────────────────────
    # One page failing must not take the shell down with it: the command bar,
    # the rail and every other page stay reachable, and the failure is stated
    # where the content would have been.
    def _safe_render(name: str, render_fn) -> None:
        try:
            render_fn()
        except Exception as e:                              # noqa: BLE001
            render_warning_box(
                title=f"Error in {name}",
                content=f"{type(e).__name__}: {e}",
            )

    # ── App shell — one real page per analytical surface ──────────────────
    # Every page below is a THIN wrapper: none recompute anything, they only
    # call the same render functions with the same arguments the tab bar used
    # to call. This is a presentation-layer restructure, not a change to what
    # gets computed or when.
    def _page_holdings() -> None:
        """Holdings — scan first, then read, then the book itself.

        There is no separate overview page. One existed and it was a landing
        strip in front of the only thing it described: five numbers about a
        book you then had to click through to see. Those numbers are now part
        of the chrome on every page, and this one opens straight onto the book.
        """
        _chrome()
        _safe_render("Holdings", lambda: render_portfolio_tab(
            portfolio, current_df, display_capital))

    def _page_performance() -> None:
        _chrome()
        _safe_render("Performance", lambda: render_analytics_tab(portfolio))

    def _page_regime() -> None:
        _chrome()
        _safe_render("Regime", lambda: render_regime_tab(
            regime_d, st.session_state.get("regime_history_series", []), training_window))

    def _page_broker() -> None:
        _chrome()
        _safe_render("Broker Sync", lambda: render_broker_sync_tab(portfolio))

    def _page_system() -> None:
        _chrome()
        _safe_render("Configuration", lambda: render_system_tab(training_window))

    # Grouped by what a reader is asking. THE BOOK is what was curated; CONTEXT
    # is the market it was curated into, which nothing downstream depends on;
    # SYSTEM is how it was produced and what to do with it next.
    pages = {
        "The Book": [
            st.Page(_page_holdings, title="Holdings",
                    icon=":material/inventory_2:", default=True),
            st.Page(_page_performance, title="Performance", icon=":material/show_chart:"),
        ],
        "Context": [
            st.Page(_page_regime, title="Regime", icon=":material/explore:"),
        ],
        "System": [
            st.Page(_page_broker, title="Broker Sync", icon=":material/sync_alt:"),
            st.Page(_page_system, title="Configuration", icon=":material/tune:"),
        ],
    }
    st.navigation(pages, position="sidebar").run()
    _render_footer()


def _run_analysis(
    selected_date: datetime,
    investment_style: str,
    capital: float,
    num_positions: int,
    selected_date_display: date,
    symbols_key: str,
    universe: str,
    index: str,
):
    """Execute the 2-phase analysis pipeline."""
    metrics = get_metrics()
    metrics.phases, metrics.errors, metrics.warnings = {}, [], []
    # Cleared with the rest of the per-run state, or a cache-hit run would
    # re-report the previous run's re-fetch as its own.
    metrics.data_recovery = {}
    # Reset the run clock: the tracker is per-SESSION (see metrics.get_metrics),
    # so without this the summary's "Total Duration" reports time since the
    # session's first run, not this run's wall time.
    import time as _time
    metrics.start_time, metrics.end_time = _time.time(), 0.0
    st.session_state.debug_info = []
    st.session_state.regime_history_series = None

    # The header states the REQUEST. Everything after it is the WORK, as a
    # numbered sequence of steps — so the terminal reads as "this was asked for,
    # and here is each thing that was done to answer it, in order, with what it
    # produced and what it cost". Symbol count is deliberately NOT in the header:
    # at this point nothing has been resolved, and the universe step reports it.
    from logger_config import generate_run_id
    current_run_id = generate_run_id()  # Fresh ID for each analysis
    _universe_label = f"{universe} · {index}" if index else universe
    log.main_header(f"PRAGYAM | Portfolio Intelligence | {VERSION}", {
        "Analysis Date": selected_date_display,
        "Universe": _universe_label,
        "Investment Style": investment_style,
        "Capital": f"₹{capital:,.0f}",
        "Positions Requested": num_positions,
        "Position Cap": f"{st.session_state.max_pos_pct*100:.0f}% per holding",
        "Run ID": current_run_id[-12:],
        "Started": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })

    log.section("Data & Regime", phase="PHASE 1")

    # Resolve the universe to get symbols
    #
    # Failure is reported on the step and acted on AFTER it closes: st.stop()
    # unwinds by raising, so calling it inside the block would end the step
    # without ever printing its outcome.
    _resolve_err: Optional[Exception] = None
    with log.task("Resolve universe", _universe_label) as _t:
        try:
            symbols_list, status_msg = resolve_universe(universe, index)
        except Exception as e:
            symbols_list, status_msg, _resolve_err = [], str(e), e
        if _resolve_err is not None:
            _t.fail(f"{type(_resolve_err).__name__}: {_resolve_err}")
        elif not symbols_list:
            _t.fail(status_msg or "no symbols returned")
        else:
            if status_msg:
                _t.item("Source", status_msg)
            _t.item("Members", ", ".join(symbols_list[:8])
                    + (f" … (+{len(symbols_list) - 8})" if len(symbols_list) > 8 else ""))
            _t.ok(f"{len(symbols_list)} symbols")
    if _resolve_err is not None:
        st.error(f"Error resolving universe: {_resolve_err}")
        st.stop()
    if not symbols_list:
        st.error(f"Could not load {index or universe}: {status_msg}")
        st.stop()

    try:
        # Custom styled progress container (matches Nishkarsh)
        progress_container = st.empty()

        # PHASE 1: DATA FETCHING
        #
        # Single progress bar contract: `progress_container` is the ONE
        # progress surface for the whole run. Every milestone below renders
        # into it with a STRICTLY NON-DECREASING percentage — the bands are
        # Phase 1 (Data & Regime) 0-20, Phase 1.5 (Intelligence) 20-35,
        # Phase 2 (Strategies & Curation) 35-100 — so the bar can never move
        # backwards regardless of which Phase 1.5 branch executes. Labels are
        # Title Case; subs carry the load-bearing datum for that milestone.
        progress_bar(progress_container, 2, "Fetching Market Data", f"yfinance · {len(symbols_list)} symbols")
        metrics.start_phase("total_execution")
        # Must match _REGIME_LOOKBACK_FILES so the regime card / regime banner /
        # regime history chart / Phase 2 curation all share one cached panel.
        LOOKBACK_FILES = _REGIME_LOOKBACK_FILES

        metrics.start_phase("data_fetching")

        # Everything the fetch was ASKED for goes in before it runs, so a hung or
        # failed download still leaves the request on the record.
        _panel_start = selected_date - timedelta(
            days=int((LOOKBACK_FILES + MAX_INDICATOR_PERIOD) * 1.5) + 30)
        with log.task("Historical panel",
                      f"{LOOKBACK_FILES}-day lookback · {len(symbols_list)} symbols") as _t:
            _t.item("Anchor", selected_date.strftime("%Y-%m-%d"))
            _t.item("Download window",
                    f"{_panel_start:%Y-%m-%d} → {selected_date:%Y-%m-%d} "
                    f"({(selected_date - _panel_start).days} calendar days, "
                    f"{MAX_INDICATOR_PERIOD} warmup bars)")
            _fetches_before = _panel_fetch_count()
            _rec_before = getattr(metrics, "data_recovery", None)
            all_hist = _load_historical_data(selected_date, LOOKBACK_FILES, symbols_key)
            if _panel_fetch_count() == _fetches_before:
                _t.detail("cache HIT — panel reused from this session")
            _log_recovery(_t, _rec_before)
            if not all_hist:
                _t.fail("no snapshots returned")
            else:
                _last_syms = {str(s) for s in all_hist[-1][1].get("symbol", [])}
                _t.item("Panel span",
                        f"{all_hist[0][0]:%Y-%m-%d} → {all_hist[-1][0]:%Y-%m-%d}")
                _t.item("Latest snapshot",
                        f"{len(_last_syms)} of {len(symbols_list)} symbols priced")
                if len(_last_syms) < len(symbols_list):
                    _t.note(f"{len(symbols_list) - len(_last_syms)} symbol(s) absent from the "
                            "latest snapshot — they cannot be sized or held")
                _t.ok(f"{len(all_hist)} trading days · {len(_last_syms)} symbols")
        if not all_hist:
            log.error("No historical data loaded — check the universe selection and date range.")
            st.error("No historical data loaded. Check universe selection and date range.")
            st.stop()

        metrics.end_phase("data_fetching", success=True, items=len(all_hist))
        metrics.days_count = len(all_hist)

        progress_bar(progress_container, 14, "Data Loaded", f"{len(all_hist)} days · {len(symbols_list)} symbols")

        # Regime detection — pass intelligence context so the 8 factor weights are
        # the learned ones (Intelligence mode) or the shared defaults (Standard).
        progress_bar(progress_container, 16, "Detecting Market Regime", "8-factor composite scoring")
        # Every factor is printed with the weight it carries into the composite,
        # so the headline regime can be checked against its own inputs instead of
        # being taken on trust.
        with log.task("Market regime", "8-factor fixed-weight composite") as _t:
            regime_result = _detect_regime_cached(selected_date, symbols_key)
            regime_name = regime_result.get("regime", "UNKNOWN")
            confidence = regime_result.get("confidence", 0.0)
            _factors = regime_result.get("factors") or {}
            for _fkey, _flabel, _fdesc_key in REGIME_FACTOR_ORDER:
                _fd = _factors.get(_fkey) or {}
                _t.item(f"{_flabel} ({FACTOR_WEIGHTS.get(_fkey, 0.0)*100:.0f}%)",
                        f"{float(_fd.get('score', 0.0)):+.2f}  "
                        f"{str(_fd.get(_fdesc_key, '—')).replace('_', ' ').lower()}")
            _t.item("Composite", f"{float(regime_result.get('composite_score', 0.0)):+.3f}")
            _t.item("Suggested mix", regime_result.get("mix_name", "—"))
            if regime_name == "UNKNOWN":
                _t.warn(f"UNKNOWN — {regime_result.get('explanation', 'no explanation given')}")
            else:
                _t.ok(f"{regime_name.replace('_', ' ')} · {confidence:.0%} confidence")

        st.session_state.regime_result_dict = regime_result
        st.session_state.suggested_mix = regime_result.get("mix_name", "Chop/Consolidate Mix")
        st.session_state.training_data_window = all_hist

        if len(all_hist) < 10:
            log.error(f"Insufficient training data: {len(all_hist)} trading days, 10 required. "
                      "Pick an earlier anchor date or a longer-listed universe.")
            st.error(f"Insufficient training data: {len(all_hist)} days (need ≥10).")
            metrics.end_phase("data_fetching", success=False, error_msg=f"Insufficient data: {len(all_hist)} days")
            st.stop()

        if not st.session_state.suggested_mix:
            log.error("Market regime could not be determined — no mix returned for this date.")
            st.error("Market regime could not be determined. Select a valid date.")
            metrics.end_phase("data_fetching", success=False, error_msg="Regime undetermined")
            st.stop()

        st.session_state.current_df = all_hist[-1][1] if all_hist else pd.DataFrame()

        progress_bar(
            progress_container, 20, "Phase 1 Complete",
            f"{regime_name.replace('_', ' ')} regime · {confidence:.0%} confidence",
        )

        # Regime history series — computed ONCE here (moved up from its old
        # position after Phase 2) so Phase 1.5 can condition calibration on
        # the regime actually in effect at each historical date (see
        # Cached in session_state so the Regime tab's chart reuses this exact
        # computation instead of recomputing it.
        with log.task("Regime history", "rolling 10-day windows, step 1") as _t:
            try:
                _regime_series_for_harvest = get_regime_history_series(all_hist, window_size=10, step=1)
            except Exception as _e:
                _regime_series_for_harvest = []
                _t.fail(f"{type(_e).__name__}: {_e}")
            else:
                _seq = [getattr(r, "regime", None) for r in _regime_series_for_harvest]
                _transitions = sum(1 for a, b in zip(_seq, _seq[1:]) if a != b)
                if not _seq:
                    _t.warn("no readings — the history chart will be empty")
                else:
                    _t.item("Span", f"{str(_seq[0]).replace('_', ' ')} → "
                                    f"{str(_seq[-1]).replace('_', ' ')}")
                    _t.ok(f"{len(_seq)} readings · {_transitions} regime transitions")
        st.session_state.regime_history_series = _regime_series_for_harvest

        # PHASE 2: COVARIANCE CURATION
        #
        # Selection AND weighting both come from the return covariance
        # structure. There is no conviction score, no regime passport and no
        # strategy layer — all three were removed after measurement showed the
        # conviction blend had no cross-sectional predictive power on this
        # universe (IC ~0.00-0.04, sign unstable) and the 95-strategy library
        # was 97.2% self-correlated, an effective count of 1.03 independent
        # strategies out of 92.
        #
        # Grinold's Fundamental Law bounds excess return from FORECASTING at
        # IR = IC x sqrt(BR) x TC — about 1%/yr here (rho 0.517, ~1.9 effective
        # bets). That bound does not constrain covariance-based allocation,
        # which forecasts nothing. See nco.py for the measured results.
        metrics.start_phase("curation")
        if investment_style in NCO_STYLES:
            _method = NCO_STYLES[investment_style]
            _spec = method_spec(_method)
            # The 40% milestone names what this method is actually doing. The old
            # copy said "Clustering Risk Structure" for every style, which was
            # wrong for three of the four: only HRP derives its weights from the
            # cluster tree. Clustering still RUNS for all of them (the correlation
            # diagnostic is shown regardless), it just isn't the allocation step.
            _stage40 = {
                "EQUAL":  ("Measuring Risk Structure", "1/N · clustering for diagnostics only"),
                "ERC":    ("Solving Equal Risk Contribution", "cyclical coordinate descent"),
                "HRP":    ("Clustering Risk Structure", "correlation-distance hierarchy"),
            }.get(_method, ("Measuring Risk Structure", _spec["formula"]))
            progress_bar(progress_container, 40, _stage40[0],
                         f"{_spec['short']} · {_stage40[1]}")

            log.section("Covariance Curation", phase="PHASE 2")

            # Prices are the one input EVERY style needs — a name without one
            # cannot be sized whatever the allocator decides — so what survives
            # this filter is reported before any weighting happens.
            with log.task("Price snapshot", f"{selected_date:%Y-%m-%d} close") as _t:
                _cur = st.session_state.current_df
                _prices = {
                    str(r["symbol"]): float(r["price"])
                    for _, r in _cur.iterrows()
                    if pd.notna(r.get("price")) and float(r.get("price") or 0) > 0
                }
                _unpriced = len(_cur) - len(_prices)
                if _unpriced > 0:
                    _t.note(f"{_unpriced} row(s) in the snapshot carry no usable price")
                if not _prices:
                    _t.fail("no priced symbols")
                else:
                    _t.ok(f"{len(_prices)} priced symbols of {len(symbols_list)} in the universe")

            _book = pd.DataFrame()
            _curation_error = None
            try:
                # Needs a deeper panel than the 126-day run window: a sample
                # covariance over ~30 assets estimated from 126 observations is
                # too ill-conditioned to cluster on. Reuses the same cache key
                # as the calibration panel, so it is free whenever that has
                # already been fetched.
                with log.task("Estimation panel",
                              f"{_CALIBRATION_LOOKBACK_FILES}-day covariance window") as _t:
                    _fetches_before = _panel_fetch_count()
                    _rec_before = getattr(metrics, "data_recovery", None)
                    _nco_hist = _load_historical_data(
                        selected_date, _CALIBRATION_LOOKBACK_FILES, symbols_key
                    ) or all_hist
                    if _panel_fetch_count() == _fetches_before:
                        _t.detail("cache HIT — panel reused from this session")
                    _log_recovery(_t, _rec_before)
                    if _nco_hist is all_hist:
                        _t.note("deep panel unavailable — falling back to the "
                                f"{LOOKBACK_FILES}-day regime panel")
                    _t.item("Panel span",
                            f"{_nco_hist[0][0]:%Y-%m-%d} → {_nco_hist[-1][0]:%Y-%m-%d}")
                    _t.ok(f"{len(_nco_hist)} trading days")

                _stage60 = ("Allocating Across Clusters" if _spec["uses_clusters"]
                            else "Balancing Risk Contributions" if _spec["rc_target"] == "equal"
                            else "Sizing Positions")
                progress_bar(progress_container, 60, _stage60,
                             f"{len(_prices)} symbols · {_spec['short']}")

                with log.task("Allocate", f"{_spec['label']} · {_spec['formula']}") as _t:
                    _t.item("Eligibility", "every priced symbol (estimates nothing)"
                            if not _spec.get("needs_covariance", True)
                            else f"names with ≥{MIN_COVERAGE:.0%} of the estimation window")
                    _t.item("Requested", f"{num_positions} positions · "
                                         f"cap {st.session_state.max_pos_pct*100:.0f}%")
                    _book = compute_nco_portfolio(
                        _nco_hist, _prices, capital, num_positions,
                        method=_method, max_pos_pct=st.session_state.max_pos_pct,
                    )
                    if _book.empty:
                        _t.fail("no book — see the reason below")
                    else:
                        _t.ok(f"{len(_book)} positions from "
                              f"{_book.attrs.get('nco_universe', 0)} eligible names")

                progress_bar(progress_container, 80, "Applying Position Cap",
                             f"max {st.session_state.max_pos_pct*100:.0f}% · "
                             f"{len(_book)} positions")
            except Exception as _e:
                _curation_error = _e
                log.error(f"{_spec['short']} curation failed: {type(_e).__name__}: {_e}")
                _book = pd.DataFrame()

            if _book.empty:
                # Equal Weight cannot fail on a covariance it never reads, so it
                # must not be told it did: the only way it comes back empty is
                # that nothing in the universe had a usable price.
                _needs_cov = bool(_spec.get("needs_covariance", True))
                log.error(
                    f"{_spec['label']} produced no portfolio — "
                    + (f"{type(_curation_error).__name__}: {_curation_error}"
                       if _curation_error is not None else
                       "the return covariance was not estimable over this universe and date"
                       if _needs_cov else
                       "no symbol returned a usable price")
                )
                st.error(
                    f"{investment_style} could not build a portfolio — the return "
                    "covariance was not estimable (too few overlapping observations "
                    "for this universe and date). Try an earlier analysis date, a "
                    "larger universe, or a later analysis date."
                    if _needs_cov else
                    f"{investment_style} could not build a portfolio — no symbol in this "
                    "universe returned a usable price for the selected date. Check the "
                    "universe selection, or try another date."
                )
                metrics.end_phase("curation", success=False,
                                  error_msg="Covariance not estimable" if _needs_cov
                                  else "No priced symbols")
                st.stop()

            st.session_state.portfolio = _book
            st.session_state.min_pos_pct_eff = _book.attrs.get("min_pos_pct_eff", 0.0)
            st.session_state.max_pos_pct_eff = _book.attrs.get(
                "max_pos_pct_eff", st.session_state.max_pos_pct)
            st.session_state.run_context = {
                "universe": universe, "selected_index": index,
                "regime_name": regime_name,
                "anchor_date": selected_date_display,
                "investment_style": investment_style,
                "capital": capital,
                "curation": _method,
            }

            _at = _book.attrs
            _disp = num(_at.get("nco_rc_dispersion"))
            _conc = num(_at.get("nco_rc_concentration"))
            _pvol = num(_at.get("nco_port_vol_ann"))
            _pcov = num(_at.get("nco_rc_coverage"))

            # What the allocator SAW: the panel it estimated on, the structure it
            # found in it, and whether it hit the target it exists to hit.
            with log.task("Risk structure",
                          f"{_spec['short']} · {_spec['family']}") as _t:
                _t.item("Estimation", f"{_at.get('nco_obs', 0)} daily observations · "
                                      f"{_at.get('nco_estimation_universe', 0)} symbols")
                # Name every symbol the coverage rule touched. A book built on 28
                # of 30 ETFs is correct when two of them listed this year, but it
                # must never be left to the reader to work that out — and under
                # Equal Weight those two names are HELD with no risk numbers,
                # which is a different fact and has to read differently.
                _excl = _at.get("nco_diagnostic_excluded") or {}
                _excl_from_book = bool(_at.get("nco_universe_excluded"))
                _t.item("Universe", f"{_at.get('nco_universe', 0)} allocated · "
                                    f"{_at.get('nco_estimation_universe', 0)} with a "
                                    "covariance estimate"
                        + (f" · {len(_excl)} below "
                           f"{_at.get('nco_coverage_required', 0.8):.0%} history "
                           + ("(excluded from the book)" if _excl_from_book
                              else "(held, no risk diagnostics)") if _excl else ""))
                for _sym, _d in sorted(_excl.items(), key=lambda kv: kv[1]["coverage"]):
                    _t.item(f"  {'excluded' if _excl_from_book else 'unestimated'} {_sym}",
                            f"{_d['obs']}/{_d['window']} obs ({_d['coverage']:.0%})")
                _t.item("Clustering",
                        (f"{_at.get('nco_clusters', 0)} clusters "
                         f"(silhouette {_at.get('nco_silhouette', 0):.3f})"
                         if _at.get("nco_cov_estimable", True)
                         else "not estimable for this window")
                        + ("" if _spec["uses_clusters"] else " · diagnostic only"))
                # Dispersion is the coefficient of variation of the risk
                # contributions: 0.00 is perfect equal-risk. "—" rather than
                # "nan" — a book whose holdings have no covariance estimate has
                # no dispersion, which is not the same as a dispersion of zero.
                _t.item("Risk balance",
                        (f"dispersion {_disp:.3f} " if _disp is not None else "dispersion — ")
                        + f"({'target 0.00' if _spec['rc_target'] == 'equal' else 'not targeted'})"
                        + (f" · concentration {_conc:.2f}x equal share"
                           if _conc is not None else " · concentration —"))
                if _spec["uses_momentum"]:
                    _t.item("Momentum tilt",
                            f"{_at.get('nco_momentum_names', 0)} names scored "
                            f"({MOMENTUM_LOOKBACK}-{MOMENTUM_SKIP} window) · "
                            f"lambda {_at.get('nco_momentum_lambda', 0):.2f}"
                            + ("" if _at.get("nco_momentum_applied") else " · NOT APPLIED"))
                if not _at.get("nco_cov_estimable", True):
                    _t.warn("no estimable covariance — book built without risk diagnostics")
                else:
                    _t.ok("ex-ante volatility "
                          + (f"{_pvol:.2%}" if _pvol is not None else "—")
                          + (f" (over {_pcov:.0%} of book weight)"
                             if _pvol is not None and _pcov is not None
                             and _pcov < 0.999 else ""))

            # What the holder GETS: the same book expressed as capital, which is
            # the only form of it that can be executed.
            with log.task("Size positions",
                          f"₹{capital:,.0f} · integer lots") as _t:
                _deployed = float(pd.to_numeric(_book["value"], errors="coerce").fillna(0).sum())
                _cash = capital - _deployed
                _w = pd.to_numeric(_book["weightage_pct"], errors="coerce")
                _cap_eff = num(_at.get("max_pos_pct_eff")) or st.session_state.max_pos_pct
                _t.item("Position cap",
                        f"{_cap_eff*100:.1f}%"
                        + (" (relaxed from "
                           f"{st.session_state.max_pos_pct*100:.0f}% — infeasible at this "
                           "position count)"
                           if abs(_cap_eff - st.session_state.max_pos_pct) > 1e-9 else ""))
                _t.item("Weights", f"min {_w.min():.2f}% · max {_w.max():.2f}% · "
                                   f"equal share {100.0/len(_book):.2f}%")
                _t.item("Deployed", f"₹{_deployed:,.0f} ({_deployed/capital:.1%}) · "
                                    f"cash ₹{_cash:,.0f} ({_cash/capital:.1%})")
                _t.item("Largest", " · ".join(
                    f"{r['symbol']} {r['weightage_pct']:.1f}%"
                    for _, r in _book.head(5).iterrows()))
                if _at.get("nco_positions_short"):
                    _t.warn(f"{len(_book)} of {num_positions} requested — "
                            + ("the eligible universe ran out"
                               if _at.get("nco_short_cause") == "universe"
                               else "the allocator zeroed the remaining names"))
                else:
                    _t.ok(f"{len(_book)} positions · {int(_book['units'].sum()):,} units")

            metrics.end_phase("curation", success=True)
            metrics.symbols_count = _book.attrs.get("nco_universe", len(_book))
            metrics.strategies_count = 0
            metrics.portfolios_generated = len(_book)
            metrics.end_phase("total_execution", success=True)
            progress_bar(progress_container, 100, "Analysis Complete",
                         f"{len(_book)} positions · {_spec['short']}")
            log.summary("Execution Summary", {
                "Run ID": current_run_id[-12:],
                "Curation": f"{_spec['label']} ({_spec['family']})",
                "Weight Formula": _spec["formula"],
                "Clusters": _book.attrs.get("nco_clusters", 0),
                "Positions Selected": len(_book),
                "Risk Dispersion": f"{_disp:.3f}" if _disp is not None else "—",
                "Risk Concentration": f"{_conc:.2f}x" if _conc is not None else "—",
                "Ex-ante Vol": f"{_pvol:.2%}" if _pvol is not None else "—",
                "Status": "SUCCESS",
            })
            metrics.print_summary(log)
            progress_container.empty()
            st.toast("Analysis Complete!")
            return
        else:
            # Defends against a stale style left in session state by an older
            # build — every live style maps into NCO_STYLES.
            log.error(f"Unknown portfolio style: {investment_style!r} — "
                      f"expected one of {', '.join(STYLE_LABELS)}")
            st.error(f"Unknown portfolio style: {investment_style}")
            metrics.end_phase("curation", success=False, error_msg="Unknown style")
            st.stop()

    except Exception as e:
        # The browser message is gone on the next rerun; the traceback is the
        # only thing that says WHERE a run died, so it goes to the terminal.
        import traceback as _tb
        log.failure("Run aborted", f"{type(e).__name__}: {e}")
        for _line in _tb.format_exc().rstrip().split("\n"):
            log.text(_line)
        metrics.add_error(type(e).__name__, str(e), "_run_analysis")
        st.error(f"Initialization failed: {e}")


def _render_footer() -> None:
    """Render the app footer with copyright and version info."""
    utc_now = datetime.now(timezone.utc)
    ist_now = utc_now + timedelta(hours=5, minutes=30)
    st.markdown(
        f'<div class="app-footer">'
        f'<div class="content">'
        f'© {ist_now.year} <strong>{PRODUCT_NAME}</strong> &nbsp;·&nbsp; {COMPANY} &nbsp;·&nbsp; {VERSION} &nbsp;·&nbsp; {ist_now.strftime("%Y-%m-%d %H:%M:%S IST")}'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# _render_footer (defined above) is the single source of truth for the app
# footer — the result-page footer previously duplicated the same markup
# inline with a slightly different timestamp construction (see
# AUDIT_DIRECTIVES.md C5.2); _render_results calls _render_footer() instead.


def _render_appearance_control() -> None:
    """The theme switch, pinned to the foot of the rail by CSS."""
    with st.container(key="appearance"):
        st.markdown('<div class="sidebar-title">Appearance</div>', unsafe_allow_html=True)
        _mode = st.segmented_control(
            "Appearance", list(APPEARANCES), key="theme_mode",
            default=theme_choice(), label_visibility="collapsed",
            help="Slate — dark, for working. Paper — light, for reading and print.",
        )
        # Mirror the widget into the DURABLE key and rerun, so the stylesheet
        # at the top of the script is re-injected with the new value. Without
        # the rerun the change lands half-way down the page and the run
        # renders as a mix of both themes.
        if _mode is not None and _mode != theme_choice():
            st.session_state[_THEME_CHOICE] = _mode
            st.rerun()


def main():
    """Main application entry point."""
    _init_session_state()

    # ─── The control rail ──────────────────────────────────────────────────
    # Everything GLOBAL lives here — what to curate, over what, with how much,
    # and how the app looks. A control's position is the only reliable
    # statement of its scope, so nothing page-local is mixed in.
    #
    # Rail order is by frequency of use: Date and Universe (every run) →
    # Parameters (most runs) → Run (the button) → Appearance (almost never,
    # and pinned to the foot by CSS).
    with st.sidebar:
        # The mark, always at the very top of the rail. Emitted from Python and
        # lifted into place by CSS — `.nav-brand` is absolutely positioned
        # against the sidebar content box, which reserves room for it with a
        # padding-top.
        render_nav_brand()

        # 1. Date
        st.markdown('<div class="sidebar-title">Date</div>', unsafe_allow_html=True)
        selected_date = st.date_input(
            "Analysis date",
            value=datetime.now().date(),
            max_value=datetime.now().date(),
            help="The snapshot the book is curated as of.",
            label_visibility="collapsed",
        )
        st.session_state.selected_date = selected_date
        selected_date_obj = datetime.combine(selected_date, datetime.min.time())

        # 2. Style
        st.markdown('<div class="sidebar-title">Style</div>', unsafe_allow_html=True)
        investment_style = st.selectbox(
            # Not "Investment Objective": no option here expresses an objective.
            # All are allocation methods over the same holdings, and the system
            # forecasts no returns at all — so the honest question is HOW capital
            # is split, not what the user is trying to achieve.
            "Weighting method",
            options=STYLE_LABELS,
            index=0,                      # Equal Weight — nothing measured beat it
            help=(
                "Every style selects and weights entirely from the return covariance "
                "structure — no return forecast is made anywhere.\n\n"
                "**Equal Weight** (default) — 1/N. Across 36 candidate allocators on "
                "three universes, nothing produced a reproducible return improvement "
                "over it. Lowest turnover of any style.\n\n"
                "**Equal Risk Contribution** — every holding contributes the same share "
                "of portfolio variance. The preferred risk-reduction style: it beats HRP "
                "on the any-date hit rate in 6 of 6 cells across two stock universes "
                "while trading ~5x less. It gives up ~0.5%/yr of return against Equal "
                "Weight in exchange for lower volatility and beta 0.92.\n\n"
                "**Risk Parity (HRP)** — clusters by correlation, splits capital by "
                "recursive bisection. Same job as ERC but five times the turnover; kept "
                "for continuity.\n\n"
                "Every style returns exactly the number of positions you select. "
                "Max Diversification was evaluated and withdrawn: it is a corner-solution "
                "optimiser that zeroes names out, so it returned 10 holdings when 15 were "
                "requested.\n\n"
                "If you are maximising absolute return without leverage, Equal Weight "
                "remains the correct choice."
            ),
            label_visibility="collapsed",
        )

        # 3. Universe
        st.markdown('<div class="sidebar-title">Universe</div>', unsafe_allow_html=True)
        universe, selected_index = render_universe_selector()
        st.session_state.selected_universe = universe
        st.session_state.selected_index = selected_index

        # Create symbols key for regime detection
        symbols_key = f"UNIVERSE:{universe}|{selected_index}"
        st.session_state.symbols_key = symbols_key

        # The regime is NOT shown here. It was a card in the rail that could only
        # ever be stale or absent: stale because it described the last run
        # rather than the controls above it, and absent because computing it
        # for a date/universe that has not been run means a blocking
        # multi-symbol download inside the sidebar's render path. The regime
        # belongs to a run, so it lives on the run's own page, where the
        # factors behind it are one click away.

        # 4. Parameters
        st.markdown('<div class="sidebar-title">Parameters</div>', unsafe_allow_html=True)
        capital = st.number_input(
            "Capital ₹",
            min_value=1000,
            max_value=100000000,
            value=2500000,
            step=1000,
            help="Total capital to allocate",
            label_visibility="visible"
        )
        st.session_state["capital"] = capital

        num_positions = st.slider(
            "Positions",
            min_value=5,
            max_value=100,
            value=30,
            step=5,
            help="Maximum portfolio positions"
        )
        st.session_state.min_pos_pct = 1.0 / 100
        st.session_state.max_pos_pct = 10.0 / 100

        # 5. Run
        run_clicked = st.button("Run Analysis", type="primary", use_container_width=True)

        if run_clicked:
            st.session_state["run_params"] = {
                "selected_date_obj": selected_date_obj,
                "investment_style": investment_style,
                "capital": capital,
                "num_positions": num_positions,
                "selected_date": selected_date,
                "symbols_key": symbols_key,
                "universe": universe,
                "index": selected_index,
            }
            st.session_state["run_analysis"] = True
            st.rerun()

        # Session readout — what this rail is currently pointed at. Rendered
        # through the shared rail component rather than hand-built spec rows,
        # so it carries the same type, alignment and tone as every other
        # readout in the app.
        st.markdown('<div class="sidebar-title">Session</div>', unsafe_allow_html=True)
        try:
            symbols_list, status_msg = resolve_universe(universe, selected_index)
            num_symbols = len(symbols_list) if symbols_list is not None else 0
            _rows = [("Universe", universe, "")]
            if selected_index:
                _rows.append(("Index", selected_index, ""))
            _rows += [
                ("Symbols", str(num_symbols), "accent" if num_symbols else "short"),
                ("Source", "yfinance", ""),
                ("Version", VERSION, ""),
            ]
        except Exception:
            _rows = [
                ("Universe", universe, ""),
                ("Symbols", "unresolved", "short"),
                ("Source", "yfinance", ""),
                ("Version", VERSION, ""),
            ]
        render_rail_readout(_rows)

        # ── Appearance ────────────────────────────────────────────────────
        # LAST control in the rail, deliberately: it is the least consequential
        # switch in the application and used to sit under the brand, which is
        # the most valuable position in it. Slate is the working theme; Paper
        # is for reading a result and for print.
        _render_appearance_control()


    # Main content area
    # ─── Show progress bar in main area (outside sidebar) when running analysis ───
    if st.session_state.get("run_analysis") and st.session_state.get("run_params"):
        params = st.session_state["run_params"]
        _run_analysis(
            params["selected_date_obj"], params["investment_style"],
            params["capital"], params["num_positions"], params["selected_date"],
            params["symbols_key"], params["universe"], params["index"],
        )
        # Clear the flag after analysis completes
        st.session_state.pop("run_analysis", None)
        st.session_state.pop("run_params", None)
        # The sidebar painted BEFORE this run executed, so its regime card and
        # regime card still shows pre-run state ("Run Analysis to detect...")
        # — the freshly-computed regime sits in session_state but nothing
        # repaints the sidebar in this script run. Rerun once (the same idiom
        # Phase 1.5 uses after a successful calibration): the flags above are
        # already popped so this cannot loop, every panel the repaint touches
        # is now cached (regime/data/portfolio all in session_state or
        # st.cache_data), the sidebar repaints from fresh state, and the
        # result page renders via st.session_state.portfolio.
        st.rerun()

    if st.session_state.portfolio is None and not st.session_state.get("run_analysis"):
        _render_header()
        _render_landing_page()
        _render_footer()
    elif st.session_state.portfolio is not None:
        # Capital comes from the FROZEN run_context — the amount this book was
        # actually sized against — not the live sidebar widget. Streamlit reruns
        # on any widget change, so reading the live value made nudging the
        # capital input repaint "Deployed / Cash" against a number the portfolio
        # was never built for (e.g. "Deployed 25% of capital") without
        # recurating a single position. Same stale-scope class as A12; falls
        # back to the live value only for a portfolio curated before
        # run_context carried capital.
        _rc = st.session_state.get("run_context") or {}
        display_capital = float(
            _rc.get("capital") or st.session_state.get("capital", 2500000)
        )
        _render_results(display_capital)


if __name__ == "__main__":
    main()
