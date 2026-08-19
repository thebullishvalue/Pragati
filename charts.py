"""
PRAGYAM — Chart Components
══════════════════════════════════════════════════════════════════════════════

"Graphite" institutional design system — see ui/theme.py.

All charts use chart_layout() and style_axes() from ui/theme.py for consistent
theming, and every colour comes from COLORS below, which resolves against the
ACTIVE theme on each lookup.

Author: @thebullishvalue
"""

import plotly.graph_objects as go
import pandas as pd
import numpy as np

from ui.theme import (chart_color, chart_layout, chart_rgba, diverging_scale,
                      panel_bg, style_axes)


# ══════════════════════════════════════════════════════════════════════════════
# COLOR PALETTE — resolved live, never bound at import
# ══════════════════════════════════════════════════════════════════════════════


class _LivePalette:
    """Semantic chart colours for the ACTIVE theme.

    A plain dict cannot work here. Its values would be bound the first time
    this module is imported, and the theme can change AFTER that — so on Paper
    every line, marker and fill would keep the hex it was given for graphite
    while the axes and grid (which do read the theme) went dark. Half a chart
    themed is worse than none of it: it reads as a rendering bug rather than a
    palette.

    Resolving on ``__getitem__`` keeps all ~20 call sites unchanged while making
    each of them theme-aware. Keys are semantic — ``accent`` is the system's own
    voice (the book, its targets, its cluster boundaries), ``emerald``/``rose``
    are the risk-versus-capital claim, ``violet`` is the shadow book, ``cyan``
    is the benchmark, ``slate`` is anything unclaimed. A ``_dim``/``_glow``
    suffix returns the same hue at a fill's opacity.
    """

    _ALPHA = {"_dim": 0.45, "_glow": 0.18}

    def __getitem__(self, key: str) -> str:
        for suffix, alpha in self._ALPHA.items():
            if key.endswith(suffix):
                return chart_rgba(key[: -len(suffix)], alpha)
        return chart_color(key)

    def get(self, key: str, default=None):
        try:
            return self[key]
        except KeyError:
            return default


COLORS = _LivePalette()


# ══════════════════════════════════════════════════════════════════════════════
# REGIME INTELLIGENCE CHARTS
# ══════════════════════════════════════════════════════════════════════════════


