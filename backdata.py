"""
PRAGYAM — Market Data & Indicator Engine
══════════════════════════════════════════════════════════════════════════════

Fetches OHLCV history from yfinance (behind a circuit breaker) and computes the
per-symbol indicator panel that every downstream layer consumes.

Produces, per symbol per day (daily and weekly timeframes where noted):
  • Liquidity Oscillator (+ 9/21 EMAs) and its 20-period z-score
  • RSI (Wilder), moving averages (20/90/200) and their deviations
  • Volume-profile features (daily): point-of-control (POC), value-area position
    (``vap`` — a volatility-normalised premium/discount to accepted value) and
    in-value position (``va_pos``). See ``compute_volume_profile``.

The canonical column set is ``COLUMN_ORDER``; ``generate_historical_data``
returns a chronological list of ``(date, snapshot_df)`` tuples in that shape,
which the regime detector and the covariance curation both read.

Author: @thebullishvalue
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import time
import warnings
import os
from typing import List, Tuple, Dict, Any, Optional, cast

# Import circuit breaker and metrics
from circuit_breaker import yfinance_circuit, RetryWithBackoff
from metrics import get_metrics

warnings.filterwarnings("ignore", category=FutureWarning)


class LiquidityOscillator:
    """Calculates the Liquidity Oscillator indicator."""

    def __init__(self, length: int = 20, impact_window: int = 3):
        if length <= 0 or impact_window <= 0:
            raise ValueError("length and impact_window must be positive integers.")
        self.length = length
        self.impact_window = impact_window

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        required_columns = {'open', 'high', 'low', 'close', 'volume'}
        if not required_columns.issubset(data.columns):
            return pd.Series(dtype=float)

        # FX and some futures report volume as 0/NaN on Yahoo; the oscillator
        # is volume-weighted and cannot be computed in that case.
        if data['volume'].fillna(0).sum() == 0:
            return pd.Series(index=data.index, dtype=float, name='liquidity_oscillator')

        df = data.copy()
        df['spread'] = (df['high'] + df['low']) / 2 - df['open']
        df['vol_ma'] = df['volume'].rolling(window=self.length).mean()
        # Divide-by-zero guard: during the first `length-1` bars vol_ma is NaN
        # (rolling warmup), and occasionally a window can sum to exactly 0
        # volume. Filling either case with 1.0 does NOT make the ratio "safe" —
        # it turns spread*volume/1.0 into a value at ~volume's natural scale
        # (often 10^5-10^6x too large), which then sits inside the next
        # 20-bar rolling means and contaminates roughly bars [length, 2*length)
        # of every symbol's oscillator with garbage instead of "no signal yet".
        # NaN-propagate instead: where vol_ma isn't a valid positive average,
        # the ratio is undefined and must stay NaN so it's dropped by the
        # rolling mean exactly like the other warm-up NaNs downstream already
        # rely on (see compute_volume_profile's docstring for the convention).
        safe_vol_ma = df['vol_ma'].where(df['vol_ma'] > 0)
        df['vwap_spread'] = (df['spread'] * df['volume'] / safe_vol_ma).rolling(window=self.length).mean()
        close_shifted = df['close'].shift(self.impact_window)
        df['price_impact'] = ((df['close'] - close_shifted) * df['volume'] / safe_vol_ma).rolling(window=self.length).mean()
        df['liquidity_score'] = df['vwap_spread'] - df['price_impact']
        df['source_value'] = df['close'] + df['liquidity_score']
        df['lowest_value'] = df['source_value'].rolling(window=self.length).min()
        df['highest_value'] = df['source_value'].rolling(window=self.length).max()
        range_value = df['highest_value'] - df['lowest_value']
        # Same principle: a zero (or NaN, from warmup) high-low source range
        # means the 200*(x-lo)/range formula is undefined, not "1.0-wide" —
        # filling with 1.0 previously made a flat-price window explode to
        # +/-Infinity-adjacent values instead of correctly reporting NaN.
        safe_range_value = range_value.where(range_value > 0)
        oscillator = 200 * (df['source_value'] - df['lowest_value']) / safe_range_value - 100
        return oscillator.rename('liquidity_oscillator')

def resample_data(df: pd.DataFrame, rule: str = 'W-FRI') -> pd.DataFrame:
    """Resample daily OHLCV data to a different timeframe."""
    if df.empty or not isinstance(df.index, pd.DatetimeIndex):
        return pd.DataFrame()
    agg_map = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
    return df.resample(rule).agg(agg_map).dropna()


def calculate_rsi(data: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate Relative Strength Index (RSI) using Wilder's smoothing."""
    if data.empty or 'close' not in data.columns or len(data) < period:
        return pd.Series(index=data.index, dtype=float)

    delta = data['close'].diff(1)
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    # avg_loss == 0 (all-gains window) is a genuine RSI=100 case, but a blanket
    # fillna(100.0) also stamps the first `period` warm-up rows (NaN from
    # min_periods=period, not from an all-gains window) as a maximally
    # overbought 100 — a phantom signal where there is actually no data yet.
    # Only backfill the true all-gains case; leave warm-up NaNs as NaN so
    # downstream consumers treat them as "no signal" like every other
    # indicator's warmup.
    all_gains = avg_loss.eq(0) & avg_gain.notna() & (avg_gain > 0)
    rsi = rsi.where(~all_gains, 100.0)
    return rsi

