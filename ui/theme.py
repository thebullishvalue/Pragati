"""
PRAGYAM — Shared CSS, chart theming, and colour constants for the UI layer.
प्रज्ञम् (Pragyam) — "Discernment / Wisdom"

UI — Institutional research terminal design language.

Aesthetic: "Graphite" — near-achromatic ground, semantic colour only
--------------------------------------------------------------------
- Display/UI:  Inter (prose, headings, labels)
- Body/Data:   JetBrains Mono (tabular numerals — every figure in the app)
- Ground:      Graphite (#0A0C10 -> #1C212A), deliberately neutral. The
               predecessor ramp was Obsidian with an amber-gold accent, which
               tinted every panel warm and forced the semantic hues to
               compete with the brand for the same attention.
- Semantic:    Cobalt #4C7DF0 (interactive), Green #2CA36B (carries less
               variance than capital), Red #DD5A5A (carries more), Amber
               #D79A3C (caution ONLY), Steel #4E9FC4 (info). Muted, not the
               stock Tailwind-500 ramp; each clears WCAG AA on every surface
               it is used on.
- Surfaces:    Flat, told apart by a hairline border and one step of tone.
               No blur, no stacked shadows — a shadow is spent on overlays.
- Themes:      Slate (dark, canonical) and Paper (light, for reading and
               print). The light theme is a token swap, not a second
               stylesheet — see LIGHT_TOKENS below.

Ported from TATTVA, the sibling terminal, so the two apps share one grammar.

Author: @thebullishvalue
"""

from __future__ import annotations

import html
from pathlib import Path

import streamlit as st

VERSION = "v11.0.0"
PRODUCT_NAME = "Pragyam"
COMPANY = "@thebullishvalue"

# ── Chart palette (dark ground) ─────────────────────────────────────────────
# The single source for every colour a chart draws with. Tabs must reach it
# through `chart_color()` / `chart_rgba()` rather than importing a COLOR_*
# constant, because those are bound at import time and cannot follow a theme
# switch — see the note on _palette() below.
_PALETTE_RGB: dict[str, tuple[int, int, int]] = {
    "emerald": (44, 163, 107),   # #2CA36B - risk under capital share / positive
    "rose":    (221, 90, 90),    # #DD5A5A - risk over capital share / negative
    "accent":  (76, 125, 240),   # #4C7DF0 - primary / interactive (brand, nav, CTA)
    "cyan":    (78, 159, 196),   # #4E9FC4 - info (informational tone only)
    "amber":   (215, 154, 60),   # #D79A3C - caution / warning ONLY, never brand
    "violet":  (155, 143, 212),  # #9B8FD4 - secondary / attribution
    "slate":   (126, 135, 151),  # #7E8797 - neutral / muted
}


def _palette_hex(name: str) -> str:
    r, g, b = _PALETTE_RGB[name]
    return f"#{r:02X}{g:02X}{b:02X}"


def rgba(name: str, alpha) -> str:
    """Semantic chart colour -> ``rgba()`` string.

    The ONE way inline Plotly fills/markers should reference the palette (never
    a raw numeric triple), so the chart palette stays single-sourced.
    """
    r, g, b = _PALETTE_RGB[name]
    return f"rgba({r},{g},{b},{alpha})"


COLOR_GREEN = _palette_hex("emerald")
COLOR_RED = _palette_hex("rose")
COLOR_GOLD = _palette_hex("amber")
COLOR_CYAN = _palette_hex("cyan")
COLOR_AMBER = _palette_hex("amber")
COLOR_ACCENT = _palette_hex("accent")
COLOR_PURPLE = _palette_hex("violet")
COLOR_MUTED = rgba("slate", 0.4)

# Path to external CSS file
CSS_PATH = Path(__file__).parent / "theme.css"

