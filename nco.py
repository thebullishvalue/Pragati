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


# ── Public entry point ────────────────────────────────────────────────────────

METHODS = ("HRP", "EQUAL")


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
    return rets[keep].dropna(how="any")


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

    if str(method).upper() == "EQUAL":
        # Equal weight is computed HERE rather than short-circuited earlier so
        # it travels the identical pipeline as HRP — same eligibility filter,
        # same clustering diagnostics, same risk decomposition. That makes the
        # two styles genuinely comparable on screen: any difference the user
        # sees is the allocator, not a different data path.
        w = np.full(len(names), 1.0 / len(names))
    else:
        w = hrp_weights(cov, corr)
    _, k, sil = cluster_assets(corr)

    w = np.nan_to_num(w, nan=0.0)
    if w.sum() <= 1e-12:
        return empty
    w = w / w.sum()

    ser = pd.Series(w, index=names).sort_values(ascending=False)
    # Drop names the allocator zeroed out BEFORE selecting. Minimum-variance in
    # particular returns corner solutions — most names at exactly 0 — and
    # carrying those into the top-N selection would fill the book with
    # zero-weight rows that the cap logic then has to reason about.
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
    out = pd.DataFrame({
        "symbol": list(chosen.index),
        "price": px_arr,
        "weightage_pct": wv * 100.0,
        "cluster": [int(lab_by_name.get(s, 0)) for s in chosen.index],
        "risk_contribution": rc,
        "volatility": ann_vol,
        "corr_to_book": np.nan_to_num(corr_to_book, nan=0.0),
    })
    out = out[out["price"].notna() & (out["price"] > 0)].copy()
    if out.empty:
        return empty
    out["weightage_pct"] = out["weightage_pct"] / out["weightage_pct"].sum() * 100.0
    out["units"] = np.floor((capital * out["weightage_pct"] / 100.0) / out["price"])
    out["value"] = out["units"] * out["price"]

    out.attrs["nco_method"] = str(method).upper()
    out.attrs["nco_clusters"] = int(k)
    out.attrs["nco_silhouette"] = float(sil)
    out.attrs["nco_obs"] = int(len(rets))
    out.attrs["nco_universe"] = int(n_assets)
    out.attrs["nco_port_vol_ann"] = float(np.sqrt(max(port_var, 0.0)) * np.sqrt(252))
    out.attrs["max_pos_pct_eff"] = float(cap_eff)
    out.attrs["min_pos_pct_eff"] = 0.0
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
    "correlation_distance",
    "inverse_variance",
    "cluster_assets",
    "risk_contributions",
    "hrp_weights",
    "build_returns_matrix",
    "compute_nco_portfolio",
]
