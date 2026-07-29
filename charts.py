"""
PRAGYAM — Chart Components
══════════════════════════════════════════════════════════════════════════════

Obsidian Quant Terminal Design System — Institutional-grade financial visualization.

All charts use chart_layout() and style_axes() from ui/theme.py for consistent theming.
Aesthetics match Nishkarsh v1.2.0 chart patterns (line widths, fills, markers, trace colors).

Author: @thebullishvalue
"""

import plotly.graph_objects as go
import pandas as pd
import numpy as np

from ui.theme import chart_layout, style_axes


# ══════════════════════════════════════════════════════════════════════════════
# COLOR PALETTE — Terminal Glass
# ══════════════════════════════════════════════════════════════════════════════

COLORS = {
    # Primary: Amber Gold (system anchor)
    "amber": "#D4A853",
    "amber_dim": "rgba(212, 168, 83, 0.6)",
    "amber_glow": "rgba(212, 168, 83, 0.25)",

    # Heatmap / Signal: Diverging scale (Rose → Slate → Emerald)
    # Bearish: Rose (sharp, warning)
    "rose": "#E8555A",
    "rose_dim": "rgba(232, 85, 90, 0.5)",
    "rose_glow": "rgba(232, 85, 90, 0.2)",
    # Neutral: Warm slate (not cold gray — maintains warmth)
    "slate": "#8B7E6A",
    "slate_dim": "rgba(139, 126, 106, 0.4)",
    # Bullish: Emerald (rich, deep)
    "emerald": "#2DD4A8",
    "emerald_dim": "rgba(45, 212, 168, 0.5)",
    "emerald_glow": "rgba(45, 212, 168, 0.2)",

    # Accent palette (used sparingly for UI elements)
    "cyan": "#06B6D4",
    "cyan_glow": "rgba(6, 182, 212, 0.2)",
    "violet": "#8B5CF6",
    "violet_glow": "rgba(139, 92, 246, 0.2)",
    "orange": "#F59E0B",
    "orange_glow": "rgba(245, 158, 11, 0.2)",
}


# ══════════════════════════════════════════════════════════════════════════════
# REGIME INTELLIGENCE CHARTS
# ══════════════════════════════════════════════════════════════════════════════