# ── Light theme — token overrides only ──────────────────────────────────────
# theme.css defines the canonical dark :root token block; every component
# rule in it reads var(--token) with nothing hardcoded outside that block.
# Light mode is therefore just a second, smaller :root that redefines the
# same custom properties — injected AFTER the base stylesheet so it wins on
# source order, no runtime DOM attribute toggling required. Hues are
# deepened versions of the dark palette (not the same RGB) so text clears
# WCAG AA on a near-white surface.
LIGHT_TOKENS = """
:root {
    /* Counterpart to the dark block's declaration — see the note there. This
       is what keeps Paper light on a device whose system theme is dark; the
       two together mean the OS preference is never consulted in either
       direction. */
    color-scheme: light;

    /* Paper — the reporting/print theme. Not "dark inverted": a near-white
       ground reflects far more light than a graphite one, so the semantic
       hues are DEEPENED rather than reused (a #2CA36B that clears 5.9:1 on
       graphite manages 2.6:1 on white and would be illegible). Every value
       below clears WCAG AA on both --surface-1 and --surface-2. */
    --bg:            #F4F6F8;
    --surface-1:     #FFFFFF;
    --surface-2:     #EEF1F5;
    --surface-3:     #E2E7EE;

    --ink:           #141920;   /* 17.7:1 on white */
    --ink-secondary: #3D4756;   /*  9.4:1 */
    --ink-tertiary:  #5E6979;   /*  5.6:1 */
    --ink-quaternary:#6B7482;   /*  4.6:1 */
    --spike: rgba(90, 100, 114, 0.45);

    --accent:        #2B5FD9;   /* 5.6:1 */
    --long:          #0F7A54;   /* 5.3:1 */
    --short:         #C0392F;   /* 5.4:1 */
    --caution:       #96660F;   /* 5.0:1 */
    --system:        #15708C;   /* 5.6:1 */
    --neutral:       #5A6472;   /* 6.0:1 */

    --accent-fill:   rgba(43, 95, 217, 0.07);
    --long-fill:     rgba(15, 122, 84, 0.08);
    --short-fill:    rgba(192, 57, 47, 0.07);
    --caution-fill:  rgba(150, 102, 15, 0.08);
    --system-fill:   rgba(21, 112, 140, 0.07);
    --accent-edge:   rgba(43, 95, 217, 0.32);
    --long-edge:     rgba(15, 122, 84, 0.32);
    --short-edge:    rgba(192, 57, 47, 0.30);
    --caution-edge:  rgba(150, 102, 15, 0.30);
    --system-edge:   rgba(21, 112, 140, 0.28);

    --line:          rgba(15, 23, 42, 0.10);
    --line-strong:   rgba(15, 23, 42, 0.18);
    --line-faint:    rgba(15, 23, 42, 0.05);

    --violet:        #6A4BC0;   /* 6.2:1 */
    --violet-fill:   rgba(106, 75, 192, 0.07);
    --violet-edge:   rgba(106, 75, 192, 0.30);

    --shadow-sm:     0 1px 2px rgba(15, 23, 42, 0.06);
    --shadow-pop:    0 10px 24px rgba(15, 23, 42, 0.12);
}
/* Two rules cannot be expressed as a token swap. On paper the primary
   button's hover needs a DARKER accent (the dark theme's is lighter), and
   the sidebar rail reads better as the tinted surface with the content
   area white — the reverse of the dark theme's arrangement. */
[data-testid="stBaseButton-primary"]:hover { background: #244EB4 !important; border-color: #244EB4 !important; }
[data-testid="stSidebar"] { background: var(--surface-2); }

/* ── Reclaiming Streamlit's own natives ──────────────────────────────────
   THIS is why Paper mode looked half-broken. `.streamlit/config.toml` pins
   Streamlit to `base = "dark"` with `textColor = #E6EAF1`, and that is a
   STATIC config — it cannot follow a runtime theme switch. So on Paper the
   token swap repaints every surface white while Streamlit keeps colouring
   its own internals near-white: the navigation labels, button faces, input
   text and placeholders all went white-on-white. "Some fonts or elements
   show up, some do not" is precisely a light ground wearing a dark-theme
   text colour.

   Anything the app styles through its own classes was already fine — which
   is why the effect looked arbitrary rather than total. The rules below
   claim the remainder. They live in LIGHT_TOKENS (not theme.css) because on
   the dark theme Streamlit's defaults are already correct and overriding
   them there would be noise. */
[data-testid="stSidebarNavLink"],
[data-testid="stSidebarNavLink"] span,
[data-testid="stSidebarNavLink"] p { color: var(--ink-tertiary) !important; }
[data-testid="stSidebarNavLink"]:hover,
[data-testid="stSidebarNavLink"]:hover span { color: var(--ink) !important; }
[data-testid="stSidebarNavLink"][aria-current="page"],
[data-testid="stSidebarNavLink"][aria-current="page"] span { color: var(--ink) !important; }
[data-testid="stNavSectionHeader"] { color: var(--ink-quaternary) !important; }

/* Buttons: Streamlit's dark-base face is a dark pill, which on paper reads
   as an inverted, "pressed" control sitting on a white rail. */
[data-testid^="stBaseButton"] {
    background: var(--surface-1) !important;
    color: var(--ink-secondary) !important;
    border-color: var(--line-strong) !important;
}
[data-testid^="stBaseButton"]:hover {
    background: var(--surface-2) !important; color: var(--ink) !important;
}
[data-testid="stBaseButton-primary"] {
    background: var(--accent) !important; color: #FFFFFF !important;
}

/* Inputs, their text, and — the easiest one to miss — their placeholders.
   The select's own FACE needs claiming too: BaseWeb paints it from
   Streamlit's dark base, so on Paper the dropdown stayed a dark well with
   dark text while the rail around it went white. */
.stTextInput input, .stNumberInput input, .stTextArea textarea,
.stSelectbox [data-baseweb="select"] span,
.stSelectbox [data-baseweb="select"] div { color: var(--ink) !important; }
input::placeholder, textarea::placeholder { color: var(--ink-quaternary) !important; opacity: 1; }
/* One ground for every field in the rail. The number and date controls are
   named by their CONTAINER, not their inner input, because that is the node
   each of them borders — see the one-node rule in theme.css. */
.stSelectbox [data-baseweb="select"] > div,
.stTextInput input, .stTextArea textarea,
[data-testid="stNumberInputContainer"],
.stDateInput [data-baseweb="input"] {
    background: var(--surface-1) !important;
    border-color: var(--line-strong) !important;
}
.stSelectbox [data-baseweb="select"] svg { color: var(--ink-quaternary) !important; }
/* The open menu is a portal at the document root — it inherits nothing from
   the app, so it needs the light surface named explicitly.

   And it needs it on EVERY node, not just the shell. BaseWeb builds these
   overlays from a JS theme object made at page load out of
   `.streamlit/config.toml`, which is static and pinned to Slate; on Paper the
   whole overlay therefore arrives painted dark, and each of its four or five
   nested divs carries its own background. Claiming the shell alone leaves
   black strips wherever a deeper node paints — which is exactly how the
   calendar failed: white day grid, black header and black empty cells.

   So the pattern for every portalled surface is: paint the shell, blank every
   descendant, then reinstate the two or three states that genuinely carry a
   fill. Source order matters — the reset precedes the states. */
[data-baseweb="popover"] > div,
[data-baseweb="popover"] ul,
[data-baseweb="popover"] [data-baseweb="menu"] {
    background: var(--surface-1) !important;
    color: var(--ink) !important;
    border-color: var(--line-strong) !important;
}
[data-baseweb="popover"] * { background-color: transparent !important; }
[data-baseweb="popover"] [role="option"] { color: var(--ink-secondary) !important; }
[data-baseweb="popover"] [role="option"]:hover { background-color: var(--surface-2) !important; }
[data-baseweb="popover"] [role="option"][aria-selected="true"] {
    color: var(--ink) !important; background-color: var(--surface-2) !important;
}
/* Tooltips are portalled to the document root like the menus, and Streamlit
   paints them from its static dark base — a black slab with white text on a
   white page. The inner div carries the background, so both are named. */
[data-baseweb="tooltip"], [data-baseweb="tooltip"] > div,
[role="tooltip"], [role="tooltip"] > div {
    background: var(--surface-3) !important;
    color: var(--ink) !important;
    border-color: var(--line-strong) !important;
}
[data-baseweb="tooltip"] *, [role="tooltip"] * {
    background-color: transparent !important; color: var(--ink) !important;
}

/* Input shells. Streamlit's dark base gives these a dark inner surface and a
   shadow to match, and the shadow survives a background override — it is what
   read as a black seam down the right edge of the capital field once the
   stepper beside it was removed. */
.stDateInput [data-baseweb="input"], .stNumberInput [data-baseweb="input"],
.stTextInput [data-baseweb="input"], .stSelectbox [data-baseweb="select"] > div {
    box-shadow: none !important;
}
.stDateInput [data-baseweb="input"] *, .stNumberInput [data-baseweb="input"] * {
    background-color: transparent !important;
}

/* Segmented controls and body copy. */
[data-testid="stButtonGroup"] button { color: var(--ink-tertiary) !important; }
[data-testid="stButtonGroup"] button[data-testid$="Active"] { color: var(--ink) !important; }
[data-testid="stMain"], [data-testid="stSidebar"] { color: var(--ink); }
.stMarkdown, .stMarkdown p, .stMarkdown li { color: var(--ink-secondary); }
"""