def compute_volume_profile(
    df: pd.DataFrame,
    window: int = 90,
    bins: int = 60,
    value_area: float = 0.70,
) -> pd.DataFrame:
    """Rolling EOD volume profile → POC / value-area position features.

    The system has no notion of *where volume actually traded*. Its only
    "value" anchor is the rolling mean baked into the oscillator z-score. This
    builds, per bar, a trailing volume profile (the proxy/binned model from the
    Inferred-Delta volume-profile indicator, adapted to a cross-sectional EOD
    panel) and returns three measured, no-inference features:

      • ``poc``        – point of control: the modal price (price bin that
                         accumulated the most volume) over the trailing window.
      • ``vap``        – Value-Area Position: where the latest close sits inside
                         the developing volume profile, volatility-normalised by
                         the value-area half-width and clamped to roughly
                         [-3, +3]. Positive = price trades at a *discount* to
                         accepted value (mean-reversion long), negative = at a
                         *premium*. This is the cross-sectional signal feeding
                         the regime detector's acceptance factor.
      • ``va_pos``     – raw position of close within [VAL, VAH] mapped to
                         [-1, +1] (inside-value vs at-an-edge), used by the
                         portfolio selection layer for structural hold/rotate.

    Volume binning replicates the indicator's profile loop: each bar's volume is
    spread across the price bins its high–low range touches, so a bar that
    straddles many levels contributes a thin slice to each. The value area is
    grown outward from the POC, always taking the heavier adjacent bin, until it
    holds ``value_area`` of the windowed volume — the same expansion the
    indicator uses for VAH/VAL.

    Per-window histogram construction is vectorized via a difference-array +
    cumsum (each bar's "add v/spread to bins [b_lo, b_hi]" range-update becomes
    two O(1) writes and one O(bins) cumulative sum instead of an O(window)
    Python loop per window) — validated bit-identical against the original
    per-bar loop, ~4-5x faster end to end. The outer per-window loop remains
    (the bin edges genuinely shift every window since [lo, hi] is a trailing
    min/max), so this is not a full incremental/streaming histogram.

    Returns a DataFrame indexed like ``df`` with columns ``poc``/``vap``/``va_pos``.
    Bars before the window is warm, or with no usable volume, are NaN — they are
    dropped downstream exactly like the other indicators' warmup NaNs.
    """
    import numpy as np
    out = pd.DataFrame(index=df.index, columns=['poc', 'vap', 'va_pos'], dtype=float)
    n = len(df)
    if n < window or not {'high', 'low', 'close', 'volume'}.issubset(df.columns):
        return out

    highs = df['high'].to_numpy(dtype=float)
    lows = df['low'].to_numpy(dtype=float)
    closes = df['close'].to_numpy(dtype=float)
    vols = df['volume'].to_numpy(dtype=float)

    for end in range(window - 1, n):
        start = end - window + 1
        wl = lows[start:end + 1]
        wh = highs[start:end + 1]
        wv = vols[start:end + 1]
        price = closes[end]

        lo = np.nanmin(wl)
        hi = np.nanmax(wh)
        # Need a real price range and some real volume to build a profile.
        if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
            continue
        total_vol = np.nansum(wv)
        if not np.isfinite(total_vol) or total_vol <= 0:
            continue

        step = (hi - lo) / bins
        if step <= 0:
            continue

        # ── Vectorized histogram build ──────────────────────────────────────
        # The original per-window loop did `for j in range(window)`, each
        # iteration slicing hist[b_lo:b_hi+1] += slice_v — 90*90 = 8,100
        # Python-level operations per symbol per window*, the dominant cost
        # of the whole data-fetch phase at universe scale (~0.2s/symbol here,
        # ~100s for a 500-symbol universe). Every bar's contribution is
        # "add `v/spread` to each bin in [b_lo, b_hi]" — a range-update, which
        # a difference array turns into two O(1) writes (+v/spread at b_lo,
        # -v/spread at b_hi+1) followed by ONE cumulative sum over `bins`
        # (60) instead of up to `bins` writes per bar. This produces the
        # IDENTICAL histogram (validated against the original loop) at a
        # fraction of the cost.
        valid = np.isfinite(wv) & (wv > 0) & np.isfinite(wl) & np.isfinite(wh)
        if not valid.any():
            continue
        wl_v, wh_v, wv_v = wl[valid], wh[valid], wv[valid]

        b_lo_arr = np.floor((wl_v - lo) / step).astype(np.int64)
        b_hi_arr = np.floor((wh_v - lo) / step).astype(np.int64)
        np.clip(b_lo_arr, 0, bins - 1, out=b_lo_arr)
        np.clip(b_hi_arr, 0, bins - 1, out=b_hi_arr)
        spread_arr = (b_hi_arr - b_lo_arr + 1).astype(np.float64)
        slice_v_arr = wv_v / spread_arr

        diff = np.zeros(bins + 1, dtype=np.float64)
        np.add.at(diff, b_lo_arr, slice_v_arr)
        np.add.at(diff, b_hi_arr + 1, -slice_v_arr)
        hist = np.cumsum(diff[:-1])

        # ── POC: modal price bin ──────────────────────────────────────────────
        poc_bin = int(np.argmax(hist))
        poc_price = lo + (poc_bin + 0.5) * step

        # ── Value area: grow outward from POC, heavier-side first, to value_area
        acc = hist[poc_bin]
        target = total_vol * value_area
        up = poc_bin
        dn = poc_bin
        while acc < target and (dn > 0 or up < bins - 1):
            v_up = hist[up + 1] if up < bins - 1 else -1.0
            v_dn = hist[dn - 1] if dn > 0 else -1.0
            if v_up >= v_dn:
                acc += v_up
                up += 1
            else:
                acc += v_dn
                dn -= 1
        vah = lo + (up + 1) * step
        val = lo + dn * step

        # ── va_pos: close inside [VAL, VAH] mapped to [-1, +1] ────────────────
        va_mid = (vah + val) / 2.0
        va_half = max((vah - val) / 2.0, step)
        va_pos = (price - va_mid) / va_half
        va_pos = float(np.clip(va_pos, -1.0, 1.0))

        # ── vap: volatility-normalised premium/discount to value (mean-rev) ───
        #  Distance of close from POC, scaled by the value-area half-width so the
        #  number is comparable across symbols of very different price/vol. We
        #  invert the sign so DISCOUNT (below value) is POSITIVE = a long bias,
        #  matching the oversold-is-positive convention of zscore_signal.
        vap = -(price - poc_price) / va_half
        vap = float(np.clip(vap, -3.0, 3.0))

        out.iat[end, 0] = poc_price
        out.iat[end, 1] = vap
        out.iat[end, 2] = va_pos

    return out