def create_regime_history_chart(regime_series: list) -> go.Figure:
    """Timeline chart of market regime transitions over a rolling window.

    Matches Nishkarsh aesthetic: subtle reference lines, dual-fill pattern,
    dynamic marker sizing, no marker borders, 1.5px line width.

    Trace colors match Nishkarsh exactly:
    - Main line: amber (#D4A853) at 1.5px
    - Positive fills: emerald rgba(52,211,153,0.06/0.08)
    - Negative fills: rose rgba(251,113,133,0.06/0.08)
    - Reference lines: 0.5px at 15% opacity

    Args:
        regime_series: List of RegimeResult objects from get_regime_history_series().

    Returns:
        Plotly Figure with dual-layer regime timeline.
    """
    if not regime_series:
        fig = go.Figure()
        fig.update_layout(**chart_layout(height=300))
        return fig

    dates = [r.date for r in regime_series]
    scores = [r.composite_score for r in regime_series]
    colors = [r.color for r in regime_series]
    regimes = [r.regime.replace("_", " ") for r in regime_series]
    confs = [r.confidence for r in regime_series]

    # Dynamic marker sizing based on confidence (matches Nishkarsh pattern)
    marker_sizes = [7 if c >= 0.7 else 5 if c >= 0.5 else 4 for c in confs]

    fig = go.Figure()

    # Upper band (invisible line for fill pattern - Nishkarsh style)
    upper = [s + c * 0.4 for s, c in zip(scores, confs)]
    lower = [s - c * 0.4 for s, c in zip(scores, confs)]

    # Positive confidence fill (above zero)
    upper_positive = [max(0, u) for u in upper]
    lower_positive = [max(0, l) for l in lower]
    fig.add_trace(
        go.Scatter(
            x=dates + dates[::-1],
            y=upper_positive + lower_positive[::-1],
            fill="toself",
            fillcolor="rgba(45, 212, 168, 0.07)",
            line=dict(color="rgba(0,0,0,0)", width=0),
            hoverinfo="skip",
            showlegend=False,
            name="",
        )
    )

    # Negative confidence fill (below zero)
    upper_negative = [min(0, u) for u in upper]
    lower_negative = [min(0, l) for l in lower]
    fig.add_trace(
        go.Scatter(
            x=dates + dates[::-1],
            y=upper_negative + lower_negative[::-1],
            fill="toself",
            fillcolor="rgba(232, 85, 90, 0.07)",
            line=dict(color="rgba(0,0,0,0)", width=0),
            hoverinfo="skip",
            showlegend=False,
            name="",
        )
    )

    # Composite score line — warm slate
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=scores,
            mode="lines+markers",
            name="Composite Score",
            line=dict(color=COLORS["slate"], width=2.5, shape='spline'),
            marker=dict(
                size=marker_sizes,
                color=colors,
                symbol='circle',
                line=dict(width=1, color='rgba(255,255,255,0.15)'),
            ),
            customdata=list(zip(regimes, [f"{c:.0%}" for c in confs])),
            hovertemplate="<b>%{customdata[0]}</b><br>Score: %{y:+.2f}<br>Confidence: %{customdata[1]}<br><span style='opacity:0.7;'>%{x|%Y-%m-%d}</span><extra></extra>",
            fill='tozeroy',
            fillcolor='rgba(139, 126, 106, 0.06)',
        )
    )

    # Reference lines — Terminal Glass aesthetic
    for y_val, color, label in [
        (1.0, "rgba(45, 212, 168, 0.25)", "Bull"),
        (0.1, "rgba(212, 168, 83, 0.25)", "Chop"),
        (-0.5, "rgba(232, 85, 90, 0.25)", "Bear"),
    ]:
        fig.add_hline(
            y=y_val,
            line_dash="dot",
            line_color=color,
            line_width=0.8,
            annotation_text=label,
            annotation_position="right",
            annotation_font=dict(color=color, size=10, family="IBM Plex Mono, monospace"),
            annotation_font_size=9,
            opacity=0.9,
        )

    # Apply Obsidian Quant theme
    fig.update_layout(**chart_layout(height=320, show_legend=False))
    style_axes(fig, y_title="Composite Score", y_range=[-2.5, 2.5])
    
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# CONVICTION HEATMAP
# ══════════════════════════════════════════════════════════════════════════════


