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
from typing import List, Dict, Tuple, Optional

# Suppress warnings
warnings.filterwarnings("ignore", category=RuntimeWarning)

import html as html_module

# ── Imports ────────────────────────────────────────────────────────────────────
from logger_config import get_console
log = get_console()

from metrics import get_metrics
from ui.theme import inject_css, VERSION, PRODUCT_NAME, COMPANY, progress_bar
from ui.components import (
    render_header,
    render_section_header,
    render_metric_card,
    render_system_card,
    section_gap,
    render_interpretation_card,
    render_kv_table,
    get_icon,
)
import streamlit.components.v1 as components
from regime import (
    MarketRegimeDetector,
    REGIME_COLORS,
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
                 MOMENTUM_LOOKBACK, MOMENTUM_SKIP)

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
    page_icon="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI+PGNpcmNsZSBjeD0iMTIiIGN5PSIxMiIgcj0iMTAiIGZpbGw9Im5vbmUiIHN0cm9rZT0iI0Q0QTg1MyIgc3Ryb2tlLXdpZHRoPSIyIi8+PHBhdGggZD0iTTggMTRsMy01IDIgMyAzLTQiIGZpbGw9Im5vbmUiIHN0cm9rZT0iI0Q0QTg1MyIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiLz48L3N2Zz4=",
    layout="wide",
    # Start EXPANDED: the landing page explicitly instructs "Configure via
    # the Sidebar", so a first-time visitor should see the sidebar controls
    # immediately rather than discover they're collapsed (see
    # AUDIT_DIRECTIVES.md C5.5).
    initial_sidebar_state="expanded",
)

# Load Obsidian Quant Terminal CSS
inject_css()


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

@st.cache_data(ttl=3600, show_spinner=False)
def _load_historical_data(end_date: datetime, lookback_files: int, symbols_key: str) -> List[Tuple[datetime, pd.DataFrame]]:
    """Fetch and cache historical indicator snapshots from yfinance."""
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
        st.error(f"Error resolving universe: {e}")
        return []
    
    try:
        return generate_historical_data(
            symbols_to_process=symbols_list,
            start_date=end_date - timedelta(days=int((lookback_files + MAX_INDICATOR_PERIOD) * 1.5) + 30),
            end_date=end_date,
        )
    except Exception as e:
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
_NCO_STYLES = {METHOD_SPECS[k]["label"]: k for k in METHOD_ORDER}
_STYLE_LABELS = list(_NCO_STYLES.keys())


def _style_spec(ctx_or_method) -> dict:
    """Registry record for a run context, a method code, or a style label."""
    if isinstance(ctx_or_method, dict):
        key = ctx_or_method.get("curation", "EQUAL")
    else:
        key = ctx_or_method
    key = _NCO_STYLES.get(str(key), str(key))
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


@st.cache_data(ttl=1800, show_spinner=False)
def _analytics_series_cached(
    symbols: Tuple[str, ...], units: Tuple[float, ...],
    anchor_iso: str, days_back: int,
    bench_ticker: str, bench_name: str,
    alt_units: Optional[Tuple[float, ...]] = None,
):
    """Cached wrapper around analytics.build_return_series.

    Keyed on the exact (symbols, units, anchor, benchmark, alt_units) tuple so
    the yfinance fetch runs ONCE per unique window and every subsequent
    render/tab-switch hits cache — no repeated downloads. Returns (port_value,
    port_returns, bench_returns, err, unpriced, alt_value). Compute stays in
    analytics.py; caching lives here (the Streamlit boundary), mirroring
    _load_historical_data / _detect_regime_cached.

    `alt_units` is the equal-weight shadow book over the SAME symbols. It rides
    along on this one call (rather than a second cached call with a different
    unit vector) so the comparison costs zero extra downloads and both series
    are guaranteed to share one price panel and one start date.
    """
    from analytics import build_return_series
    _port = pd.DataFrame({"symbol": list(symbols), "units": list(units)})
    anchor_dt = datetime.fromisoformat(anchor_iso)
    _alt = dict(zip(symbols, alt_units)) if alt_units else None
    return build_return_series(
        _port, days_back, bench_ticker, bench_name,
        anchor_date=anchor_dt, alt_quantities=_alt,
    )


# ══════════════════════════════════════════════════════════════════════════════
# UI PRIMITIVES
# ══════════════════════════════════════════════════════════════════════════════

def _section_header(title: str, subtitle: str = "") -> str:
    """Generate styled section header HTML."""
    sub = f"<p class='section-subtitle'>{subtitle}</p>" if subtitle else ""
    return f"<div class='section'><div class='section-header'><h3 class='section-title'>{title}</h3>{sub}</div></div>"


def _section_divider():
    """Render section divider."""
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB RENDERERS
# ══════════════════════════════════════════════════════════════════════════════

def _render_portfolio_tab(portfolio: pd.DataFrame, current_df: pd.DataFrame, capital: float):
    """Tab 1 — the curated book, read through its risk structure.

    This replaces the old conviction-signal overlay. That overlay described a
    score which no longer exists, and which — while it did — had no measurable
    cross-sectional predictive power on this universe (IC ~0.00-0.04, sign
    unstable across horizons). What drives the book now is the covariance
    structure, so that is what the table and heatmaps show.
    """
    _rc = st.session_state.get("run_context") or {}
    _label = _style_spec(_rc)["label"]
    render_section_header(
        "Curated Portfolio Holdings",
        f"{len(portfolio)} positions · {_label}",
        icon="briefcase", accent="amber",
    )

    if portfolio is None or portfolio.empty:
        render_interpretation_card(
            title="NO PORTFOLIO",
            body="Run an analysis to curate a book.",
            color="warning")
        return

    df = portfolio.copy()
    for c in ("cluster", "risk_contribution", "volatility", "corr_to_book"):
        if c not in df.columns:
            df[c] = np.nan
    # Sorted by weight, largest first — the order a holder reads a book in.
    # (The risk heatmap below still groups by cluster, where the block structure
    # is the point.)
    df = df.sort_values("weightage_pct", ascending=False)

    n = len(df)
    eq_share = 100.0 / n if n else 0.0

    rows = []
    for _, r in df.iterrows():
        sym = html_module.escape(str(r["symbol"]))
        rc_pct = float(r["risk_contribution"]) * 100 if pd.notna(r["risk_contribution"]) else float("nan")
        w_pct = float(r["weightage_pct"])
        # Risk-vs-capital gap: the number this method exists to control. A
        # holding taking materially more variance than capital is exactly what a
        # naive equal-weight book hides.
        gap = rc_pct - w_pct if pd.notna(rc_pct) else float("nan")
        # Green = carries LESS variance than capital (what the allocator wants),
        # red = more. The colour follows the outcome, not the sign of the number.
        gap_cls = (
            "risk-under" if gap < -0.5
            else ("risk-over" if gap > 0.5 else "risk-balanced")
        )
        vol = float(r["volatility"]) * 100 if pd.notna(r["volatility"]) else float("nan")
        indep = 1.0 - abs(float(r["corr_to_book"])) if pd.notna(r["corr_to_book"]) else float("nan")
        cl = int(r["cluster"]) if pd.notna(r["cluster"]) else 0
        rows.append(
            "<tr>"
            f'<td class="col-symbol symbol">{sym}</td>'
            f'<td class="col-units numeric">{float(r["units"]):,.0f}</td>'
            f'<td class="col-price numeric currency">&#8377;{float(r["price"]):,.2f}</td>'
            f'<td class="col-weight numeric">{w_pct:.2f}%</td>'
            f'<td class="col-value numeric currency">&#8377;{float(r["value"]):,.0f}</td>'
            f'<td class="col-cluster numeric">C{cl}</td>'
            f'<td class="col-risk numeric">{rc_pct:.2f}%</td>'
            f'<td class="col-gap numeric {gap_cls}">{gap:+.2f}</td>'
            f'<td class="col-vol numeric">{vol:.1f}%</td>'
            f'<td class="col-indep numeric">{indep:.2f}</td>'
            "</tr>"
        )

    css = (
        "<style>"
        # The iframe is a separate document: ui/theme.css does not apply inside
        # it, so the global scrollbar styling has to be restated or this table
        # renders a default OS scrollbar next to every themed one in the app.
        "*{scrollbar-width:thin;scrollbar-color:#4B5563 transparent;}"
        "::-webkit-scrollbar{width:5px;height:5px;}"
        "::-webkit-scrollbar-track{background:transparent;}"
        "::-webkit-scrollbar-thumb{background:#4B5563;border-radius:3px;}"
        "::-webkit-scrollbar-thumb:hover{background:#6B7280;}"
        "html,body{scrollbar-gutter:stable;}"
        ".portfolio-table{width:100%;border-radius:10px;overflow:hidden;"
        "border:1px solid rgba(255,255,255,0.05);"
        "background:linear-gradient(145deg,rgba(17,24,39,0.45) 0%,rgba(17,24,39,0.4) 100%);}"
        ".portfolio-table table{width:100%;border-collapse:collapse;table-layout:fixed;}"
        ".portfolio-table thead th{background:linear-gradient(180deg,rgba(10,14,23,0.95) 0%,"
        "rgba(10,14,23,0.85) 100%);color:#4B5563;font-size: 0.74rem;font-weight:600;"
        "text-transform:uppercase;letter-spacing:0.1em;padding:0.7rem 0.6rem;"
        "border-bottom:2px solid rgba(212,168,83,0.3);text-align:left;"
        "font-family:'IBM Plex Mono',monospace;}"
        # Every column but Symbol is numeric and right-aligned, so its header
        # has to sit over the digits it labels rather than at the far side of
        # the cell. Scoped to th.numeric to beat the thead rule above.
        ".portfolio-table thead th.numeric{text-align:right;}"
        ".portfolio-table td{padding:0.6rem;font-size: 0.88rem;"
        "border-bottom:1px solid rgba(255,255,255,0.04);"
        "font-family:'IBM Plex Mono',monospace;color:#CBD5E1;}"
        ".portfolio-table tr:hover td{background:rgba(212,168,83,0.04);}"
        ".portfolio-table td.numeric{text-align:right;}"
        ".portfolio-table td.symbol{color:#D4A853;font-weight:600;}"
        ".portfolio-table td.currency{color:#94A3B8;}"
        # Risk − Wt is the one column where LOWER is better, so the colours key
        # off the outcome, not the sign: under-weighted risk is green even
        # though the number is negative. Named for the outcome to keep that
        # readable.
        ".portfolio-table td.risk-under{color:#2DD4A8;}"
        ".portfolio-table td.risk-over{color:#E8555A;}"
        ".portfolio-table td.risk-balanced{color:#8B7E6A;}"
        ".col-symbol{width:15%;}.col-units{width:9%;}.col-price{width:11%;}"
        ".col-weight{width:10%;}.col-value{width:13%;}.col-cluster{width:8%;}"
        ".col-risk{width:9%;}.col-gap{width:9%;}.col-vol{width:8%;}.col-indep{width:8%;}"
        "</style>"
    )
    # Header and row heights are MEASURED against the current type scale (see
    # ui/theme.css --fs-*): header wraps to two lines at --fs-xs, data rows sit
    # at --fs-base. The iframe cannot size itself, so these must be re-measured
    # in the browser whenever the scale moves or the table silently clips.
    _pt_natural = 52 + 38 * n + 2
    _pt_h = min(760, _pt_natural)
    _pt_scroll = _pt_natural > 760
    head = (
        "<div class='portfolio-table'><table><thead><tr>"
        "<th class='col-symbol'>Symbol</th>"
        "<th class='col-units numeric'>Units</th>"
        "<th class='col-price numeric'>Price (&#8377;)</th>"
        "<th class='col-weight numeric'>Weight %</th>"
        "<th class='col-value numeric'>Value (&#8377;)</th>"
        "<th class='col-cluster numeric'>Cluster</th>"
        "<th class='col-risk numeric'>Risk Share</th>"
        "<th class='col-gap numeric'>Risk &minus; Wt</th>"
        "<th class='col-vol numeric'>Vol</th>"
        "<th class='col-indep numeric'>Indep</th>"
        "</tr></thead><tbody>"
    )
    body = "".join(rows) + "</tbody></table></div>"
    components.html(
        "<html><head><meta charset='utf-8'></head>"
        "<body style='margin:0;background:transparent;'>" + css + head + body + "</body></html>",
        height=_pt_h, scrolling=_pt_scroll,
    )

    st.caption(
        f"**Risk Share** is each holding's contribution to portfolio variance; **Weight** is its "
        f"share of capital. Equal capital does not mean equal risk — **Risk − Wt** is that gap, "
        f"and controlling it is what this allocator does. It is the one column where lower is "
        f"better, so green marks a holding carrying *less* variance than its capital share and "
        f"red marks one carrying more. **Indep** is 1 − |correlation to the "
        f"book|, so higher means the holding diversifies rather than duplicates. An equal share "
        f"at this position count would be {eq_share:.2f}%."
    )

    if not CHARTS_AVAILABLE:
        return

    _at = portfolio.attrs if hasattr(portfolio, "attrs") else {}
    _rc_target = _at.get("nco_rc_target", "none")
    _mspec = _style_spec(st.session_state.get("run_context") or {})

    _section_divider()
    render_section_header(
        "Risk Profile",
        f"Per-holding, row-relative · scored against {_mspec['short']}'s own objective",
        icon="activity", accent="emerald")
    st.plotly_chart(create_risk_allocation_heatmap(df), width="stretch",
                    key="risk_alloc_heatmap")
    # What "green" means is method-dependent, so the caption must be too. Telling
    # an HRP user that green means "risk share near 1/N" would be wrong: HRP
    # balances across clusters, not holdings.
    st.caption(
        "Each row is scored against its own peers, oriented so **green is the calm, "
        "diversifying end** — low volatility, high independence. "
        + ("Because this style targets **equal risk contribution**, green on the risk row "
           "means a holding sitting *at* its equal share; any red is a name the selection "
           "or the position cap pulled off target."
           if _rc_target == "equal" else
           "This style does not target equal risk contribution, so green on the risk row "
           "simply means a holding carrying *less* variance than its capital share — the gap "
           "between the Weight and Risk rows is the risk this method leaves unbalanced.")
    )

    _section_divider()
    render_section_header(
        "Risk Contribution", "Capital share vs variance share, on one scale",
        icon="bar-chart-2", accent="amber")
    st.plotly_chart(create_risk_contribution_chart(df), width="stretch",
                    key="risk_contrib_chart")
    st.caption(
        {
            "equal": ("Grey is capital, coloured is variance. This style solves for **flat** "
                      "risk bars on the dashed equal-share line — the header reports the "
                      "solver's own dispersion (target 0.000) separately from the realised "
                      "figure, because top-N selection and the position cap move the held "
                      "book away from the solution."),
            "cluster": ("Grey is capital, coloured is variance. Uneven risk bars are **expected** "
                        "here: HRP balances risk across *clusters*, not across individual "
                        "holdings, so a small risk share inside a large cluster is a correct "
                        "outcome rather than an imbalance."),
        }.get(_rc_target,
              "Grey is capital, coloured is variance. This style does not manage risk "
              "contribution at all — the spread of the coloured bars is simply where the "
              "covariance puts the variance, and the distance between the two series is the "
              "argument for risk-based weighting.")
    )

    corr = portfolio.attrs.get("corr_matrix")
    labels = portfolio.attrs.get("cluster_labels")
    if corr is not None and not getattr(corr, "empty", True):
        _section_divider()
        k = portfolio.attrs.get("nco_clusters", 0)
        sil = portfolio.attrs.get("nco_silhouette", 0.0)
        _clusters_drive = bool(portfolio.attrs.get("nco_uses_clusters", False))
        render_section_header(
            "Risk Structure",
            f"Correlation matrix ordered by cluster · {k} clusters · silhouette {sil:.2f}"
            + ("" if _clusters_drive else " · diagnostic only"),
            icon="layers", accent="violet")
        st.plotly_chart(create_cluster_correlation_heatmap(corr, labels),
                        width="stretch", key="cluster_corr_heatmap")
        st.caption(
            "Blocks along the diagonal are groups that move together — one bet wearing several "
            "tickers. Amber rules mark the cluster boundaries. Crisp blocks mean the clustering "
            "found real structure; a uniformly warm matrix means the universe is effectively a "
            "single bet, which no allocator can fix. "
            + ("These are the boundaries the allocator actually **used** to split capital."
               if _clusters_drive else
               "This style does **not** allocate from the cluster tree — the matrix is shown so "
               "you can see the structure the weights were computed against.")
        )