def calculate_all_indicators(
    symbol_data: pd.DataFrame,
    oscillator_calculator: LiquidityOscillator
) -> pd.DataFrame | None:
    """
    Calculate all indicators for a single symbol's full history.

    Returns a DataFrame indexed by date with columns for price, returns,
    oscillators, RSI, moving averages, deviations, and z-scores across
    daily and weekly timeframes, plus the daily volume-profile features
    (POC, value-area position ``vap``, and in-value position ``va_pos``).
    Returns ``None`` on empty input.
    """
    daily_data = symbol_data.copy()
    if daily_data.empty:
        return None

    weekly_data = resample_data(daily_data, 'W-FRI')
    
    all_results_df = pd.DataFrame(index=daily_data.index)
    all_results_df['price'] = daily_data['close']
    all_results_df['% change'] = daily_data['close'].pct_change()

    timeframes = {'latest': daily_data, 'weekly': weekly_data}
    
    for tf_name, df in timeframes.items():
        if len(df) < 2:
            continue
        
        osc = oscillator_calculator.calculate(df)
        if not osc.dropna().empty:
            all_results_df[f'osc {tf_name}'] = osc
            all_results_df[f'9ema osc {tf_name}'] = osc.ewm(span=9).mean()
            all_results_df[f'21ema osc {tf_name}'] = osc.ewm(span=21).mean()

            if len(osc.dropna()) >= 20:
                osc_sma20 = osc.rolling(window=20).mean()
                osc_std20 = osc.rolling(window=20).std()
                safe_std20 = osc_std20.replace(0, pd.NA).fillna(1.0)
                all_results_df[f'zscore {tf_name}'] = (osc - osc_sma20) / safe_std20

        rsi_series = calculate_rsi(df)
        if rsi_series is not None and not rsi_series.dropna().empty:
            all_results_df[f'rsi {tf_name}'] = rsi_series

        for period in [20, 90, 200]:
            if len(df) >= period:
                all_results_df[f'ma{period} {tf_name}'] = df['close'].rolling(window=period).mean()
                if period == 20:
                    all_results_df[f'dev{period} {tf_name}'] = df['close'].rolling(window=period).std()

    # ── Volume profile (daily only): POC / value-area position ────────────────
    #  Measured, no-inference structure ported from the Inferred-Delta volume
    #  profile. Gives the system its missing "where volume actually traded"
    #  dimension; feeds the regime detector's acceptance factor.
    vp = compute_volume_profile(daily_data)
    all_results_df['poc latest'] = vp['poc']
    all_results_df['vap latest'] = vp['vap']
    all_results_df['va_pos latest'] = vp['va_pos']

    all_results_df = all_results_df.reindex(daily_data.index)

    weekly_cols = [col for col in all_results_df.columns if 'weekly' in col]
    all_results_df[weekly_cols] = all_results_df[weekly_cols].ffill()
    
    return all_results_df


