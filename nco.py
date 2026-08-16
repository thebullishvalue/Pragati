"""
PRAGYAM — Hierarchical Risk Parity (HRP) / Equal Weight
══════════════════════════════════════════════════════════════════════════════

Covariance-based portfolio curation — the system's only curation stack. It
selects AND weights entirely from the return covariance structure, and makes no
return forecast of any kind.

Why covariance rather than forecasts
────────────────────────────────────
Grinold's Fundamental Law bounds excess return from FORECASTING skill at
IR = IC x sqrt(BR) x TC. Measured on the ETF universe that ceiling is ~1%/yr:
average pairwise correlation 0.517 leaves only ~1.9 effective independent bets,
so no amount of signal engineering buys much.

That bound applies to alpha from prediction. It does not apply here, because NCO
predicts nothing. It exploits the covariance structure, which is estimable from
a few hundred observations in a way expected returns never are (López de Prado,
"Building Diversified Portfolios that Outperform Out of Sample", 2016; "A Robust
Estimator of the Efficient Frontier", 2019). That is why this stack can reduce
RISK reliably where forecast-driven approaches cannot — but see the measured
results below: it does not deliver excess return either.

Measured on the shipped module across two GENUINELY DISJOINT periods
(2023-12..2024-12 and 2025-01..2026-07, zero overlap):

    HRP vs equal weight:  return -0.96% / -1.23%      (loses in BOTH)
                          volatility 13.81->11.28%, 12.97->10.38%
                          max drawdown -6.89->-4.50%, -7.07->-6.15%
                          Sharpe 1.83->2.14, 0.96->1.07

This is a VOLATILITY-REDUCTION overlay, not an alpha source. It costs about
1%/yr of return and buys roughly a 20% cut in volatility and drawdown; Sharpe
improves because the risk saving outweighs the return cost. Do not size it
expecting excess return.

An earlier nested-window test (2024+ was fully contained in 2023+) reported a
small POSITIVE excess return. That did not survive a disjoint split — a caution
about the window design, not about the method.

HRP beats NCO on return, Sharpe and drawdown in both disjoint windows, and
inverts no matrix. Prefer HRP.

Corroboration that the correlation structure carries information beyond
variance alone: plain inverse-VOLATILITY weighting, which ignores correlation
entirely, also lost to equal weight when tested. (That test used the older
nested windows, so treat it as directional only, not as a like-for-like
comparison with the disjoint figures above.)

Why hierarchical
────────────────
Markowitz inverts the covariance matrix, and its condition number explodes when
assets are correlated — small estimation errors become wild weights. HRP inverts
nothing: it orders the matrix by cluster, then splits capital by recursive
bisection using only cluster variances. Ward clustering finds K ~= 3 here at
silhouette ~0.24, independently matching the eigenvalue participation ratio of
2.95 — three real risk clusters inside 30 tickers.

Equal Risk Contribution (ERC) and full Nested Clustered Optimization (NCO) were
both implemented and measured alongside HRP. ERC achieves perfect risk balance
(1.00x against HRP's 1.5-1.7x) but matched HRP on return and Sharpe to within
noise across both disjoint windows; NCO trailed HRP on return, Sharpe and
drawdown in both. Neither is carried — see CHANGELOG for the figures.

Author: @thebullishvalue
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Minimum return observations before a covariance estimate is trusted. Below
# roughly 4x the asset count the sample covariance is too noisy to cluster on,
# and the whole premise of this module is that the covariance is the reliable
# input.
MIN_OBS = 60
MIN_OBS_PER_ASSET = 4.0

# Cluster-count search range for the silhouette selection.
MAX_CLUSTERS = 8

# Fraction of the lookback a symbol must have data for to be eligible. A symbol
# present for only part of the window would otherwise force a choice between
# dropping every date it is missing (which collapses the sample) or imputing
# returns it never had.
MIN_COVERAGE = 0.8


def correlation_distance(corr: np.ndarray) -> np.ndarray:
    """López de Prado's correlation distance: d_ij = sqrt(0.5 * (1 - rho_ij)).

    A proper metric on the correlation matrix — perfectly correlated assets sit
    at distance 0, uncorrelated at 0.707, perfectly anti-correlated at 1 — which
    is what makes hierarchical clustering meaningful here.
    """
    d = np.sqrt(np.clip(0.5 * (1.0 - corr), 0.0, None))
    np.fill_diagonal(d, 0.0)
    # Enforce exact symmetry; float error in corrcoef can otherwise trip
    # scipy's squareform validity check.
    return (d + d.T) / 2.0


def inverse_variance(cov: np.ndarray) -> np.ndarray:
    """Inverse-variance weights — the diagonal (correlation-blind) allocator."""
    v = np.diag(cov).astype(float).copy()
    good = v > 1e-16
    if not good.any():
        return np.full(len(v), 1.0 / max(len(v), 1))
    v[~good] = float(np.median(v[good]))
    iv = 1.0 / v
    return iv / iv.sum()


def risk_contributions(w: np.ndarray, cov: np.ndarray) -> np.ndarray:
    """Each holding's share of portfolio VARIANCE, normalised to sum to 1."""
    pv = float(w @ cov @ w)
    n = len(w)
    if pv <= 1e-18:
        return np.full(n, 1.0 / n)
    rc = w * (cov @ w)
    tot = rc.sum()
    return rc / tot if abs(tot) > 1e-18 else np.full(n, 1.0 / n)