# Chart-theming constants below are read by Plotly, which cannot see CSS
# custom properties — each theme needs its own literal hex set. Keyed the
# same way `inject_css(theme=...)` is, so a single `theme` argument threaded
# through `chart_layout`/`style_axes` flips chrome and charts together.
_CHART_THEME = {
    "dark": dict(
        font_color="#8B95A6",          # --ink-tertiary
        hover_bg="rgba(21, 25, 32, 0.96)",   # --surface-2
        hover_border="rgba(255,255,255,0.13)",
        hover_text="#E6EAF1",
        grid="rgba(255,255,255,0.05)",
        grid_zero="rgba(255,255,255,0.11)",
        axis_line="rgba(255,255,255,0.09)",
        tick="#737D8E",
        spike="rgba(139,149,166,0.45)",
    ),
    "light": dict(
        font_color="#5E6979",
        hover_bg="rgba(255,255,255,0.97)",
        hover_border="rgba(15,23,42,0.18)",
        hover_text="#141920",
        grid="rgba(15,23,42,0.07)",
        grid_zero="rgba(15,23,42,0.16)",
        axis_line="rgba(15,23,42,0.12)",
        tick="#5E6979",
        spike="rgba(90,100,114,0.45)",
    ),
}


def _active_theme() -> str:
    """The active theme name — dark unless the appearance control has set light."""
    return str(st.session_state.get("theme", "dark"))