def _render_regime_tab(regime_result: Dict, regime_series: List, training_data: Optional[List] = None):
    """Tab 2 — Market regime analysis."""
    if not regime_result:
        st.info("Run analysis to populate regime data.")
        return

    regime_name = regime_result.get("regime", "UNKNOWN")
    mix_name = regime_result.get("mix_name", "—")
    confidence = regime_result.get("confidence", 0.0)
    score = regime_result.get("composite_score", 0.0)
    color = regime_result.get("color", "#888888")
    icon_key = regime_result.get("icon", "help-circle")
    factors_raw = regime_result.get("factors", {})

    # Current Regime Banner
    render_section_header("Current Market Regime", "10-day indicator window", icon="eye")

    # NOTE: the badge + factor scores are rendered as ONE self-contained HTML flex
    # row (not st.columns), so vertical centring is under our control — Streamlit's
    # column wrappers made the badge impossible to centre reliably. The flex row's
    # `align-items:center` centres the badge card against the factor list, period.

    # The regime detector uses FIXED factor weights (not calibrated); display them
    # so the percentages match what the composite actually used.
    try:
        from regime import FACTOR_WEIGHTS
        _fw = FACTOR_WEIGHTS
    except Exception:
        _fw = {}
    factor_order = [
        ("momentum", "Momentum", "strength"),
        ("trend", "Trend", "quality"),
        ("breadth", "Breadth", "quality"),
        ("velocity", "Velocity", "acceleration"),
        ("extremes", "Extremes", "type"),
        ("volatility", "Volatility", "regime"),
        ("acceptance", "Acceptance", "state"),
        ("correlation", "Correlation", "regime"),
    ]
    # Each factor score is a SIGNED value in [-2, +2] (bearish ↔ bullish), rendered
    # as a CENTER-ANCHORED diverging bar: a zero line in the middle, the fill
    # growing RIGHT (emerald) for a positive score or LEFT (rose) for a negative
    # one, with magnitude = |score| / 2. A 0→100% fill would misread a signed value.
    _rows = []
    for fkey, fbase, label_key in factor_order:
        fd = factors_raw.get(fkey, {})
        fs = float(fd.get("score", 0.0))
        fl = fd.get(label_key, "—")
        _wpct = _fw.get(fkey)
        fname = f"{fbase} ({_wpct*100:.0f}%)" if _wpct is not None else fbase
        half = min(50.0, abs(fs) / 2.0 * 50.0)
        if fs > 0.05:
            val_color = "var(--emerald)"
            fill = (f'<div style="position:absolute; left:50%; top:0; bottom:0; '
                    f'width:{half}%; background:var(--emerald); border-radius:0 3px 3px 0;"></div>')
        elif fs < -0.05:
            val_color = "var(--rose)"
            fill = (f'<div style="position:absolute; right:50%; top:0; bottom:0; '
                    f'width:{half}%; background:var(--rose); border-radius:3px 0 0 3px;"></div>')
        else:
            val_color = "var(--ink-tertiary)"
            fill = ""
        _rows.append(
            f'<div style="margin:0 0 12px 0;">'
            f'<div style="display:flex; justify-content:space-between; font-size: 0.88rem; margin-bottom:4px;">'
            f'<span style="color:var(--ink-primary); font-weight:600;">{fname}</span>'
            f'<span style="color:var(--ink-tertiary);">{fl} '
            f'<span style="color:{val_color}; font-weight:700;">({fs:+.1f})</span></span>'
            f'</div>'
            f'<div style="position:relative; height:8px; background:var(--bg-elevated); border-radius:3px; overflow:hidden;">'
            f'{fill}'
            f'<div style="position:absolute; left:50%; top:0; bottom:0; width:1px; background:var(--border-active); transform:translateX(-0.5px);"></div>'
            f'</div>'
            f'</div>'
        )
    _factors_html = "".join(_rows)
    _badge_icon = get_icon(icon_key, size=40, stroke_width=1.5)
    _fs_icon = get_icon("activity", size=16, stroke_width=1.8)

    # ── ONE flex row: factor scores (left, flex:2) + regime badge (right, flex:1).
    #    align-items:stretch makes both columns equal-height; the badge card is
    #    height:100% so it runs FLUSH top-and-bottom with the factor list.
    st.markdown(
        f'<div style="display:flex; align-items:stretch; gap:24px; margin-top:8px;">'
        # LEFT — factor scores (flex:1.7)
        f'<div style="flex:1.7; min-width:0;">'
        f'<div style="display:flex; align-items:center; gap:8px; margin:0 0 4px 0;">'
        f'<span style="color:var(--cyan, #6CD3D7); display:inline-flex;">{_fs_icon}</span>'
        f'<span style="font-family:var(--display); font-size: 1.1rem; font-weight:700; '
        f'text-transform:uppercase; letter-spacing:0.06em; color:var(--ink-primary);">Factor Scores</span>'
        f'</div>'
        f'<div style="font-family:var(--data); font-size: 0.82rem; color:var(--ink-tertiary); margin:0 0 12px 0;">'
        f'Signed composite inputs · −2 bearish ↔ +2 bullish</div>'
        f'<div style="display:flex; justify-content:space-between; font-family:var(--data); '
        f'font-size: 0.74rem; letter-spacing:0.08em; color:var(--ink-tertiary); '
        f'text-transform:uppercase; margin:0 0 8px 0;">'
        f'<span>−2 Bearish</span><span>0 Neutral</span><span>+2 Bullish</span></div>'
        f'{_factors_html}'
        f'</div>'
        # RIGHT — regime badge card (flex:1), flush to the factor list height
        f'<div style="flex:1; display:flex; min-width:0;">'
        f'<div class="regime-badge" style="width:100%; height:100%; border-color:{color}66; '
        f'background:linear-gradient(160deg, {color}12 0%, {color}05 45%, transparent 100%), var(--glass);">'
        f'<div class="regime-icon">{_badge_icon}</div>'
        f'<div class="regime-name" style="color:{color}; font-size: 2.3rem;">{regime_name.replace("_", " ")}</div>'
        f'<div class="regime-sub">{mix_name}</div>'
        f'<div class="regime-score">Score: {score:+.2f}</div>'
        f'<div class="regime-conf">'
        f'<div class="conf-bar-bg"><div class="conf-bar-fill" style="width:{confidence*100:.0f}%; background:{color};"></div></div>'
        f'<span style="color:{color}; font-size: 1.1rem; font-weight:700;">{confidence:.0%} confidence</span>'
        f'</div></div></div>'
        f'</div>',
        unsafe_allow_html=True,
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

                '<div class="intel-method-tile tile-learns">'
                    '<div class="tile-label">Momentum &amp; Trend</div>'
                    '<div class="tile-body">'
                        'RSI trajectory, oscillator direction, price/MA alignment and the share of '
                        'names above their 200-DMA — the primary directional drivers (largest weights).'
                    '</div>'
                '</div>'

                '<div class="intel-method-tile tile-how">'
                    '<div class="tile-label">Breadth &amp; Velocity</div>'
                    '<div class="tile-body">'
                        'Cross-sectional participation and the first/second derivative of momentum '
                        '(is the move accelerating or decaying) — confirmation and turning-point cues.'
                    '</div>'
                '</div>'

                '<div class="intel-method-tile tile-obj">'
                    '<div class="tile-label">Extremes, Volatility &amp; Acceptance</div>'
                    '<div class="tile-body">'
                        'Z-score crowding, Bollinger band-width regime, and the volume-profile '
                        'value distribution (discount vs premium) — stress and mean-reversion context.'
                    '</div>'
                '</div>'

                '<div class="intel-method-tile tile-safety">'
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
        _section_divider()
        render_section_header("Regime Score History", "Rolling 10-day composite", icon="activity", accent="emerald")

        regimes_seq = [r.regime for r in regime_series_to_use]
        transitions = sum(1 for i in range(1, len(regimes_seq)) if regimes_seq[i] != regimes_seq[i-1])
        # The chart and the cards share the same underlying panel as the sidebar
        # regime card (see _detect_regime_cached + _load_historical_data), so the
        # last bar of the chart is the canonical regime by construction.
        last_regime = regimes_seq[-1] if regimes_seq else "—"
        prev_regime = regimes_seq[-2] if len(regimes_seq) > 1 else "—"

        if CHARTS_AVAILABLE:
            fig_rh = create_regime_history_chart(regime_series_to_use)
            st.plotly_chart(fig_rh, width='stretch', key="tab2_regime_history")
            st.caption(
                "The composite score blends eight factors with **fixed** weights, so the same "
                "market conditions always produce the same reading. The shaded band is "
                "confidence: wider means the factors disagree. This is **context only** — the "
                "portfolio is curated from the return covariance and is not conditioned on the "
                "regime, so a bearish reading does not move a single weight."
            )

        c1, c2, c3 = st.columns(3)

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

        with c1:
            render_metric_card("Transitions", str(transitions), "Over analysis window", "info")
        with c2:
            render_metric_card("Current", last_regime.replace("_", " "), "Latest", regime_color(last_regime))
        with c3:
            render_metric_card("Prior", prev_regime.replace("_", " "), "Previous", regime_color(prev_regime))


def _render_system_tab(training_window: List):
    """Tab — System configuration + methodology reference (Obsidian Quant)."""
    # ── Configuration — the run's settings as a clean KV readout ───────────────
    render_section_header("Configuration", "Run settings & data source", icon="settings", accent="cyan")
    # Everything here comes from the FROZEN run_context — the settings this book
    # was actually built under, never the live sidebar. Browsing after a run
    # must not relabel a curated portfolio.
    _ctx = st.session_state.get("run_context") or {}
    _pf = st.session_state.get("portfolio")
    _at = _pf.attrs if _pf is not None and hasattr(_pf, "attrs") else {}
    _style = _ctx.get("investment_style", "—")
    _spec = _style_spec(_ctx)
    _max_eff = _at.get("max_pos_pct_eff", st.session_state.max_pos_pct)
    _max_relaxed = abs(_max_eff - st.session_state.max_pos_pct) > 1e-9
    _disp = _at.get("nco_rc_dispersion")
    _solved = _at.get("nco_rc_dispersion_solved")
    details = {
        "Version": VERSION,
        "Portfolio Style": _style,
        "Curation Method": f"{_spec['label']} ({_spec['family']})",
        "Weight Formula": _spec["formula"],
        "Risk Clusters": f"{_at.get('nco_clusters', '—')} "
                         f"(silhouette {_at.get('nco_silhouette', 0):.2f})"
                         + ("" if _spec["uses_clusters"] else " — diagnostic only"),
        "Risk Balance": (
            f"dispersion {_disp:.3f}"
            + (f" (solved {_solved:.3f})" if _solved is not None
               and _spec["rc_target"] == "equal" else "")
            + (" · target 0.000" if _spec["rc_target"] == "equal" else " · not targeted")
            if _disp is not None else "—"),
        "Risk Concentration": f"{_at.get('nco_rc_concentration', 0):.2f}x equal share",
        "Positions": (
            f"{_at.get('nco_positions_delivered', 0)} of "
            f"{_at.get('nco_positions_requested', '-')} requested"
            + ("" if not _at.get("nco_positions_short")
               else f" - {_at['nco_positions_short']} short ("
                    + ("eligible universe exhausted"
                       if _at.get("nco_short_cause") == "universe"
                       else "allocator zeroed names") + ")")),
        "Universe": (
            f"{_at.get('nco_universe', 0)} eligible"
            + (f" of {_at['nco_universe_requested']} in universe"
               if _at.get("nco_universe_requested") else "")
            + (f" · {len(_at.get('nco_universe_excluded') or {})} excluded"
               f" (<{_at.get('nco_coverage_required', 0.8):.0%} history)"
               if _at.get("nco_universe_excluded") else "")),
        "Estimation Window": f"{_at.get('nco_obs', 0)} daily observations",
        "Ex-ante Volatility": f"{_at.get('nco_port_vol_ann', 0):.2%}",
        "Max Position": f"{_max_eff*100:.1f}%" + (" (relaxed)" if _max_relaxed else ""),
        "Data Source": "yfinance (NSE)",
        "Lookback Period": f"{len(training_window)} days",
    }
    render_kv_table(details)
    if _max_relaxed:
        st.caption(
            f"Cap relaxed from the nominal "
            f"{st.session_state.max_pos_pct*100:.0f}% because the selected position count "
            "made them mathematically infeasible (too few/many positions to satisfy both "
            "the cap and 100% allocation)."
        )

    _section_divider()

    # ── Methodology ───────────────────────────────────────────────────────────
    render_section_header("Methodology", "How a portfolio is curated",
                          icon="target", accent="emerald")
    _m_spec = _style_spec(st.session_state.get("run_context") or {})
    method_html = (
        '<div class="intel-method-card">'
            '<div class="intel-method-header">'
                '<div class="intel-method-title">Curation Pipeline</div>'
                '<div class="intel-method-pill">cluster &rarr; allocate &rarr; size</div>'
            '</div>'
            '<div class="intel-method-lede">'
                'Capital is allocated from the return covariance structure. Nothing here '
                'forecasts returns &mdash; the book is built to spread risk across genuinely '
                'distinct exposures, not to predict which holding will win.'
            '</div>'
            '<div class="intel-method-grid">'

                '<div class="intel-method-tile tile-learns">'
                    '<div class="tile-label">Cluster</div>'
                    '<div class="tile-body">'
                        'Holdings are grouped by <code>d = sqrt(0.5(1 - &rho;))</code> correlation '
                        'distance using Ward linkage, with the cluster count chosen by silhouette '
                        'score. Typically resolves to ~3 groups &mdash; matching the eigenvalue '
                        'participation ratio of the same matrix.'
                    '</div>'
                '</div>'

                '<div class="intel-method-tile tile-how">'
                    '<div class="tile-label">Allocate</div>'
                    '<div class="tile-body">'
                        + {
                            "EQUAL": ('Equal weight: every selected holding receives an identical '
                                      '<code>1/N</code> share, ignoring the covariance entirely. '
                                      'Shown alongside the cluster structure so the risk it leaves '
                                      'unbalanced is visible.'),
                            "ERC": ('Equal Risk Contribution: weights are solved by cyclical '
                                    'coordinate descent so that <code>w<sub>i</sub> &times; '
                                    '(&Sigma;w)<sub>i</sub></code> is identical for every holding '
                                    '&mdash; each name contributes the same share of portfolio '
                                    'variance. Nothing is inverted, and the Risk Contribution chart '
                                    'shows directly whether the solver reached its target.'),
                            "HRP": ('Hierarchical Risk Parity: recursive bisection splits capital '
                                    'between sub-clusters in inverse proportion to their variance. '
                                    'No matrix is inverted, which is what makes it robust when '
                                    'correlations are high and the sample is short.'),
                          }.get(_m_spec["short"] if _m_spec["short"] in ("ERC", "HRP", "EQUAL")
                                else "EQUAL", _m_spec["formula"])
                    + '</div>'
                '</div>'

                '<div class="intel-method-tile tile-obj">'
                    '<div class="tile-label">What it targets</div>'
                    '<div class="tile-body">'
                        + _m_spec["evidence"].replace("--", "&mdash;")
                    + '</div>'
                '</div>'

                '<div class="intel-method-tile tile-safety">'
                    '<div class="tile-label">Why not forecast</div>'
                    '<div class="tile-body">'
                        'Grinold\'s Fundamental Law caps forecast-driven excess return at '
                        '<code>IR = IC &times; &radic;BR &times; TC</code>. At &rho; 0.52 these '
                        '30 ETFs are only ~1.9 independent bets, so that ceiling is ~1%/yr '
                        'however good the signal. Covariance is estimable where expected '
                        'returns are not.'
                    '</div>'
                '</div>'

            '</div>'
        '</div>'
    )
    st.markdown(method_html, unsafe_allow_html=True)


def _sync_broker_json(json_data, quantity_map: Dict[str, int]) -> Tuple[list, int, int]:
    """Map curated per-symbol units into a broker order-template JSON.

    Walks each instrument in the template, and where its
    ``instrument.tradingsymbol`` matches a curated holding WITH units > 0,
    writes the holding's unit count into ``params.quantity``. A match with
    units == 0 is left untouched rather than zeroing out the template's
    existing quantity — the method card promises non-matching instruments
    are "untouched", and a matched-but-zero-unit holding silently
    zeroing a possibly-intentional manual quantity was a third, undocumented
    case (see AUDIT_DIRECTIVES.md B8). Returns (mutated JSON, instruments
    updated, instruments matched-but-skipped-for-zero-units).
    """
    updated = 0
    skipped_zero = 0
    for item in json_data:
        try:
            symbol = item.get("instrument", {}).get("tradingsymbol")
            if symbol and symbol in quantity_map and "params" in item:
                qty = int(quantity_map[symbol])
                if qty > 0:
                    item["params"]["quantity"] = qty
                    updated += 1
                else:
                    skipped_zero += 1
        except Exception:
            continue
    return json_data, updated, skipped_zero


def _render_broker_sync_tab(portfolio: pd.DataFrame):
    """Tab — Broker JSON Sync: write curated units into broker order templates.

    Reads the LIVE curated portfolio (no CSV re-upload) and maps each holding's
    unit count onto the matching instrument's ``params.quantity`` in every
    uploaded broker template (e.g. Kite ETF.json), producing ready-to-import
    order files. The natural final step of the flow: curate → sync → execute.
    """
    import json as _json

    render_section_header(
        "Broker JSON Sync",
        "Write curated units into broker order templates · curate → sync → execute",
        icon="download",
        accent="cyan",
    )

    # Guard: nothing to sync until a portfolio has been curated.
    if portfolio is None or portfolio.empty or "symbol" not in portfolio.columns or "units" not in portfolio.columns:
        render_interpretation_card(
            title="NO CURATED PORTFOLIO",
            body=(
                "Run an analysis first — the sync uses the live curated portfolio "
                "directly, so there is nothing to map onto your broker templates yet."
            ),
            color="warning",
        )
        return

    # Build the symbol → units map from the live portfolio (units ≥ 0, integer).
    qty_map: Dict[str, int] = {
        str(sym): int(u)
        for sym, u in zip(portfolio["symbol"], portfolio["units"].fillna(0))
    }
    tradable = sum(1 for u in qty_map.values() if u > 0)

    # ── Balanced two-column layout, mirroring the Intelligence tab exactly ─────
    #    col1 = status card + template uploader
    #    col2 = results table + totals line + per-file downloads
    col1, col2 = st.columns([1, 1])

    # Process uploaded templates once, up front, so both columns read the same
    # deterministic result set (status card, results table, download buttons).
    json_files = st.session_state.get("broker_sync_json_uploader")
    results = []  # (fname, payload_or_None, updated_count, skipped_zero_count, error_or_None)
    if json_files:
        for j_file in json_files:
            try:
                j_file.seek(0)
                content = _json.load(j_file)
                updated_json, count, skipped_zero = _sync_broker_json(content, qty_map)
                results.append((j_file.name, _json.dumps(updated_json, indent=4), count, skipped_zero, None))
            except Exception as e:
                results.append((j_file.name, None, 0, 0, str(e)))
    n_templates = len(results)
    ok = sum(1 for _, p, _, _, _ in results if p is not None)
    total_updated = sum(c for _, p, c, _, _ in results if p is not None)
    total_skipped_zero = sum(s for _, p, _, s, _ in results if p is not None)

    with col1:
        if n_templates == 0:
            render_interpretation_card(
                title="AWAITING TEMPLATES",
                body=(
                    f"Curated book holds <strong>{tradable}</strong> tradable holding(s). "
                    "Upload one or more broker order-template JSONs (e.g. Kite "
                    "<strong>ETF.json</strong>) to sync their quantities."
                ),
                color="info",
            )
        elif ok == 0:
            render_interpretation_card(
                title="NO FILES SYNCED",
                body=(
                    f"None of the <strong>{n_templates}</strong> uploaded template(s) could be "
                    "processed. Check that each is a valid broker order JSON."
                ),
                color="danger",
            )
        else:
            _skip_note = (
                f" <strong>{total_skipped_zero}</strong> matched instrument(s) left untouched "
                "(curated at 0 units)."
                if total_skipped_zero > 0 else ""
            )
            render_interpretation_card(
                title="READY TO EXPORT",
                body=(
                    f"Synced <strong>{ok}/{n_templates}</strong> template(s) · "
                    f"<strong>{total_updated}</strong> instrument(s) updated from "
                    f"<strong>{tradable}</strong> tradable holding(s).{_skip_note} "
                    "Download the import-ready files on the right."
                ),
                color="success",
            )

        st.file_uploader(
            "Upload broker JSON templates",
            type=["json"],
            accept_multiple_files=True,
            help="Your original broker order files (e.g. ETF.json). Each instrument's "
                 "quantity is set from the curated units for its trading symbol.",
            key="broker_sync_json_uploader",
            label_visibility="collapsed",
        )

    with col2:
        if n_templates == 0:
            st.markdown(
                '<div class="intel-table-wrap"><table class="portfolio-table-2col">'
                '<colgroup><col style="width:52%;"><col style="width:23%;">'
                '<col style="width:25%;"></colgroup>'
                '<thead><tr><th class="col-iw-factor">Template</th>'
                '<th class="col-iw-long">Updated</th>'
                '<th class="col-iw-short">Status</th></tr></thead>'
                '<tbody><tr><td colspan="3" '
                'style="text-align:center; color:var(--ink-tertiary); '
                'font-family:var(--data); font-size: 0.88rem; padding:var(--sp-6) var(--sp-3);">'
                'No templates uploaded</td>'
                '</tr></tbody></table></div>',
                unsafe_allow_html=True,
            )
        else:
            rows_html = []
            for fname, payload, count, skipped_zero, err in results:
                if err is not None:
                    rows_html.append(
                        f'<tr>'
                        f'<td class="iw-label">{html_module.escape(fname)}</td>'
                        f'<td class="iw-long" style="color:var(--rose)">—</td>'
                        f'<td class="iw-short" style="color:var(--rose)">ERROR</td>'
                        f'</tr>'
                    )
                else:
                    c_color = "var(--emerald)" if count > 0 else "var(--ink-secondary)"
                    s_color = "var(--emerald)" if count > 0 else "var(--amber)"
                    # Distinguish "matched nothing at all" from "matched, but
                    # every match was a 0-unit holding left untouched" — the
                    # old NO MATCH label conflated both (see AUDIT_DIRECTIVES.md B8).
                    if count > 0:
                        s_text = "SYNCED"
                    elif skipped_zero > 0:
                        s_text = f"SKIPPED ({skipped_zero} @ 0 units)"
                    else:
                        s_text = "NO MATCH"
                    rows_html.append(
                        f'<tr>'
                        f'<td class="iw-label">{html_module.escape(fname)}</td>'
                        f'<td class="iw-long" style="color:{c_color}">{count}</td>'
                        f'<td class="iw-short" style="color:{s_color}">{s_text}</td>'
                        f'</tr>'
                    )
            st.markdown(
                f'''
                <div class="intel-table-wrap">
                    <table class="portfolio-table-2col">
                        <colgroup>
                            <col style="width:52%;">
                            <col style="width:23%;">
                            <col style="width:25%;">
                        </colgroup>
                        <thead>
                            <tr>
                                <th class="col-iw-factor">Template</th>
                                <th class="col-iw-long">Updated</th>
                                <th class="col-iw-short">Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {"".join(rows_html)}
                        </tbody>
                    </table>
                </div>
                ''',
                unsafe_allow_html=True,
            )

            for fname, payload, count, skipped_zero, err in results:
                if err is None:
                    st.download_button(
                        label=f"Download updated {fname}",
                        data=payload,
                        file_name=f"updated_{fname}",
                        mime="application/json",
                        use_container_width=True,
                        key=f"broker_sync_dl_{fname}",
                    )

    # ── Full-width METHOD card (Obsidian Quant fidelity) — mirrors the
    #    Intelligence tab's method card: header + pill + lede + tile grid.
    method_html = (
        '<div class="intel-method-card">'
            '<div class="intel-method-header">'
                '<div class="intel-method-title">How the Sync Works</div>'
                '<div class="intel-method-pill">'
                'symbol → units → params.quantity'
                '</div>'
            '</div>'
            '<div class="intel-method-lede">'
                'The Broker Sync closes the loop from a curated book to broker execution. '
                'It reads the <strong>live curated portfolio</strong> directly — no CSV '
                're-upload — and writes each holding\'s unit count into the matching '
                'instrument of every broker order template you upload.'
            '</div>'
            '<div class="intel-method-grid">'

                '<div class="intel-method-tile tile-learns">'
                    '<div class="tile-label">Source</div>'
                    '<div class="tile-body">'
                        'The live curated portfolio in memory — its <code>symbol</code> and '
                        '<code>units</code> columns, exactly as shown in the Portfolio tab. '
                        'Nothing to export or re-import.'
                    '</div>'
                '</div>'

                '<div class="intel-method-tile tile-how">'
                    '<div class="tile-label">Mapping</div>'
                    '<div class="tile-body">'
                        'For each instrument in a template, if its '
                        '<code>instrument.tradingsymbol</code> matches a curated holding, '
                        'that holding\'s units are written to <code>params.quantity</code>.'
                    '</div>'
                '</div>'

                '<div class="intel-method-tile tile-obj">'
                    '<div class="tile-label">Templates</div>'
                    '<div class="tile-body">'
                        'Standard broker order JSONs (e.g. Kite <code>ETF.json</code>). '
                        'Upload as many as you like; each is synced and offered as a '
                        'separate <code>updated_*</code> download.'
                    '</div>'
                '</div>'

                '<div class="intel-method-tile tile-safety">'
                    '<div class="tile-label">Safety</div>'
                    '<div class="tile-body">'
                        'Non-destructive: instruments with no matching holding, or matching a '
                        'holding curated at <strong>0 units</strong>, are left '
                        '<strong>untouched</strong> rather than zeroed out — and the original '
                        'files are never modified, you download fresh copies.'
                    '</div>'
                '</div>'

            '</div>'
        '</div>'
    )
    st.markdown(method_html, unsafe_allow_html=True)


def _render_analytics_tab(portfolio: pd.DataFrame):
    """Tab — Portfolio Analytics: track the curated book vs a universe-matched
    benchmark (adapted from the SWING Analysis engine, re-themed to Obsidian Quant).

    Anchored to the analysis date (metrics run anchor → today). Shows a normalized
    portfolio-vs-benchmark chart plus risk-adjusted, risk, and benchmark-comparison
    metric cards. Uses the LIVE curated portfolio (no upload); the yfinance fetch is
    cached (see _analytics_series_cached).

    On Swing / SIP runs the chart carries a THIRD line: the same selected names
    weighted 1/N (the equal-weight shadow book). The benchmark measures the book
    against the market; the shadow measures the weighting decision alone, since
    selection is identical across styles. Omitted on Equal Weight runs, where it
    would duplicate the portfolio line.
    """
    from analytics import resolve_benchmark, resolve_risk_free_rate, compute_metrics
    from charts import create_benchmark_comparison_chart

    # Scope comes from the FROZEN run_context — the universe this book was
    # actually curated under. Browsing the sidebar after a run must not resolve
    # the benchmark against a different universe than the holdings came from.
    _ctx = st.session_state.get("run_context") or {}
    universe = _ctx.get("universe") or st.session_state.get("selected_universe") or "default"
    selected_index = _ctx.get("selected_index") or st.session_state.get("selected_index")
    bench_ticker, bench_name = resolve_benchmark(universe, selected_index)
    RISK_FREE_RATE = resolve_risk_free_rate(bench_ticker)

    # Guard: needs a curated portfolio with priced units.
    if portfolio is None or portfolio.empty or "symbol" not in portfolio.columns or "units" not in portfolio.columns:
        render_interpretation_card(
            title="NO CURATED PORTFOLIO",
            body=(
                "Run an analysis first — analytics track the live curated portfolio's "
                "performance against the benchmark, so there is nothing to measure yet."
            ),
            color="warning",
        )
        return

    # ── ANCHOR = the analysis date THIS PORTFOLIO was curated under (frozen in
    #    run_context — see _intel_context's docstring), NOT the live sidebar
    #    date picker. Browsing the sidebar to a different date after a run must
    #    not silently re-anchor the already-curated book's performance window.
    #    Metrics run anchor -> today; the window is dictated by the anchor (no
    #    user timeframe picker). Handle edge cases. ──
    _run_ctx = st.session_state.get("run_context") or {}
    _sel = _run_ctx.get("anchor_date") or st.session_state.get("selected_date")
    anchor_date = _sel if isinstance(_sel, date) else (
        _sel.date() if isinstance(_sel, datetime) else datetime.now().date()
    )
    today = datetime.now().date()

    # Edge: anchor is today or in the future → no forward history to measure.
    if anchor_date >= today:
        render_interpretation_card(
            title="ANCHORED TO TODAY",
            body=(
                f"The analysis date is <strong>{anchor_date.strftime('%d %b %Y')}</strong>, so there "
                "is no forward performance history yet. Analytics measure the curated book from the "
                "analysis date to the present — pick an earlier analysis date (with at least a few "
                "trading days elapsed) to see metrics."
            ),
            color="info",
        )
        return

    _elapsed_days = (today - anchor_date).days
    # Fetch enough calendar days to cover the anchor window (+buffer for alignment);
    # build_return_series then clips precisely to anchor → today.
    days_back = _elapsed_days + 5
    anchor_dt = datetime.combine(anchor_date, datetime.min.time())

    # ── Fetch + compute (CACHED) ───────────────────────────────────────────────
    #  The heavy yfinance fetch is behind _analytics_series_cached, keyed on the
    #  (symbols, units, anchor, benchmark) tuple, so it runs at most ONCE per
    #  unique window and every tab-switch / cosmetic rerun hits cache. Metrics
    #  render immediately on opening the tab — a scoped spinner only shows during
    #  the genuine first (cache-miss) fetch.
    _symbols = tuple(str(s) for s in portfolio["symbol"].tolist())
    _units = tuple(float(u or 0) for u in portfolio["units"].tolist())

    # ── Equal-weight shadow book ───────────────────────────────────────────────
    # A third reference line on HRP runs. The benchmark answers "did the book
    # beat the market?"; this answers the narrower and more actionable question
    # "did the ALLOCATOR earn its complexity?" — the same holdings, same anchor,
    # same capital, split 1/N instead of by cluster variance. The shadow units
    # below are exactly what an Equal Weight run of this scope would have
    # produced, integer-lot flooring included, so it is a real alternative book
    # rather than an idealized fractional one.
    #
    # Suppressed on Equal Weight runs, where the trace would draw the portfolio
    # line twice.
    _style = _run_ctx.get("investment_style", "Equal Weight")
    _eq_capital = float(_run_ctx.get("capital") or st.session_state.get("capital") or 0.0)
    _alt_units: Optional[Tuple[float, ...]] = None
    # Drawn for every style EXCEPT equal weight itself, where the trace would
    # draw the portfolio line twice. Keyed off the registry code rather than the
    # display label so renaming a style cannot silently re-enable the duplicate.
    if _run_ctx.get("curation") != "EQUAL" and _eq_capital > 0 and "price" in portfolio.columns:
        _n = len(portfolio)
        _per_pos = _eq_capital / _n if _n else 0.0
        _prices = pd.to_numeric(portfolio["price"], errors="coerce")
        if _per_pos > 0 and _prices.notna().all() and (_prices > 0).all():
            _alt_units = tuple(float(np.floor(_per_pos / p)) for p in _prices)
            # An equal slice that can't buy a single share of even one name
            # makes the comparison meaningless rather than merely approximate.
            if not any(u > 0 for u in _alt_units):
                _alt_units = None

    with st.spinner(f"Loading performance history · {bench_name} benchmark…"):
        (port_value, port_returns, bench_returns, err, unpriced,
         alt_value, bench_value) = _analytics_series_cached(
            _symbols, _units, anchor_dt.isoformat(), days_back, bench_ticker, bench_name,
            alt_units=_alt_units,
        )

    if err:
        render_interpretation_card(
            title="DATA UNAVAILABLE",
            body=f"Could not build the performance series: {html_module.escape(err)}",
            color="danger",
        )
        return

    # Surface any held symbols that couldn't be priced/matched — the metrics below
    # exclude them, so the reported performance is for the priced remainder only.
    if unpriced:
        _shown = ", ".join(html_module.escape(s) for s in unpriced[:12])
        _more = f" (+{len(unpriced) - 12} more)" if len(unpriced) > 12 else ""
        render_interpretation_card(
            title="SOME HOLDINGS NOT PRICED",
            body=(
                f"<strong>{len(unpriced)}</strong> held symbol(s) could not be priced and are "
                f"<strong>excluded</strong> from these metrics: {_shown}{_more}. "
                "The performance below reflects only the priced holdings."
            ),
            color="warning",
        )

    # Edge: too few trading days since the anchor to compute meaningful metrics.
    if len(port_returns) < 2:
        render_interpretation_card(
            title="NOT ENOUGH HISTORY YET",
            body=(
                f"Only <strong>{len(port_returns)}</strong> trading day(s) have elapsed since "
                f"<strong>{anchor_date.strftime('%d %b %Y')}</strong>. Risk and benchmark metrics "
                "need at least a few daily returns — check back after more trading days, or use an "
                "earlier analysis date."
            ),
            color="warning",
        )
        return

    m = compute_metrics(port_returns, bench_returns, RISK_FREE_RATE)

    # ── Relative performance: header → anchor-window chip → normalized chart ────
    _has_alt = alt_value is not None and len(alt_value) > 1 and float(alt_value.iloc[0]) != 0
    _rel_sub = (
        f"Portfolio vs {bench_name} vs Equal Weight · indexed to 100" if _has_alt
        else f"Portfolio vs {bench_name} · indexed to 100"
    )
    render_section_header("Relative Performance", _rel_sub, icon="activity", accent="amber")
    st.markdown(
        f'<div style="display:flex; align-items:center; gap:10px; margin:0 0 10px 0; '
        f'font-family:var(--data); font-size: 0.82rem; letter-spacing:0.04em; color:var(--ink-tertiary);">'
        f'<span style="display:inline-flex; align-items:center; gap:6px; padding:4px 12px; '
        f'border:1px solid var(--border-active); border-radius:999px; background:rgba(212,168,83,0.06); '
        f'color:var(--amber); text-transform:uppercase; font-weight:700;">'
        f'Anchored · {anchor_date.strftime("%d %b %Y")} → Today</span>'
        f'<span>{len(port_returns)} trading days · {_elapsed_days} calendar day(s) elapsed</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    # Normalize the benchmark from its PRICE series on the portfolio's own
    # calendar. (1 + returns).cumprod() would start a bar late and rebase there,
    # under-reporting the benchmark and disagreeing with the cards below.
    _bench_series = bench_value if (bench_value is not None and len(bench_value) > 1) else None
    if CHARTS_AVAILABLE and len(port_value) > 0:
        fig = create_benchmark_comparison_chart(
            port_value, _bench_series, bench_name, m.get("total_return", 0.0),
            alt_series=alt_value if _has_alt else None,
            alt_label="Equal Weight",
        )
        st.plotly_chart(fig, width="stretch", key="analytics_benchmark_chart")

    # Read the allocation decision out loud: the chart shows three lines, this
    # states the one number the third exists to produce — what the risk-based
    # allocator added, or cost, versus splitting the same holdings evenly.
    if not _has_alt:
        st.caption(
            f"All series are indexed to 100 at the anchor date, so the vertical gap between "
            f"lines is cumulative relative performance. **{bench_name}** is the market; the "
            f"portfolio line is the curated book."
        )
    if _has_alt:
        _eq_ret = (float(alt_value.iloc[-1]) / float(alt_value.iloc[0]) - 1.0) * 100.0
        _edge = m.get("total_return", 0.0) - _eq_ret
        _edge_color = "var(--emerald)" if _edge > 0 else "var(--rose)" if _edge < 0 else "var(--ink-tertiary)"
        # A real st.caption, not a hand-styled div. Matching the caption rule by
        # hand kept this line the same SIZE while leaving it in the mono data
        # face, and mono reads visibly larger than the sans captions at an
        # identical pixel size — so it never actually matched. Going through
        # st.caption inherits size, family, colour and leading from
        # ui/theme.css's stCaptionContainer rule and cannot drift from it.
        # Only the two value spans carry inline colour.
        st.caption(
            f'<strong style="color:var(--violet,#8B5CF6);">Equal Weight</strong> — the same '
            f'{len(portfolio)} holdings, same anchor, same capital, split 1/N instead of by '
            f'cluster variance — returned <strong>{_eq_ret:+.2f}%</strong>. '
            f'{html_module.escape(_style)} therefore added '
            f'<strong style="color:{_edge_color};">{_edge:+.2f}%</strong> on return. Expect this '
            f'to be negative as often as not: the allocator targets risk, and the return it '
            f'gives up is the price of the volatility it removes.',
            unsafe_allow_html=True,
        )

    # ── Head-to-head comparison ───────────────────────────────────────────────
    # One table, three books, read horizontally. This replaced four stacked
    # 6-card rows: every number was present but answering "how does my book
    # compare?" meant scanning disconnected blocks and holding figures in
    # memory. Only statistics that exist for a single book go here; genuinely
    # pairwise ones (beta, capture, tracking error) follow below.
    _cagr_ok = m.get("cagr_meaningful", True)
    _section_divider()
    render_section_header(
        "Head to Head",
        f"{_style} vs equal weight vs {bench_name}"
        + ("" if _cagr_ok else " · CAGR hidden, window too short to annualize"),
        icon="zap", accent="emerald",
    )

    _alt_m = None
    if _has_alt:
        _alt_r = alt_value.pct_change(fill_method=None).dropna()
        _alt_m = compute_metrics(_alt_r, bench_returns, RISK_FREE_RATE)
        _alt_total = (float(alt_value.iloc[-1]) / float(alt_value.iloc[0]) - 1.0) * 100.0
    _bench_m = None
    if bench_returns is not None and len(bench_returns) > 2:
        _bench_m = compute_metrics(bench_returns, bench_returns, RISK_FREE_RATE)

    def _col(metric, fmt="{:+.2f}%", src=None):
        vals = []
        for mm in (m, _alt_m, _bench_m):
            if mm is None:
                vals.append(None)
            else:
                vals.append(mm.get(metric))
        if src is not None:
            vals[1] = src
        return vals

    # (row label, metric key, format, higher_is_better, show?)
    rows_spec = [
        ("Period Return",   "total_return",  "{:+.2f}%", True,  True),
        ("CAGR",            "cagr",          "{:+.2f}%", True,  _cagr_ok),
        ("Volatility",      "volatility",    "{:.2f}%",  False, True),
        ("Sharpe",          "sharpe",        "{:.2f}",   True,  True),
        ("Sortino",         "sortino",       "{:.2f}",   True,  True),
        ("Max Drawdown",    "max_drawdown",  "{:.2f}%",  True,  True),
        ("Calmar",          "calmar",        "{:.2f}",   True,  _cagr_ok),
        ("VaR (95%)",       "var_95",        "{:.2f}%",  True,  True),
        ("CVaR (95%)",      "cvar_95",       "{:.2f}%",  True,  True),
        ("Win Rate",        "win_rate",      "{:.0f}%",  True,  True),
    ]

    heads = [_style, "Equal Weight", bench_name]
    body = []
    for label, key, fmt, hib, show in rows_spec:
        if not show:
            continue
        vals = _col(key)
        # Equal-weight period return comes from the shadow series directly, so
        # it matches the chart legend exactly rather than being recomputed.
        if key == "total_return" and _has_alt:
            vals[1] = _alt_total
        live = [(i, v) for i, v in enumerate(vals) if v is not None and np.isfinite(v)]
        best = None
        if len(live) > 1:
            best = (max(live, key=lambda x: x[1]) if hib else min(live, key=lambda x: x[1]))[0]
        cells = []
        for i, v in enumerate(vals):
            if v is None or not np.isfinite(v):
                cells.append('<td class="hh-num hh-na">—</td>')
            else:
                cls = "hh-num hh-best" if i == best else "hh-num"
                cells.append(f'<td class="{cls}">{fmt.format(v)}</td>')
        body.append(f'<tr><td class="hh-label">{html_module.escape(label)}</td>'
                    + "".join(cells) + "</tr>")

    _hh_css = (
        "<style>"
        "*{scrollbar-width:thin;scrollbar-color:#4B5563 transparent;}"
        "::-webkit-scrollbar{width:5px;height:5px;}"
        "::-webkit-scrollbar-track{background:transparent;}"
        "::-webkit-scrollbar-thumb{background:#4B5563;border-radius:3px;}"
        "::-webkit-scrollbar-thumb:hover{background:#6B7280;}"
        ".hh{width:100%;border-radius:10px;overflow:hidden;"
        "border:1px solid rgba(255,255,255,0.05);"
        "background:linear-gradient(145deg,rgba(17,24,39,0.45) 0%,rgba(17,24,39,0.4) 100%);}"
        ".hh table{width:100%;border-collapse:collapse;table-layout:fixed;}"
        ".hh thead th{background:linear-gradient(180deg,rgba(10,14,23,0.95) 0%,"
        "rgba(10,14,23,0.85) 100%);color:#4B5563;font-size: 0.74rem;font-weight:600;"
        "text-transform:uppercase;letter-spacing:0.1em;padding:0.7rem 0.6rem;"
        "border-bottom:2px solid rgba(212,168,83,0.3);"
        "font-family:'IBM Plex Mono',monospace;text-align:right;}"
        ".hh thead th.hh-h0{text-align:left;width:26%;}"
        ".hh td{padding:0.55rem 0.6rem;font-size: 0.88rem;"
        "border-bottom:1px solid rgba(255,255,255,0.04);"
        "font-family:'IBM Plex Mono',monospace;color:#CBD5E1;}"
        ".hh tr:hover td{background:rgba(212,168,83,0.04);}"
        ".hh td.hh-label{color:#94A3B8;}"
        ".hh td.hh-num{text-align:right;}"
        ".hh td.hh-best{color:#2DD4A8;font-weight:600;background:rgba(45,212,168,0.07);}"
        ".hh td.hh-na{color:#4B5563;}"
        "</style>"
    )
    # Measured against the current type scale, same caveat as the portfolio
    # table above: single-line header at --fs-xs, rows at --fs-base.
    _hh_natural = 38 + 37 * len(body) + 2
    _hh_h = min(560, _hh_natural)
    _hh_scroll = _hh_natural > 560
    _hh_head = ("<div class='hh'><table><thead><tr><th class='hh-h0'>Metric</th>"
                + "".join(f"<th>{html_module.escape(h)}</th>" for h in heads)
                + "</tr></thead><tbody>")
    components.html(
        "<html><head><meta charset='utf-8'></head>"
        "<body style='margin:0;background:transparent;'>"
        + _hh_css + _hh_head + "".join(body) + "</tbody></table></div></body></html>",
        height=_hh_h, scrolling=_hh_scroll,
    )
    st.caption(
        f"Green marks the best value in each row. **{_style}** is the curated book; "
        f"**Equal Weight** is the same {len(portfolio)} holdings split 1/N — the like-for-like "
        f"test of the allocator; **{bench_name}** is the market. Max Drawdown, VaR and CVaR are "
        f"negative numbers, so *higher is better* — the least negative wins. Expect the allocator "
        f"to lead on volatility and drawdown while trailing on return: that is the trade it makes, "
        f"not a fault."
    )

    # ── Relationship to benchmark ─────────────────────────────────────────────
    # These have no meaning for a single book — every one is a statistic ABOUT
    # the pairing — so they cannot live in the table above.
    _section_divider()
    render_section_header("Relationship to Benchmark", f"How the book moves with {bench_name}",
                          icon="compass", accent="cyan")
    r3 = st.columns(6)
    with r3[0]:
        _b = m.get("beta", 1)
        render_metric_card("Beta", f"{_b:.2f}", "Market sensitivity",
                           "warning" if _b > 1.2 else "info" if _b < 0.8 else "neutral")
    with r3[1]:
        if _cagr_ok:
            _a = m.get("alpha", 0)
            render_metric_card("Alpha", f"{_a:+.2f}%", "CAPM excess",
                               "success" if _a > 0 else "danger" if _a < 0 else "neutral")
        else:
            render_metric_card("Alpha", "—", "Window too short", "neutral")
    with r3[2]:
        render_metric_card("Correlation", f"{m.get('correlation', 0):.2f}",
                           f"R² {m.get('r_squared', 0):.2f}", "info")
    with r3[3]:
        render_metric_card("Tracking Error", f"{m.get('tracking_error', 0):.1f}%",
                           "Annualized", "info")
    with r3[4]:
        _uc = m.get("up_capture", 100)
        render_metric_card("Up Capture", f"{_uc:.0f}%", "In rising markets",
                           "success" if _uc > 100 else "warning")
    with r3[5]:
        _dc = m.get("down_capture", 100)
        render_metric_card("Down Capture", f"{_dc:.0f}%", "In falling markets",
                           "success" if _dc < 100 else "danger")
    st.caption(
        f"**Beta** is the book's sensitivity to {bench_name}; **Alpha** is return beyond what that "
        f"beta explains. **Up/Down Capture** are the share of the benchmark's rise and fall the book "
        f"participates in — the ideal pairing is above 100% up and below 100% down. **Tracking "
        f"Error** is the volatility of the difference, so it measures how far the book is allowed "
        f"to wander from the market, not whether it wandered profitably."
    )


def _render_header() -> None:
    """Render the main masthead header."""
    render_header(
        title=f"{PRODUCT_NAME}",
        tagline="Covariance-Based Portfolio Curation · Equal Weight · ERC · HRP · Live NSE Data"
    )


def _render_landing_page():
    """Render landing page with system status cards."""
    section_gap()

    col1, col2, col3 = st.columns(3, gap="small")

    with col1:
        render_system_card(
            title="PORTFOLIO",
            description="Capital allocated from the return covariance structure. No return "
                        "forecast is made — the book is built to spread risk across distinct "
                        "exposures.",
            specs=[
                ("Cluster", "Ward linkage on correlation distance"),
                ("Allocate", "1/N · equal risk contribution · cluster bisection"),
                ("Styles", " · ".join(METHOD_SPECS[k]["short"] for k in METHOD_ORDER)),
                ("Targets", "Volatility & drawdown, not excess return"),
            ],
            card_class="portfolio",
            icon="briefcase"
        )

    with col2:
        render_system_card(
            title="REGIME",
            description="Eight-factor market regime detection with fixed composite weights. "
                        "Context for reading the book — nothing downstream is conditioned on it.",
            specs=[
                ("Regimes", "Strong Bull · Bull · Weak Bull · Chop · Weak Bear · Bear · Crisis"),
                ("Factors", "Momentum · Trend · Breadth · Acceptance"),
                ("Output", "Composite score + confidence"),
                ("History", "Rolling window timeline"),
            ],
            card_class="regime",
            icon="compass"
        )

    with col3:
        render_system_card(
            title="RISK STRUCTURE",
            description="The correlation matrix reordered by cluster, so the blocks that drive "
                        "the allocation are visible rather than implied.",
            specs=[
                ("Clusters", "Silhouette-selected, typically ~3"),
                ("Per-holding", "Weight · risk share · volatility · independence"),
                ("Diagnostic", "Risk share vs capital share gap"),
                ("Benchmark", "Equal-weight shadow of the same book"),
            ],
            card_class="strategies",
            icon="layers"
        )

    section_gap()
    
    st.markdown("""
    <div class='landing-prompt'>
        <h4>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polygon points="10 8 16 12 10 16 10 8"/></svg>
            AWAITING PARAMETERS
        </h4>
        <p>Configure via the <strong>Sidebar</strong>: select <strong>Analysis Date</strong>, <strong>Investment Style</strong>, <strong>Capital</strong>, and <strong>Number of Positions</strong>.<br>
           Execute <strong>Run Analysis</strong> to cluster the universe and curate a risk-balanced portfolio.<br>
           <span style="color:var(--ink-secondary); font-size:0.85em; margin-top:0.5rem; display:inline-block;">System will detect market regime · Cluster the correlation structure · Allocate across clusters</span></p>
    </div>
    """, unsafe_allow_html=True)


def _render_results(display_capital: float):
    """Render results page with portfolio, regime, and system tabs."""
    portfolio = st.session_state.portfolio
    if portfolio.empty or "value" not in portfolio.columns:
        st.warning("Portfolio is empty. Adjust parameters and re-run.")
        return

    current_df = st.session_state.current_df
    regime_d = st.session_state.regime_result_dict or {}
    training_window = st.session_state.get("training_data_window", [])

    total_value = portfolio["value"].sum()
    cash_remaining = display_capital - total_value

    # Top metrics — logical color coding
    mc1, mc2, mc3, mc4 = st.columns(4)

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

    with mc1:
        render_metric_card("Deployed", f"₹{total_value:,.0f}", f"{total_value / display_capital * 100:.0f}% of capital", "info")
    with mc2:
        render_metric_card("Cash", f"₹{cash_remaining:,.0f}", f"{cash_pct:.1f}% remaining", cash_color)
    with mc3:
        render_metric_card("Positions", str(len(portfolio)), "Curated holdings", "warning")
    with mc4:
        render_metric_card(
            "Risk Concentration",
            f"{_rc_ratio:.2f}x" if np.isfinite(_rc_ratio) else "—",
            "Top holding vs equal risk share", _rc_color)

    # No divider before the tabs: the tab bar carries its own bottom rule, so a
    # section-divider directly above it drew two horizontal lines 40px apart
    # separating the same two things. The block gap alone reads the boundary.

    # Tab background pattern
    st.markdown('<div class="tab-bg portfolio"></div>', unsafe_allow_html=True)

    # Tabs
    tabs = ["Portfolio", "Analytics", "Regime", "Broker Sync", "System"]
    t_objs = st.tabs(tabs)

    with t_objs[0]:
        _render_portfolio_tab(portfolio, current_df, display_capital)

    with t_objs[1]:
        _render_analytics_tab(portfolio)

    with t_objs[2]:
        _render_regime_tab(regime_d, st.session_state.get("regime_history_series", []), training_window)

    with t_objs[3]:
        _render_broker_sync_tab(portfolio)

    with t_objs[4]:
        _render_system_tab(training_window)

    # Footer
    _section_divider()
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
    # Reset the run clock: the tracker is per-SESSION (see metrics.get_metrics),
    # so without this the summary's "Total Duration" reports time since the
    # session's first run, not this run's wall time.
    import time as _time
    metrics.start_time, metrics.end_time = _time.time(), 0.0
    st.session_state.debug_info = []
    st.session_state.regime_history_series = None

    # Resolve the universe to get symbols
    try:
        symbols_list, status_msg = resolve_universe(universe, index)
    except Exception as e:
        st.error(f"Error resolving universe: {e}")
        st.stop()

    if not symbols_list:
        st.error(f"Could not load {index or universe}: {status_msg}")
        st.stop()

    try:
        # Print main header with run details
        from logger_config import generate_run_id
        current_run_id = generate_run_id()  # Fresh ID for each analysis
        run_details = {
            "Analysis Date": selected_date_display,
            "Universe": universe,
            "Index": index if index else "N/A",
            "Symbols": len(symbols_list),
            "Investment Style": investment_style,
            "Capital": f"₹{capital:,.0f}",
            "Positions": num_positions,
            "Run ID": current_run_id[-12:],
            "Started": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        log.main_header(f"PRAGYAM | Portfolio Intelligence | {VERSION}", run_details)

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

        if not symbols_list:
            st.error("Symbol universe empty — select a valid universe.")
            st.stop()

        all_hist = _load_historical_data(selected_date, LOOKBACK_FILES, symbols_key)
        if not all_hist:
            st.error("No historical data loaded. Check universe selection and date range.")
            st.stop()

        metrics.end_phase("data_fetching", success=True, items=len(all_hist))
        metrics.days_count = len(all_hist)

        progress_bar(progress_container, 14, "Data Loaded", f"{len(all_hist)} days · {len(symbols_list)} symbols")

        # Regime detection — pass intelligence context so the 8 factor weights are
        # the learned ones (Intelligence mode) or the shared defaults (Standard).
        progress_bar(progress_container, 16, "Detecting Market Regime", "8-factor composite scoring")
        regime_result = _detect_regime_cached(selected_date, symbols_key)
        regime_name = regime_result.get("regime", "UNKNOWN")
        confidence = regime_result.get("confidence", 0.0)

        st.session_state.regime_result_dict = regime_result
        st.session_state.suggested_mix = regime_result.get("mix_name", "Chop/Consolidate Mix")
        # Keep the regime-computation markers in sync so the sidebar card's
        # change-detection agrees with what the main flow just computed (otherwise
        # the sidebar can think the card is fresh when it is a run behind).
        st.session_state.regime_date = st.session_state.get("selected_date")
        st.session_state.regime_symbols_key = symbols_key
        st.session_state.training_data_window = all_hist

        if len(all_hist) < 10:
            st.error(f"Insufficient training data: {len(all_hist)} days (need ≥10).")
            metrics.end_phase("data_fetching", success=False, error_msg=f"Insufficient data: {len(all_hist)} days")
            st.stop()

        if not st.session_state.suggested_mix:
            st.error("Market regime could not be determined. Select a valid date.")
            metrics.end_phase("data_fetching", success=False, error_msg="Regime undetermined")
            st.stop()

        st.session_state.current_df = all_hist[-1][1] if all_hist else pd.DataFrame()

        # Mirror the Phase 1 milestone to the terminal so the console trace
        # carries the same checkpoints the progress bar showed.
        log.section("Data & Regime", phase="PHASE 1")
        log.item("Historical Panel", f"{len(all_hist)} trading days · {len(symbols_list)} symbols")
        log.item("Market Regime", f"{regime_name.replace('_', ' ')} · {confidence:.0%} confidence")

        progress_bar(
            progress_container, 20, "Phase 1 Complete",
            f"{regime_name.replace('_', ' ')} regime · {confidence:.0%} confidence",
        )

        # Regime history series — computed ONCE here (moved up from its old
        # position after Phase 2) so Phase 1.5 can condition calibration on
        # the regime actually in effect at each historical date (see
        # Cached in session_state so the Regime tab's chart reuses this exact
        # computation instead of recomputing it.
        try:
            _regime_series_for_harvest = get_regime_history_series(all_hist, window_size=10, step=1)
        except Exception:
            _regime_series_for_harvest = []
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
        if investment_style in _NCO_STYLES:
            _method = _NCO_STYLES[investment_style]
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
            try:
                _cur = st.session_state.current_df
                _prices = {
                    str(r["symbol"]): float(r["price"])
                    for _, r in _cur.iterrows()
                    if pd.notna(r.get("price")) and float(r.get("price") or 0) > 0
                }
                # Needs a deeper panel than the 126-day run window: a sample
                # covariance over ~30 assets estimated from 126 observations is
                # too ill-conditioned to cluster on. Reuses the same cache key
                # as the calibration panel, so it is free whenever that has
                # already been fetched.
                _nco_hist = _load_historical_data(
                    selected_date, _CALIBRATION_LOOKBACK_FILES, symbols_key
                ) or all_hist
                _stage60 = ("Allocating Across Clusters" if _spec["uses_clusters"]
                            else "Balancing Risk Contributions" if _spec["rc_target"] == "equal"
                            else "Sizing Positions")
                progress_bar(progress_container, 60, _stage60,
                             f"{len(_prices)} symbols · {_spec['short']}")
                _book = compute_nco_portfolio(
                    _nco_hist, _prices, capital, num_positions,
                    method=_method, max_pos_pct=st.session_state.max_pos_pct,
                )
                progress_bar(progress_container, 80, "Applying Position Cap",
                             f"max {st.session_state.max_pos_pct*100:.0f}% · "
                             f"{len(_book)} positions")
            except Exception as _e:
                log.warning(f"{_spec['short']} curation failed: {type(_e).__name__}: {_e}")
                _book = pd.DataFrame()

            if _book.empty:
                st.error(
                    f"{investment_style} could not build a portfolio — the return "
                    "covariance was not estimable (too few overlapping observations "
                    "for this universe and date). Try an earlier analysis date, a "
                    "larger universe, or a later analysis date."
                )
                metrics.end_phase("curation", success=False,
                                  error_msg="Covariance not estimable")
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
                "capital": float(capital),
                "curation": _method,
            }

            log.section("Covariance Curation", phase="PHASE 2")
            log.item("Method", f"{_spec['label']} [{_spec['short']}] · {_spec['family']}")
            log.item("Weight formula", _spec["formula"])
            log.item("Estimation", f"{_book.attrs.get('nco_obs', 0)} daily observations · "
                                   f"{_book.attrs.get('nco_universe', 0)} symbols")
            # Name every symbol the coverage rule dropped. A book built on 28 of
            # 30 ETFs is correct when two of them listed this year, but it must
            # never be left to the reader to work that out.
            _excl = _book.attrs.get("nco_universe_excluded") or {}
            if _excl:
                log.item("Universe",
                         f"{_book.attrs.get('nco_universe', 0)} of "
                         f"{_book.attrs.get('nco_universe_requested', 0)} eligible · "
                         f"{len(_excl)} excluded below "
                         f"{_book.attrs.get('nco_coverage_required', 0.8):.0%} history")
                for _sym, _d in sorted(_excl.items(), key=lambda kv: kv[1]["coverage"]):
                    log.item(f"  excluded {_sym}",
                             f"{_d['obs']}/{_d['window']} obs ({_d['coverage']:.0%})")
            log.item("Clustering", f"{_book.attrs.get('nco_clusters', 0)} clusters "
                                   f"(silhouette {_book.attrs.get('nco_silhouette', 0):.3f})"
                                   + ("" if _spec["uses_clusters"] else " · diagnostic only"))
            # Risk balance is the number that says whether the method achieved
            # what it targets. Dispersion is the coefficient of variation of the
            # risk contributions: 0.00 is perfect equal-risk.
            _disp = _book.attrs.get("nco_rc_dispersion", float("nan"))
            _conc = _book.attrs.get("nco_rc_concentration", float("nan"))
            log.item("Risk balance", f"dispersion {_disp:.3f} "
                                     f"({'target 0.00' if _spec['rc_target'] == 'equal' else 'not targeted'})"
                                     f" · concentration {_conc:.2f}x equal share")
            if _spec["uses_momentum"]:
                log.item("Momentum tilt",
                         f"{_book.attrs.get('nco_momentum_names', 0)} names scored "
                         f"({MOMENTUM_LOOKBACK}-{MOMENTUM_SKIP} window) · "
                         f"lambda {_book.attrs.get('nco_momentum_lambda', 0):.2f}"
                         + ("" if _book.attrs.get("nco_momentum_applied") else " · NOT APPLIED"))
            log.item("Positions", f"{len(_book)} curated · ex-ante vol "
                                  f"{_book.attrs.get('nco_port_vol_ann', 0):.2%}")
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
                "Risk Dispersion": f"{_book.attrs.get('nco_rc_dispersion', 0):.3f}",
                "Risk Concentration": f"{_book.attrs.get('nco_rc_concentration', 0):.2f}x",
                "Ex-ante Vol": f"{_book.attrs.get('nco_port_vol_ann', 0):.2%}",
                "Status": "SUCCESS",
            })
            metrics.print_summary(log)
            progress_container.empty()
            st.toast("Analysis Complete!")
            return
        else:
            # Defends against a stale style left in session state by an older
            # build — every live style maps into _NCO_STYLES.
            st.error(f"Unknown portfolio style: {investment_style}")
            metrics.end_phase("curation", success=False, error_msg="Unknown style")
            st.stop()

    except Exception as e:
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