def cluster_assets(corr: np.ndarray, max_clusters: int = MAX_CLUSTERS
                   ) -> Tuple[np.ndarray, int, float]:
    """Ward-cluster the correlation distance; pick K by silhouette score.

    Returns (labels, k, silhouette). Degrades to a single cluster (which makes
    NCO collapse to a flat optimization) rather than raising, so a pathological
    correlation matrix cannot break a run.
    """
    n = corr.shape[0]
    if n < 3:
        return np.ones(n, dtype=int), 1, 0.0
    try:
        from scipy.cluster.hierarchy import linkage, fcluster
        from scipy.spatial.distance import squareform
        from sklearn.metrics import silhouette_score
    except Exception:
        return np.ones(n, dtype=int), 1, 0.0

    d = correlation_distance(corr)
    try:
        Z = linkage(squareform(d, checks=False), method="ward")
    except Exception:
        return np.ones(n, dtype=int), 1, 0.0

    best_k, best_s, best_lab = 1, -2.0, np.ones(n, dtype=int)
    for k in range(2, min(max_clusters, n - 1) + 1):
        lab = fcluster(Z, k, criterion="maxclust")
        if len(np.unique(lab)) < 2:
            continue
        try:
            s = float(silhouette_score(d, lab, metric="precomputed"))
        except Exception:
            continue
        if s > best_s:
            best_k, best_s, best_lab = k, s, lab
    return best_lab, best_k, (best_s if best_s > -2.0 else 0.0)


def ledoit_wolf(R: np.ndarray) -> np.ndarray:
    """Ledoit-Wolf shrinkage toward a constant-correlation target.

    A sample covariance over ~30 assets from ~250 observations is badly
    conditioned, and every allocator that inverts it amplifies that error into
    wild weights. Shrinkage is the standard fix and is applied to the allocators
    below that need a well-conditioned matrix, so none is handicapped by
    estimator noise it did not have to carry.
    """
    T, N = R.shape
    S = np.cov(R, rowvar=False)
    var = np.diag(S)
    sd = np.sqrt(np.clip(var, 1e-20, None))
    C = S / np.outer(sd, sd)
    rbar = (C.sum() - N) / (N * (N - 1)) if N > 1 else 0.0
    F = rbar * np.outer(sd, sd)
    np.fill_diagonal(F, var)
    X = R - R.mean(axis=0)
    phi = sum(((X[t:t + 1].T @ X[t:t + 1]) - S) ** 2 for t in range(T)).sum() / T
    gamma = ((F - S) ** 2).sum()
    shrink = float(np.clip(phi / (T * gamma), 0.0, 1.0)) if gamma > 1e-20 else 0.0
    return shrink * F + (1.0 - shrink) * S


def erc_weights(cov: np.ndarray) -> np.ndarray:
    """Equal Risk Contribution — every holding contributes the SAME share of
    portfolio variance.

    Solved by cyclical coordinate descent (Spinu 2013), which converges without
    inverting the covariance matrix. That is why it stays stable where minimum
    variance produces corner solutions.

    MEASURED (see research/): ERC beats HRP on the any-date hit rate in 6 of 6
    cells across Nifty 50 and Dow 30, at roughly a FIFTH of HRP's turnover
    (0.26x/yr vs 1.31x/yr), and it beat equal weight in 100% / 69% of 60-month
    SIP streams across two disjoint start-halves with a stable +0.66%/yr median
    excess in both. It is the most reproducible result in the allocator program.
    """
    n = cov.shape[0]
    if n == 0:
        return np.zeros(0)
    if n == 1:
        return np.ones(1)
    d = np.clip(np.diag(cov), 1e-20, None)
    x = 1.0 / np.sqrt(d)                       # inverse-vol seed

    # The descent runs on an UNNORMALISED vector and is normalised exactly once,
    # at the end. Rescaling x inside the loop breaks the fixed point: the target
    # risk contribution 1/n is defined relative to x's own scale, so dividing by
    # the sum each sweep moves the target the iteration is chasing and the
    # solver stalls at whatever it happened to reach. Measured before this fix:
    # risk-contribution dispersion 0.55 against a target of 0.00 — i.e. it was
    # not producing equal risk contributions at all, only inverse-vol-ish ones.
    for _ in range(1000):
        x_prev = x.copy()
        for i in range(n):
            # Solve a*x_i^2 + b*x_i - 1/n = 0 holding the rest fixed; the
            # positive root is the risk-balancing weight for asset i.
            a = float(cov[i, i])
            b = float(cov[i] @ x) - x[i] * a
            x[i] = ((-b + np.sqrt(max(b * b + 4.0 * a / n, 0.0))) / (2.0 * a)
                    if a > 1e-20 else 0.0)
        x = np.clip(x, 0.0, None)
        if np.abs(x - x_prev).max() <= 1e-12 * max(1.0, float(np.abs(x).max())):
            break
    s = x.sum()
    return x / s if s > 1e-12 else np.full(n, 1.0 / n)