def get_default_universe() -> List[str]:
    """Get the default ETF universe from the universe module.

    universe.ETF_UNIVERSE is the single source of truth (see
    AUDIT_DIRECTIVES.md B4 — this function previously had its own
    hardcoded 30-symbol list that had silently drifted from
    universe.ETF_UNIVERSE, a THIRD divergent definition alongside
    symbols.txt). If the universe module is ever unavailable, fall back to
    symbols.txt (kept in sync with universe.ETF_UNIVERSE) rather than a
    second hardcoded copy that can drift again.
    """
    try:
        from universe import ETF_UNIVERSE
        return ETF_UNIVERSE
    except ImportError:
        try:
            here = os.path.dirname(os.path.abspath(__file__))
            with open(os.path.join(here, "symbols.txt"), "r") as f:
                return [line.strip() for line in f if line.strip()]
        except OSError:
            return []

# Default universe (can be overridden by caller)
SYMBOLS_UNIVERSE = get_default_universe()

# Define the column order here so it can be used by the generator
COLUMN_ORDER = [
    'date', 'symbol', 'price', 'rsi latest', 'rsi weekly',
    '% change', 'osc latest', 'osc weekly',
    '9ema osc latest', '9ema osc weekly',
    '21ema osc latest', '21ema osc weekly',
    'zscore latest', 'zscore weekly',
    'ma20 latest', 'ma90 latest', 'ma200 latest',
    'ma20 weekly', 'ma90 weekly', 'ma200 weekly',
    'dev20 latest', 'dev20 weekly',
    # Volume-profile features (daily): point-of-control + value-area position.
    'poc latest', 'vap latest', 'va_pos latest',
]

# --- NEW: Export max indicator period ---
INDICATOR_PERIODS = [20, 90, 200]
MAX_INDICATOR_PERIOD = max(INDICATOR_PERIODS)


# ── Second-pass recovery for symbols the batch download missed ────────────────
#
# `yf.download` over a LIST of tickers does not raise when only SOME of them
# fail — it returns all-NaN columns for those. The RetryWithBackoff wrapped
# around the batch call therefore never fires for the common case (two or three
# symbols out of thirty), and those columns were dropped silently, leaving the
# run on a quietly smaller universe. Because the panel is cached for an hour
# (app._load_historical_data), one unlucky fetch degraded every rerun until the
# TTL expired.
#
# The constants below bound a per-symbol second pass over exactly the symbols
# that came back empty. It is deliberately NOT attempted when most of the
# universe is missing: that is a service outage, and re-requesting 200 symbols
# one at a time turns a fast failure into a very slow one.
_RECOVERY_MAX_SYMBOLS = 40        # cap on single-symbol fetches per run
_RECOVERY_FAILURE_RATIO = 0.5     # >50% of the universe missing = outage, don't retry
_RECOVERY_ABORT_AFTER = 5         # consecutive failures that mean "stop, it's the service"
_RECOVERY_ATTEMPTS = 2            # attempts per symbol
_RECOVERY_DELAY = 1.0             # seconds between attempts on one symbol

# Trading bars a symbol may lag the panel end before it counts as missed rather
# than merely quiet. Shared with the forward-fill below so "recoverable gap" and
# "gap we carry the last price across" are the same number by construction.
_STALE_BARS = 5


def _unfetched_symbols(close: pd.DataFrame, symbols: List[str]) -> List[str]:
    """Symbols whose batch download returned nothing, or stopped early.

    Two distinct failures share one signature here: a column that is entirely
    NaN (nothing came back at all) and a column whose last valid bar sits more
    than ``_STALE_BARS`` before the end of the panel (the download stopped
    early, so every price the run reads for that symbol is stale).

    A LEADING gap is deliberately NOT counted as missed. A symbol that listed
    part-way through the window genuinely has no earlier history, and retrying
    it every run would spend the whole recovery budget re-requesting data that
    does not exist.
    """
    if close is None or close.empty:
        return list(symbols)

    missed: List[str] = []
    n_rows = len(close.index)
    for sym in symbols:
        if sym not in close.columns:
            missed.append(sym)              # yfinance omitted the column outright
            continue
        col = pd.to_numeric(close[sym], errors="coerce")
        if not col.notna().any():
            missed.append(sym)              # column present, nothing in it
            continue
        last = col.last_valid_index()
        loc = int(close.index.get_indexer(pd.Index([last]))[0]) if last is not None else -1
        if loc < 0:
            continue
        if n_rows - 1 - loc > _STALE_BARS:
            missed.append(sym)
    return missed