def _chart_theme() -> dict:
    return _CHART_THEME.get(_active_theme(), _CHART_THEME["dark"])


# ── Theme-aware CHART palette ───────────────────────────────────────────────
# `_PALETTE_RGB` above is a single palette tuned for the dark ground, and the
# tab files imported its COLOR_* constants BY VALUE at module load. That is
# why Paper mode only half-worked: the chrome flipped to a white ground while
# every line, bar and marker kept the colour it had been given for graphite —
# a #2CA36B green that clears 5.9:1 on #0F1217 manages 2.6:1 on white, so
# roughly half the ink on a chart faded out while the other half (the axis and
# grid, which DO read the theme) went dark. "Some elements show up, some do
# not" is exactly what a half-themed palette looks like.
#
# The light values below are the SAME hexes LIGHT_TOKENS gives the chrome, so a
# green line equals the green value beside it in either theme, and each clears
# WCAG AA on its own ground.
_PALETTE_LIGHT: dict[str, tuple[int, int, int]] = {
    "emerald": (15, 122, 84),    # #0F7A54  5.3:1 on white
    "rose":    (192, 57, 47),    # #C0392F  5.4:1
    "accent":  (43, 95, 217),    # #2B5FD9  5.6:1
    "cyan":    (21, 112, 140),   # #15708C  5.6:1
    "amber":   (150, 102, 15),   # #96660F  5.0:1
    "violet":  (106, 75, 192),   # #6A4BC0  6.2:1
    "slate":   (90, 100, 114),   # #5A6472  6.0:1
}


def _palette() -> dict:
    return _PALETTE_LIGHT if _active_theme() == "light" else _PALETTE_RGB


def chart_color(name: str) -> str:
    """A semantic chart colour for the ACTIVE theme, as ``#RRGGBB``.

    The one way a tab names a colour. Use it in place of the ``COLOR_*``
    constants, which are bound at import time and therefore cannot flip.
    """
    r, g, b = _palette()[name]
    return f"#{r:02X}{g:02X}{b:02X}"


def chart_rgba(name: str, alpha) -> str:
    """A semantic chart colour for the active theme, as ``rgba(...)``.

    Signature-compatible with the module-level ``rgba`` so call sites only change
    which module they import from.
    """
    r, g, b = _palette()[name]
    return f"rgba({r},{g},{b},{alpha})"


def panel_bg() -> str:
    """The panel surface a chart is drawn on, as a solid hex.

    For marker outlines, whose job is to separate overlapping points by
    painting a sliver of the BACKGROUND between them. One tab hardcoded
    ``rgba(10,14,23,0.8)`` for this — the previous theme's background, which
    on Paper draws a near-black halo around every marker on a white panel.
    """
    return "#FFFFFF" if _active_theme() == "light" else "#0F1217"