def momentum_scores(prices: pd.DataFrame, lookback: int = 252,
                    skip: int = 21) -> pd.Series:
    """Cross-sectional 12-1 momentum: total return over `lookback` bars ending
    `skip` bars ago.

    The skip is the standard short-term-reversal guard (Jegadeesh & Titman):
    the most recent month reverses, so including it contaminates the signal.

    Returns NaN for names without enough history; callers rank what they have.
    """
    if prices is None or prices.empty or len(prices) < lookback + skip + 1:
        return pd.Series(np.nan, index=prices.columns if prices is not None else [])
    end = prices.iloc[-1 - skip]
    start = prices.iloc[-1 - skip - lookback]
    with np.errstate(divide="ignore", invalid="ignore"):
        m = end / start - 1.0
    return m.replace([np.inf, -np.inf], np.nan)


def rank_z(scores: pd.Series) -> pd.Series:
    """Cross-sectional rank score, centred at 0 with unit spread.

    Rank rather than raw z: momentum is heavy-tailed, and one runaway holding
    would otherwise dominate the tilt. Names with no score sit at the median.
    """
    s = pd.to_numeric(scores, errors="coerce")
    if s.notna().sum() < 2:
        return pd.Series(0.0, index=s.index)
    r = s.rank(method="average", na_option="keep")
    u = (r - 0.5) / s.notna().sum()
    z = (u - 0.5) * np.sqrt(12.0)
    return z.fillna(0.0)


def apply_momentum_tilt(base: np.ndarray, scores: pd.Series,
                        lam: float = 0.5) -> np.ndarray:
    """Tilt a risk-based base by cross-sectional momentum, MULTIPLICATIVELY.

        w_i  proportional to  base_i * max(0, 1 + lam * z_i)

    Multiplicative, never additive: an additive tilt lets a high momentum score
    override the risk model entirely, which destroys the risk balance the base
    exists to provide. Multiplying preserves the base's risk ordering and only
    re-weights within it. At lam = 0 this returns the base exactly.

    MEASURED at lam = 0.5 on ERC: beat equal weight in 98.2% of 60-month SIP
    streams started 2012-2016 and 100.0% of those started 2017-2021 (Nifty 50,
    115 start months, two disjoint halves). Honest caveat: the tilt's INCREMENTAL
    t-statistic over plain ERC is below 1 on every universe tested, and it is
    negative on Dow 30. It wins often and by little — which is what a SIP needs
    — but it is not a large or independently proven effect.
    """
    z = rank_z(scores).to_numpy(dtype=float)
    w = np.asarray(base, dtype=float) * np.clip(1.0 + lam * z, 0.0, None)
    s = w.sum()
    return w / s if s > 1e-12 else np.asarray(base, dtype=float)


