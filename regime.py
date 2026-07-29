"""
PRAGYAM — Market Regime Intelligence
══════════════════════════════════════════════════════════════════════════════

Market regime detection with multi-factor composite scoring.

This module is now DISPLAY AND CONTEXT ONLY. Conviction scoring lived here and
was removed: measured on the ETF universe the blend had no cross-sectional
predictive power (IC ~0.00-0.04, sign unstable across horizons), and the
portfolio is now curated from the return covariance structure (see nco.py).
The regime read is retained because it is genuinely informative about market
state, not because anything downstream is conditioned on it.

8-Factor Composite Scoring Architecture — blended with FIXED weights (see
FACTOR_WEIGHTS). Nothing in this system is calibrated any more — the weights
below are fixed by design, which is what makes the regime read reproducible.
  1. Momentum    (28%) — RSI trajectory + oscillator direction
  2. Trend       (23%) — Price/MA alignment + pct stocks above 200DMA
  3. Breadth     (14%) — Cross-sectional RSI/oscillator distribution
  4. Velocity    (14%) — dRSI/dt (first derivative) + d²RSI/dt² (acceleration)
  5. Extremes     (9%) — Z-score distribution: oversold / overbought crowding
  6. Volatility   (5%) — Bollinger Band Width regime (squeeze → panic)
  7. Correlation  (0%) — Herding proxy (diagnostic only)
  8. Acceptance   (7%) — Volume-profile value distribution (discount vs premium)

Regime Hierarchy (composite score, descending):
  STRONG_BULL (≥1.50) → BULL (≥1.00) → WEAK_BULL (≥0.50)
  → CHOP (≥0.10) → WEAK_BEAR (≥−0.10) → BEAR (≥−0.50) → CRISIS (<−0.50)

Author: @thebullishvalue
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime


# ══════════════════════════════════════════════════════════════════════════════
# DESIGN SYSTEM — REGIME COLOURS / ICONS / LABELS
# ══════════════════════════════════════════════════════════════════════════════

REGIME_COLORS: Dict[str, str] = {
    "STRONG_BULL": "#10b981",  # Emerald
    "BULL":        "#34d399",  # Light emerald
    "WEAK_BULL":   "#a3e635",  # Lime
    "CHOP":        "#f59e0b",  # Amber
    "WEAK_BEAR":   "#fb923c",  # Orange
    "BEAR":        "#ef4444",  # Red
    "CRISIS":      "#dc2626",  # Deep red
    "UNKNOWN":     "#6b7280",  # Gray
}

REGIME_ICONS: Dict[str, str] = {
    "STRONG_BULL": "rocket", "BULL": "trending-up", "WEAK_BULL": "arrow-up-right",
    "CHOP": "move-horizontal", "WEAK_BEAR": "arrow-down-right", "BEAR": "trending-down",
    "CRISIS": "alert-triangle", "UNKNOWN": "help-circle",
}

REGIME_DESCRIPTIONS: Dict[str, str] = {
    "STRONG_BULL": "Dominant uptrend with broad participation and accelerating momentum. Full momentum allocation.",
    "BULL":        "Healthy uptrend with positive breadth. Momentum and trend-following strategies favored.",
    "WEAK_BULL":   "Uptrend showing divergence or waning momentum. Selective momentum with defensive overlay.",
    "CHOP":        "Directionless market with no clear bias. Mean-reversion and relative-value strategies preferred.",
    "WEAK_BEAR":   "Downtrend developing with deteriorating breadth. Defensive positioning, reduce exposure.",
    "BEAR":        "Established downtrend with weak breadth and negative momentum. Primarily defensive.",
    "CRISIS":      "Severe market stress with panic volatility and capitulation breadth. Maximum capital preservation.",
    "UNKNOWN":     "Insufficient data to classify market regime reliably.",
}

REGIME_MIX_MAP: Dict[str, str] = {
    "STRONG_BULL": "Bull Market Mix", "BULL": "Bull Market Mix",
    "WEAK_BULL":   "Chop/Consolidate Mix", "CHOP": "Chop/Consolidate Mix",
    "WEAK_BEAR":   "Chop/Consolidate Mix", "BEAR": "Bear Market Mix",
    "CRISIS":      "Bear Market Mix", "UNKNOWN": "Chop/Consolidate Mix",
}

# Score normalisation helpers for factor bars in the UI
# Score range per factor: [-2, +2]
FACTOR_SCORE_RANGE = (-2.0, 2.0)

# Fixed 8-factor composite weights. The regime detector uses these directly — it
# is NOT calibrated. This mirrors the legacy
# hardcoded-weighting design, extended with the volume-profile `acceptance`
# factor at a small fixed weight. Correlation stays a 0-weight diagnostic.
FACTOR_WEIGHTS: Dict[str, float] = {
    "momentum": 0.28, "trend": 0.23, "breadth": 0.14, "velocity": 0.14,
    "extremes": 0.09, "volatility": 0.05, "correlation": 0.00, "acceptance": 0.07,
}


# ══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class FactorScores:
    """Breakdown of all 8 regime detection factors."""
    momentum:    Dict[str, Any] = field(default_factory=dict)
    trend:       Dict[str, Any] = field(default_factory=dict)
    breadth:     Dict[str, Any] = field(default_factory=dict)
    volatility:  Dict[str, Any] = field(default_factory=dict)
    extremes:    Dict[str, Any] = field(default_factory=dict)
    correlation: Dict[str, Any] = field(default_factory=dict)
    velocity:    Dict[str, Any] = field(default_factory=dict)
    # Acceptance: cross-sectional volume-profile read — how much of the universe
    # is trading at a DISCOUNT to its accepted value (vap). Contributes to the
    # composite at a FIXED weight (see FACTOR_WEIGHTS) like every other factor —
    # the regime detector is NOT calibrated.
    acceptance:  Dict[str, Any] = field(default_factory=dict)

    def _active_weights(self) -> Dict[str, float]:
        return FACTOR_WEIGHTS

    def composite_score(self) -> float:
        weights = self._active_weights()
        total = 0.0
        for name, w in weights.items():
            factor_dict = getattr(self, name, {})
            total += factor_dict.get("score", 0.0) * w
        return round(total, 3)

    def to_display_list(self) -> List[Tuple[str, float, str, float]]:
        """Return [(factor_name, score, label, weight)] for UI rendering."""
        weights = self._active_weights()
        mapping = {
            "Momentum":    (self.momentum, "strength", "momentum"),
            "Trend":       (self.trend, "quality", "trend"),
            "Breadth":     (self.breadth, "quality", "breadth"),
            "Velocity":    (self.velocity, "acceleration", "velocity"),
            "Extremes":    (self.extremes, "type", "extremes"),
            "Volatility":  (self.volatility, "regime", "volatility"),
            "Acceptance":  (self.acceptance, "state", "acceptance"),
            "Correlation": (self.correlation, "regime", "correlation"),
        }
        result = []
        for fname, (fdict, label_key, wkey) in mapping.items():
            result.append((
                fname,
                float(fdict.get("score", 0.0)),
                str(fdict.get(label_key, "—")),
                float(weights.get(wkey, 0.0)),
            ))
        return result


@dataclass
class RegimeResult:
    """Complete result of regime detection for a single date."""
    date: datetime
    regime: str
    mix_name: str
    confidence: float
    composite_score: float
    factors: FactorScores
    explanation: str

    # ── computed on creation ─────────────────────────────────────────────────
    color: str = field(init=False)
    icon: str = field(init=False)
    description: str = field(init=False)

    def __post_init__(self):
        self.color = REGIME_COLORS.get(self.regime, REGIME_COLORS["UNKNOWN"])
        self.icon  = REGIME_ICONS.get(self.regime, "help-circle")
        self.description = REGIME_DESCRIPTIONS.get(self.regime, "")

    def to_dict(self) -> Dict[str, Any]:
        """Serialisable dict for st.session_state / st.cache_data."""
        return {
            "date": self.date.isoformat(),
            "regime": self.regime,
            "mix_name": self.mix_name,
            "confidence": self.confidence,
            "composite_score": self.composite_score,
            "color": self.color,
            "icon": self.icon,
            "description": self.description,
            "explanation": self.explanation,
            "factors": {
                "momentum":    self.factors.momentum,
                "trend":       self.factors.trend,
                "breadth":     self.factors.breadth,
                "volatility":  self.factors.volatility,
                "extremes":    self.factors.extremes,
                "correlation": self.factors.correlation,
                "velocity":    self.factors.velocity,
                "acceptance":  self.factors.acceptance,
            },
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RegimeResult":
        """Reconstruct from to_dict() output."""
        factors = FactorScores(
            momentum=d["factors"]["momentum"],
            trend=d["factors"]["trend"],
            breadth=d["factors"]["breadth"],
            volatility=d["factors"]["volatility"],
            extremes=d["factors"]["extremes"],
            correlation=d["factors"]["correlation"],
            velocity=d["factors"]["velocity"],
            acceptance=d["factors"].get("acceptance", {}),
        )
        return cls(
            date=datetime.fromisoformat(d["date"]),
            regime=d["regime"],
            mix_name=d["mix_name"],
            confidence=d["confidence"],
            composite_score=d["composite_score"],
            factors=factors,
            explanation=d["explanation"],
        )


# ══════════════════════════════════════════════════════════════════════════════
# REGIME DETECTOR
# ══════════════════════════════════════════════════════════════════════════════

class MarketRegimeDetector:
    """
    Institutional-grade market regime detector.

    Uses an 8-factor composite score. Each factor contributes a signal score
    in the range [−2, +2]; the composite is the weighted sum of all factors.

    Reference architecture:
    - Momentum / Trend:  Jegadeesh & Titman (1993), Fama & French (1988)
    - Breadth:           Zweig Breadth Thrust (1986)
    - Velocity:          Hamilton (1989) regime-switching; first/second derivatives
    - Volatility:        Bollinger (1983) Band Width
    - Acceptance:        Steidlmayer Market Profile (value area / point of control)

    The eight factor weights are FIXED (regime.FACTOR_WEIGHTS) — the detector is
    not calibrated.
    """

    _THRESHOLDS: List[Tuple[str, float, float]] = [
        # (regime, min_score, base_confidence)
        ("STRONG_BULL", 1.50, 0.85),
        ("BULL",        1.00, 0.75),
        ("WEAK_BULL",   0.50, 0.65),
        ("CHOP",        0.10, 0.60),
        ("WEAK_BEAR",  -0.10, 0.65),
        ("BEAR",       -0.50, 0.75),
        ("CRISIS",     -9.99, 0.85),  # catch-all floor
    ]

    # ── Public API ──────────────────────────────────────────────────────────

    def detect(
        self,
        historical_data: List[Tuple[datetime, pd.DataFrame]],
        analysis_date: Optional[datetime] = None,
    ) -> RegimeResult:
        """
        Detect market regime from a list of (date, DataFrame) historical snapshots.

        The 8 factors are blended with FIXED weights (FACTOR_WEIGHTS) — the regime
        detector is not calibrated.

        Args:
            historical_data: Chronologically ordered list of (date, indicator_df) tuples.
                             Minimum 5 entries; 10 recommended for meaningful classification.
            analysis_date:   Override the result timestamp (defaults to last entry's date).

        Returns:
            RegimeResult with complete factor breakdown and composite classification.
        """
        if len(historical_data) < 5:
            date = analysis_date or datetime.now()
            return RegimeResult(
                date=date, regime="UNKNOWN", mix_name="Chop/Consolidate Mix",
                confidence=0.30, composite_score=0.0,
                factors=FactorScores(),
                explanation="Insufficient data (< 5 periods) for regime classification.",
            )

        window = historical_data[-min(10, len(historical_data)):]
        last_date, latest_df = window[-1]
        result_date = analysis_date or last_date

        factors = FactorScores(
            momentum=self._momentum(window),
            trend=self._trend(window),
            breadth=self._breadth(latest_df),
            volatility=self._volatility(window),
            extremes=self._extremes(latest_df),
            correlation=self._correlation(latest_df),
            velocity=self._velocity(window),
            acceptance=self._acceptance(latest_df),
        )

        score = factors.composite_score()
        regime, confidence = self._classify(score, factors)

        # ── Crisis override: panic vol + capitulation breadth ───────────────
        if (
            factors.volatility.get("regime") == "PANIC"
            and score < -0.5
            and factors.breadth.get("quality") == "CAPITULATION"
        ):
            regime, confidence = "CRISIS", 0.92

        explanation = self._explain(regime, confidence, factors, score)

        return RegimeResult(
            date=result_date,
            regime=regime,
            mix_name=REGIME_MIX_MAP.get(regime, "Chop/Consolidate Mix"),
            confidence=confidence,
            composite_score=score,
            factors=factors,
            explanation=explanation,
        )

    # ── Factor computation ───────────────────────────────────────────────────

    def _momentum(self, window: list) -> Dict[str, Any]:
        rsi_vals = [df["rsi latest"].mean() for _, df in window]
        osc_vals = [df["osc latest"].mean() for _, df in window]
        cur_rsi = rsi_vals[-1]
        rsi_trend = np.polyfit(range(len(rsi_vals)), rsi_vals, 1)[0]
        cur_osc = osc_vals[-1]
        osc_trend = np.polyfit(range(len(osc_vals)), osc_vals, 1)[0]

        if cur_rsi > 65 and rsi_trend > 0.5:    strength, score = "STRONG_BULLISH", 2.0
        elif cur_rsi > 55 and rsi_trend >= 0:    strength, score = "BULLISH", 1.0
        elif cur_rsi < 35 and rsi_trend < -0.5:  strength, score = "STRONG_BEARISH", -2.0
        elif cur_rsi < 45 and rsi_trend <= 0:    strength, score = "BEARISH", -1.0
        else:                                    strength, score = "NEUTRAL", 0.0

        return {
            "strength": strength, "score": score,
            "current_rsi": round(cur_rsi, 1), "rsi_trend": round(rsi_trend, 3),
            "current_osc": round(cur_osc, 1), "osc_trend": round(osc_trend, 3),
        }

    def _trend(self, window: list) -> Dict[str, Any]:
        above200 = [(df["price"] > df["ma200 latest"]).mean() for _, df in window]
        align90 = [(df["ma90 latest"] > df["ma200 latest"]).mean() for _, df in window]
        cur200   = above200[-1]
        cur_align = align90[-1]
        consistency = np.polyfit(range(len(above200)), above200, 1)[0]

        if cur200 > 0.75 and cur_align > 0.70 and consistency >= 0: quality, score = "STRONG_UPTREND", 2.0
        elif cur200 > 0.60 and cur_align > 0.55:                    quality, score = "UPTREND", 1.0
        elif cur200 < 0.30 and cur_align < 0.30 and consistency < 0:quality, score = "STRONG_DOWNTREND", -2.0
        elif cur200 < 0.45 and cur_align < 0.45:                    quality, score = "DOWNTREND", -1.0
        else:                                                        quality, score = "TRENDLESS", 0.0

        return {
            "quality": quality, "score": score,
            "above_200dma": round(cur200, 3),
            "ma_alignment": round(cur_align, 3),
            "trend_consistency": round(consistency, 4),
        }

    def _breadth(self, df: pd.DataFrame) -> Dict[str, Any]:
        rsi_bull = (df["rsi latest"] > 50).mean()
        osc_pos  = (df["osc latest"] > 0).mean()
        rsi_weak = (df["rsi latest"] < 40).mean()
        osc_os   = (df["osc latest"] < -50).mean()
        divergence = abs(rsi_bull - osc_pos)

        if rsi_bull > 0.70 and osc_pos > 0.60 and divergence < 0.15: quality, score = "STRONG_BROAD", 2.0
        elif rsi_bull > 0.55 and osc_pos > 0.45:                      quality, score = "HEALTHY", 1.0
        elif rsi_weak > 0.60 and osc_os > 0.50:                       quality, score = "CAPITULATION", -2.0
        elif rsi_weak > 0.45 and osc_os > 0.35:                       quality, score = "WEAK", -1.0
        elif divergence > 0.25:                                        quality, score = "DIVERGENT", -0.5
        else:                                                          quality, score = "MIXED", 0.0

        return {
            "quality": quality, "score": score,
            "rsi_bullish_pct": round(rsi_bull, 3),
            "osc_positive_pct": round(osc_pos, 3),
            "divergence": round(divergence, 3),
        }

    def _volatility(self, window: list) -> Dict[str, Any]:
        """Bollinger Band Width regime, classified by PERCENTILE within the
        trailing window rather than absolute magnitude.

        Raw BBW is scale- and asset-class-dependent: typical FX BBW is
        ~0.01-0.03 while crypto routinely runs ~0.2-0.6, so a fixed
        0.08/0.12/0.15 cutoff reads FX as permanently "SQUEEZE" and crypto as
        permanently "ELEVATED"/"PANIC" regardless of what's actually
        happening (see AUDIT_DIRECTIVES.md A13). Ranking the current reading
        against its own trailing distribution makes the classification
        relative to each asset class's own normal range instead. The
        window here is only ever up to 10 snapshots (see detect()), so this
        is a short-horizon percentile, not a long-run one — still strictly
        better than a hardcoded absolute threshold for non-equity universes.
        """
        bbw = [
            ((4.0 * df["dev20 latest"]) / (df["ma20 latest"] + 1e-6)).mean()
            for _, df in window
        ]
        cur_bbw = bbw[-1]
        trend = np.polyfit(range(len(bbw)), bbw, 1)[0]

        bbw_arr = np.asarray(bbw, dtype=float)
        pct = float((bbw_arr <= cur_bbw).mean()) if len(bbw_arr) > 1 else 0.5

        if pct <= 0.2 and trend < 0:   regime, score = "SQUEEZE", 0.5
        elif pct >= 0.9 and trend > 0:  regime, score = "PANIC", -1.0
        elif pct >= 0.75:               regime, score = "ELEVATED", -0.5
        else:                           regime, score = "NORMAL", 0.0

        return {
            "regime": regime, "score": score,
            "current_bbw": round(cur_bbw, 4),
            "vol_trend": round(trend, 5),
            "bbw_percentile": round(pct, 3),
        }

    def _extremes(self, df: pd.DataFrame) -> Dict[str, Any]:
        os_pct = (df["zscore latest"] < -2.0).mean()
        ob_pct = (df["zscore latest"] > 2.0).mean()

        if os_pct > 0.40:   ext, score = "DEEPLY_OVERSOLD", 1.5
        elif ob_pct > 0.40: ext, score = "DEEPLY_OVERBOUGHT", -1.5
        elif os_pct > 0.20: ext, score = "OVERSOLD", 0.75
        elif ob_pct > 0.20: ext, score = "OVERBOUGHT", -0.75
        else:               ext, score = "NORMAL", 0.0

        return {
            "type": ext, "score": score,
            "oversold_pct": round(os_pct, 3),
            "overbought_pct": round(ob_pct, 3),
        }

    def _correlation(self, df: pd.DataFrame) -> Dict[str, Any]:
        rsi_med = df["rsi latest"].median()
        osc_med = df["osc latest"].median()
        rsi_dir = abs((df["rsi latest"] > rsi_med).mean() - 0.5) * 2.0
        osc_dir = abs((df["osc latest"] > osc_med).mean() - 0.5) * 2.0
        agree = (
            ((df["rsi latest"] < 40) & (df["osc latest"] < -30)).mean() +
            ((df["rsi latest"] > 60) & (df["osc latest"] > 30)).mean()
        )
        disp = (df["rsi latest"].std() / 50 + df["osc latest"].std() / 100) / 2
        raw = np.clip((rsi_dir + osc_dir) / 2 * (1.0 - disp) + agree * 0.3, 0, 1)

        if raw > 0.7:   regime, score = "HIGH_CORRELATION", -0.5
        elif raw < 0.4: regime, score = "LOW_CORRELATION", 0.5
        else:           regime, score = "NORMAL", 0.0

        return {
            "regime": regime, "score": score,
            "correlation_score": round(raw, 3),
        }

    def _acceptance(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Cross-sectional volume-profile acceptance (vap distribution).

        Reads where the universe sits relative to its accepted value: a market
        where many names trade at a DISCOUNT to value (vap > 0) is primed for
        mean reversion; one where most sit at a PREMIUM (vap < 0) is extended.
        Scored on [-2, +2] like the other factors, and contributes to the
        composite at its FIXED weight in FACTOR_WEIGHTS. Degrades to NEUTRAL when
        the volume-profile column is absent (e.g. legacy snapshots)."""
        if "vap latest" not in df.columns:
            return {"state": "UNKNOWN", "score": 0.0, "discount_pct": 0.0, "premium_pct": 0.0}
        vap = pd.to_numeric(df["vap latest"], errors="coerce").dropna()
        if vap.empty:
            return {"state": "UNKNOWN", "score": 0.0, "discount_pct": 0.0, "premium_pct": 0.0}

        discount = float((vap > 1.0).mean())   # below value area = mean-rev room
        premium  = float((vap < -1.0).mean())  # above value area = extended

        if discount > 0.50:    state, score = "DEEP_DISCOUNT", 1.5
        elif discount > 0.30:  state, score = "DISCOUNT", 0.75
        elif premium > 0.50:   state, score = "RICH", -1.5
        elif premium > 0.30:   state, score = "PREMIUM", -0.75
        else:                  state, score = "FAIR_VALUE", 0.0

        return {
            "state": state, "score": score,
            "discount_pct": round(discount, 3),
            "premium_pct": round(premium, 3),
        }

    def _velocity(self, window: list) -> Dict[str, Any]:
        if len(window) < 5:
            return {"acceleration": "UNKNOWN", "score": 0.0, "avg_velocity": 0.0, "acceleration_value": 0.0}

        rsis = np.array([w[1]["rsi latest"].mean() for w in window[-5:]])
        vel = np.diff(rsis)
        avg_vel = np.mean(vel)
        accel_vals = np.diff(vel)
        cur_accel = accel_vals[-1] if len(accel_vals) else 0.0

        if avg_vel > 1.5 and cur_accel > 0:         label, score = "ACCELERATING_UP", 1.5
        elif avg_vel > 1.0 and cur_accel >= 0:       label, score = "RISING_FAST", 1.0
        elif avg_vel > 0.5:                          label, score = "RISING", 0.5
        elif avg_vel < -1.5 and cur_accel < 0:       label, score = "ACCELERATING_DOWN", -1.5
        elif avg_vel < -1.0 and cur_accel <= 0:      label, score = "FALLING_FAST", -1.0
        elif avg_vel < -0.5:                         label, score = "FALLING", -0.5
        elif abs(avg_vel) < 0.5 and cur_accel > 0.5: label, score = "COILING_UP", 0.3
        elif abs(avg_vel) < 0.5 and cur_accel < -0.5:label, score = "COILING_DOWN", -0.3
        else:                                        label, score = "STABLE", 0.0

        return {
            "acceleration": label, "score": score,
            "avg_velocity": round(avg_vel, 3),
            "acceleration_value": round(cur_accel, 3),
        }

    # ── Classification ───────────────────────────────────────────────────────

    def _classify(self, score: float, factors: FactorScores) -> Tuple[str, float]:
        breadth_div = factors.breadth.get("quality") == "DIVERGENT"
        for regime, threshold, base_conf in self._THRESHOLDS:
            if score >= threshold:
                conf = base_conf * 0.75 if breadth_div else base_conf
                return regime, round(conf, 2)
        return "CRISIS", 0.85

    # ── Explanation ──────────────────────────────────────────────────────────

    def _explain(self, regime: str, confidence: float, factors: FactorScores, score: float) -> str:
        from ui.components import get_icon
        icon_key = REGIME_ICONS.get(regime, "help-circle")
        icon_svg = get_icon(icon_key, size=20, stroke_width=2)

        lines = [
            f'<div style="display:flex; align-items:center; gap:8px; margin-bottom:12px;">{icon_svg} <span style="font-size: 1.3rem; font-weight:700;">{regime.replace("_", " ")}</span></div>',
            f"**Composite Score:** {score:+.2f} | **Confidence:** {confidence:.0%}",
            "",
            f"**Market Assessment:** {REGIME_DESCRIPTIONS.get(regime, '')}",
            "",
            "**Factor Breakdown:**",
        ]

        display = factors.to_display_list()
        for fname, fscore, flabel, fweight in display:
            if fscore > 0.2:
                dir_icon = get_icon("arrow-up", size=12, stroke_width=2.5)
            elif fscore < -0.2:
                dir_icon = get_icon("arrow-down", size=12, stroke_width=2.5)
            else:
                dir_icon = "—"
            
            lines.append(f'<div style="display:flex; align-items:center; gap:6px; font-size: 0.95rem; margin-bottom:4px;">'
                         f'• <strong>{fname}</strong> ({fweight:.0%} weight): {flabel} '
                         f'<span style="color:{"var(--emerald)" if fscore > 0.2 else ("var(--rose)" if fscore < -0.2 else "var(--ink-tertiary)")}; display:inline-flex; align-items:center;">'
                         f'{dir_icon}</span> <strong>{fscore:+.1f}</strong></div>')

        if factors.breadth.get("quality") == "DIVERGENT":
            lines += ["", "⚠️ **Alert:** Breadth divergence detected — narrow leadership may not persist."]

        if factors.volatility.get("regime") == "SQUEEZE":
            lines += ["", "📌 **Note:** Volatility squeeze detected — potential directional breakout imminent."]

        if factors.extremes.get("type") in ("DEEPLY_OVERSOLD", "OVERSOLD"):
            lines += ["", "🔍 **Opportunity:** Statistical oversold conditions present — mean-reversion potential elevated."]

        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# REGIME HISTORY SERIES
# ══════════════════════════════════════════════════════════════════════════════

def get_regime_history_series(
    historical_data: List[Tuple[datetime, pd.DataFrame]],
    window_size: int = 10,
    step: int = 1,
) -> List[RegimeResult]:
    """
    Compute a rolling time series of regime readings over a historical window.

    Slides a look-back window of `window_size` days forward by `step` days,
    yielding one RegimeResult per position.  Enables regime transition charts.

    Args:
        historical_data: Chronologically ordered (date, DataFrame) tuples.
        window_size:     Days per detection window (default 10).
        step:            Slide step between successive windows (default 1).

    Returns:
        List of RegimeResult objects, one per window position.
    """
    detector = MarketRegimeDetector()
    results: List[RegimeResult] = []

    if len(historical_data) < window_size:
        return results

    for i in range(window_size, len(historical_data) + 1, step):
        window = historical_data[max(0, i - window_size): i]
        analysis_date, _ = historical_data[i - 1]
        try:
            result = detector.detect(window, analysis_date=analysis_date)
            results.append(result)
        except Exception:
            continue

    return results


__all__ = [
    "MarketRegimeDetector",
    "RegimeResult",
    "FactorScores",
    "REGIME_COLORS",
    "REGIME_ICONS",
    "REGIME_DESCRIPTIONS",
    "REGIME_MIX_MAP",
    "get_regime_history_series",
]