def diverging_scale(low: str = "emerald", high: str = "rose") -> list:
    """The app's one diverging colourscale, resolved for the ACTIVE theme.

    Every heatmap in the app reads this rather than composing its own ramp, and
    the two rules it encodes are the whole reason it exists.

    THE MIDPOINT IS THE PANEL, not a colour. A cell at zero is a cell with
    nothing to say, and the honest way to draw nothing is to let the panel show
    through — so zero disappears and only the cells carrying a claim have ink.
    The correlation matrix had a hardcoded ``rgba(20,20,24,0.85)`` midpoint:
    near-black in BOTH appearances, so on Paper a matrix of mild correlations
    rendered as a dark slab in the middle of a white page, and the one value
    that means "no relationship" was the most visually assertive thing on it.

    NO ALPHA IN THE RAMP. The risk heatmap used ``slate_dim`` (45% grey) as its
    midpoint, which Plotly composites over the plot ground — the ramp then
    changes character with the surface behind it instead of being one scale.
    Both stops are opaque semantic colours; the panel supplies the middle.
    """
    return [[0.0, chart_color(low)], [0.5, panel_bg()], [1.0, chart_color(high)]]


def grid_rgba(alpha: float = 1.0) -> str:
    """A hairline colour that works on BOTH grounds.

    Tab code drew in-plot rules with literal ``rgba(255,255,255,0.06)`` — white
    on white in Paper mode, i.e. invisible. This returns white-alpha on the
    dark ground and slate-alpha on the light one, scaled by ``alpha`` against
    the theme's own base grid opacity.
    """
    if _active_theme() == "light":
        return f"rgba(15,23,42,{min(0.9, alpha * 1.6):.3f})"
    return f"rgba(255,255,255,{alpha:.3f})"


# ── Shared Plotly layout config ─────────────────────────────────────────────
# Eliminates massive duplication across all tab files. chart_layout() and
# style_axes() read the theme-aware _chart_theme(), so every chart in the app
# flips with the appearance toggle without the six tab files needing to change
# a single call site.

# (PLOTLY_FONT and PLOTLY_HOVERLABEL lived here as "dark-theme defaults for
# any external/legacy caller". Nothing in the app, the tabs or the research
# suite imported either, and both still carried the PREVIOUS palette's
# literals — #94A3B8 ink on a rgba(4,7,13) navy — so the only thing they could
# have done, had a caller appeared, is reintroduce the old theme. The
# theme-aware _chart_theme() is the single source; these are removed.)

#: Legend. Two things were wrong with it.
#: (1) Anchored at y=1.02, top-right — exactly where Plotly puts the modebar,
#:     so the toolbar sat on top of the series names on every hover.
#: (2) Its font dict named a size and family but NO colour, which makes Plotly
#:     fall back to its own default ink rather than inheriting the layout font
#:     — invisible on Paper. The colour is now supplied per theme in
#:     chart_layout(), which is the only place that knows which theme is on.
#: It now sits BELOW the plot, right-aligned: clear of the toolbar, clear of
#: the y-axis, and reading as a caption to the chart rather than a header.
PLOTLY_LEGEND = dict(
    orientation="h",
    yanchor="top",
    y=-0.16,
    xanchor="right",
    x=1,
    font=dict(size=10, family="JetBrains Mono, monospace"),
    bgcolor="rgba(0,0,0,0)",
    itemsizing="constant",
)
#: Plot margins. `t` is set per-figure by ``chart_layout`` — a legend anchored
#: at y=1.02 needs room ABOVE the plot area to sit in, and the single fixed
#: t=20 this used to be clipped every legended chart in the app while wasting
#: the same 20px on every chart without one.
PLOTLY_MARGIN = dict(t=28, l=52, r=16, b=38)

# ── The one Plotly config, passed to EVERY st.plotly_chart in the app ────────
# This existed as PLOTLY_MODEBAR and was never wired to a single call site, so
# all twenty charts rendered Plotly's stock toolbar — including the Plotly
# logo, a link out to plotly.com, and buttons for lasso/box-select that do
# nothing in a read-only research view. It was the one element in the app that
# visibly belonged to another product.
#
# What survives is what a research reader actually uses: zoom, pan, reset, and
# a PNG export named after the chart. Everything else is removed, the logo with
# it. `displayModeBar="hover"` keeps the toolbar out of the composition until
# the pointer is inside the panel.
PLOTLY_CONFIG = dict(
    displaylogo=False,
    displayModeBar="hover",
    modeBarButtonsToRemove=[
        "lasso2d", "select2d", "autoScale2d", "toggleSpikelines",
        "hoverClosestCartesian", "hoverCompareCartesian", "zoom3d", "pan3d",
        "orbitRotation", "tableRotation", "resetCameraDefault3d",
        "resetCameraLastSave3d", "hoverClosest3d",
    ],
    toImageButtonOptions=dict(format="png", scale=2, filename="tattva-chart"),
    scrollZoom=False,
    doubleClick="reset",
    responsive=True,
)