def create_risk_allocation_heatmap(portfolio: pd.DataFrame) -> go.Figure:
    """Per-holding risk profile — the successor to the conviction heatmap.

    Same idea as the signal heatmap it replaces (one row per position, one
    column per dimension, diverging colour), but the dimensions are the ones
    that actually drive a covariance-curated book:

      Weight        share of capital
      Risk Share    share of PORTFOLIO VARIANCE this holding contributes
      Volatility    its own annualized volatility
      Independence  1 - |correlation to the finished book|

    Colour is a within-column percentile, so each column is read against its own
    peers rather than on incompatible absolute scales. Every column is oriented
    so GREEN is the calm, diversifying end: low volatility, high independence,
    and — for Weight and Risk Share — a contribution close to its equal share
    rather than a concentration. That makes a well-balanced book read as an
    even green field, and any red row is a position carrying more risk than its
    capital suggests.

    The gap between the Weight and Risk Share columns is the whole point of the
    method: equal capital does NOT mean equal risk, and this is where you see it.
    """
    need = ["symbol", "weightage_pct"]
    if portfolio is None or portfolio.empty or not all(c in portfolio.columns for c in need):
        fig = go.Figure()
        fig.update_layout(**chart_layout(height=220))
        return fig

    df = portfolio.copy()
    for c, default in (("risk_contribution", np.nan), ("volatility", np.nan),
                       ("corr_to_book", np.nan), ("cluster", 0)):
        if c not in df.columns:
            df[c] = default
    # Cluster first, then weight — so structurally similar holdings sit together
    # and the block pattern is legible.
    df = df.sort_values(["cluster", "weightage_pct"], ascending=[True, False]).head(40)

    n = len(df)
    eq_share = 1.0 / n if n else 0.0
    w = pd.to_numeric(df["weightage_pct"], errors="coerce").fillna(0.0) / 100.0
    rc = pd.to_numeric(df["risk_contribution"], errors="coerce").fillna(eq_share)
    vol = pd.to_numeric(df["volatility"], errors="coerce")
    indep = 1.0 - pd.to_numeric(df["corr_to_book"], errors="coerce").abs()

    # Raw display values, and the "greener is better" ordering key per column.
    cols = [
        ("Weight",       w * 100.0,   -(w - eq_share).abs(), "{:.2f}%"),
        ("Risk Share",   rc * 100.0,  -(rc - eq_share).abs(), "{:.2f}%"),
        ("Volatility",   vol * 100.0, -vol,                   "{:.1f}%"),
        ("Independence", indep,        indep,                 "{:.2f}"),
    ]

    z, text = [], []
    for _, raw, key, fmt in cols:
        k = pd.to_numeric(key, errors="coerce")
        pct = k.rank(pct=True) if k.notna().sum() > 1 else pd.Series(0.5, index=k.index)
        z.append((pct.fillna(0.5) * 2.0 - 1.0).tolist())
        text.append([fmt.format(v) if pd.notna(v) else "—" for v in raw])

    labels = [c[0] for c in cols]
    fig = go.Figure(go.Heatmap(
        z=z, x=df["symbol"].tolist(), y=labels,
        text=text, texttemplate="%{text}",
        textfont=dict(size=9, family="IBM Plex Mono, monospace"),
        colorscale=[[0.0, COLORS["rose"]], [0.5, COLORS["slate_dim"]], [1.0, COLORS["emerald"]]],
        zmid=0.0, zmin=-1.0, zmax=1.0, showscale=False, xgap=2, ygap=3,
        hovertemplate="<b>%{x}</b><br>%{y}: %{text}<extra></extra>",
    ))
    fig.update_layout(**chart_layout(height=max(200, 46 * len(labels) + 90), show_legend=False))
    style_axes(fig)
    fig.update_xaxes(tickangle=-60, tickfont=dict(size=9))
    fig.update_yaxes(autorange="reversed")
    return fig


def create_cluster_correlation_heatmap(corr: "pd.DataFrame | None",
                                       cluster_labels: "dict | None" = None) -> go.Figure:
    """Holdings correlation matrix, reordered so cluster blocks are visible.

    This is the quasi-diagonalization at the heart of hierarchical allocation:
    reorder the correlation matrix by the clustering and the structure stops
    being a wall of numbers and becomes visible blocks along the diagonal. Each
    block is a group of holdings that move together — a single bet wearing
    several tickers.

    It is the diagnostic for the whole method. If the blocks are crisp, the
    clustering found something real and the allocator is spreading capital
    across genuinely distinct risks. If the matrix is uniformly warm with no
    block structure, the universe is one bet and no allocator can fix that.
    """
    if corr is None or not isinstance(corr, pd.DataFrame) or corr.empty:
        fig = go.Figure()
        fig.update_layout(**chart_layout(height=260))
        return fig

    syms = list(corr.columns)
    fig = go.Figure(go.Heatmap(
        z=corr.to_numpy(), x=syms, y=syms,
        colorscale=[[0.0, COLORS["emerald"]], [0.5, "rgba(20,20,24,0.85)"], [1.0, COLORS["rose"]]],
        zmid=0.0, zmin=-1.0, zmax=1.0, showscale=True,
        colorbar=dict(title=dict(text="ρ", font=dict(size=10)), thickness=10, len=0.7,
                      tickfont=dict(size=9)),
        hovertemplate="<b>%{x}</b> vs <b>%{y}</b><br>ρ = %{z:.2f}<extra></extra>",
    ))

    # Rule off the cluster boundaries so the blocks are unambiguous.
    if cluster_labels:
        seq = [cluster_labels.get(sm) for sm in syms]
        for i in range(1, len(seq)):
            if seq[i] != seq[i - 1]:
                fig.add_shape(type="line", x0=i - 0.5, x1=i - 0.5, y0=-0.5, y1=len(syms) - 0.5,
                              line=dict(color=COLORS["amber"], width=1.2))
                fig.add_shape(type="line", y0=i - 0.5, y1=i - 0.5, x0=-0.5, x1=len(syms) - 0.5,
                              line=dict(color=COLORS["amber"], width=1.2))

    size = max(320, min(620, 20 * len(syms) + 120))
    fig.update_layout(**chart_layout(height=size, show_legend=False))
    style_axes(fig)
    fig.update_xaxes(tickangle=-60, tickfont=dict(size=8))
    fig.update_yaxes(tickfont=dict(size=8), autorange="reversed")
    return fig


