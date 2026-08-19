"""
PRAGYAM — The curated book, read through its risk structure.

Holdings first, then the structure that produced them: what each name is,
what share of capital and of variance it carries, and where the two disagree.

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
    render_note,
    render_section_header,
    render_table_panel,
)
from ui.shared import NCO_STYLES, REGIME_FACTOR_ORDER, STYLE_LABELS, num, style_spec
import html as html_module

import streamlit.components.v1 as components

# Charts are optional: a missing plotly must degrade this tab to its tables
# and readouts rather than take the whole app down on import.
try:
    from charts import (
        create_cluster_correlation_heatmap,
        create_risk_allocation_heatmap,
        create_risk_contribution_chart,
    )
    CHARTS_AVAILABLE = True
except ImportError:                                     # pragma: no cover
    CHARTS_AVAILABLE = False


def _render_portfolio_tab(portfolio: pd.DataFrame, current_df: pd.DataFrame, capital: float):
    """Tab 1 — the curated book, read through its risk structure.

    This replaces the old conviction-signal overlay. That overlay described a
    score which no longer exists, and which — while it did — had no measurable
    cross-sectional predictive power on this universe (IC ~0.00-0.04, sign
    unstable across horizons). What drives the book now is the covariance
    structure, so that is what the table and heatmaps show.
    """
    _rc = st.session_state.get("run_context") or {}
    _label = style_spec(_rc)["label"]
    render_section_header(
        "Curated Portfolio Holdings",
        f"{len(portfolio)} positions · {_label}",
        icon="briefcase", accent="accent",
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

    # One table primitive for the whole app. This block used to hand-build a
    # <table> with its own <style> inside a components.html iframe — 110 lines
    # of markup that could not inherit a single token from the stylesheet,
    # which is exactly why the theme switch could never reach it.
    view = pd.DataFrame({
        "Symbol": df["symbol"].astype(str),
        "Units": pd.to_numeric(df["units"], errors="coerce"),
        "Price": pd.to_numeric(df["price"], errors="coerce"),
        "Weight %": pd.to_numeric(df["weightage_pct"], errors="coerce"),
        "Value": pd.to_numeric(df["value"], errors="coerce"),
        # Cluster is a LABEL, not a quantity: "C3" is not three of anything, and
        # right-aligning it as a number would invite exactly that reading. An
        # unestimated holding has no cluster at all.
        "Cluster": ["—" if pd.isna(c) else f"C{int(c)}" for c in df["cluster"]],
        "Risk Share %": pd.to_numeric(df["risk_contribution"], errors="coerce") * 100,
        "Risk − Wt": (pd.to_numeric(df["risk_contribution"], errors="coerce") * 100
                      - pd.to_numeric(df["weightage_pct"], errors="coerce")),
        "Vol %": pd.to_numeric(df["volatility"], errors="coerce") * 100,
        "Indep": 1.0 - pd.to_numeric(df["corr_to_book"], errors="coerce").abs(),
    })
    render_table_panel(
        view, "holdings", context=f"{n} holdings · sorted by weight",
        show_index=False,
        label_col="Symbol",
        col_precision={"Units": 0, "Price": 2, "Weight %": 2, "Value": 0,
                       "Risk Share %": 2, "Risk − Wt": 2, "Vol %": 1, "Indep": 2},
        lower_is_better_cols={"Risk − Wt"},
        max_height=520,
    )

    render_note(
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
    _mspec = style_spec(st.session_state.get("run_context") or {})
    render_section_header(
        "Risk Profile",
        f"Per-holding, row-relative · scored against {_mspec['short']}'s own objective",
        icon="activity", accent="emerald")
    render_chart_panel(create_risk_allocation_heatmap(df), "risk-alloc",
                       context=f"{len(df)} holdings · row-relative percentile")
    # What "green" means is method-dependent, so the caption must be too. Telling
    # an HRP user that green means "risk share near 1/N" would be wrong: HRP
    # balances across clusters, not holdings.
    render_note(
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
    render_section_header(
        "Risk Contribution", "Capital share vs variance share, on one scale",
        icon="bar-chart-2", accent="accent")
    render_chart_panel(create_risk_contribution_chart(df), "risk-contrib",
                       context=f"capital vs variance · equal share {eq_share:.2f}%")
    render_note(
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
        k = portfolio.attrs.get("nco_clusters", 0)
        sil = portfolio.attrs.get("nco_silhouette", 0.0)
        _clusters_drive = bool(portfolio.attrs.get("nco_uses_clusters", False))
        render_section_header(
            "Risk Structure",
            f"Correlation matrix ordered by cluster · {k} clusters · silhouette {sil:.2f}"
            + ("" if _clusters_drive else " · diagnostic only"),
            icon="layers", accent="violet")
        render_chart_panel(create_cluster_correlation_heatmap(corr, labels),
                           "cluster-corr",
                           context=f"{k} clusters · silhouette {sil:.2f}")
        render_note(
            "Blocks along the diagonal are groups that move together — one bet wearing several "
            "tickers. The gaps cut through the field mark the cluster boundaries. Crisp blocks "
            "mean the clustering "
            "found real structure; a uniformly warm matrix means the universe is effectively a "
            "single bet, which no allocator can fix. "
            + ("These are the boundaries the allocator actually **used** to split capital."
               if _clusters_drive else
               "This style does **not** allocate from the cluster tree — the matrix is shown so "
               "you can see the structure the weights were computed against.")
        )