#: Back-compat alias. Anything still importing the old name gets the new
#: config rather than a second, divergent one.
PLOTLY_MODEBAR = PLOTLY_CONFIG


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
    ct = _chart_theme()
    # Legended charts need headroom for the legend anchored above the plot
    # area; unlegended ones should not pay for it.
    _margin = dict(PLOTLY_MARGIN)
    if show_legend:
        _margin["b"] = 58        # the legend now sits under the x-axis
    else:
        _margin["t"] = 12
    base = dict(
        height=height,
        showlegend=show_legend,
        legend=({**PLOTLY_LEGEND,
                 "font": {**PLOTLY_LEGEND["font"], "color": ct["font_color"]}}
                if show_legend else None),
        # PAINT THE CANVAS, never leave it transparent.
        #
        # These were rgba(0,0,0,0). A transparent Plotly canvas renders nothing
        # of its own and shows whatever sits behind it, so the chart ground was
        # never actually chosen by this app — it was inherited. On a device
        # whose SYSTEM theme is light, any light bleed from the browser or from
        # a Streamlit surface that has not been overridden lands inside the plot
        # area, and Slate renders with pale patches behind dark-theme ink.
        #
        # Painting it with `panel_bg()` makes the ground explicit AND keeps it
        # appearance-aware, which is the part a blanket "force dark" would get
        # wrong: panel_bg() is #0F1217 under Slate and #FFFFFF under Paper, so
        # Paper stays light on a dark-mode device by exactly the same mechanism
        # that keeps Slate dark on a light-mode one. The device preference stops
        # being consulted in either direction.
        paper_bgcolor=panel_bg(),
        plot_bgcolor=panel_bg(),
        font=dict(family="JetBrains Mono, monospace", color=ct["font_color"], size=10),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor=ct["hover_bg"],
            font=dict(family="JetBrains Mono, monospace", size=11, color=ct["hover_text"]),
            bordercolor=ct["hover_border"],
            align="left",
        ),
        margin=margin or _margin,
        spikedistance=-1,
        # Colourway: any trace that does not name a colour draws from the app's
        # own semantic ramp instead of Plotly's default D3 category-10 (the
        # orange/purple/brown sequence that reads as a different product).
        # Resolved per render, not from the import-time COLOR_* constants, so
        # an unnamed trace follows the active theme like every named one.
        colorway=[chart_color(n) for n in
                  ("accent", "cyan", "emerald", "amber", "rose", "violet")],
    )
    if responsive:
        base["autosize"] = True
    return base


#: Axis type. One family, one size, one colour across every plot — the same
#: mono the tables and cards use, at the app's --fs-3xs (9px) tick / --fs-2xs
#: (10px) title tiers, so a chart's axis labels are visibly the same kind of
#: text as a table's column headers rather than Plotly's default 12px sans.
_AXIS_TICK_FONT = dict(size=9, family="JetBrains Mono, monospace")
_AXIS_TITLE_FONT = dict(size=10, family="JetBrains Mono, monospace")