def create_benchmark_comparison_chart(
    port_value: pd.Series,
    bench_series: "pd.Series | None",
    benchmark_name: str = "Benchmark",
    port_return: float = 0.0,
    alt_series: "pd.Series | None" = None,
    alt_label: str = "Equal Weight",
) -> go.Figure:
    """Normalized portfolio-vs-benchmark line chart (all series pegged to 100).

    Args:
        port_value: Portfolio value time series (any base; normalized to 100).
        bench_series: Benchmark price series (or None to plot portfolio only).
        benchmark_name: Legend label for the benchmark.
        port_return: Portfolio period return (%) for the legend label.
        alt_series: Optional third value series — the same book weighted a
            different way (the equal-weight shadow book). None omits the trace.
        alt_label: Legend label for ``alt_series``.

    Returns:
        Plotly Figure in the Obsidian Quant theme — amber portfolio line,
        dotted cyan benchmark line, dashed violet alternate-weighting line,
        value axis on the right.
    """
    fig = go.Figure()
    if port_value is None or len(port_value) == 0:
        fig.update_layout(**chart_layout(height=380))
        return fig

    port_norm = (port_value / port_value.iloc[0]) * 100.0
    fig.add_trace(go.Scatter(
        x=port_norm.index, y=port_norm.values, mode="lines",
        name=f"Portfolio ({port_return:+.2f}%)",
        line=dict(color=COLORS["amber"], width=2.5),
        hovertemplate="%{x|%b %d, %Y}<br>Portfolio: %{y:.2f}<extra></extra>",
    ))

    # Equal-weight shadow of the SAME names, plotted between the book and the
    # benchmark in visual weight: it is the closer, more diagnostic comparison
    # (it isolates the weighting decision, holding selection constant), so it
    # gets its own hue rather than reusing the benchmark's.
    if alt_series is not None and len(alt_series) > 0:
        alt = alt_series.dropna()
        if len(alt) > 0 and float(alt.iloc[0]) != 0:
            alt_norm = (alt / alt.iloc[0]) * 100.0
            alt_ret = ((alt.iloc[-1] / alt.iloc[0]) - 1) * 100.0
            fig.add_trace(go.Scatter(
                x=alt_norm.index, y=alt_norm.values, mode="lines",
                name=f"{alt_label} ({alt_ret:+.2f}%)",
                line=dict(color=COLORS["violet"], width=2, dash="dash"),
                hovertemplate=f"%{{x|%b %d, %Y}}<br>{alt_label}: %{{y:.2f}}<extra></extra>",
            ))

    if bench_series is not None and len(bench_series) > 0:
        bench = bench_series.dropna()
        if len(bench) > 0:
            bench_norm = (bench / bench.iloc[0]) * 100.0
            bench_ret = ((bench.iloc[-1] / bench.iloc[0]) - 1) * 100.0
            fig.add_trace(go.Scatter(
                x=bench_norm.index, y=bench_norm.values, mode="lines",
                name=f"{benchmark_name} ({bench_ret:+.2f}%)",
                line=dict(color=COLORS["cyan"], width=2, dash="dot"),
                hovertemplate=f"%{{x|%b %d, %Y}}<br>{benchmark_name}: %{{y:.2f}}<extra></extra>",
            ))

    fig.update_layout(**chart_layout(height=380, show_legend=True))
    style_axes(fig, y_title="Indexed to 100")
    fig.update_yaxes(side="right")
    fig.update_xaxes(rangeslider=dict(visible=False), rangeselector=dict(visible=False))
    return fig


__all__ = [
    "COLORS",
    "create_regime_history_chart",
    "create_risk_allocation_heatmap",
    "create_cluster_correlation_heatmap",
    "create_benchmark_comparison_chart",
]