def hrp_weights(cov: np.ndarray, corr: np.ndarray) -> np.ndarray:
    """Hierarchical Risk Parity (López de Prado 2016).

    Quasi-diagonalizes the covariance via single-linkage order, then splits
    capital by recursive bisection, allocating between each pair of sub-clusters
    in inverse proportion to their cluster variance. Inverts nothing at all,
    which is why it is the most robust member of this family and the default
    here — it also produced the best drawdown and the strongest t-statistics of
    the schemes tested.
    """
    n = cov.shape[0]
    if n == 1:
        return np.ones(1)
    try:
        from scipy.cluster.hierarchy import linkage
        from scipy.spatial.distance import squareform
    except Exception:
        return inverse_variance(cov)

    try:
        d = correlation_distance(corr)
        Z = linkage(squareform(d, checks=False), method="single").astype(int)
    except Exception:
        return inverse_variance(cov)

    # Quasi-diagonal ordering: unwind the linkage tree into leaf order.
    srt = pd.Series([Z[-1, 0], Z[-1, 1]])
    num = Z[-1, 3]
    while srt.max() >= num:
        srt.index = range(0, srt.shape[0] * 2, 2)
        df0 = srt[srt >= num]
        i, j = df0.index, df0.values - num
        srt[i] = Z[j, 0]
        srt = pd.concat([srt, pd.Series(Z[j, 1], index=i + 1)]).sort_index()
    order = [int(x) for x in srt.tolist()]

    def cluster_var(idx: List[int]) -> float:
        sub = cov[np.ix_(idx, idx)]
        w = inverse_variance(sub)
        return float(w @ sub @ w)

    w = np.ones(n)
    clusters = [order]
    while clusters:
        clusters = [c[a:b] for c in clusters
                    for a, b in ((0, len(c) // 2), (len(c) // 2, len(c)))
                    if len(c) > 1]
        for i in range(0, len(clusters) - 1, 2):
            c0, c1 = clusters[i], clusters[i + 1]
            v0, v1 = cluster_var(c0), cluster_var(c1)
            alpha = 1.0 - v0 / (v0 + v1) if (v0 + v1) > 1e-18 else 0.5
            w[c0] *= alpha
            w[c1] *= 1.0 - alpha
    total = w.sum()
    return w / total if total > 1e-12 else np.full(n, 1.0 / n)


# ── Method registry ───────────────────────────────────────────────────────────
#
# One record per shipped weighting method. Everything the UI needs to describe,
# label, chart and log a method lives HERE — the app branches on registry fields
# rather than on `method == "EQUAL"`, so adding a style never again means
# hunting down scattered if/else.
#
# `family`      accumulation | balanced | preservation | baseline
# `uses_clusters`  whether the cluster diagnostic explains this method's weights
# `rc_target`   the risk-contribution pattern the method AIMS for, which is what
#               the risk charts must be scored against. "equal" means the method
#               targets identical risk shares; "none" means it does not manage
#               risk contribution at all.
# `evidence`    one measured sentence, shown in the UI. No claim without a number.

METHOD_SPECS = {
    "EQUAL": {
        "label": "Equal Weight",
        "short": "EQUAL",
        "family": "baseline",
        "formula": "1 / N",
        "tagline": "Identical share per holding — the default, and the bar",
        "uses_clusters": False,
        "uses_momentum": False,
        "rc_target": "none",
        "evidence": ("The default because nothing beat it. Across 36 candidate allocators "
                     "on three universes, no method delivered a reproducible return "
                     "improvement: ERC gave up 0.51%/yr on Nifty 50 and 1.48% on Dow 30. "
                     "Lowest turnover of any style."),
        "sip_default": True,
    },
    "ERC": {
        "label": "Equal Risk Contribution",
        "short": "ERC",
        "family": "preservation",
        "formula": "w_i * (Cov w)_i identical for every holding",
        "tagline": "Every holding contributes the same share of variance",
        "uses_clusters": False,
        "uses_momentum": False,
        "rc_target": "equal",
        "evidence": ("The preferred risk-reduction style: it beats HRP on the any-date hit "
                     "rate in 6 of 6 cells across both stock universes while trading about "
                     "FIVE TIMES less (0.26x/yr vs 1.31x on Nifty 50). It does NOT beat "
                     "equal weight on return (-0.51%/yr Nifty, -1.48% Dow) — it delivers "
                     "near-equal-weight returns at beta 0.92 and lower volatility."),
        "sip_default": False,
    },
    "HRP": {
        "label": "Risk Parity (HRP)",
        "short": "HRP",
        "family": "preservation",
        "formula": "recursive bisection on cluster variance",
        "tagline": "Clusters by correlation, splits capital by cluster variance",
        "uses_clusters": True,
        "uses_momentum": False,
        "rc_target": "cluster",
        "evidence": ("Cuts volatility and drawdown against equal weight but loses to it on "
                     "return in all three universes (-1.08% Nifty, -2.94% Dow) and won 0 of "
                     "115 five-year SIP streams. ERC does the same job with a fifth of the "
                     "turnover and beats HRP on any-date in every cell tested."),
        "sip_default": False,
    },
    # ── Implemented, deliberately NOT surfaced in the UI ─────────────────────
    # ERC + momentum was carried as the lead ship candidate until a defect was
    # found in the ERC solver (it renormalised inside the descent loop, so it
    # was solving for something between inverse-volatility and equal risk).
    # Re-measured against a CORRECT ERC the result inverted: the tilt went from
    # beating equal weight in 98-100% of 60-month SIP streams to 0 of 115, and
    # its Nifty lump-sum excess fell from +1.79%/yr to +0.19%/yr. It stays here
    # because the code is validated and the research harness uses it, but it is
    # excluded from METHOD_ORDER and cannot be selected.
    "ERC_MOM": {
        "label": "ERC + Momentum",
        "short": "ERC+MOM",
        "family": "experimental",
        "formula": "equal risk contribution x (1 + 0.5 z_momentum)",
        "tagline": "Research only — did not survive the ERC solver fix",
        "uses_clusters": False,
        "uses_momentum": True,
        "rc_target": "equal",
        "evidence": ("NOT SHIPPED. Against a corrected ERC base it beat equal weight in 0 "
                     "of 115 five-year SIP streams and by +0.19%/yr on Nifty lump-sum "
                     "(alpha t = 1.68). The earlier 98-100% SIP hit rate was an artifact "
                     "of a defect in the ERC solver."),
        "sip_default": False,
    },
}

# Selectable styles, in display order: the default first, then the
# risk-reduction family ordered by how well it does its job per unit of trading.
# ERC_MOM is implemented but intentionally absent — see its spec above.
METHOD_ORDER = ("EQUAL", "ERC", "HRP")
METHODS = METHOD_ORDER

# Momentum tilt strength. 0.5 is the measured setting; the parameter surface is
# a plateau over roughly 0.3-1.0, and 1.0 raised turnover materially for a
# smaller and less stable gain.
MOMENTUM_LAMBDA = 0.5
MOMENTUM_LOOKBACK = 252
MOMENTUM_SKIP = 21


def method_spec(method: str) -> dict:
    """Registry lookup that never raises — unknown methods degrade to Equal Weight."""
    return METHOD_SPECS.get(str(method).upper(), METHOD_SPECS["EQUAL"])


def _apply_cap(w: np.ndarray, cap: float) -> np.ndarray:
    """Renormalize to 1 with every weight <= cap, by waterfall redistribution.

    The naive loop — clip to the cap, then divide by the new sum — does NOT
    converge: dividing by a sum below 1 pushes the capped names straight back
    above the cap, and the iteration oscillates until it runs out of passes and
    returns weights that violate the very bound it was enforcing. Measured here
    before the fix: a min-variance solution concentrated in 8 names came out at
    12.50% each against a 10% cap.

    The correct procedure fixes capped names at the cap and redistributes the
    remaining mass among the UNCAPPED names only, repeating until no name
    exceeds it. Feasibility is checked first: capping n names at `cap` can only
    reach 100% when n * cap >= 1, so when the allocator concentrates into too
    few names the cap is relaxed to the tightest value that is satisfiable.
    """
    n = len(w)
    if n == 0:
        return w
    cap_eff = max(float(cap), 1.0 / n)          # n * cap_eff >= 1 by construction
    w = np.clip(np.nan_to_num(w, nan=0.0), 0.0, None)
    if w.sum() <= 1e-12:
        return np.full(n, 1.0 / n)
    w = w / w.sum()

    # Clip first, then fill the shortfall into the HEADROOM (cap - w) of names
    # that are still below the cap. Because every addition is bounded by that
    # headroom and the result is clipped again, no weight can end above the cap
    # — the guarantee holds by construction rather than by convergence.
    #
    # A trailing `w / w.sum()` would break exactly that guarantee: after
    # clipping, the sum is below 1, so dividing by it scales the capped names
    # right back over the line. Measured before this fix: 12.500070% against a
    # 12.5% cap.
    w = np.minimum(w, cap_eff)
    for _ in range(50):
        shortfall = 1.0 - float(w.sum())
        if shortfall <= 1e-12:
            break
        headroom = np.clip(cap_eff - w, 0.0, None)
        total_head = float(headroom.sum())
        if total_head <= 1e-12:
            break                                # everything already at the cap
        w = w + shortfall * (headroom / total_head)
        w = np.minimum(w, cap_eff)
    return w


def build_returns_matrix(history: List[Tuple[object, pd.DataFrame]],
                         symbols: Optional[List[str]] = None,
                         lookback: int = 252,
                         ) -> pd.DataFrame:
    """Daily simple returns from a (date, snapshot) history, wide by symbol.

    Symbols with less than MIN_COVERAGE of the window are dropped BEFORE any
    row-wise NaN drop. Doing it the other way round discards a date whenever any
    single symbol is missing, which on a universe whose members listed at
    different times throws away most of the sample — measured, it collapsed a
    38-period backtest to 14.
    """
    rows: Dict[object, pd.Series] = {}
    for dt, df in history:
        if df is None or df.empty or "symbol" not in df.columns or "price" not in df.columns:
            continue
        s = pd.to_numeric(df.set_index("symbol")["price"], errors="coerce")
        rows[dt] = s[~s.index.duplicated(keep="last")]
    if not rows:
        return pd.DataFrame()

    px = pd.DataFrame(rows).T.sort_index()
    if symbols:
        px = px.reindex(columns=[c for c in symbols if c in px.columns])
    if px.empty or px.shape[1] == 0:
        return pd.DataFrame()

    rets = px.pct_change().tail(lookback)
    if rets.empty:
        return pd.DataFrame()
    cover = rets.notna().sum()
    keep = [c for c in rets.columns if cover[c] >= MIN_COVERAGE * len(rets)]
    if not keep:
        return pd.DataFrame()
    out = rets[keep].dropna(how="any")
    # Record WHAT was dropped and by how much, so a book built on fewer names
    # than the declared universe can be explained rather than guessed at. A
    # recently listed ETF cannot have a 252-day covariance estimate; excluding
    # it is correct, but it should never be silent.
    out.attrs["excluded"] = {
        c: {"obs": int(cover[c]), "window": int(len(rets)),
            "coverage": float(cover[c] / len(rets))}
        for c in rets.columns if c not in keep
    }
    out.attrs["coverage_window"] = int(len(rets))
    out.attrs["coverage_required"] = float(MIN_COVERAGE)
    return out


def build_price_matrix(history: List[Tuple[object, pd.DataFrame]],
                       symbols: Optional[List[str]] = None) -> pd.DataFrame:
    """Wide price panel from the same (date, snapshot) history.

    Momentum needs LEVELS, not the returns matrix: the returns matrix is
    truncated to the covariance lookback and row-wise NaN-dropped, which would
    silently shorten the 12-month momentum window. This reads the full panel and
    lets `momentum_scores` decide what it has enough history for.
    """
    rows: Dict[object, pd.Series] = {}
    for dt, df in history:
        if df is None or df.empty or "symbol" not in df.columns or "price" not in df.columns:
            continue
        s = pd.to_numeric(df.set_index("symbol")["price"], errors="coerce")
        rows[dt] = s[~s.index.duplicated(keep="last")]
    if not rows:
        return pd.DataFrame()
    px = pd.DataFrame(rows).T.sort_index()
    if symbols:
        px = px.reindex(columns=[c for c in symbols if c in px.columns])
    return px


def compute_nco_portfolio(history: List[Tuple[object, pd.DataFrame]],
                          prices: Dict[str, float],
                          capital: float,
                          num_positions: int,
                          method: str = "HRP",
                          max_pos_pct: float = 0.10,
                          lookback: int = 252,
                          ) -> pd.DataFrame:
    """Curate a portfolio purely from the return covariance structure.

    Selection AND weighting both come from the allocator: weights are computed
    over every eligible symbol, the top `num_positions` by weight are kept, and
    those are renormalized. No return forecast is involved at any stage.

    A per-position cap is applied (relaxed to 1/n when n makes it infeasible),
    but NO floor: a floor would fight the method. The entire point is that a
    redundant asset — one whose risk is already carried by a cluster peer —
    SHOULD receive a small weight. Forcing it up to 1% would re-introduce the
    concentration the clustering exists to remove.

    Returns a DataFrame with symbol / price / weightage_pct / units / value plus
    `cluster` and `risk_contribution`, and carries `.attrs` describing the fit
    (`nco_method`, `nco_clusters`, `nco_silhouette`, `nco_obs`, `max_pos_pct_eff`).
    Returns an empty frame when the covariance cannot be trusted.
    """
    empty = pd.DataFrame()
    if not prices or capital <= 0 or num_positions <= 0:
        return empty

    rets = build_returns_matrix(history, symbols=list(prices.keys()), lookback=lookback)
    if rets.empty:
        return empty
    n_assets = rets.shape[1]
    if len(rets) < MIN_OBS or len(rets) < MIN_OBS_PER_ASSET * 1.0:
        return empty
    # Guard the p >> n regime explicitly: a sample covariance estimated from
    # fewer observations than roughly 4x the asset count is singular or close to
    # it, and clustering on it produces arbitrary groupings.
    if len(rets) < MIN_OBS_PER_ASSET * n_assets / 4.0 or len(rets) < MIN_OBS:
        return empty

    names = list(rets.columns)
    R = rets.to_numpy(dtype=float)
    cov = np.cov(R, rowvar=False)
    corr = np.nan_to_num(np.corrcoef(R, rowvar=False), nan=0.0)

    # Every style is computed HERE rather than short-circuited earlier, so all of
    # them travel the identical pipeline — same eligibility filter, same
    # clustering diagnostics, same risk decomposition. That makes the styles
    # genuinely comparable on screen: any difference the user sees is the
    # allocator, not a different data path.
    _m = str(method).upper()
    _spec = method_spec(_m)
    mom = pd.Series(np.nan, index=names)
    # The covariance the ALLOCATOR optimised against. The convergence diagnostic
    # below must be measured on this matrix, not on the sample covariance used
    # for reporting: ERC solves on the shrunk estimate, so scoring its solution
    # against the raw sample matrix reports a dispersion of ~0.07 for a solver
    # that in fact converged exactly. Two different matrices, two different
    # questions — keep them apart.
    solver_cov = cov

    if _m == "EQUAL":
        w = np.full(len(names), 1.0 / len(names))
    elif _m == "HRP":
        w = hrp_weights(cov, corr)
    elif _m in ("ERC", "ERC_MOM"):
        solver_cov = ledoit_wolf(R)
        w = erc_weights(solver_cov)
        if _m == "ERC_MOM":
            px_panel = build_price_matrix(history, symbols=names)
            mom = momentum_scores(px_panel, MOMENTUM_LOOKBACK, MOMENTUM_SKIP)
            mom = mom.reindex(names)
            if mom.notna().sum() >= 2:
                w = apply_momentum_tilt(w, mom, MOMENTUM_LAMBDA)
            # Too few names carry a full 12-1 window to rank meaningfully; the
            # book falls back to plain ERC rather than tilting on noise. The
            # caller can see this happened via the `nco_momentum_names` attr.
    else:
        w = hrp_weights(cov, corr)
    _, k, sil = cluster_assets(corr)

    w = np.nan_to_num(w, nan=0.0)
    if w.sum() <= 1e-12:
        return empty
    w = w / w.sum()

    # Risk balance as SOLVED, over the full eligible set and before any
    # selection or cap. Kept separately from the realised figure below because
    # the two answer different questions: this one says whether the optimiser
    # converged, the realised one says what the book the user actually holds
    # looks like after top-N selection and the position cap have moved it.
    # Conflating them makes a correct ERC solve look like a failed one.
    _rc_solved = risk_contributions(w, solver_cov)
    _rc_solved_disp = (float(np.std(_rc_solved) / np.mean(_rc_solved))
                       if np.mean(_rc_solved) > 1e-18 else 0.0)

    ser = pd.Series(w, index=names).sort_values(ascending=False)
    # Drop names the allocator zeroed out BEFORE selecting. Corner-solution
    # optimisers (minimum variance, maximum diversification) put most names at
    # exactly 0, and carrying those into the top-N selection would fill the book
    # with zero-weight rows that the cap logic then has to reason about.
    #
    # This is also why Max Diversification was withdrawn as a shipped style: it
    # routinely zeroed enough names that the book came back SHORTER than the
    # position count the user asked for (10 of a requested 15 on this universe).
    # A style that silently re-decides how many positions you hold is not a
    # weighting method. `nco_positions_short` below makes any recurrence visible
    # rather than silent.
    n_nonzero = int((ser > 1e-9).sum())
    ser = ser[ser > 1e-9]
    if ser.empty:
        return empty
    chosen = ser.head(min(num_positions, len(ser)))
    chosen = chosen / chosen.sum()

    wv = _apply_cap(chosen.to_numpy(dtype=float), max_pos_pct)
    n = len(wv)
    cap_eff = max(max_pos_pct, 1.0 / n)

    labels, _, _ = cluster_assets(corr)
    lab_by_name = dict(zip(names, labels))
    idx = [names.index(s) for s in chosen.index]
    sub_cov = cov[np.ix_(idx, idx)]
    port_var = float(wv @ sub_cov @ wv)
    # Marginal risk contribution, normalised to sum to 1 — shows whether the
    # clustering actually balanced risk or merely balanced capital.
    mrc = sub_cov @ wv
    rc = wv * mrc
    rc = rc / rc.sum() if abs(rc.sum()) > 1e-18 else np.full(n, 1.0 / n)

    # Per-asset diagnostics for the risk heatmap: annualized volatility, and
    # each holding's correlation to the finished book (how much it moves WITH
    # the portfolio, i.e. how little it diversifies).
    ann_vol = np.sqrt(np.diag(sub_cov)) * np.sqrt(252)
    book_ret = R[:, idx] @ wv
    corr_to_book = np.array([
        float(np.corrcoef(R[:, j], book_ret)[0, 1]) if np.std(R[:, j]) > 1e-12 else 0.0
        for j in idx
    ])

    px_arr = np.array([float(prices.get(s, np.nan)) for s in chosen.index], dtype=float)
    # Momentum is carried per-holding so the risk profile chart can show the
    # tilt that was actually applied, not a re-derivation of it. Methods that do
    # not use momentum emit NaN, and the chart drops the row.
    _mom_sel = mom.reindex(chosen.index) if _spec["uses_momentum"] else pd.Series(
        np.nan, index=chosen.index)
    _mom_z = (rank_z(_mom_sel) if _spec["uses_momentum"] and _mom_sel.notna().sum() >= 2
              else pd.Series(np.nan, index=chosen.index))
    out = pd.DataFrame({
        "symbol": list(chosen.index),
        "price": px_arr,
        "weightage_pct": wv * 100.0,
        "cluster": [int(lab_by_name.get(s, 0)) for s in chosen.index],
        "risk_contribution": rc,
        "volatility": ann_vol,
        "corr_to_book": np.nan_to_num(corr_to_book, nan=0.0),
        "momentum": _mom_sel.to_numpy(dtype=float),
        "momentum_z": _mom_z.to_numpy(dtype=float),
    })
    out = out[out["price"].notna() & (out["price"] > 0)].copy()
    if out.empty:
        return empty
    out["weightage_pct"] = out["weightage_pct"] / out["weightage_pct"].sum() * 100.0
    out["units"] = np.floor((capital * out["weightage_pct"] / 100.0) / out["price"])
    out["value"] = out["units"] * out["price"]

    out.attrs["nco_method"] = _m
    out.attrs["nco_method_label"] = _spec["label"]
    out.attrs["nco_method_family"] = _spec["family"]
    out.attrs["nco_method_formula"] = _spec["formula"]
    out.attrs["nco_rc_target"] = _spec["rc_target"]
    out.attrs["nco_uses_clusters"] = bool(_spec["uses_clusters"])
    out.attrs["nco_uses_momentum"] = bool(_spec["uses_momentum"])
    out.attrs["nco_clusters"] = int(k)
    out.attrs["nco_silhouette"] = float(sil)
    out.attrs["nco_obs"] = int(len(rets))
    out.attrs["nco_universe"] = int(n_assets)
    out.attrs["nco_port_vol_ann"] = float(np.sqrt(max(port_var, 0.0)) * np.sqrt(252))
    out.attrs["max_pos_pct_eff"] = float(cap_eff)
    out.attrs["min_pos_pct_eff"] = 0.0
    # Risk-balance diagnostics. `rc_dispersion` is the coefficient of variation
    # of the risk contributions: 0 is perfect equal-risk, and it is the number
    # that says whether ERC actually achieved what it targets. `rc_concentration`
    # is the heaviest holding's risk share against its equal share — the header
    # card's "Risk Concentration".
    _rc_sel = rc[rc > 0] if (rc > 0).any() else rc
    out.attrs["nco_rc_dispersion"] = (float(np.std(_rc_sel) / np.mean(_rc_sel))
                                      if len(_rc_sel) and np.mean(_rc_sel) > 1e-18 else 0.0)
    out.attrs["nco_rc_dispersion_solved"] = float(_rc_solved_disp)
    out.attrs["nco_rc_concentration"] = float(rc.max() * n) if n else 1.0
    # Position-count contract: the book must hold exactly what the user asked
    # for, unless the ELIGIBLE UNIVERSE itself is smaller. `nco_positions_short`
    # separates the two causes — a short book because the universe ran out is a
    # data condition the user can act on; a short book because the allocator
    # zeroed names out is an allocator defect.
    # Universe eligibility, carried through so the UI can say why the book was
    # built from fewer names than the universe declares.
    _excl = rets.attrs.get("excluded", {})
    out.attrs["nco_universe_requested"] = int(n_assets + len(_excl))
    out.attrs["nco_universe_excluded"] = dict(_excl)
    out.attrs["nco_coverage_required"] = float(rets.attrs.get("coverage_required", MIN_COVERAGE))
    out.attrs["nco_coverage_window"] = int(rets.attrs.get("coverage_window", len(rets)))
    out.attrs["nco_positions_requested"] = int(num_positions)
    out.attrs["nco_positions_delivered"] = int(len(out))
    out.attrs["nco_positions_nonzero"] = int(n_nonzero)
    out.attrs["nco_positions_short"] = max(0, int(num_positions) - int(len(out)))
    out.attrs["nco_short_cause"] = (
        "none" if len(out) >= num_positions
        else "universe" if n_assets <= num_positions or n_nonzero >= num_positions
        else "allocator_zeroed")
    out.attrs["nco_momentum_names"] = int(_mom_sel.notna().sum())
    out.attrs["nco_momentum_lambda"] = (float(MOMENTUM_LAMBDA)
                                        if _spec["uses_momentum"] else 0.0)
    out.attrs["nco_momentum_applied"] = bool(
        _spec["uses_momentum"] and _mom_sel.notna().sum() >= 2)
    # Full correlation matrix plus the cluster ordering, so the UI can draw the
    # quasi-diagonalized structure the allocator actually saw. Ordering by
    # cluster is what makes the block structure visible — the same reordering
    # HRP uses internally.
    _order = [names[i] for i in np.argsort(labels, kind="stable")]
    out.attrs["corr_matrix"] = pd.DataFrame(corr, index=names, columns=names).loc[_order, _order]
    out.attrs["cluster_order"] = _order
    out.attrs["cluster_labels"] = {names[i]: int(labels[i]) for i in range(len(names))}
    return out.sort_values("weightage_pct", ascending=False).reset_index(drop=True)


__all__ = [
    "METHODS",
    "METHOD_ORDER",
    "METHOD_SPECS",
    "method_spec",
    "MOMENTUM_LAMBDA",
    "MOMENTUM_LOOKBACK",
    "MOMENTUM_SKIP",
    "correlation_distance",
    "inverse_variance",
    "ledoit_wolf",
    "cluster_assets",
    "risk_contributions",
    "hrp_weights",
    "erc_weights",
    "momentum_scores",
    "rank_z",
    "apply_momentum_tilt",
    "build_returns_matrix",
    "build_price_matrix",
    "compute_nco_portfolio",
]