def style_axes(fig, y_title: str = "", x_title: str = "", y_range=None, row=None, col=None) -> None:
    """Apply the app's one axis grammar to a Plotly figure.

    Ticks and axis titles share the data face at the app's own micro sizes;
    titles are a step dimmer than the ticks they label, because the number is
    the reading and the unit is the caption. The crosshair is a hairline in
    the theme's spike colour, and — critically — it now reads from the theme,
    so on Paper it is a dark hairline rather than the white one that was
    invisible against a white panel.
    """
    kw = {}
    if row is not None:
        kw["row"] = row
    if col is not None:
        kw["col"] = col

    ct = _chart_theme()
    fig.update_xaxes(
        showgrid=True,
        gridcolor=ct["grid"],
        gridwidth=0.5,
        zeroline=False,
        linecolor=ct["axis_line"],
        title_text=x_title,
        title_font=dict(**_AXIS_TITLE_FONT, color=ct["tick"]),
        tickfont=dict(**_AXIS_TICK_FONT, color=ct["tick"]),
        # Crosshair. It was rendering as a hard white rule across the plot,
        # which is the loudest mark on the panel and belongs to no part of the
        # design system. A crosshair is a pointer, not a series: sub-pixel
        # weight, dotted, and at the theme's own low-alpha spike colour.
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikethickness=1,
        spikedash="dash",
        spikecolor=ct["spike"],
        **kw,
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor=ct["grid"],
        gridwidth=0.5,
        zeroline=True,
        zerolinecolor=ct["grid_zero"],
        zerolinewidth=1,
        linecolor=ct["axis_line"],
        title_text=y_title,
        title_font=dict(**_AXIS_TITLE_FONT, color=ct["tick"]),
        range=y_range,
        tickfont=dict(**_AXIS_TICK_FONT, color=ct["tick"]),
        hoverformat=".2f",
        # NO horizontal spike. A second crosshair arm doubles the ink for a
        # reading the gridlines already give, and in `x unified` hover mode
        # Plotly draws it as a hard opaque rule regardless of the alpha asked
        # for — the solid white line across the plot. One dashed vertical
        # crosshair is the whole crosshair now.
        showspikes=False,
        # (6) A FIXED standoff between the axis title and its tick labels.
        # Plotly otherwise sets it from each subplot's widest tick label, so a
        # stacked figure whose rows carry different magnitudes ("0.5" vs
        # "-100") puts each row's y-title at a different x — the small
        # misalignment down the left edge of the convergence chart.
        title_standoff=14,
        **kw,
    )
    # ── Crosshair, enforced on EVERY x-axis ──────────────────────────────
    # This is why the white line survived three attempts to style it. The
    # spike settings above are applied with `row=`/`col=`, which addresses one
    # subplot's axis. On a stacked figure with `shared_xaxes=True` the visible
    # spike is drawn from a DIFFERENT axis object than the ones being updated,
    # so it kept Plotly's default — an opaque white rule — no matter what the
    # per-row call said. A row-less update writes every x-axis in the figure.
    fig.update_xaxes(
        showspikes=True, spikemode="across", spikesnap="cursor",
        spikethickness=1, spikedash="dot", spikecolor=ct["spike"],
    )
    fig.update_yaxes(showspikes=False)

    # Backfill a 2-decimal hover on every visible trace. style_axes runs after
    # all traces are added and right before st.plotly_chart on every chart, so
    # this is the one place that fixes hover precision for ALL plots at once.
    apply_default_hover(fig)


def apply_default_hover(fig, precision: int = 2) -> None:
    """Give every visible trace a 2-decimal hover, robustly.

    We do NOT rely on a d3 number format inside the hovertemplate
    (``%{y:.2f}``): under ``hovermode="x unified"`` Plotly leaves that format
    UNAPPLIED and the hover leaks full float precision (e.g.
    "Consensus (50/50): -0.3687992004699925"). Instead the values are
    pre-formatted to strings in Python and stashed in ``customdata``, then the
    template just inserts the finished string (``%{customdata[0]}``) — no
    client-side number formatting involved, so it cannot be ignored.

    Idempotent-ish: skips ``hoverinfo="skip"`` fills. Traces that already carry
    a hover string via ``customdata`` (i.e. previously processed) are re-set
    safely. Keeps the marker ``text`` label (e.g. the hero "S. Buy"/"Hold") and
    the trace name when present.
    """
    for tr in fig.data:
        if getattr(tr, "hoverinfo", None) == "skip":
            continue
        # Preserve two kinds of intentional templates:
        #  • "%{x…}" — traces that show the X value on hover (e.g. the precedent
        #    Z-vs-forward scatter, "Z: %{x:.2f}"); those run in closest mode where
        #    d3 formats fine and the X is the point of the hover.
        #  • "%{customdata…}" — already pre-formatted (by us on a prior pass, so
        #    this stays idempotent across multi-row style_axes calls, or by a
        #    caller that wants a custom label with a clipped value).
        # Everything else (bare traces, and signal lines whose %{y:.2f} silently
        # fails under x-unified) we (re)format via customdata below.
        _ht = getattr(tr, "hovertemplate", None)
        if _ht and ("%{x" in _ht or "%{customdata" in _ht):
            continue
        y = getattr(tr, "y", None)
        if y is None:
            continue
        cd = []
        for v in y:
            try:
                if v is None or (isinstance(v, float) and v != v):
                    cd.append("—")
                else:
                    cd.append(f"{float(v):.{precision}f}")
            except (TypeError, ValueError):
                cd.append("—")           # non-numeric (category/text) → dash
        try:
            tr.customdata = [[s] for s in cd]
        except (ValueError, TypeError):
            continue
        has_text = getattr(tr, "text", None) is not None
        name = getattr(tr, "name", None)
        if has_text:
            tr.hovertemplate = "%{customdata[0]} · %{text}<extra></extra>"
        elif name:
            tr.hovertemplate = "%{fullData.name}: %{customdata[0]}<extra></extra>"
        else:
            tr.hovertemplate = "%{customdata[0]}<extra></extra>"


