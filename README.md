# PRAGYAM (प्रज्ञम) — Portfolio Intelligence

**Version:** 11.0.0
**Author:** @thebullishvalue
**License:** Proprietary (See LICENSE file)

Covariance-based portfolio curation over a fixed ETF universe. The book is built
to **spread risk**, not to predict returns.

---

## What changed in v11, and why

v11 removed the conviction scoring engine, the 95-strategy library and the
per-regime weight calibration — roughly 9,900 lines. Not a stylistic clean-up;
each was removed after measurement.

| Removed | Measured finding |
|---|---|
| Conviction blend | No cross-sectional predictive power on this universe: IC ~0.00–0.04, sign unstable across horizons. A top-quintile-by-conviction book *underperformed* a bottom-quintile one. |
| 95-strategy library | Mean pairwise return correlation **0.972** — an effective **1.03 independent strategies out of 92**. Ninety-five engines producing one opinion. |
| Per-regime calibration | Could not clear its own significance gate on realistic panels. |

The strategy redundancy is **structural, not authorial**. Long-only baskets of
assets that are themselves 52% correlated cannot decorrelate: 60 random
long-only portfolios of the same ETFs measure 0.962 correlated even when their
weights share nothing. No rewrite of the strategies would have fixed it.

### The reasoning behind the replacement

Grinold's Fundamental Law bounds excess return from *forecasting* at
`IR = IC × √BR × TC`. On 30 ETFs at ρ = 0.517 — only ~1.9 effective independent
bets, with measured transfer coefficient 0.88–0.92 — that ceiling is about
**1%/yr**, however good the signal.

Covariance-based allocation is not bound by it, because it forecasts nothing.
Covariance is estimable from a few hundred observations in a way expected
returns are not (López de Prado 2016, 2019).

### What it actually delivers — stated plainly

Measured on the shipped module across two **genuinely disjoint** periods:

```
                   CAGR    vs 1/N     Vol   Sharpe    MaxDD
A 2023-12..2024-12
       Equal      27.30%   +0.00%  13.81%    1.83    -6.89%
       HRP        26.33%   -0.96%  11.28%    2.14    -4.50%
B 2025-01..2026-07
       Equal      12.31%   +0.00%  12.97%    0.96    -7.07%
       HRP        11.08%   -1.23%  10.38%    1.07    -6.15%
```

**HRP does not beat equal weight on return — it loses ~1%/yr in both periods.**
What it consistently delivers is a ~20% cut in volatility and drawdown, and a
higher Sharpe. It is a volatility-reduction overlay. **Do not size it expecting
excess return.**

If you are maximising absolute return without leverage, Equal Weight is the
correct choice and ships as a first-class style.

> Note on method: an earlier nested-window test (2024+ fully contained in 2023+)
> reported HRP *beating* equal weight. That does not survive a disjoint split.
> Every figure above uses non-overlapping periods.

---

## Architecture

```
app.py          Streamlit UI + 2-phase pipeline
nco.py          HRP / Equal Weight curation — selection AND weighting
regime.py       8-factor regime detection (context only)
backdata.py     yfinance fetch + indicator panel
analytics.py    portfolio-vs-benchmark metrics
charts.py       Plotly builders
universe.py     universe resolution
research/       offline evidence harness (not imported by the app)
```

**Pipeline:** Phase 1 data + regime → Phase 2 covariance curation. About 2s once
the panel is cached.

---

## Usage

```bash
streamlit run app.py
```

**Sidebar:** Analysis Date · Portfolio Style · Universe · Capital · Positions.

**Styles**

| Style | Behaviour |
|---|---|
| **Risk Parity (HRP)** | Clusters holdings by correlation distance, then splits capital by recursive bisection on cluster variance. Inverts no matrix. |
| **Equal Weight** | Identical `1/N` per holding. Travels the same pipeline, so the clustering diagnostics still render — you see the risk it leaves unbalanced. |

**Result tabs**

| Tab | Contents |
|---|---|
| **Portfolio** | Holdings with weight, risk share, volatility, independence · risk-profile heatmap · cluster correlation matrix |
| **Analytics** | Three-way head-to-head table (book / equal weight / benchmark) plus benchmark-relationship statistics, over an indexed performance chart |
| **Regime** | 8-factor composite + history. Context only — nothing is conditioned on it |
| **Broker Sync** | Writes curated units into broker order-template JSONs |
| **System** | Configuration, methodology, execution metrics |

---

## Reading the Portfolio tab

**Risk Share vs Weight** is the number the method exists to control. Weight is
share of capital; Risk Share is share of portfolio *variance*. Equal capital
does not mean equal risk, and the `Risk − Wt` column is that gap. It is the one
column where lower is better, so the colour follows the outcome rather than the
sign: green is a holding carrying *less* variance than its capital share, red is
one carrying more.

**Risk Concentration** (header card) is the heaviest holding's risk share
against its equal share. 1.0× is perfect balance; above ~3× means one holding
dominates the book's variance.

**Risk Structure** is the correlation matrix reordered by cluster. Crisp blocks
along the diagonal mean the clustering found real structure. A uniformly warm
matrix means the universe is effectively a single bet — which no allocator can
fix.

## Reading the Analytics tab

The **Head to Head** table puts all three books side by side, so comparison is a
horizontal read. Green marks the best value per row. Max Drawdown, VaR and CVaR
are negative, so higher (least negative) wins.

**Equal Weight** there is the same holdings split 1/N — the like-for-like test
of the allocator, with market exposure held constant. **Benchmark** is the
market. Expect the book to lead on volatility and drawdown while trailing on
return: that is the trade, not a fault.

**Relationship to Benchmark** holds the statistics that only exist for a pairing
— beta, alpha, correlation, tracking error, up/down capture — which is why they
cannot sit in the table above.

---

## Known limits

- **Breadth is the binding constraint.** 30 ETFs at ρ = 0.517 are ~1.9
  independent bets. Uncorrelated exposures (debt, gold, international) would
  raise the ceiling by more than any allocator change.
- **~3 years of usable history.** Most of these ETFs are too young for more, so
  every t-statistic in testing sits below 2. Treat all figures as directional.
- **Long-only.** Dollar-neutral construction measured a 28.6× breadth gain and a
  ~6× ceiling increase — but needs borrow that Indian thematic ETFs are unlikely
  to have.

See `research/README.md` for the harness that reproduces every claim here.
