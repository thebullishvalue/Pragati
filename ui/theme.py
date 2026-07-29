"""
PRAGYAM — UI Theme (CSS, Chart Theming & Color Constants)
══════════════════════════════════════════════════════════════════════════════

The "Obsidian Quant" Institutional Research Terminal design language — a
precision-instrument aesthetic for quantitative finance.
- Display/UI:  Syne (geometric, authoritative, distinctive)
- Body/Data:   JetBrains Mono (refined monospace, tabular precision)
- Palette:     Obsidian (#0A0E17 -> #050810), Amber Gold (#D4A853)
- Surfaces:    Frameless glass panels with thin border strokes.

Author: @thebullishvalue
"""

from __future__ import annotations

import html
from pathlib import Path

import streamlit as st

VERSION = "v11.0.0"
PRODUCT_NAME = "Pragyam"
COMPANY = "@thebullishvalue"

# Path to external CSS file
CSS_PATH = Path(__file__).parent / "theme.css"

# ── Shared Plotly layout config ─────────────────────────────────────────────
# Eliminates massive duplication across all tab files.

PLOTLY_FONT = dict(family="JetBrains Mono, monospace", color="#94A3B8", size=10)
PLOTLY_HOVERLABEL = dict(
    bgcolor="rgba(10, 14, 23, 0.95)",
    font=dict(family="JetBrains Mono, monospace", size=11, color="#F1F5F9"),
    bordercolor="rgba(255,255,255,0.08)",
    align="left",
)
PLOTLY_LEGEND = dict(
    orientation="h",
    yanchor="bottom",
    y=1.02,
    xanchor="right",
    x=1,
    font=dict(size=10, family="JetBrains Mono, monospace"),
    bgcolor="rgba(0,0,0,0)",
)
PLOTLY_MARGIN = dict(t=20, l=50, r=20, b=40)
PLOTLY_GRID = "rgba(255,255,255,0.035)"
PLOTLY_GRID_ZERO = "rgba(255,255,255,0.06)"

# Interactive chart config — click + zoom + pan
PLOTLY_MODEBAR = dict(
    modeBarButtonsToRemove=["lasso2d", "select2d"],
    modeBarButtonsToAdd=[
        "drawline",
        "eraseshape",
    ],
    displaylogo=False,
)


def chart_layout(
    height: int = 360,
    show_legend: bool = True,
    margin: dict | None = None,
    responsive: bool = False,
) -> dict:
    """Return a base Plotly layout dict for the Obsidian Quant theme.

    Args:
        height: Fixed pixel height for the chart.
        show_legend: Whether to show the legend.
        margin: Custom margin dict.
        responsive: If True, adds CSS-based responsive sizing via autosize.
    """
    base = dict(
        height=height,
        showlegend=show_legend,
        legend=PLOTLY_LEGEND if show_legend else None,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=PLOTLY_FONT,
        hovermode="x unified",
        hoverlabel=PLOTLY_HOVERLABEL,
        margin=margin or PLOTLY_MARGIN,
        spikedistance=-1,
    )
    if responsive:
        base["autosize"] = True
    return base


def style_axes(fig, y_title: str = "", x_title: str = "", y_range=None, row=None, col=None) -> None:
    """Apply consistent axis styling to a Plotly figure."""
    kw = {}
    if row is not None:
        kw["row"] = row
    if col is not None:
        kw["col"] = col

    fig.update_xaxes(
        showgrid=True,
        gridcolor=PLOTLY_GRID,
        gridwidth=0.5,
        zeroline=False,
        linecolor="rgba(255,255,255,0.04)",
        title_text=x_title,
        tickfont=dict(size=9, family="JetBrains Mono, monospace", color="#64748B"),
        # Vertical crosshair — dashed dim grey
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikethickness=0.5,
        spikedash="dash",
        spikecolor="rgba(148,163,184,0.18)",
        **kw,
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor=PLOTLY_GRID,
        gridwidth=0.5,
        zeroline=True,
        zerolinecolor=PLOTLY_GRID_ZERO,
        zerolinewidth=0.5,
        linecolor="rgba(255,255,255,0.04)",
        title_text=y_title,
        range=y_range,
        tickfont=dict(size=9, family="JetBrains Mono, monospace", color="#64748B"),
        hoverformat=".2f",
        **kw,
    )


def inject_css() -> None:
    """Inject the Obsidian Quant Terminal CSS into the Streamlit app.

    Loads from external theme.css file for maintainability.
    Injects on every render — Streamlit deduplicates identical <style> blocks.
    """
    if CSS_PATH.exists():
        # Force UTF-8: theme.css contains non-ASCII bytes that the Windows
        # default codec (cp1252) cannot decode (UnicodeDecodeError on 0x8d).
        css = CSS_PATH.read_text(encoding="utf-8")
    else:
        css = "/* theme.css not found */"

    # Cache-bust: tag the <style> with the file's mtime so an edited theme.css is
    # never byte-identical to the previously-injected block (Streamlit dedupes
    # identical <style> blocks, which otherwise serves stale CSS after an edit).
    try:
        _stamp = int(CSS_PATH.stat().st_mtime)
    except Exception:
        _stamp = 0
    st.markdown(f"<style data-css-v='{_stamp}'>\n/* v{_stamp} */\n{css}</style>", unsafe_allow_html=True)


def progress_bar(slot, pct: int, label: str, sub: str = "") -> None:
    """Render a themed progress card into an ``st.empty()`` slot."""
    is_complete = pct >= 100
    bar_color = "#34D399" if is_complete else "#D4A853" if pct > 50 else "#22D3EE"
    dot_class = "pulse-dot complete" if is_complete else "pulse-dot"
    slot.markdown(
        f"""
    <div class="progress-card">
        <div class="progress-label">
            <span class="{dot_class}"></span>{html.escape(label)}
        </div>
        {f'<div class="progress-sub">{html.escape(sub)}</div>' if sub else ''}
        <div class="progress-track">
            <div class="progress-fill" style="width:{pct}%;background:{bar_color};box-shadow:0 0 10px {bar_color};"></div>
        </div>
        <div class="progress-pct">{pct}%</div>
    </div>
    """,
        unsafe_allow_html=True,
    )


def apply_chart_theme(fig) -> None:
    """Apply the Obsidian Quant Terminal theme to a Plotly figure (mutates in place)."""
    fig.update_layout(**chart_layout())
    style_axes(fig)