def create_regime_history_chart(regime_series: list) -> go.Figure:
    """Timeline of the composite regime score over a rolling window.

    ONE LINE, ONE COLOUR. The score is the system's own reading, so it is drawn
    in the accent — the system's voice — and nothing else on the plot competes
    with it. Each point used to be coloured by its own regime, which put seven
    hues on one series: a rainbow, in a design system whose rule is that a
    colour carries a claim. The regime is already stated by WHERE the line sits
    against the labelled bands behind it; colouring the point as well says it
    twice and reserves no hue for anything that needs one.

    The confidence band is the one place a tint earns its keep: it widens where
    the eight factors agree and narrows where they do not, so the reader can
    see how much to trust the line's position without a second chart. It takes
    the accent at fill strength rather than green/red, because a wide band is
    not bullish — it is confident.

    Straight segments, not splines. A spline draws values between readings that
    were never computed; on a series whose whole claim is "this is what the
    composite measured on these dates", the curve is a fiction.

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
    regimes = [r.regime.replace("_", " ") for r in regime_series]
    confs = [r.confidence for r in regime_series]

    # Marker size carries confidence: a firmer reading is a bigger dot.
    marker_sizes = [7 if c >= 0.7 else 5 if c >= 0.5 else 4 for c in confs]

    fig = go.Figure()

    # ── Confidence band ───────────────────────────────────────────────────
    # One band, drawn as a single closed polygon around the line. It was two
    # polygons — the part above zero tinted green and the part below tinted
    # red — which made the WIDTH of the band, its only meaning, read as a
    # direction instead. Width is agreement; the line's position is direction.
    upper = [s_ + c * 0.4 for s_, c in zip(scores, confs)]
    lower = [s_ - c * 0.4 for s_, c in zip(scores, confs)]
    fig.add_trace(go.Scatter(
        x=dates + dates[::-1], y=upper + lower[::-1],
        fill="toself", fillcolor=chart_rgba("accent", 0.08),
        line=dict(color="rgba(0,0,0,0)", width=0),
        hoverinfo="skip", showlegend=False, name="",
    ))

    # ── The composite ─────────────────────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=dates, y=scores, mode="lines+markers", name="Composite score",
        line=dict(color=COLORS["accent"], width=2),
        # Size still carries confidence — a bigger dot is a firmer reading —
        # but every dot is the same colour as its line. Seven regime hues on
        # one series was the only rainbow left in the app.
        marker=dict(size=marker_sizes, color=COLORS["accent"], symbol="circle",
                    line=dict(width=1, color=panel_bg())),
        customdata=list(zip(regimes, [f"{c:.0%}" for c in confs])),
        hovertemplate="<b>%{customdata[0]}</b><br>Score: %{y:+.2f}"
                      "<br>Confidence: %{customdata[1]}"
                      "<br><span style='opacity:0.7;'>%{x|%Y-%m-%d}</span><extra></extra>",
    ))

    # ── Regime thresholds ────────────────────────────────────────────────
    # Thresholds, not data: a quarter-strength semantic tint each, resolved for
    # the active theme. These were literal rgba() triples from the retired
    # Obsidian palette — the amber one in particular is now the app's caution
    # colour, so a routine "Chop" gridline was drawn in the one hue reserved
    # for a warning.
    for y_val, color, label in [
        (1.0, chart_rgba("emerald", 0.25), "Bull"),
        (0.1, chart_rgba("slate", 0.3), "Chop"),
        (-0.5, chart_rgba("rose", 0.25), "Bear"),
    ]:
        fig.add_hline(
            y=y_val,
            line_dash="dot",
            line_color=color,
            line_width=0.8,
            annotation_text=label,
            annotation_position="right",
            annotation_font=dict(color=color, size=10, family="JetBrains Mono, monospace"),
            annotation_font_size=9,
            opacity=0.9,
        )

    fig.update_layout(**chart_layout(height=320, show_legend=False))
    style_axes(fig, y_title="Composite score", y_range=[-2.5, 2.5])
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# CONVICTION HEATMAP
# ══════════════════════════════════════════════════════════════════════════════


def create_risk_allocation_heatmap(portfolio: pd.DataFrame) -> go.Figure:
    """Per-holding risk profile, scored against THIS method's own objective.

    One row per dimension, one column per holding, diverging colour:

      Weight        share of capital
      Risk Share    share of PORTFOLIO VARIANCE this holding contributes
      Volatility    its own annualized volatility
      Independence  1 - |correlation to the finished book|
      Momentum      the 12-1 rank score (only for methods that tilt on it)

    Colour is a within-row percentile, so each dimension is read against its own
    peers rather than on incompatible absolute scales.

    WHAT "GREEN" MEANS DEPENDS ON THE METHOD, and that is the point of scoring
    against `nco_rc_target`. Reading every book against "risk share close to
    1/N" is only correct when the method actually targets equal risk:

      rc_target "equal"  (ERC)  — green = risk share AT its equal share. The
                                  chart is then a direct read on whether the
                                  solver achieved what it was asked to.
      rc_target "cluster" (HRP) — green = risk share BELOW equal. HRP balances
                                  across clusters, not across holdings, so a
                                  low-risk name inside a big cluster is a
                                  correct outcome, not an imbalance.
      rc_target "none"   (1/N, MaxDiv) — green = risk share below equal, since
                                  neither method manages risk contribution at
                                  all and the honest read is simply "who is
                                  carrying the variance".

    The gap between the Weight and Risk Share rows is the whole point: equal
    capital does NOT mean equal risk, and this is where you see it.
    """
    need = ["symbol", "weightage_pct"]
    if portfolio is None or portfolio.empty or not all(c in portfolio.columns for c in need):
        fig = go.Figure()
        fig.update_layout(**chart_layout(height=220))
        return fig

    attrs = getattr(portfolio, "attrs", {}) or {}
    rc_target = attrs.get("nco_rc_target", "none")
    uses_momentum = bool(attrs.get("nco_uses_momentum", False))

    df = portfolio.copy()
    for c, default in (("risk_contribution", np.nan), ("volatility", np.nan),
                       ("corr_to_book", np.nan), ("cluster", 0),
                       ("momentum_z", np.nan)):
        if c not in df.columns:
            df[c] = default
    # Cluster first, then weight — so structurally similar holdings sit together
    # and the block pattern is legible.
    df = df.sort_values(["cluster", "weightage_pct"], ascending=[True, False]).head(40)

    n = len(df)
    eq_share = 1.0 / n if n else 0.0
    w = pd.to_numeric(df["weightage_pct"], errors="coerce").fillna(0.0) / 100.0
    # NaN is left NaN on purpose: a holding with no covariance estimate (Equal
    # Weight can hold one) has no risk share, and filling it with the equal
    # share would print a fabricated number in a cell the table shows as "—".
    # Unranked NaN falls to the neutral colour and renders as an em dash below.
    rc = pd.to_numeric(df["risk_contribution"], errors="coerce")
    vol = pd.to_numeric(df["volatility"], errors="coerce")
    indep = 1.0 - pd.to_numeric(df["corr_to_book"], errors="coerce").abs()
    momz = pd.to_numeric(df["momentum_z"], errors="coerce")

    # Score the risk-share row against the method's OWN objective (see docstring).
    rc_key = -(rc - eq_share).abs() if rc_target == "equal" else -rc
    rc_label = "Risk Share" + (" vs target" if rc_target == "equal" else "")

    # Raw display values, and the "greener is better" ordering key per row.
    cols = [
        ("Weight",       w * 100.0,   -(w - eq_share).abs(), "{:.2f}%"),
        (rc_label,       rc * 100.0,  rc_key,                "{:.2f}%"),
        ("Volatility",   vol * 100.0, -vol,                  "{:.1f}%"),
        ("Independence", indep,        indep,                "{:.2f}"),
    ]
    if uses_momentum and momz.notna().any():
        # Shown only when a tilt was actually applied, so the chart never
        # implies a factor the book does not use.
        cols.append(("Momentum", momz, momz, "{:+.2f}"))

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
        # The app's data face, at the axis tick tier. This said IBM Plex Mono,
        # which is not among the fonts the stylesheet loads — so every cell
        # label fell back to the system monospace and the one type in the app
        # that was not ours sat inside the chart.
        textfont=dict(size=9, family="JetBrains Mono, monospace"),
        # Green is the calm end here, so the ramp runs rose -> panel -> emerald.
        # The midpoint is the panel itself: a holding sitting at its peers'
        # median has nothing to report, and nothing is what it should look like.
        colorscale=diverging_scale("rose", "emerald"),
        zmid=0.0, zmin=-1.0, zmax=1.0, showscale=False, xgap=2, ygap=3,
        hovertemplate="<b>%{x}</b><br>%{y}: %{text}<extra></extra>",
    ))
    _lab = max((len(str(s)) for s in df["symbol"]), default=8)
    fig.update_layout(**chart_layout(
        height=max(200, 46 * len(labels) + 90), show_legend=False,
        margin=dict(t=12, l=96, r=16, b=min(150, 38 + int(_lab * 5.5))),
    ))
    style_axes(fig)
    fig.update_xaxes(tickangle=-60, tickfont=dict(size=9))
    fig.update_yaxes(autorange="reversed")
    return fig


def create_risk_contribution_chart(portfolio: pd.DataFrame) -> go.Figure:
    """Capital share vs variance share, per holding — did the method do its job?

    Two bars per holding: weight (capital) and risk contribution (variance),
    against a dashed line at the equal share. This is the single most direct
    read on a weighting method, and what it should look like differs by method:

      ERC     the risk bars should sit FLAT on the equal-share line. Any
              visible step means the solver did not converge, and the header
              reports the dispersion so it cannot be missed.
      HRP     risk bars uneven by design — it balances clusters, not holdings.
      1/N     capital bars flat, risk bars wherever the covariance puts them.
              The gap between the two series IS the argument for risk weighting.
      MaxDiv  both uneven; it optimises the diversification ratio, not either
              of these series directly.

    The risk-allocation heatmap shows the same numbers as a percentile field;
    this shows them on a shared absolute scale, where "flat" is verifiable by
    eye rather than inferred from colour.
    """
    need = ["symbol", "weightage_pct"]
    if portfolio is None or portfolio.empty or not all(c in portfolio.columns for c in need):
        fig = go.Figure()
        fig.update_layout(**chart_layout(height=240))
        return fig

    attrs = getattr(portfolio, "attrs", {}) or {}
    rc_target = attrs.get("nco_rc_target", "none")

    df = portfolio.copy()
    if "risk_contribution" not in df.columns:
        df["risk_contribution"] = np.nan
    df = df.sort_values("weightage_pct", ascending=False).head(40)
    n = len(df)
    eq = 100.0 / n if n else 0.0
    w = pd.to_numeric(df["weightage_pct"], errors="coerce").fillna(0.0)
    # Unestimated holdings draw NO risk bar rather than a zero one: zero risk is
    # a measurement, and this is the absence of one.
    rc = pd.to_numeric(df["risk_contribution"], errors="coerce") * 100.0

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["symbol"], y=w, name="Capital",
        marker=dict(color=COLORS["slate_dim"]),
        hovertemplate="<b>%{x}</b><br>Capital %{y:.2f}%<extra></extra>",
    ))
    # Risk bars carry the verdict colour: at target is calm, over is hot. For
    # methods that do not target equal risk, "over its equal share" is still the
    # meaningful warning, so the same rule reads correctly for all of them.
    over = rc > eq * 1.15
    fig.add_trace(go.Bar(
        x=df["symbol"], y=rc, name="Risk (variance share)",
        marker=dict(color=[COLORS["rose"] if o else COLORS["emerald"] for o in over]),
        hovertemplate="<b>%{x}</b><br>Risk share %{y:.2f}%<extra></extra>",
    ))
    # The reference line carries no label. It had one — "equal share 3.33%",
    # pinned inside the plot at the top left — and inside a 30-bar chart there
    # is no corner that stays empty: at top right it sat under the legend, at
    # top left it sat over the first two bars. The panel header already states
    # the number ("capital vs variance · equal share 3.33%"), so the label was
    # a second copy of a fact competing with the data for the same pixels.
    fig.add_hline(y=eq, line=dict(color=COLORS["accent"], width=1.2, dash="dash"))

    disp = attrs.get("nco_rc_dispersion")
    solved = attrs.get("nco_rc_dispersion_solved")
    # `disp` is NaN when no holding carried a covariance estimate. Unreachable
    # for an rc_target=="equal" style (it cannot solve without one), but the
    # annotation would read "did not converge" rather than "not measured".
    if rc_target == "equal" and disp is not None and np.isfinite(disp):
        # Two numbers, not one. The solver's own dispersion says whether it
        # converged; the realised dispersion says what the held book looks like
        # after top-N selection and the position cap have pulled it away from
        # the solution. Showing only the realised figure makes a correct solve
        # read as a failure whenever the cap binds.
        ok = (solved if solved is not None else disp) < 0.01
        txt = f"risk dispersion — solved {solved:.3f}" if solved is not None else ""
        txt = (txt + f" · realised {disp:.3f} after selection + cap") if txt else \
              f"risk dispersion {disp:.3f}"
        fig.add_annotation(
            xref="paper", yref="paper", x=0, y=1.10, showarrow=False,
            text=txt + ("  ✓ solver balanced" if ok else "  — solver did not converge"),
            font=dict(size=10, family="JetBrains Mono, monospace",
                      color=COLORS["emerald"] if ok else COLORS["rose"]),
            align="left",
        )

    # THE LEGEND GOES ABOVE, not below.
    # `chart_layout` docks it under the x-axis, which is right for a handful of
    # short categories and wrong here: this chart carries one rotated ticker
    # per holding, so "under the axis" IS the label block, and the legend
    # printed straight through it. `y` is a fraction of the PLOT area, so
    # buying more bottom margin moved the plot up and took the legend with it —
    # the overlap survived every margin I gave it. Above the plot the space is
    # genuinely empty, and the two series are named before they are read.
    _lab = max((len(str(s)) for s in df["symbol"]), default=8)
    fig.update_layout(**chart_layout(
        height=max(300, 26 * 10 + 120), show_legend=True,
        margin=dict(t=44, l=52, r=16, b=min(150, 38 + int(_lab * 5.5))),
    ))
    fig.update_layout(
        barmode="group", bargap=0.25, bargroupgap=0.08,
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1, bgcolor="rgba(0,0,0,0)",
                    font=dict(size=10, family="JetBrains Mono, monospace"),
                    itemsizing="constant"),
    )
    style_axes(fig)
    fig.update_xaxes(tickangle=-60, tickfont=dict(size=9))
    fig.update_yaxes(title_text="% of book", tickfont=dict(size=9))
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
        # Red is a HIGH correlation — two holdings that are one bet — so the
        # ramp runs emerald (diversifying) -> panel (unrelated) -> rose.
        colorscale=diverging_scale("emerald", "rose"),
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
                # A boundary is STRUCTURE, not a claim: it is drawn in the panel's
                # own ground, so it reads as a gap cut through the field rather
                # than as a third semantic colour competing with the data. In
                # accent blue it was the most saturated thing on a matrix whose
                # whole point is the red blocks.
                for kw in ({"x0": i - 0.5, "x1": i - 0.5, "y0": -0.5, "y1": len(syms) - 0.5},
                           {"y0": i - 0.5, "y1": i - 0.5, "x0": -0.5, "x1": len(syms) - 0.5}):
                    fig.add_shape(type="line", line=dict(color=panel_bg(), width=2), **kw)

    size = max(320, min(620, 20 * len(syms) + 120))
    _lab = max((len(str(s)) for s in syms), default=8)
    fig.update_layout(**chart_layout(
        height=size, show_legend=False,
        margin=dict(t=12, l=96, r=16, b=min(150, 38 + int(_lab * 5.5))),
    ))
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
        line=dict(color=COLORS["accent"], width=2.5),
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