def main():
    """Main application entry point."""
    _init_session_state()

    # Sidebar
    with st.sidebar:
        st.markdown(
            """
        <div style="text-align:center;padding:0.5rem 0 0.75rem 0;">
            <div style="font-family:var(--display);font-size: 1.55rem;font-weight:700;color:var(--amber);letter-spacing:0.04em;">PRAGYAM</div>
            <div style="font-family:var(--data);color:var(--ink-tertiary);font-size: 0.74rem;margin-top:0.1rem;letter-spacing:0.06em;text-transform:uppercase;">प्रज्ञम | Portfolio Intelligence</div>
        </div>
        <hr style="margin: 0.5rem 0; opacity: 0.1;">
        """,
            unsafe_allow_html=True,
        )

        # 1. Analysis Date
        st.markdown('<div class="sidebar-title">Analysis Date</div>', unsafe_allow_html=True)
        selected_date = st.date_input(
            "Date",
            value=datetime.now().date(),
            max_value=datetime.now().date(),
            help="Select the snapshot date for portfolio curation",
            label_visibility="visible"
        )
        st.session_state.selected_date = selected_date
        selected_date_obj = datetime.combine(selected_date, datetime.min.time())

        # 2. Portfolio Style
        st.markdown('<div class="sidebar-title">Portfolio Style</div>', unsafe_allow_html=True)
        investment_style = st.selectbox(
            # Not "Investment Objective": no option here expresses an objective.
            # All are allocation methods over the same holdings, and the system
            # forecasts no returns at all — so the honest question is HOW capital
            # is split, not what the user is trying to achieve.
            "Weighting Method",
            options=_STYLE_LABELS,
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
            label_visibility="visible"
        )

        # 3. Analysis Universe
        st.markdown('<div class="sidebar-title">Analysis Universe</div>', unsafe_allow_html=True)
        universe, selected_index = render_universe_selector()
        st.session_state.selected_universe = universe
        st.session_state.selected_index = selected_index

        # Create symbols key for regime detection
        symbols_key = f"UNIVERSE:{universe}|{selected_index}"
        st.session_state.symbols_key = symbols_key

        # 4. Regime Card
        # NOTE: read the "last regime computation" markers, NOT selected_date as a
        # fallback — selected_date was just overwritten above with the NEW date, so
        # falling back to it would make date_changed always False and freeze the
        # card. When no regime has been computed yet, treat it as needing update.
        previous_date = st.session_state.get("regime_date")
        previous_symbols_key = st.session_state.get("regime_symbols_key")
        date_changed = previous_date != selected_date
        universe_changed = previous_symbols_key != symbols_key

        rd = st.session_state.get("regime_result_dict", {})
        regime_needs_update = not rd or date_changed or universe_changed

        # Lazy regime card: auto-compute WITHOUT a spinner/blocking fetch only
        # when this exact (date, universe) combo is the one the last
        # completed Run Analysis used — that combo is guaranteed already in
        # Streamlit's cache (@st.cache_data(ttl=3600) on _load_historical_data
        # / _detect_regime_cached), so the call below resolves instantly. Any
        # OTHER combo (the user browsing to a new date/universe without
        # having run it yet) is a probable cache MISS: auto-computing there
        # used to trigger a full synchronous yfinance multi-symbol download
        # inside the sidebar's render path — 10-30s of a frozen sidebar just
        # for looking around (see AUDIT_DIRECTIVES.md C4). Show a simple
        # "awaiting first run" state instead — no manual refresh control:
        # clicking Run Analysis always computes and stores the regime as part
        # of Phase 1, so the card self-resolves on the next rerun with no
        # user action beyond the button they were already going to click.
        _last_run_ctx = st.session_state.get("run_context")
        _likely_cached = (
            _last_run_ctx is not None
            and _last_run_ctx.get("anchor_date") == selected_date
            and _last_run_ctx.get("universe") == universe
            and _last_run_ctx.get("selected_index") == selected_index
        )

        if regime_needs_update and _likely_cached:
            rd = _detect_regime_cached(selected_date_obj, symbols_key)
            st.session_state.regime_result_dict = rd
            st.session_state.suggested_mix = rd.get("mix_name", "Chop/Consolidate Mix")
            st.session_state.regime_date = selected_date
            st.session_state.regime_symbols_key = symbols_key
            regime_needs_update = False

        if rd and isinstance(rd, dict) and not regime_needs_update:
            regime_name_sb = rd.get("regime", "UNKNOWN")
            color_sb = rd.get("color", "#888888")
            conf_sb = rd.get("confidence", 0.0)
            score_sb = rd.get("composite_score", 0.0)
            st.markdown(f"""
            <div style="background:{color_sb}12; border:1px solid {color_sb}40; border-radius:10px;
                        padding:12px; margin:var(--sp-6) 0 var(--sp-3) 0;">
                <div style="color:var(--ink-tertiary); font-size: 0.82rem; text-transform:uppercase; letter-spacing:0.5px; font-weight:600; margin-bottom:4px; font-family:var(--data);">Market Regime</div>
                <div style="color:{color_sb}; font-size: 1.3rem; font-weight:700; line-height:1.2; font-family:var(--display); display:flex; align-items:center; gap:8px;">
                    {get_icon(rd.get('icon', ''), size=20, stroke_width=1.8)} {regime_name_sb.replace('_', ' ')}
                </div>
                <div style="display:flex; justify-content:space-between; align-items:center; margin-top:8px;">
                    <span style="color:var(--ink-tertiary); font-size: 0.88rem; font-family:var(--data);">Score {score_sb:+.2f}</span>
                    <span style="color:{color_sb}; font-weight:700; font-size: 0.88rem; font-family:var(--data);">{conf_sb:.0%} confidence</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
        elif regime_needs_update:
            st.markdown("""
            <div style="background:rgba(148,163,184,0.06); border:1px solid rgba(148,163,184,0.18);
                        border-radius:10px; padding:12px; margin:var(--sp-6) 0 var(--sp-3) 0;">
                <div style="color:var(--ink-tertiary); font-size: 0.82rem; text-transform:uppercase;
                            letter-spacing:0.5px; font-weight:600; margin-bottom:4px; font-family:var(--data);">Market Regime</div>
                <div style="color:var(--ink-tertiary); font-size: 0.88rem; font-family:var(--data);">
                    Run Analysis to detect the market regime for this date and universe.
                </div>
            </div>
            """, unsafe_allow_html=True)

        # 5. Portfolio Parameters
        st.markdown('<div class="sidebar-title">Portfolio Parameters</div>', unsafe_allow_html=True)
        capital = st.number_input(
            "Capital (₹)",
            min_value=1000,
            max_value=100000000,
            value=2500000,
            step=1000,
            help="Total capital to allocate",
            label_visibility="visible"
        )
        st.session_state["capital"] = capital

        num_positions = st.slider(
            "Number of Positions",
            min_value=5,
            max_value=100,
            value=30,
            step=5,
            help="Maximum portfolio positions"
        )
        st.session_state.min_pos_pct = 1.0 / 100
        st.session_state.max_pos_pct = 10.0 / 100

        # 6. Run Button
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

        # Show current universe info
        try:
            symbols_list, status_msg = resolve_universe(universe, selected_index)
            rows = [
                '<div class="system-spec">',
                '<div class="spec-row"><span class="spec-label">Version</span><span class="spec-value">' + VERSION + '</span></div>',
                '<div class="spec-row"><span class="spec-label">Universe</span><span class="spec-value">' + universe + '</span></div>',
            ]
            if selected_index:
                rows.append('<div class="spec-row"><span class="spec-label">Index</span><span class="spec-value">' + selected_index + '</span></div>')
            num_symbols = len(symbols_list) if symbols_list is not None else 0
            rows.append('<div class="spec-row"><span class="spec-label">Symbols</span><span class="spec-value">' + str(num_symbols) + '</span></div>')
            rows.append('<div class="spec-row"><span class="spec-label">Data</span><span class="spec-value">yfinance</span></div>')
            rows.append('</div>')
            st.markdown(''.join(rows), unsafe_allow_html=True)
        except Exception:
            rows = [
                '<div class="system-spec">',
                '<div class="spec-row"><span class="spec-label">Version</span><span class="spec-value">' + VERSION + '</span></div>',
                '<div class="spec-row"><span class="spec-label">System</span><span class="spec-value">Covariance-Based</span></div>',
                '<div class="spec-row"><span class="spec-label">Data</span><span class="spec-value">yfinance</span></div>',
                '</div>',
            ]
            st.markdown(''.join(rows), unsafe_allow_html=True)


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