def _refetch_symbol(symbol: str, start_date: datetime,
                    end_date: datetime) -> Optional[pd.DataFrame]:
    """Re-fetch ONE symbol through ``Ticker.history`` — a different endpoint.

    Using a different endpoint is the point: when the batch quote endpoint
    returns an empty column for a symbol it is frequently a per-request failure
    rather than a missing instrument, and the per-ticker chart endpoint returns
    the series normally.

    Deliberately OUTSIDE the circuit breaker. A delisted or misspelled symbol
    fails on every attempt, and counting those against the breaker would trip it
    (threshold 5) and block the next run's batch download for a minute over what
    is a universe problem, not a service problem.

    Returns a tz-naive daily frame, or None when nothing came back.
    """
    for attempt in range(_RECOVERY_ATTEMPTS):
        try:
            df = yf.Ticker(symbol).history(
                start=start_date,
                end=end_date + timedelta(days=1),
                auto_adjust=True,     # matches yf.download's default, so recovered
                actions=False,        # prices sit on the same adjustment basis
            )
        except Exception:
            df = None
        if df is not None and not df.empty:
            idx = pd.DatetimeIndex(df.index)
            if idx.tz is not None:
                # The batch panel is tz-naive; Ticker.history returns
                # Asia/Kolkata for .NS names. Reindexing one onto the other
                # without this silently yields an all-NaN column.
                idx = idx.tz_localize(None)
            out: pd.DataFrame = df.copy()
            out.index = idx.normalize()
            return out
        if attempt + 1 < _RECOVERY_ATTEMPTS:
            time.sleep(_RECOVERY_DELAY)
    return None


