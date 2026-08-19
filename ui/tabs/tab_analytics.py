"""
PRAGYAM — The book against a benchmark and against its own shadow.

Two comparisons, not one. The benchmark answers "did it beat the market?";
the equal-weight shadow of the SAME holdings answers the narrower and more
actionable question "did the allocator earn its complexity?".

Author: @thebullishvalue
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st

from ui.components import (
    render_chart_panel,
    render_interpretation_card,
    render_kpi_strip,
    render_note,
    render_section_header,
    render_table_panel,
)
from ui.shared import NCO_STYLES, REGIME_FACTOR_ORDER, STYLE_LABELS, num, style_spec
import html as html_module
from datetime import date, datetime

import streamlit.components.v1 as components

from logger_config import get_console

# Charts are optional: a missing plotly must degrade this tab to its tables
# and readouts rather than take the whole app down on import.
try:
    from charts import (create_benchmark_comparison_chart)
    CHARTS_AVAILABLE = True
except ImportError:                                     # pragma: no cover
    CHARTS_AVAILABLE = False

log = get_console()


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
    # Logged from INSIDE the cached body, so the terminal shows this step only
    # when it actually costs a download. A line on every rerun would say nothing
    # about the run and bury the lines that do.
    with log.task("Performance series",
                  f"{days_back}d · {len(symbols)} holdings · vs {bench_name}") as _t:
        _t.item("Anchor", anchor_dt.strftime("%Y-%m-%d"))
        if _alt:
            _t.detail("valuing the equal-weight shadow book on the same price panel")
        result = build_return_series(
            _port, days_back, bench_ticker, bench_name,
            anchor_date=anchor_dt, alt_quantities=_alt,
        )
        _port_value, _, _bench_returns, _err, _unpriced, _, _ = result
        if _err:
            _t.fail(_err)
        else:
            if _unpriced:
                # A dropped holding under-represents the book rather than
                # failing it, which is exactly the kind of quiet distortion that
                # has to be named.
                _t.note(f"{len(_unpriced)} holding(s) could not be priced: "
                        + ", ".join(str(s) for s in _unpriced[:8])
                        + (" …" if len(_unpriced) > 8 else ""))
            if _bench_returns is None:
                _t.note(f"no {bench_name} series — the benchmark comparison will be empty")
            _n_points = len(_port_value) if _port_value is not None else 0
            _t.item("Window", f"{_port_value.index[0]:%Y-%m-%d} → {_port_value.index[-1]:%Y-%m-%d}"
                    if _n_points else "empty")
            _t.ok(f"{_n_points} daily points"
                  + (f" · book {float(_port_value.iloc[-1] / _port_value.iloc[0] - 1):+.2%}"
                     if _n_points > 1 and float(_port_value.iloc[0]) > 0 else ""))
        return result


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
    from analytics import (CAGR_MIN_DAYS, resolve_benchmark, resolve_risk_free_rate,
                           compute_metrics)
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
    # "did the ALLOCATOR earn its complexity?" — THIS book's holdings, same
    # anchor, same capital, split 1/N instead of by cluster variance. Integer-lot
    # flooring included, so it is a real alternative book rather than an
    # idealized fractional one.
    #
    # It isolates the WEIGHTING, not the style: a genuine Equal Weight run is no
    # longer confined to the covariance-eligible names (see
    # nco.compute_nco_portfolio), so it can select a different set. Holding the
    # holdings fixed is what makes this a clean read on the weights.
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
    render_section_header("Relative Performance", _rel_sub, icon="activity", accent="accent")
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
        # The anchor window belongs in the PANEL HEADER, which is the app's
        # slot for "which instrument, which window" — not in a chip and a note
        # stacked between the section header and the chart. Those two lines
        # were three near-empty rows deep before the plot started, each holding
        # one short phrase across a 1900px measure, and the panel header was
        # already saying the same thing in fewer words one row further down.
        render_chart_panel(
            fig, "benchmark",
            context=f"Anchored {anchor_date.strftime('%d %b %Y')} → today · "
                    f"rebased to 100 · vs {bench_name}",
            meta=f"{len(port_returns)} trading days · {_elapsed_days} calendar",
        )

    # Read the allocation decision out loud: the chart shows three lines, this
    # states the one number the third exists to produce — what the risk-based
    # allocator added, or cost, versus splitting the same holdings evenly.
    if not _has_alt:
        render_note(
            f"All series are indexed to 100 at the anchor date, so the vertical gap between "
            f"lines is cumulative relative performance. **{bench_name}** is the market; the "
            f"portfolio line is the curated book."
        )
    if _has_alt:
        _eq_ret = (float(alt_value.iloc[-1]) / float(alt_value.iloc[0]) - 1.0) * 100.0
        _edge = m.get("total_return", 0.0) - _eq_ret
        _edge_cls = "ink-long" if _edge > 0 else "ink-short" if _edge < 0 else ""
        # The one caption tier, which takes markup: the three emphasised values
        # are coloured by the classes that read the same tokens the chart marks
        # do, so the sentence and the lines it describes cannot disagree about
        # which green they mean.
        render_note(
            f'<strong class="ink-violet">Equal Weight</strong> — the same '
            f'{len(portfolio)} holdings, same anchor, same capital, split 1/N instead of by '
            f'cluster variance — returned <strong>{_eq_ret:+.2f}%</strong>. '
            f'{html_module.escape(_style)} therefore added '
            f'<strong class="{_edge_cls}">{_edge:+.2f}%</strong> on return. Expect this '
            f'to be negative as often as not: the allocator targets risk, and the return it '
            f'gives up is the price of the volatility it removes.'
        )

    # ── Head-to-head comparison ───────────────────────────────────────────────
    # One table, three books, read horizontally. This replaced four stacked
    # 6-card rows: every number was present but answering "how does my book
    # compare?" meant scanning disconnected blocks and holding figures in
    # memory. Only statistics that exist for a single book go here; genuinely
    # pairwise ones (beta, capture, tracking error) follow below.
    _cagr_ok = m.get("cagr_meaningful", True)
    render_section_header(
        "Comparative Statistics",
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

    # Built as a frame and handed to the one table primitive. This was 60
    # lines of hand-built <table> markup with its own <style> inside an
    # iframe — a second table system, in a second typeface, that no token
    # could reach. `best_in_row` keeps the one thing that markup did carry:
    # the winning cell per row, with the polarity stated per row because this
    # table mixes returns with drawdowns.
    # THE SHADOW COLUMN ONLY EXISTS WHEN THERE IS A SHADOW.
    #
    # It used to be emitted unconditionally, which broke this table on the
    # DEFAULT style. On an Equal Weight run the shadow is suppressed — it would
    # be the same book twice — so that column was all-NaN, and worse, its
    # header was the string "Equal Weight", which is also `_style`. Two columns
    # with one name makes `view[c]` return a DataFrame instead of a Series, so
    # every cell rendered as a stringified pandas object:
    # "Equal Weight 1.091768 Equal Weight NaN Name: 0, dtype: object", and the
    # per-row winner compared a frame against a float.
    #
    # Dropping the column when it carries nothing fixes both at once, and the
    # dedupe below means no future style name colliding with the benchmark's
    # can reintroduce it.
    _cols = [(_style, 0)]
    if _has_alt:
        _cols.append(("Equal Weight", 1))
    if _bench_m is not None:
        _cols.append((bench_name, 2))
    _seen: dict[str, int] = {}
    heads = []
    for name, _ in _cols:
        _seen[name] = _seen.get(name, 0) + 1
        heads.append(name if _seen[name] == 1 else f"{name} ({_seen[name]})")

    hh_rows, hh_polarity, hh_precision = [], [], {}
    for label, key, fmt, hib, show in rows_spec:
        if not show:
            continue
        vals = _col(key)
        # Equal-weight period return comes from the shadow series directly, so
        # it matches the chart legend exactly rather than being recomputed.
        if key == "total_return" and _has_alt:
            vals[1] = _alt_total
        hh_rows.append([label] + [
            (vals[i] if (vals[i] is not None and np.isfinite(vals[i])) else np.nan)
            for _, i in _cols])
        hh_polarity.append(bool(hib))
        hh_precision[label] = 0 if fmt.endswith("{:.0f}%") else 2

    hh = pd.DataFrame(hh_rows, columns=["Metric"] + heads)
    render_table_panel(
        hh, "head-to-head",
        context=" · ".join(heads),
        show_index=False,
        label_col="Metric",
        precision=2,
        best_in_row=hh_polarity,
        max_height=560,
    )
    render_note(
        f"Green marks the best value in each row. **{_style}** is the curated book"
        + (f"; **Equal Weight** is the same {len(portfolio)} holdings split 1/N — the "
           "like-for-like test of the allocator" if _has_alt else "")
        + f"; **{bench_name}** is the market. Max Drawdown, VaR and CVaR are "
        f"negative numbers, so *higher is better* — the least negative wins. Expect the allocator "
        f"to lead on volatility and drawdown while trailing on return: that is the trade it makes, "
        f"not a fault."
    )

    # ── Relationship to benchmark ─────────────────────────────────────────────
    # These have no meaning for a single book — every one is a statistic ABOUT
    # the pairing — so they cannot live in the table above.
    render_section_header("Benchmark Relationship", f"How the book moves with {bench_name}",
                          icon="compass", accent="cyan")
    # One strip, not six hand-placed columns: the strip owns the wrapping rule,
    # so this row reflows to two rows of three on a tablet instead of six
    # columns squeezed to 90px each.
    _b = m.get("beta", 1)
    # Alpha reports the ANNUALIZED CAPM residual once the window can carry one,
    # and the PERIOD residual before that. Both answer "did the book beat what
    # its beta entitled it to"; only the first also claims a per-annum rate,
    # which is the part a six-week window cannot support. The card previously
    # printed a dash and "Window too short" for the whole metric, which read as
    # a broken feature rather than a withheld annualization — the residual was
    # always computable and is the number a reader actually wants.
    # alpha_days is 0 only when the benchmark series never overlapped the book's
    # window — no pairing, so no residual. That is the one case with genuinely
    # nothing to print, and it is a different statement from a short window.
    _a_days = int(m.get("alpha_days", 0) or 0)
    _a_paired = _a_days > 0
    _a_annual = _a_paired and _cagr_ok and _a_days >= CAGR_MIN_DAYS
    _a = m.get("alpha", 0) if _a_annual else m.get("alpha_period", 0)
    _uc = m.get("up_capture", 100)
    _dc = m.get("down_capture", 100)
    render_kpi_strip([
        {"label": "Beta", "value": f"{_b:.2f}", "subtext": "Market sensitivity",
         "color_class": "warning" if _b > 1.2 else "info" if _b < 0.8 else "neutral"},
        {"label": "Alpha" if _a_annual or not _a_paired else "Alpha · Period",
         "value": f"{_a:+.2f}%" if _a_paired else "—",
         "subtext": ("CAPM excess, annualized" if _a_annual else
                     f"CAPM excess over {_a_days} trading days · "
                     f"annualized from {CAGR_MIN_DAYS}") if _a_paired else
                    f"No overlap with {bench_name}",
         "color_class": ("success" if _a > 0 else "danger" if _a < 0 else "neutral")
                        if _a_paired else "neutral"},
        {"label": "Correlation", "value": f"{m.get('correlation', 0):.2f}",
         "subtext": f"R² {m.get('r_squared', 0):.2f}", "color_class": "info"},
        {"label": "Tracking Error", "value": f"{m.get('tracking_error', 0):.1f}%",
         "subtext": "Annualized", "color_class": "info"},
        {"label": "Up Capture", "value": f"{_uc:.0f}%", "subtext": "In rising markets",
         "color_class": "success" if _uc > 100 else "warning"},
        {"label": "Down Capture", "value": f"{_dc:.0f}%", "subtext": "In falling markets",
         "color_class": "success" if _dc < 100 else "danger"},
    ], max_cols=6, key="benchmark-rel")
    render_note(
        f"**Beta** is the book's sensitivity to {bench_name}; **Alpha** is return beyond what that "
        f"beta explains"
        + ("." if _a_annual or not _a_paired else
           f" — stated here **over the window itself**, not per annum, because "
           f"{_a_days} trading days is under the {CAGR_MIN_DAYS} an annualized figure needs. "
           f"Extrapolating a window this short multiplies its noise by the same factor it "
           f"multiplies the return, so the rate is withheld while the excess it is built from "
           f"is not.")
        + f" **Up/Down Capture** are the share of the benchmark's rise and fall the book "
        f"participates in — the ideal pairing is above 100% up and below 100% down. **Tracking "
        f"Error** is the volatility of the difference, so it measures how far the book is allowed "
        f"to wander from the market, not whether it wandered profitably."
    )
