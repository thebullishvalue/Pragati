"""
PRAGYAM — Portfolio Analytics (Performance vs Benchmark)
══════════════════════════════════════════════════════════════════════════════

Adapted from the SWING Analysis-mode engine (@thebullishvalue). Tracks the LIVE
curated Pragyam portfolio's performance against a universe-matched benchmark:
period return, CAGR, volatility, risk-adjusted ratios (Sharpe / Sortino /
Calmar), tail risk (VaR / CVaR), and benchmark-relative metrics (Alpha, Beta,
R², correlation, tracking error, information ratio, up/down capture).

The curated portfolio (``st.session_state.portfolio`` with ``symbol`` + ``units``)
is the book — no CSV/Excel upload. Historical prices are fetched and aligned to
the benchmark's trading calendar, then a value-weighted portfolio return series
is compared to the benchmark return series.

``build_return_series`` can additionally value a SECOND unit vector over the
same names off the same price panel (``alt_quantities``) — used to chart an
equal-weight shadow of the curated book beside it.

Author: @thebullishvalue
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

# ── Constants ──────────────────────────────────────────────────────────────────
RISK_FREE_RATE = 0.065          # annualized INR risk-free rate (India) — the
                                 # default for Sharpe/Sortino/Treynor. Non-INR
                                 # books should use resolve_risk_free_rate()
                                 # instead of this constant directly.
US_RISK_FREE_RATE = 0.045       # annualized USD risk-free rate proxy (~UST yield)
DEFAULT_BENCHMARK_TICKER = "^NSEI"
DEFAULT_BENCHMARK_NAME = "NIFTY 50"

# Selectable look-back windows (days). YTD is resolved at call time.
#: Trading days below which a return is not annualized. Extrapolating a
#: sub-quarter window by 252/n multiplies its noise by that same factor, so
#: CAGR — and the annualized alpha built from two CAGRs — are withheld under
#: this many aligned observations. Note what is NOT withheld: the period
#: figures, which involve no extrapolation and are perfectly well defined over
#: any window. See `alpha_period` in compute_metrics.
CAGR_MIN_DAYS = 60

TIMEFRAMES: Dict[str, Optional[int]] = {
    "1M": 30, "3M": 90, "6M": 180, "YTD": None,
    "1Y": 365, "2Y": 730, "5Y": 1825, "MAX": 3650,
}

# ── Universe → benchmark map ────────────────────────────────────────────────────
# Maps a Pragyam (universe, selected_index) to a Yahoo benchmark ticker + label.
# NIFTY family → their Yahoo index tickers; sensible broad-market fallbacks
# otherwise. selected_index (e.g. "NIFTY 500", "NIFTY MIDCAP 150", "S&P 500")
# takes priority — it also covers the US_INDEX_LIST entries (universe.py),
# since those are passed as `selected_index` too, not just NIFTY names.
_INDEX_BENCHMARKS: Dict[str, Tuple[str, str]] = {
    "NIFTY 50":         ("^NSEI",      "NIFTY 50"),
    "NIFTY NEXT 50":    ("^NSMIDCP",   "NIFTY Midcap"),   # proxy
    "NIFTY 100":        ("^CNX100",    "NIFTY 100"),
    "NIFTY 200":        ("^CNX100",    "NIFTY 100"),       # proxy
    "NIFTY 500":        ("^CRSLDX",    "NIFTY 500"),
    "NIFTY MIDCAP 50":  ("^NSEMDCP50", "NIFTY Midcap 50"),
    "NIFTY MIDCAP 100": ("NIFTY_MIDCAP_100.NS", "NIFTY Midcap 100"),
    "NIFTY MIDCAP 150": ("NIFTYMIDCAP150.NS",   "NIFTY Midcap 150"),
    "NIFTY MID SELECT": ("^NSEMDCP50", "NIFTY Midcap 50"),  # proxy
    "NIFTY SMLCAP 50":  ("^CNXSC",     "NIFTY Smallcap"),
    "NIFTY SMLCAP 100": ("^CNXSC",     "NIFTY Smallcap 100"),
    "NIFTY SMLCAP 250": ("NIFTYSMLCAP250.NS", "NIFTY Smallcap 250"),
    "NIFTY BANK":         ("^NSEBANK", "NIFTY Bank"),
    "NIFTY IT":           ("^CNXIT",   "NIFTY IT"),
    "NIFTY AUTO":         ("^CNXAUTO", "NIFTY Auto"),
    "NIFTY PHARMA":       ("^CNXPHARMA", "NIFTY Pharma"),
    "NIFTY FMCG":         ("^CNXFMCG",  "NIFTY FMCG"),
    "NIFTY METAL":        ("^CNXMETAL", "NIFTY Metal"),
    "NIFTY ENERGY":       ("^CNXENERGY", "NIFTY Energy"),
    "NIFTY REALTY":       ("^CNXREALTY", "NIFTY Realty"),
    # US indexes (universe.US_INDEX_LIST) — these are the exact strings passed
    # as `selected_index` when universe == "US Indexes", so they belong here
    # alongside the NIFTY names rather than in the universe-level fallback map
    # (which was previously keyed on strings like "us_sp500" that never
    # matched the real universe value "US Indexes" — see AUDIT_DIRECTIVES.md A11).
    "S&P 500":          ("^GSPC", "S&P 500"),
    "DOW JONES":        ("^DJI",  "Dow Jones"),
    "NASDAQ 100":       ("^NDX",  "NASDAQ 100"),
}

# Universe-level fallback when no specific index is selected — keyed on the
# EXACT universe strings from universe.UNIVERSE_OPTIONS, not substrings that
# never occur in real values. Previously this map's keys ("us_sp500", etc.)
# never matched the actual universe strings ("US Indexes", "Commodities", ...),
# so every non-NIFTY universe silently fell through to the NIFTY 50 default.
_UNIVERSE_BENCHMARKS: Dict[str, Tuple[str, str]] = {
    "US Indexes":    ("^GSPC",   "S&P 500"),
    "Commodities":   ("DBC",     "Bloomberg Commodity proxy (DBC)"),
    "Crypto":        ("BTC-USD", "Bitcoin"),
    "Currency":      ("UUP",     "USD Index proxy (UUP)"),
    "ETF Index":     ("^NSEI",   "NIFTY 50"),
    "India Indexes": ("^NSEI",   "NIFTY 50"),
}


def resolve_benchmark(universe: str = "default",
                      selected_index: Optional[str] = None) -> Tuple[str, str]:
    """Return (yahoo_ticker, display_name) for the active (universe, index).

    A specific index selection (NIFTY family or US_INDEX_LIST) wins;
    otherwise fall back to the exact-match universe default, then NIFTY 50.
    """
    if selected_index and selected_index in _INDEX_BENCHMARKS:
        return _INDEX_BENCHMARKS[selected_index]
    if universe in _UNIVERSE_BENCHMARKS:
        return _UNIVERSE_BENCHMARKS[universe]
    return (DEFAULT_BENCHMARK_TICKER, DEFAULT_BENCHMARK_NAME)


# US-denominated benchmark tickers — any resolved benchmark starting with one
# of these means the book (and its risk-free comparison) is USD, not INR.
_USD_BENCHMARK_TICKERS = {"^GSPC", "^DJI", "^NDX"}


def resolve_risk_free_rate(benchmark_ticker: str) -> float:
    """Annualized risk-free rate matching the benchmark's currency zone.

    Sharpe/Sortino/Treynor are only meaningful relative to a risk-free rate
    denominated in the same currency as the returns being measured — using
    the INR rate for a USD-benchmarked book (or vice versa) silently biases
    every risk-adjusted metric. Extend _USD_BENCHMARK_TICKERS if more
    non-INR benchmarks are added to _INDEX_BENCHMARKS / _UNIVERSE_BENCHMARKS.
    """
    return US_RISK_FREE_RATE if benchmark_ticker in _USD_BENCHMARK_TICKERS else RISK_FREE_RATE


def _to_yf_ticker(symbol: str, is_us: bool = False) -> str:
    """Map a stored Pragyam symbol to its Yahoo Finance ticker.

    NSE symbols are stored without the ``.NS`` suffix (stripped in backdata), so
    bare Indian symbols need it re-applied. US universe symbols (S&P 500 / NASDAQ
    100 / Dow — e.g. ``AAPL``, ``NVDA``, ``BRK-B``) are stored bare and are ALREADY
    valid Yahoo tickers; appending ``.NS`` to them yields non-existent tickers
    (``AAPL.NS``) and the whole portfolio fetch comes back empty. ``is_us`` (derived
    from a USD benchmark by the caller) suppresses the ``.NS`` re-application.

    Already-qualified tickers (containing ``.``, an ``^`` index prefix, or an ``=``
    futures marker) are passed through untouched in either mode."""
    s = str(symbol).strip()
    if not s:
        return s
    if is_us:
        return s
    return s if "." in s or s.startswith("^") or "=" in s else f"{s}.NS"


def fetch_analysis_data(
    symbols: list, days_back: int,
    benchmark_ticker: str = DEFAULT_BENCHMARK_TICKER,
    benchmark_name: str = DEFAULT_BENCHMARK_NAME,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Fetch historical close prices for the portfolio and its benchmark.

    Portfolio prices are aligned to the benchmark's trading dates to avoid
    holiday/timezone edge cases. Returns (portfolio_prices, benchmark_prices);
    either may be empty on failure.

    Prices are ADJUSTED closes (``auto_adjust=True``) to match how ``backdata``
    prices the curated book — it sizes ``units`` off adjusted closes (yfinance's
    default), so the analytics return series must start from the same adjusted
    price or the total return won't reconcile with the downloaded portfolio.
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)

    try:
        benchmark_data = yf.download(
            tickers=benchmark_ticker,
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
            interval="1d", progress=False, auto_adjust=True,
        )
        if benchmark_data.empty:
            return pd.DataFrame(), pd.DataFrame()

        benchmark_close = benchmark_data["Close"]
        if isinstance(benchmark_close, pd.DataFrame):
            benchmark_close = benchmark_close.iloc[:, 0]
        benchmark_df = benchmark_close.to_frame(name=benchmark_name)
        valid_dates = benchmark_df.index

        # US books (USD benchmark) store bare, already-valid Yahoo tickers;
        # appending .NS to them (the NSE default) breaks the entire fetch.
        is_us = benchmark_ticker in _USD_BENCHMARK_TICKERS
        ticker_map = {_to_yf_ticker(s, is_us): s for s in symbols}
        tickers = list(ticker_map.keys())

        portfolio_data = yf.download(
            tickers=tickers,
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
            interval="1d", progress=False, threads=True, auto_adjust=True,
        )
        if portfolio_data.empty:
            return pd.DataFrame(), benchmark_df

        if len(tickers) == 1:
            portfolio_close = portfolio_data["Close"].to_frame()
            portfolio_close.columns = [symbols[0]]
        else:
            portfolio_close = portfolio_data["Close"]
            portfolio_close.columns = [ticker_map.get(c, c) for c in portfolio_close.columns]

        portfolio_aligned = portfolio_close.reindex(valid_dates).ffill()
        return portfolio_aligned, benchmark_df

    except Exception:
        return pd.DataFrame(), pd.DataFrame()


def compute_metrics(
    returns: pd.Series,
    benchmark_returns: Optional[pd.Series] = None,
    rf_rate: float = RISK_FREE_RATE,
) -> Dict[str, Any]:
    """Compute institutional-grade performance metrics from a daily return series.

    Ported verbatim (behaviour-preserving) from the SWING engine. Handles short
    periods, negative totals, zero volatility, and missing benchmark data.
    """
    m: Dict[str, Any] = {}

    if returns.empty or len(returns) < 2:
        return {
            "total_return": 0, "cagr": 0, "cagr_meaningful": False,
            "volatility": 0, "daily_vol": 0,
            "max_drawdown": 0, "drawdown_series": pd.Series(dtype=float),
            "sharpe": 0, "sortino": 0, "calmar": 0,
            "var_95": 0, "var_99": 0, "cvar_95": 0,
            "win_rate": 0, "win_days": 0, "lose_days": 0,
            "best_day": 0, "worst_day": 0,
            "skewness": 0, "kurtosis": 0, "profit_factor": 0,
            "beta": 1, "alpha": 0, "alpha_period": 0, "alpha_days": 0,
            "correlation": 0, "r_squared": 0,
            "tracking_error": 0, "info_ratio": 0, "treynor": 0,
            "up_capture": 100, "down_capture": 100, "benchmark_return": 0,
        }

    total_ret = (1 + returns).prod() - 1
    n_days = len(returns)
    # Geometric annualization exponent. This was previously capped at 1 for
    # sub-year windows (min(252/n_days, 1)), which made "CAGR" silently equal
    # the RAW PERIOD RETURN for any window of 20-251 trading days — the
    # "CAGR" subtext just repeated Period Return under the wrong label,
    # Calmar's numerator wasn't annualized, and the Info Ratio divided a
    # period-return spread by an ANNUALIZED tracking error (systematically
    # understated for sub-year windows). CAGR is annualized by definition;
    # the sub-quarter reliability concern is handled by cagr_meaningful
    # below (UI hides CAGR/Alpha/Calmar under 60 days), not by quietly
    # de-annualizing the number.
    ann_factor = 252 / n_days
    m["total_return"] = total_ret * 100

    # Annualizing a sub-quarter return window is statistically indefensible
    # (CFA Institute GIPS guidance advises against annualizing periods under a
    # year) — a 4-day +2% run linearly extrapolated to "252 days" prints a
    # three-digit "CAGR" that has no forecasting content. Below 60 trading
    # days (~a quarter), CAGR/Alpha are computed for completeness but flagged
    # via cagr_meaningful=False so the UI can hide those cards rather than
    # display a number that reads as precise but is actually noise amplified
    # by a large extrapolation factor.
    m["cagr_meaningful"] = n_days >= CAGR_MIN_DAYS
    if total_ret > -1:
        if n_days < 20:
            m["cagr"] = total_ret * (252 / n_days) * 100
        else:
            m["cagr"] = ((1 + total_ret) ** ann_factor - 1) * 100
    else:
        m["cagr"] = -100

    daily_vol = returns.std()
    m["volatility"] = daily_vol * np.sqrt(252) * 100 if daily_vol > 0 else 0
    m["daily_vol"] = daily_vol * 100

    cum = (1 + returns).cumprod()
    peak = cum.expanding().max()
    dd = (cum - peak) / peak
    m["max_drawdown"] = dd.min() * 100
    m["drawdown_series"] = dd * 100

    rf_daily = rf_rate / 252
    excess = returns - rf_daily
    excess_mean = excess.mean()

    if daily_vol > 1e-8:
        m["sharpe"] = (excess_mean / daily_vol) * np.sqrt(252)
    else:
        m["sharpe"] = 0 if abs(excess_mean) < 1e-8 else (np.sign(excess_mean) * 10)

    downside = returns[returns < 0]
    if len(downside) > 0:
        downside_vol = downside.std()
        m["sortino"] = (excess_mean / downside_vol) * np.sqrt(252) if downside_vol > 1e-8 else m["sharpe"]
    else:
        m["sortino"] = m["sharpe"] * 1.5 if m["sharpe"] > 0 else 0

    if abs(m["max_drawdown"]) > 0.01:
        m["calmar"] = m["cagr"] / abs(m["max_drawdown"])
    else:
        m["calmar"] = m["cagr"] if m["cagr"] > 0 else 0

    m["var_95"] = np.percentile(returns, 5) * 100
    m["var_99"] = np.percentile(returns, 1) * 100
    var_threshold = np.percentile(returns, 5)
    tail = returns[returns <= var_threshold]
    m["cvar_95"] = tail.mean() * 100 if len(tail) > 0 else m["var_95"]

    m["win_rate"] = (returns > 0).mean() * 100
    m["win_days"] = int((returns > 0).sum())
    m["lose_days"] = int((returns < 0).sum())
    m["best_day"] = returns.max() * 100
    m["worst_day"] = returns.min() * 100

    if n_days >= 5:
        m["skewness"] = returns.skew()
        m["kurtosis"] = returns.kurtosis()
    else:
        m["skewness"] = 0
        m["kurtosis"] = 0

    gains = returns[returns > 0].sum()
    losses = abs(returns[returns < 0].sum())
    if losses > 1e-8:
        m["profit_factor"] = gains / losses
    elif gains > 0:
        m["profit_factor"] = 10
    else:
        m["profit_factor"] = 0

    # Benchmark defaults
    m.update({
        "beta": 1, "alpha": 0, "alpha_period": 0, "alpha_days": 0,
        "correlation": 0, "r_squared": 0,
        "tracking_error": 0, "info_ratio": 0, "treynor": 0,
        "up_capture": 100, "down_capture": 100, "benchmark_return": 0,
    })

    if benchmark_returns is not None and len(benchmark_returns) > 5:
        aligned = pd.concat([returns, benchmark_returns], axis=1).dropna()
        if len(aligned) > 5:
            p_ret = aligned.iloc[:, 0]
            b_ret = aligned.iloc[:, 1]

            var_b = b_ret.var()
            m["beta"] = (np.cov(p_ret, b_ret)[0, 1] / var_b) if var_b > 1e-10 else 1

            b_total = (1 + b_ret).prod() - 1
            m["benchmark_return"] = b_total * 100

            # Alpha compares p_cagr (portfolio) vs b_cagr (benchmark), so both
            # MUST be annualized on the exact same day-count basis and
            # convention — previously p_cagr used m["cagr"] (computed on the
            # portfolio's own n_days, possibly before benchmark alignment)
            # while b_cagr used aligned_days with a different <20 threshold,
            # so the two sides of the alpha subtraction weren't strictly
            # comparable. Recompute p_cagr on the SAME aligned window here.
            aligned_days = len(aligned)
            # Same exponent convention as ann_factor above (the min(...,1)
            # cap that de-annualized sub-year windows was removed there too).
            aligned_ann = 252 / aligned_days
            p_total_aligned = (1 + p_ret).prod() - 1

            def _cagr_on(total_ret_: float, n_: int, ann_: float) -> float:
                if total_ret_ <= -1:
                    return -1.0
                return (total_ret_ * (252 / n_)) if n_ < 20 else ((1 + total_ret_) ** ann_ - 1)

            b_cagr = _cagr_on(b_total, aligned_days, aligned_ann)
            p_cagr = _cagr_on(p_total_aligned, aligned_days, aligned_ann)

            expected_return = rf_rate + m["beta"] * (b_cagr - rf_rate)
            # Alpha inherits the same sub-quarter unreliability as CAGR (it IS
            # a function of two CAGRs) — gate it on the same aligned-window
            # day count rather than the portfolio's own (possibly longer,
            # pre-alignment) n_days.
            m["cagr_meaningful"] = m["cagr_meaningful"] and aligned_days >= CAGR_MIN_DAYS
            m["alpha"] = (p_cagr - expected_return) * 100

            # PERIOD alpha — the same CAPM residual, computed on the window's
            # own raw returns with nothing annualized.
            #
            # The annualized alpha above is withheld under CAGR_MIN_DAYS
            # because extrapolating by 252/n amplifies the estimate's noise by
            # that factor. The residual itself carries no such defect: "did the
            # book beat what its beta entitled it to, over these six weeks" is
            # a well-posed question with a well-defined answer on any window
            # long enough to fit a beta. Withholding BOTH numbers reported a
            # measurement problem the short window does not actually have, and
            # left a book anchored a few weeks ago with a dash where its one
            # risk-adjusted verdict belongs.
            rf_period = rf_rate * (aligned_days / 252.0)
            m["alpha_period"] = (
                p_total_aligned - (rf_period + m["beta"] * (b_total - rf_period))
            ) * 100
            m["alpha_days"] = int(aligned_days)

            corr = p_ret.corr(b_ret)
            m["correlation"] = corr if not np.isnan(corr) else 0
            m["r_squared"] = m["correlation"] ** 2

            tracking = (p_ret - b_ret).std() * np.sqrt(252)
            m["tracking_error"] = tracking * 100
            m["info_ratio"] = ((p_cagr - b_cagr) / tracking) if tracking > 1e-8 else 0
            m["treynor"] = ((p_cagr - rf_rate) / m["beta"]) if abs(m["beta"]) > 0.01 else 0

            up_mask = b_ret > 0
            down_mask = b_ret < 0
            if up_mask.sum() > 0:
                up_b = (1 + b_ret[up_mask]).prod()
                if up_b > 0:
                    m["up_capture"] = ((1 + p_ret[up_mask]).prod() / up_b) * 100
            if down_mask.sum() > 0:
                down_b = (1 + b_ret[down_mask]).prod()
                if down_b > 0 and down_b != 1:
                    m["down_capture"] = ((1 + p_ret[down_mask]).prod() / down_b) * 100

    return m


def build_return_series(
    portfolio: pd.DataFrame,
    days_back: int,
    benchmark_ticker: str,
    benchmark_name: str,
    anchor_date: Optional[datetime] = None,
    alt_quantities: Optional[Dict[str, float]] = None,
) -> Tuple[pd.Series, pd.Series, Optional[pd.Series], str, list, pd.Series, pd.Series]:
    """From a curated portfolio, produce
    ``(port_value, port_returns, bench_returns, error, unpriced, alt_value,
    bench_value)``.

    ``bench_value`` is the benchmark PRICE series on the same trimmed calendar as
    ``port_value``. Charts must normalize from it rather than from
    ``(1 + bench_returns).cumprod()``: pct_change drops the first bar, so the
    cumprod both starts one bar late AND rebases to day 1, silently discarding
    the opening day's move. Measured on a 6-bar toy series, that reported a
    benchmark at +7.84% when its true return over the window was +10.00% — and it
    made the chart disagree with the Benchmark Comparison cards, which read from
    ``bench_returns`` and were correct.

    ``portfolio`` must have ``symbol`` and ``units`` columns (the live Pragyam
    book). Returns an error string (non-empty) instead of raising on failure.

    ``unpriced`` lists held symbols (with non-zero units) that could not be
    priced/matched — the caller should surface these, since a dropped holding
    silently under-represents the book.

    ``alt_quantities`` is an OPTIONAL second ``{symbol: units}`` vector over the
    same names — used by the Analytics tab to chart an equal-weight shadow of
    the same book alongside it. It is valued here rather than by a second call
    so both series come off ONE price download and, more importantly, share the
    identical trading-date index and leading-row trim: two independently built
    series could start on different dates and would then be normalized from
    different bases, making the comparison quietly wrong. ``alt_value`` is an
    empty Series when ``alt_quantities`` is None.
    """
    _empty = pd.Series(dtype=float)
    if portfolio is None or portfolio.empty or "symbol" not in portfolio.columns or "units" not in portfolio.columns:
        return _empty, _empty, None, "No curated portfolio.", [], _empty, _empty

    symbols = [str(s) for s in portfolio["symbol"].tolist()]
    quantities = {str(s): float(u or 0) for s, u in zip(portfolio["symbol"], portfolio["units"])}

    # Held symbols we actually need a price for (units > 0). Zero-unit rows can't
    # affect value, so their absence is not a data gap.
    held = {s for s in symbols if quantities.get(s, 0.0) > 0}

    port_prices, bench_prices = fetch_analysis_data(symbols, days_back, benchmark_ticker, benchmark_name)
    if port_prices.empty:
        return _empty, _empty, None, "Unable to fetch historical data.", sorted(held), _empty, _empty

    if anchor_date is not None:
        cut = pd.Timestamp(anchor_date)
        port_prices = port_prices[port_prices.index >= cut]
        bench_prices = bench_prices[bench_prices.index >= cut]
        if port_prices.empty:
            return _empty, _empty, None, "No data from the anchor date.", sorted(held), _empty, _empty

    # Which held symbols never got a price column at all (unmatched / delisted /
    # ticker-suffix mismatch)? Those are genuinely absent from the value series.
    priced_cols = [c for c in port_prices.columns if c in quantities and quantities[c] > 0]
    unpriced = sorted(held - set(priced_cols))

    port_value = pd.DataFrame(index=port_prices.index)
    for sym in port_prices.columns:
        if sym in quantities:
            port_value[sym] = port_prices[sym] * quantities[sym]
    if port_value.empty:
        return _empty, _empty, None, "No priced holdings.", unpriced, _empty, _empty

    alt_value = pd.DataFrame(index=port_prices.index)
    if alt_quantities:
        for sym in port_prices.columns:
            if sym in alt_quantities:
                alt_value[sym] = port_prices[sym] * float(alt_quantities[sym])

    # Drop LEADING rows until every priced holding has a value on that date.
    # Otherwise `.sum(axis=1)` (which skips NaN) would treat a not-yet-available
    # holding as 0 on early days, then spike the portfolio value the moment its
    # price appears — injecting a fabricated return. Anchoring the series to the
    # first fully-priced date keeps the composition constant.
    if priced_cols:
        fully_priced = port_value[priced_cols].notna().all(axis=1)
        if fully_priced.any():
            first_valid = fully_priced.idxmax()  # first True
            port_value = port_value.loc[first_valid:]
            bench_prices = bench_prices[bench_prices.index >= first_valid]
            # Same trim for the alternate book — it holds the same names, so it
            # must start on the same date to be normalized from the same base.
            if not alt_value.empty:
                alt_value = alt_value.loc[first_valid:]

    port_value["Portfolio"] = port_value.sum(axis=1)
    port_value = port_value["Portfolio"].dropna()

    port_returns = port_value.pct_change(fill_method=None).dropna()

    if alt_value.empty:
        alt_series = _empty
    else:
        alt_series = alt_value.sum(axis=1).dropna()
        # Reindex onto the main series' dates so the two lines are plotted (and
        # any excess return computed) over exactly the same window.
        alt_series = alt_series.reindex(port_value.index).dropna()

    bench_returns = None
    bench_value = _empty
    if not bench_prices.empty and benchmark_name in bench_prices.columns:
        bench_value = bench_prices[benchmark_name].dropna()
        # Anchor the benchmark to the portfolio's own first date so both lines
        # are normalized from the SAME bar. Without this the chart starts the
        # benchmark one bar late and rebases it there.
        if not port_value.empty:
            bench_value = bench_value[bench_value.index >= port_value.index[0]]
        bench_returns = bench_value.pct_change(fill_method=None).dropna()

    return port_value, port_returns, bench_returns, "", unpriced, alt_series, bench_value


__all__ = [
    "CAGR_MIN_DAYS",
    "TIMEFRAMES",
    "RISK_FREE_RATE",
    "US_RISK_FREE_RATE",
    "resolve_benchmark",
    "resolve_risk_free_rate",
    "fetch_analysis_data",
    "compute_metrics",
    "build_return_series",
]