def _recover_missing_symbols(
    all_data: pd.DataFrame,
    symbols_to_process: List[str],
    start_date: datetime,
    end_date: datetime,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Re-fetch and merge the symbols the batch download missed.

    Runs BEFORE the failed-ticker drop, so a symbol recovered here stays in the
    universe rather than disappearing from the book. Recovered bars only ever
    FILL holes — an existing batch value is never overwritten, so recovery
    cannot quietly restate prices the rest of the panel was built on.
    """
    report: Dict[str, Any] = {"missing": [], "recovered": [], "failed": [],
                              "skipped_reason": None}
    try:
        # Selecting one level of a MultiIndex column yields a DataFrame. The
        # pandas stubs type __getitem__(str) as returning a Series, which it is
        # not here, so the shape has to be asserted rather than inferred.
        close = cast(pd.DataFrame, all_data["Close"])
    except (KeyError, TypeError):
        return all_data, report

    missing = _unfetched_symbols(close, symbols_to_process)
    report["missing"] = list(missing)
    if not missing:
        return all_data, report

    # An outage is not a per-symbol problem, and the batch retry has already
    # covered the transient case. Fail fast instead of grinding.
    if len(missing) > _RECOVERY_FAILURE_RATIO * len(symbols_to_process):
        report["skipped_reason"] = "outage"
        return all_data, report
    if len(missing) > _RECOVERY_MAX_SYMBOLS:
        report["skipped_reason"] = "budget"
        missing = missing[:_RECOVERY_MAX_SYMBOLS]

    console = None
    try:
        from logger_config import console as _c
        console = _c
    except Exception:
        pass

    recovered: Dict[str, pd.DataFrame] = {}
    consecutive_failures = 0
    for sym in missing:
        df = _refetch_symbol(sym, start_date, end_date)
        if df is None:
            report["failed"].append(sym)
            consecutive_failures += 1
            if consecutive_failures >= _RECOVERY_ABORT_AFTER:
                # Nothing is coming back at all — stop spending the budget.
                report["skipped_reason"] = "aborted"
                break
            continue
        consecutive_failures = 0
        recovered[sym] = df
        report["recovered"].append(sym)

    for sym, df in recovered.items():
        for field_name in ("Open", "High", "Low", "Close", "Volume"):
            if field_name not in df.columns:
                continue
            series = pd.to_numeric(df[field_name], errors="coerce").reindex(all_data.index)
            col = (field_name, sym)
            if col in all_data.columns:
                all_data[col] = all_data[col].fillna(series)   # fill holes only
            else:
                all_data[col] = series
    if recovered:
        # Adding columns leaves the MultiIndex unsorted, which makes the
        # (slice(None), tickers) selection below raise or warn.
        all_data = all_data.sort_index(axis=1)

    if report["recovered"] or report["failed"]:
        msg = (f"Re-fetch: {len(report['recovered'])} of {len(report['missing'])} "
               f"missing symbol(s) recovered"
               + (f", {len(report['failed'])} still unavailable" if report["failed"] else ""))
        if console is not None:
            try:
                if report["recovered"]:
                    console.success(msg)
                else:
                    console.warning(msg)
            except Exception:
                pass
    return all_data, report


def generate_historical_data(
    symbols_to_process: List[str],
    start_date: datetime,
    end_date: datetime,
) -> List[Tuple[datetime, pd.DataFrame]]:
    """
    Generate historical indicator snapshots for a list of symbols.
    
    LITERATURE-RIGOROUS VALIDATION:
    - Validates symbol universe
    - Validates date range
    - Validates data quality
    - Propagates errors explicitly
    - Uses circuit breaker for yfinance

    Args:
        symbols_to_process: Stock ticker symbols (e.g. ``["RELIANCE.NS"]``).
        start_date: Beginning of the download window (must include warmup).
        end_date: End of the snapshot window.

    Returns:
        Chronologically ordered list of ``(date, indicator_df)`` tuples.
        
    Raises:
        ValueError: If symbol universe is empty or date range is invalid
        ConnectionError: If yfinance API fails
        RuntimeError: If no valid data received
    """
    # Get metrics tracker
    metrics = get_metrics()
    
    # === VALIDATION 1: Symbol Universe ===
    if not symbols_to_process:
        metrics.add_error("ValueError", "Symbol universe is empty", "generate_historical_data")
        raise ValueError("Symbol universe is empty - please select a valid universe")
    
    if len(symbols_to_process) > 500:
        metrics.add_warning(f"Large universe ({len(symbols_to_process)} symbols) - may be slow")
        console_message = f"⚠️ Large universe: {len(symbols_to_process)} symbols (recommended: <300)"
        try:
            from logger_config import console
            console.warning(console_message)
        except Exception:
            pass
    
    # === VALIDATION 2: Date Range ===
    if start_date > end_date:
        metrics.add_error(
            "ValueError",
            f"Start date ({start_date}) is after end date ({end_date})",
            "generate_historical_data"
        )
        raise ValueError(f"Start date ({start_date}) cannot be after end date ({end_date})")
    
    # Note: No limit on date range - allow user to fetch any range they need
    # Large date ranges will take longer but are valid
    
    # Update metrics
    metrics.symbols_count = len(symbols_to_process)
    
    # === DOWNLOAD WITH CIRCUIT BREAKER + RETRY ===
    try:
        # Retry INSIDE the circuit breaker, breaker OUTSIDE: a single yfinance
        # transient (the common case — brief rate-limit blip, momentary
        # network hiccup) gets a couple of quick backoff retries before
        # counting as a breaker failure. Without this, RetryWithBackoff was
        # imported but never applied anywhere, so one transient failure
        # ended the whole run immediately (see AUDIT_DIRECTIVES.md B6).
        @yfinance_circuit.protect
        @RetryWithBackoff(max_retries=2, initial_delay=2.0, backoff_factor=2.0)
        def download_data():
            return yf.download(
                symbols_to_process,
                start=start_date,
                end=end_date + timedelta(days=1),
                progress=False,
            )

        all_data = download_data()
        
    except Exception as e:
        # Circuit breaker or download failed
        metrics.add_error(type(e).__name__, str(e), "yfinance.download")
        
        # Check if it's a circuit breaker error
        if "Circuit" in str(e) and "OPEN" in str(e):
            raise ConnectionError(
                f"yfinance service unavailable (circuit breaker OPEN): {str(e)}"
            ) from e
        else:
            raise ConnectionError(f"yfinance API failed: {str(e)}") from e
    
    # === VALIDATION 3: Data Received ===
    if all_data.empty or all_data['Close'].dropna(how='all').empty:
        metrics.add_error("RuntimeError", "No valid market data received from yfinance", "data_validation")
        raise ValueError("No valid market data received from yfinance - check symbols and date range")
    
    # === RECOVERY: re-fetch what the batch download missed ===
    # Runs BEFORE the drop below, so a symbol that comes back on the second pass
    # keeps its place in the universe instead of vanishing from the book.
    if len(symbols_to_process) > 1:
        all_data, recovery = _recover_missing_symbols(
            all_data, symbols_to_process, start_date, end_date
        )
        metrics.data_recovery = recovery
        if recovery["recovered"]:
            metrics.add_warning(
                f"Re-fetched {len(recovery['recovered'])} symbol(s) the batch download "
                f"missed: {', '.join(recovery['recovered'])}"
            )

    # === VALIDATION 4: Remove Failed Tickers ===
    if len(symbols_to_process) > 1:
        valid_tickers = all_data['Close'].dropna(how='all', axis=1).columns
        invalid_tickers = [s for s in symbols_to_process if s not in valid_tickers]
        
        if invalid_tickers:
            invalid_ratio = len(invalid_tickers) / len(symbols_to_process)
            # Every drop is now reported, not just a majority failure: a book
            # built on 28 of 30 names is a different book, and the two symbols
            # survived a dedicated re-fetch before being given up on.
            metrics.add_warning(
                f"{len(invalid_tickers)}/{len(symbols_to_process)} tickers have no data "
                f"after re-fetch: {', '.join(invalid_tickers[:12])}"
                + (" …" if len(invalid_tickers) > 12 else "")
            )
            try:
                from logger_config import console
                if invalid_ratio > 0.5:
                    console.warning(
                        f"⚠️ {len(invalid_tickers)}/{len(symbols_to_process)} tickers have no data - check symbol validity"
                    )
                else:
                    console.warning(
                        f"Dropping {len(invalid_tickers)} symbol(s) with no data after re-fetch: "
                        f"{', '.join(invalid_tickers[:12])}"
                    )
            except Exception:
                pass
            
            if len(invalid_tickers) == len(symbols_to_process):
                metrics.add_error(
                    "RuntimeError", 
                    "No valid tickers in data - all symbols failed", 
                    "ticker_validation"
                )
                raise ValueError("No valid tickers in data - all symbols failed. Check your universe selection")
            
            all_data = all_data.loc[:, (slice(None), valid_tickers)]
            # Filter the EXISTING order rather than adopting yfinance's column
            # order, which is alphabetical. Snapshot rows are emitted in this
            # order and Equal Weight now selects in it (see nco.compute_nco_
            # portfolio), so a partial failure must not silently reorder the
            # universe.
            _valid = set(valid_tickers)
            symbols_to_process = [s for s in symbols_to_process if s in _valid]
    
    # Update metrics with actual valid symbols
    metrics.symbols_count = len(symbols_to_process)
    
    all_data.columns.names = ['Indicator', 'Symbol']
    oscillator_calculator = LiquidityOscillator(length=20, impact_window=3)
    
    # 2. --- Pre-calculate all indicators for all symbols ---
    ticker_indicator_cache = {}
    for i, ticker in enumerate(symbols_to_process):
        try:
            if len(symbols_to_process) > 1:
                symbol_df = all_data.xs(ticker, level='Symbol', axis=1).copy()
            else:
                symbol_df = all_data.copy()
                
            symbol_df.columns = [col.lower() for col in symbol_df.columns]
            
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in symbol_df.columns:
                    symbol_df[col] = pd.to_numeric(symbol_df[col], errors='coerce')
            
            symbol_df = symbol_df.dropna(subset=['close', 'volume'])
            symbol_df.name = ticker
            
            if not symbol_df.empty:
                indicators_df = calculate_all_indicators(symbol_df, oscillator_calculator)
                # calculate_all_indicators returns None for a symbol it cannot
                # compute. Caching that None meant the snapshot loop below
                # dereferenced it (`full_indicator_df.index`) and took the whole
                # run down over one bad symbol — the failure mode the per-symbol
                # skip in this loop's except clause exists to prevent.
                if indicators_df is not None:
                    ticker_indicator_cache[ticker] = indicators_df

        except (pd.errors.DataError, KeyError, IndexError, ValueError) as e:
            # ValueError added: a malformed bar (e.g. NaN high/low reaching an
            # int(np.floor(...)) call before the guard in compute_volume_profile
            # was fixed) previously aborted the WHOLE data-fetch phase for
            # every symbol, not just the offending one. One bad ticker must
            # not fail the run — log and skip it instead.
            try:
                from logger_config import console
                console.warning(f"Skipping {ticker}: indicator computation failed ({type(e).__name__}: {e})")
            except Exception:
                pass
            continue

    # 3. --- Generate Daily Snapshots in Memory ---
    pragati_data_list: List[Tuple[datetime, pd.DataFrame]] = []
    # Use the index of the downloaded data as the authoritative date range
    date_range = all_data.index.normalize().unique()

    # Warm-up is measured in TRADING bars, not calendar days: ma200 needs 200
    # trading rows (~290 calendar days for NSE/US calendars with weekends +
    # holidays), so a calendar-day cutoff of MAX_INDICATOR_PERIOD (200) days
    # left the first ~90 calendar days (~30% of a typical panel) with NaN
    # ma200/ma90-weekly etc. still being emitted as snapshots. Skip the first
    # MAX_INDICATOR_PERIOD *bars* of date_range instead — the caller already
    # over-fetches enough calendar days (see _load_historical_data's x1.5+30
    # buffer) to have that many bars available before the requested window.
    _warm_dates = set(date_range[:MAX_INDICATOR_PERIOD])

    # Align every symbol onto the SHARED trading calendar with a bounded
    # forward-fill.
    #
    # Each symbol's indicator frame is indexed by its OWN print dates. A thinly
    # traded instrument that simply didn't tick on a given day was therefore
    # absent from that day's snapshot entirely — not "stale", but gone: excluded
    # from the eligible set and from the book. On the ETF
    # universe this silently removed 19 of 30 names from the live run measured
    # on 2026-07-28, because yfinance had not yet published that bar for them.
    # A one-day data gap is not a reason to liquidate a position.
    #
    # Reindexing onto the union calendar with ffill(limit=_STALE_BARS) carries a
    # symbol's last known values across a short gap while still dropping
    # anything that has genuinely stopped trading. The limit is what makes this
    # safe: an unbounded ffill would keep a delisted instrument in the book
    # forever at a frozen price. Leading NaNs are untouched (ffill only
    # propagates forward), so a symbol still cannot appear before its history
    # begins, and the warmup skip above is unaffected.
    for _t in list(ticker_indicator_cache):
        _df = ticker_indicator_cache[_t]
        if _df is None or _df.empty:
            continue
        ticker_indicator_cache[_t] = _df.reindex(date_range).ffill(limit=_STALE_BARS)

    for snapshot_date in date_range:
        # --- Only start generating snapshots *after* the indicator warmup
        # We also only care about dates *within* the requested range (end_date)
        if snapshot_date in _warm_dates or snapshot_date > end_date:
            continue

        daily_results: List[Dict[str, Any]] = []
        for ticker in symbols_to_process:
            if ticker not in ticker_indicator_cache:
                continue
            
            full_indicator_df = ticker_indicator_cache[ticker]
            
            if snapshot_date not in full_indicator_df.index:
                continue
                
            try:
                indicator_row = full_indicator_df.loc[snapshot_date]
                if indicator_row.isnull().all() or pd.isna(indicator_row.get('price')):
                    continue # Skip if all data is NaN or price is NaN

                indicators = indicator_row.to_dict()
                indicators['symbol'] = ticker.replace('.NS', '')
                indicators['date'] = snapshot_date.strftime('%d %b')
                indicators['% change'] = indicators['% change'] * 100
                
                daily_results.append(indicators)
            except KeyError:
                continue
        
        if daily_results:
            final_df = pd.DataFrame(daily_results)
            for col in COLUMN_ORDER:
                if col not in final_df.columns:
                    final_df[col] = pd.NA
            
            final_df = final_df[COLUMN_ORDER]
            pragati_data_list.append((snapshot_date, final_df))

    return pragati_data_list


def main():
    """Standalone Streamlit UI for generating indicator snapshots."""
    import streamlit as st
    import zipfile
    import shutil

    st.set_page_config(
        page_title="Indicator Snapshot Generator (Optimized)",
        page_icon="⚡",
        layout="wide"
    )
    
    st.title("📊 Daily Indicator Snapshot Generator (Optimized)")

    with st.sidebar:
        st.header("1. Select Date Range")
        today = datetime.now()
        # --- UPDATED: Default start date to be far enough back for indicators
        default_start = today - timedelta(days=MAX_INDICATOR_PERIOD + 90)
        start_date = st.date_input("Start Date", default_start)
        end_date = st.date_input("End Date", today)

        st.header("2. Ticker Universe")
        if SYMBOLS_UNIVERSE:
            st.info(f"Using default ETF universe ({len(SYMBOLS_UNIVERSE)} tickers).")
            with st.expander("View Tickers"):
                st.dataframe(SYMBOLS_UNIVERSE, width='stretch')
        else:
            st.error("No tickers available. Cannot proceed.")
        
        st.header("3. Generate")
        process_button = st.button("Generate Snapshots", type="primary", width='stretch')

    if process_button:
        if start_date > end_date:
            st.error("Error: Start date cannot be after end date.")
        elif not SYMBOLS_UNIVERSE:
            st.error("Error: No tickers available in the default universe.")
        else:
            symbols_to_process = SYMBOLS_UNIVERSE
            
            fetch_start_date = start_date - timedelta(days=int(MAX_INDICATOR_PERIOD * 1.5) + 30)

            with st.spinner(f"Generating historical data from {fetch_start_date} to {end_date}..."):
                all_generated_data = generate_historical_data(
                    symbols_to_process, 
                    fetch_start_date, # Pass the earlier date for indicator warmup
                    end_date
                )
            
            if not all_generated_data:
                st.error("Failed to generate any data.")
                return

            # --- Filter the generated data to *only* the user's requested date range
            all_generated_data = [
                (date, df) for date, df in all_generated_data 
                if date.date() >= start_date and date.date() <= end_date
            ]
            
            if not all_generated_data:
                st.warning("Data was fetched, but no valid trading days found in the selected Start/End range.")
                return

            base_dir = "data"
            reports_dir = os.path.join(base_dir, "historical")
            zip_dir = os.path.join(base_dir, "zip")

            if os.path.exists(base_dir):
                shutil.rmtree(base_dir)
            os.makedirs(reports_dir)
            os.makedirs(zip_dir)

            st.info("Saving daily snapshots to 'data/historical' folder...")
            progress_bar = st.progress(0)
            last_day_df = pd.DataFrame()

            if all_generated_data:
                for i, (snapshot_date, final_df) in enumerate(all_generated_data):
                    if not final_df.empty:
                        last_day_df = final_df
                        filename = os.path.join(reports_dir, f"{snapshot_date.strftime('%Y-%m-%d')}.csv")
                        final_df.to_csv(filename, index=False, float_format='%.2f')
                    
                    progress_bar.progress((i + 1) / len(all_generated_data))
            
                zip_file_name_only = f"indicator_reports_{start_date.strftime('%Y%m%d')}_to_{end_date.strftime('%Y%m%d')}.zip"
                zip_full_path = os.path.join(zip_dir, zip_file_name_only)
                
                with zipfile.ZipFile(zip_full_path, 'w') as zipf:
                    for root, _, files in os.walk(reports_dir):
                        for file in files:
                            zipf.write(os.path.join(root, file), os.path.join(os.path.basename(root), file))

                st.success("✅ Snapshots and Zip file generated successfully in the 'data' folder!")
                
                st.subheader(f"Data for {end_date.strftime('%Y-%m-%d')} (Last Day)")
                if not last_day_df.empty:
                    st.dataframe(last_day_df[COLUMN_ORDER].round(2))
                
                with open(zip_full_path, "rb") as fp:
                    st.download_button(
                        label="⬇️ Download All Reports (.zip)",
                        data=fp,
                        file_name=zip_file_name_only,
                        mime="application/zip"
                    )
            else:
                st.warning("No data was generated for the selected date range.")

__all__ = [
    'LiquidityOscillator',
    'resample_data',
    'calculate_rsi',
    'calculate_all_indicators',
    'get_default_universe',
    'generate_historical_data',
    'SYMBOLS_UNIVERSE',
    'MAX_INDICATOR_PERIOD',
]

if __name__ == "__main__":
    main()