def inject_css(theme: str = "dark") -> None:
    """Inject the Obsidian Quant Terminal CSS into the Streamlit app.

    Loads from external theme.css file for maintainability. theme.css defines
    the canonical DARK token block; when ``theme == "light"`` a second, small
    ``:root { ... }`` override (``LIGHT_TOKENS``) is appended after it — later
    source wins on identical specificity, so this repaints every component
    without touching a single component rule or the DOM. No runtime
    ``document.documentElement`` attribute toggling involved.

    Injects on every render — Streamlit deduplicates identical <style> blocks.
    """
    if CSS_PATH.exists():
        # Explicit UTF-8: theme.css embeds a Devanagari string (प्रज्ञम्) in a
        # content: "..." rule. Path.read_text() with no encoding= falls back to
        # the OS locale encoding, which on many Windows machines is cp1252 (not
        # UTF-8) — that raises UnicodeDecodeError on the non-ASCII bytes and
        # crashes the app on startup before anything else can render.
        css = CSS_PATH.read_text(encoding="utf-8")
    else:
        css = "/* theme.css not found */"

    if theme == "light":
        css += LIGHT_TOKENS

    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


# ── The run's two phases, and the percentage band each one owns ─────────────
# One table, read by the progress bar and matching the phase headings the
# console prints (`log.section(..., phase="PHASE 1")` in app.py). Without it
# the bar showed a percentage and a free-text label with no way to tell which
# phase of the run you were in, while the terminal beside it printed
# "PHASE 2: Covariance Curation" — the same run described two different ways.
#
# The bands are closed intervals and must not overlap, because the phase is
# DERIVED from the percentage: that keeps every call site free of a phase
# argument it would have to keep in sync by hand, but it means a call site's
# number decides which phase it is reported under. Phase 1 therefore ends at
# 20 (its "Phase 1 Complete" milestone) and Phase 2 opens at 21.
RUN_PHASES = (
    (1, 0, 20, "Data & Regime"),
    (2, 21, 100, "Covariance Curation"),
)


def _phase_of(pct: int) -> "tuple[int, int, str]":
    """Which phase a percentage falls in, as ``(n, total, name)``."""
    for n, lo, hi, name in RUN_PHASES:
        if lo <= pct <= hi:
            return n, len(RUN_PHASES), name
    return len(RUN_PHASES), len(RUN_PHASES), RUN_PHASES[-1][3]


def progress_bar(slot, pct: int, label: str, sub: str = "") -> None:
    """Render the pipeline's progress card into an ``st.empty()`` slot.

    The markup here and the rules in theme.css had drifted apart: the
    stylesheet targeted ``.progress-track > i`` while this emitted a ``<div>``,
    so the fill's width transition never applied and its colour had to be
    inlined. The inline style also carried ``box-shadow: 0 0 10px <colour>`` —
    a glow, on the one element every user watches for a minute on every run,
    in a design system whose stated rule is that nothing glows.

    Now: an ``<i>`` the stylesheet can actually reach, state carried by a
    class rather than an inlined colour, and width the only inline value
    (it is the datum).
    """
    is_complete = pct >= 100
    state = " complete" if is_complete else ""
    n, total, phase = _phase_of(pct)
    slot.markdown(
        f'<div class="progress-card{state}">'
        f'<div class="progress-phase">Phase {n} of {total}'
        f'<span class="pp-name">{html.escape(phase)}</span></div>'
        f'<div class="progress-label">'
        f'<span class="pulse-dot"></span>{html.escape(label)}'
        f'<span class="progress-pct">{int(pct)}%</span>'
        f'</div>'
        + (f'<div class="progress-sub">{html.escape(sub)}</div>' if sub else "")
        + f'<div class="progress-track"><i style="width:{int(pct)}%"></i></div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def apply_chart_theme(fig) -> None:
    """Apply the Obsidian Quant Terminal theme to a Plotly figure (mutates in place)."""
    fig.update_layout(**chart_layout())
    style_axes(fig)
