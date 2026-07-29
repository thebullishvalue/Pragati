# Changelog

All notable changes to PRAGYAM (प्रज्ञम) — Portfolio Intelligence will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [11.0.0] - 2026-07-29

### 🧹 Shipping polish

- **Unreachable allocator code removed.** `nco.py` still carried the full Nested
  Clustered Optimization path and an Equal Risk Contribution path, neither of
  which any UI style could reach (`_NCO_STYLES` maps only to `HRP` and `EQUAL`).
  Both branches and the three functions only they called — `nco_weights`,
  `erc_weights`, `min_var_long_only` — are gone; `METHODS` is now
  `("HRP", "EQUAL")` and the module is 571 → 456 lines. Both were measured
  before removal: ERC achieves perfect risk balance (1.00x against HRP's
  1.5–1.7x) but matched HRP on return and Sharpe to within noise in both
  disjoint windows; NCO trailed HRP on return, Sharpe and drawdown in both.
- **Stale Portfolio Style tooltip rewritten.** It still described Swing / SIP /
  Nested Clustered and quoted the superseded nested-window figures
  ("drawdown -11.4% to -7.7%, Sharpe 0.80 to 1.42"). It now describes the two
  shipped styles and carries the corrected disjoint-window result: HRP gives up
  ~1%/yr for roughly a 20% cut in volatility and drawdown.

- **Analytics rebuilt for comprehension.** Four stacked six-card rows (24 cards)
  became a **Head to Head** table with the three books side by side, so
  comparison is a horizontal read instead of a scan across disconnected blocks
  holding figures in memory. Best value per row is marked. Only genuinely
  pairwise statistics (beta, alpha, correlation, tracking error, up/down
  capture) remain as cards, in a **Relationship to Benchmark** block — they have
  no meaning for a single book, which is why they cannot live in the table.
- **Every metric formula verified** against direct computation on a constructed
  series: beta, correlation, R², CAGR, tracking error, volatility, Sharpe,
  Sortino, CAPM alpha, information ratio, up/down capture, max drawdown, Calmar
  and VaR all match exactly. No arithmetic changes were needed.
- **Uniform descriptor captions.** Every chart and table now carries an
  explainer in the same voice, stating what the reader is looking at and how to
  read it. Previously only three of six had one — the Risk Profile heatmap and
  the regime history chart had none, and the performance chart lost its
  descriptor whenever the equal-weight shadow was absent.
- **Vertical rhythm normalised.** The rule is now one `_section_divider()` per
  section boundary in every tab (dividers == headers − 1). Analytics was mixing
  a divider for one boundary and a bare `section_gap()` for the next.
- **Scrollbar palette corrected.** The holdings-table iframe used
  `#8B7E6A` (slate-warm) while `ui/theme.css` uses `--ink-tertiary` (`#4B5563`),
  so that one scrollbar sat visibly lighter than every other surface. Both
  in-iframe tables now use the theme token, with a `#6B7280` hover.
- **Dead code removed; lint is clean at zero.** Unused imports across seven
  modules, unused locals, and a duplicate definition of
  `VERSION`/`PRODUCT_NAME`/`COMPANY` in `app.py` that shadowed the `ui.theme`
  import — two sources of truth for the version string, now one.
- **Shipping hygiene.** `VERSION` → `v11.0.0`; `optuna` dropped from
  dependencies (the calibration it served was removed in v11); `requirements.txt`
  and `pyproject.toml` rewritten to describe the covariance system;
  `.gitignore` added, excluding `__pycache__`, research `.pkl` artefacts and the
  local `core/` version archives.

### 🐛 Fixed — Analytics benchmark alignment & Portfolio table

- **The benchmark line started a bar late and was rebased there.** The chart
  built its benchmark series as `(1 + bench_returns).cumprod()`. `pct_change`
  drops the first bar, so that series began one bar after the portfolio AND
  normalized from day 1 instead of day 0 — silently discarding the opening day's
  move. It also made the chart disagree with the Benchmark Comparison cards,
  which read `bench_returns` directly and were correct.
  `build_return_series` now returns `bench_value`, the benchmark PRICE series
  trimmed to the portfolio's own first date, and the chart normalizes from it.
  Verified: all three traces now share a start date and index to exactly 100,
  and the benchmark reports its true window return (+4.5802%, where the old path
  reported +4.5455%).
- **Equal-Weight Comparison card row** added to Analytics, mirroring the
  benchmark row: equal-weight return, excess return, Sharpe edge, volatility
  edge, drawdown edge and correlation. The benchmark answers "did the book beat
  the market?"; this answers what the allocator is actually accountable for —
  "did it beat the same holdings in equal size?" Volatility Edge is coloured so
  LOWER is favourable, since trading return for lower volatility is the intended
  behaviour rather than a failure.
- **Portfolio table** reordered to Symbol / Units / Price / Weight % / Value
  first with the risk diagnostics after, and sorted by weight descending (was
  cluster-then-weight; the risk heatmap still groups by cluster, where the block
  structure is the point).
- **Table scrollbar** now matches the rest of the app. The holdings table renders
  through `components.html`, an isolated iframe that `ui/theme.css` never
  reaches, so it drew a default OS scrollbar beside every themed one. The global
  scrollbar rule is restated inside the iframe document.


### 💥 Removed — the conviction stack

Roughly **9,900 lines deleted**: `strategies.py` (95 engines), `intelligence.py`
(passport calibration), `portfolio.py` (conviction weighting), plus
`regime.compute_conviction_signals`, the Position Guide and Intelligence tabs,
and the Model Passport sidebar. Each removal followed a measurement:

- **Conviction blend** — no cross-sectional predictive power on this universe
  (IC ~0.00-0.04, sign unstable by horizon); a top-quintile-by-conviction book
  underperformed a bottom-quintile one.
- **95-strategy library** — mean pairwise return correlation **0.972**, an
  effective **1.03 independent strategies of 92**. Structural, not authorial:
  60 random long-only portfolios of the same ETFs measure 0.962 correlated even
  sharing no weights, because the assets are themselves 52% correlated.
- **Per-regime calibration** — never cleared its own significance gate.

### ✨ The system now

- **Two styles only: Risk Parity (HRP) and Equal Weight.** Both travel the
  identical pipeline — same eligibility filter, clustering diagnostics and risk
  decomposition — so any on-screen difference is the allocator and nothing else.
- **Five tabs** (was seven): Portfolio · Analytics · Regime · Broker Sync ·
  System. Regime is retained as context; nothing is conditioned on it.
- **New Portfolio tab** built on what actually drives the book: weight, risk
  share, the risk-minus-weight gap, volatility and independence
  (1 - |correlation to book|), grouped by cluster.
- **Risk Profile heatmap** — successor to the conviction heatmap. Same shape
  (one row per position, diverging colour) with the dimensions that matter, each
  column a within-column percentile oriented so green is calm and diversifying.
- **Risk Structure heatmap** — the correlation matrix quasi-diagonalized by
  cluster, with amber rules on the boundaries. The diagnostic for the method:
  crisp blocks mean real structure, a uniformly warm matrix means one bet.
- **Risk Concentration** replaces Avg Conviction in the header: heaviest
  holding's risk share against its equal share.

### 📊 Honest performance note

HRP **does not beat equal weight on return.** Across two genuinely disjoint
periods it loses 0.96% and 1.23%/yr, while cutting volatility ~20%
(13.81->11.28%, 12.97->10.38%) and drawdown (-6.89->-4.50%, -7.07->-6.15%).
It is a volatility-reduction overlay, not an alpha source.

An earlier nested-window test (2024+ was fully contained in 2023+) reported HRP
beating equal weight; that result does not survive a disjoint split. All figures
in this release use non-overlapping periods.

---

## [Unreleased]

### ✨ Added

- **Third portfolio style: Equal Weight.** The sidebar's Portfolio Style
  selector now offers `Equal Weight` alongside `Swing Trading` and
  `SIP Investment`. It builds an equally-weighted book — the user's selected
  number of positions, drawn from the user's selected universe, funded with
  the user's selected capital, each position receiving an identical
  `100 / N` share.
  - **Selection is unchanged.** All three styles pick the same names: top N by
    conviction, ties broken by value-area position. Style decides only how
    capital is spread across those names — Swing concentrates aggressively
    (`conviction ** 4.5`), SIP moderately (`conviction ** 2.5`), Equal Weight
    not at all.
  - `portfolio.compute_conviction_based_weights()` short-circuits the
    power-law dispersion transform when `investment_style == "Equal Weight"`.
    The check runs **before** `apply_dispersion` / `dispersion_params`, so a
    caller's dispersion arguments can never silently concentrate a book the
    user asked to be equally weighted.
  - The `1/N` weight always satisfies the effective per-position bounds by
    construction (`min_pos_pct_eff <= 1/n <= max_pos_pct_eff`), so the
    clip-renormalize loop is a no-op — a 5-position equal-weight book is a
    clean 20% × 5, with the existing "bounds relaxed" caption explaining the
    departure from the nominal 10% cap.
  - `run_context` now freezes `investment_style` and `capital`, and the System
    tab reports the style as **Portfolio Style** with a style-aware Weight
    Formula (`1 / N (equal weight)`) and Methodology card. As with the rest of
    `run_context`, this is the style the book was *actually* weighted under —
    browsing the sidebar after a run cannot relabel a curated portfolio.
- **Analytics: an equal-weight comparison trace.** On Swing Trading and SIP
  Investment runs, the Relative Performance chart now carries a **third line** —
  the same selected names, same anchor, same capital, split `1/N` — beside the
  portfolio and the benchmark. The benchmark answers *"did the book beat the
  market?"*; this answers *"did the conviction weighting earn its complexity?"*,
  a question the benchmark cannot address. A caption under the chart states the
  resulting edge (or drag) in one number.
  - The isolation is only valid because selection is identical across styles, so
    the shadow book differs from the real one in **weighting alone**. Its units
    are `floor((capital / N) / anchor_price)` — exactly what an Equal Weight run
    of the same scope would have produced, integer-lot flooring included, rather
    than an idealized fractional `1/N`.
  - `analytics.build_return_series()` takes an optional `alt_quantities` vector
    and values it off the **same** price panel, returning it as a sixth tuple
    element. Sharing one fetch is not just a cost saving: two independently
    built series could land on different start dates after the leading-row trim
    and would then be normalized from different bases — a silently wrong
    comparison. Returns an empty Series when not requested.
  - `charts.create_benchmark_comparison_chart()` accepts `alt_series` /
    `alt_label` and draws it dashed violet (portfolio amber solid, benchmark
    cyan dotted).
  - Suppressed on Equal Weight runs, where the trace would draw the portfolio
    line twice.
- **Value-Area (vap) removed from the conviction blend.** It measurably
  ANTI-predicted forward returns and was the specific cause of the composite
  score's sign instability. Four independent lines of evidence, all agreeing:
  - **Signal IC** negative at every horizon tested: 5d `-0.049`, 10d `-0.032`,
    21d `-0.080`, 42d `-0.004`.
  - **Quintile spread inverted** — a bottom-5-by-vap book beat a top-5-by-vap
    book by +12.5% CAGR.
  - **Blend IC improves at every horizon** once it is dropped, and the 21-day
    sign flip is repaired: the six-signal composite scored `-0.040` at 21d,
    the five-signal composite scores `+0.022`.
  - **Portfolio return improves in 4/4 (window x style) cells**, with Sharpe up
    in all four. Measured on the shipped code path, all 30 ETFs held:

    ```
                         2024+ window        2023+ window
    before (with vap)  SIP -1.01%  Swing -0.56%   SIP +0.52%  Swing +1.09%
    after  (no vap)    SIP +0.72%  Swing +1.51%   SIP +1.96%  Swing +2.73%
    ```

  The cause is structural, not statistical: `vap` is a mean-reversion construct
  ("price at a discount to accepted value = buy") applied to trending
  sector/thematic instruments, so its sign was wrong by construction rather
  than merely weak. Note the individual t-statistics remain below 2 (max
  +1.35) — the confidence here comes from four independent measurements
  agreeing plus a mechanism, not from any single test.
  - `DEFAULT_WEIGHTS` is now five signals at 1/5. `w_vap` no longer exists.
  - Calibration searches a 4-simplex (`_softmax4`); `PASSPORT_VERSION` →
    `v9-pragyam-conviction-novap`, invalidating v8 passports so every scope
    recalibrates without vap.
  - `vap` is still COMPUTED and surfaced as a diagnostic (`vap_value`), and the
    regime detector's `acceptance` factor still uses it — that is a different
    consumer and was not measured as harmful. `va_pos` (position inside the
    value area) is a distinct quantity and still breaks selection ties.
  - The VAP column is removed from the holdings table and the conviction
    heatmap; freed width returns to Symbol and Signal.
- **MA-alignment (`ma_signal`) removed from the conviction blend.** Same gate as
  vap, same verdict:
  - **Signal IC zero-to-negative at every horizon**: 5d `+0.005`, 10d `-0.018`,
    21d `-0.030`, 63d `-0.068`.
  - **Blend IC rises at every horizon** once it is dropped, and the 5-day
    composite reaches `+0.063` at **t = +2.55** — the only statistically
    significant reading produced anywhere in this testing.
  - **Portfolio improves 4/4 (window x style)** on the shipped code path:

    ```
                      2024+ window            2023+ window
    with vap + ma   SIP -1.01%  Swing -0.56%   SIP +0.52%  Swing +1.09%
    vap removed     SIP +0.72%  Swing +1.51%   SIP +1.96%  Swing +2.73%
    both removed    SIP +1.17%  Swing +2.03%   SIP +2.45%  Swing +3.47%
    ```

  `ma_signal` was a coarse count of five boolean MA conditions mapped onto
  `[-2, +2]`; whatever trend content it carried is already expressed by RSI at
  finer resolution, so on a 30-name cross-section it diluted the blend rather
  than adding to it. `ma_count` is retained as a displayed diagnostic.
  - The blend is now four signals — RSI, Oscillator, Z-Score,
    Strategy-Endorsement — at 1/4 each. Calibration searches a 3-simplex
    (`_softmax3`); `PASSPORT_VERSION` → `v10-pragyam-conviction-rsi-osc-z-strat`.
  - MA column removed from the holdings table and conviction heatmap.

  **Caveat carried forward:** vap and ma were both removed on the strength of
  the same ~3 years of ETF history. Each removal is independently supported
  (negative IC, blend IC improvement, 4/4 portfolio cells) and each has a
  mechanism, but sequential pruning guided by one dataset is itself a form of
  selection. Individual t-statistics remain below 2 (max +1.65).

- **New curation stack: covariance-based portfolio construction (`nco.py`).**
  Two new Portfolio Styles — **Risk Parity (HRP)** and **Nested Clustered (NCO)**
  — that select AND weight purely from the return covariance structure. They
  read no conviction score, no regime passport and no strategy endorsement; the
  95 strategies are not run at all and Phase 1.5 calibration is skipped.
  - **Why a second stack.** Grinold's Fundamental Law bounds excess return from
    FORECASTING at `IR = IC x sqrt(BR) x TC`, which on this universe
    (rho 0.517, ~1.9 effective bets, measured TC 0.88-0.92) is ~1%/yr. That
    bound does not constrain covariance-based allocation, which forecasts
    nothing — covariance is estimable from a few hundred observations in a way
    expected returns are not (López de Prado 2016, 2019).
  - **What it actually delivers — measured on the shipped module across two
    GENUINELY DISJOINT periods (an earlier nested-window test flattered it):**

    ```
                       CAGR    vs 1/N     Vol   Sharpe    MaxDD
    A 2023-12..2024-12
           Equal      27.30%   +0.00%  13.81%    1.83    -6.89%
           HRP        26.33%   -0.96%  11.28%    2.14    -4.50%
           NCO        26.22%   -1.08%  11.53%    2.09    -4.67%
    B 2025-01..2026-07
           Equal      12.31%   +0.00%  12.97%    0.96    -7.07%
           HRP        11.08%   -1.23%  10.38%    1.07    -6.15%
           NCO        10.74%   -1.57%  10.36%    1.04    -6.24%
    ```

    **Neither beats equal weight on return** — both lose ~1-1.6%/yr in BOTH
    periods. What is consistent is risk: HRP cuts volatility ~20% and improves
    drawdown and Sharpe in both windows. The accurate description is a
    volatility-reduction overlay costing ~1%/yr of return, not an alpha source.
    HRP beats NCO on CAGR, Sharpe and drawdown in both windows — prefer HRP.
  - An earlier nested-window test reported +0.13% to +0.78% excess return. Those
    windows were not independent (2024+ was 100% contained in 2023+), and the
    return edge does not survive a disjoint split. Research scripts showing
    +3.2% to +8.9% were weaker still — a 20/27-period sub-sample with no
    position cap.
  - Ward clustering on the correlation distance finds **K ~= 3** (silhouette
    ~0.28), independently matching the eigenvalue participation ratio of 2.95:
    three real risk clusters inside 30 tickers.
  - HRP is the recommended default — it inverts no matrix, produced the best
    drawdown, and holds every name. NCO uses inverse-variance within clusters
    and min-variance across them; min-variance *within* clusters was rejected
    because it returned corner solutions concentrating the book in 8 of 28
    names, defeating a 30-position mandate.
  - `_apply_cap` enforces the position cap by headroom-fill rather than
    clip-and-renormalize. The naive version does not converge — dividing by a
    post-clip sum below 1 pushes capped names straight back over the line
    (measured: 12.500070% against a 12.5% cap). No floor is applied at all: a
    floor would fight the method, since a redundant asset whose risk a cluster
    peer already carries *should* receive a small weight.
  - Runs in ~2s against ~27s for the conviction path when the panel is cached.

### 🐛 Fixed — live data pipeline

- **63% of the ETF universe was silently missing from every book.** Each
  symbol's indicator frame is indexed by its OWN print dates, and the snapshot
  loop skipped any symbol without a row on the exact snapshot date. A thinly
  traded instrument that simply didn't tick that day wasn't *stale* — it was
  **gone**: excluded from candidates, from conviction scoring, and from the
  portfolio. Measured on a live run for 2026-07-28, yfinance had not yet
  published that bar for 19 of 30 ETFs, so the app curated an **11-position**
  book from a 30-name universe and reported it as complete.
  - `generate_historical_data` now reindexes every symbol onto the shared
    trading calendar with a **bounded** forward fill (`ffill(limit=5)`). A short
    data gap carries the last known values across; anything that has genuinely
    stopped trading still drops out. The limit is what makes it safe — an
    unbounded fill would keep a delisted instrument in the book forever at a
    frozen price. Leading NaNs are untouched, so a symbol still cannot appear
    before its history begins.
  - Verified end to end: names per snapshot went from `min 11` to
    `min 30 / median 30 / max 30`, and a live run went from
    `Candidates: 11 / Positions: 11` to `Candidates: 30 / Positions: 30`.
  - **This also reconciles the app with the research harness.** Every backtest
    in this release was run on a 28-name panel built directly from yfinance,
    which bypassed this path — so the measured results described a
    well-diversified book while the live app was producing a far more
    concentrated one. They now describe the same portfolio.

### 🐛 Fixed — full-system audit

- **Strategy Endorsement was statistically noise on any universe above ~150
  symbols.** `BaseStrategy._allocate_portfolio` clips weights to a 1% floor,
  but strategies are handed the WHOLE universe (they filter nothing), so once
  the candidate count passes ~100 the average weight `1/N` falls below that
  floor, the floor binds for essentially every name, and the weight
  distribution collapses to a **single value** (measured: 500 candidates → 1
  distinct weight). Phase 2 ranked its top-quartile endorsement vote on that
  flattened column, so `nlargest` fell through to DataFrame row order — i.e.
  the vote was cast by *universe ordering*. Measured top-quartile overlap with
  the strategy's true ranking: **21.6% at N=500 against a 25% random-chance
  baseline.** That noise then entered conviction as a full sixth signal at a
  weight `calibrate()` is structurally forbidden from learning away.
  - `_allocate_portfolio` now emits `raw_weight_pct`, the strategy's own
    conviction *before* the bounds, and Phase 2 ranks the vote on it.
    Post-fix overlap: **100% at every N tested.**
  - A strategy whose ranking column is constant (e.g. the equal-weight fallback
    taken when its multipliers degenerate) now **abstains** instead of casting a
    row-order vote. Run logs report votes cast vs abstentions, and a run where
    nobody voted raises a warning rather than silently scoring on five signals.
- **The allocator's bounds loop always exited after one pass.** It tested
  `abs(sum - 1.0) < 1e-6` immediately after dividing by the sum — true by
  construction — so the final normalize left names outside the bounds it exists
  to enforce (measured: 14 of 40 below the 1% floor). It now converges on the
  bounds themselves, with the floor **dropped** (not tightened to `1/n`, which
  admits only the uniform solution) when `n * 1% > 1` makes it infeasible.
- **The Cash card was red exactly when the system was working.** Thresholds ran
  `<5% = danger`, but integer-lot flooring leaves ~0.5–2% residual by
  construction, so the correct outcome painted red on *every* run while a book
  leaving ≥15% of capital uninvested painted green. Inverted to match what the
  engine is for: full deployment is success, large idle cash is the defect.
- **Deployed / Cash were computed against the live sidebar capital.** Streamlit
  reruns on any widget change, so nudging the capital input repainted those
  cards against a number the book was never sized for — without recurating a
  position. Now read from the frozen `run_context`, same as every other scope
  value (the A12 class of bug).
- **Calibration and inference scored rows differently.** `_weighted_score` gave
  a missing signal a neutral 0 at *full weight*, while
  `regime.compute_conviction_signals` renormalizes weights over the signals that
  actually have data. Weights were learned under one composition rule and
  deployed under another — invisible for a universe-wide dead signal, wrong for
  partial coverage (e.g. short-history names missing `ma200`). The harvest now
  carries per-signal availability flags and `_weighted_score` renormalizes per
  row, matching inference exactly. `PASSPORT_VERSION` → `v8-pragyam-conviction-renorm`,
  which invalidates v7 passports so every scope recalibrates against the
  corrected objective.
- **Failed calibration re-paid its full cost on every run.** Failure is a common
  path (the significance gate needs ≥ `min_calibration_dates()` in-family dates,
  which many scopes lack), and it is the expensive one: `build_harvest` is an
  `iterrows()` loop over the whole estimation panel (~200k row iterations at 500
  symbols) that ran *before* `calibrate()` could fail-fast. A session-scoped
  negative cache keyed on `(scope, anchor date)` now short-circuits the repeat,
  and both Reset paths clear it so a deliberate reset always re-tries.
- **Passports overstated their own evidence.** `n_train_dates` reported the
  train partition's date *span* (~70) while the IR behind it is estimated from
  non-overlapping dates only (~7) — making a 5-parameter, 100-trial search look
  far better evidenced than it is. Passports now also record
  `n_train_ic_dates` / `n_val_ic_dates`, and the Intelligence card reports
  "N independent dates of M spanned".
- **The circuit breaker counted cumulative, not consecutive, failures.**
  `_on_success` reset the counter only in `HALF_OPEN`, and the breaker is a
  process-lifetime singleton, so five unrelated transients spread across hours
  of successful calls would trip it. A success in `CLOSED` now clears the run.
- **Re-scoring an already-scored portfolio was a silent no-op.**
  `compute_conviction_signals` merged only columns *absent* from the input, so
  the result tabs (which pass the curated book) ran a full scoring pass and
  discarded it, returning the stale values. Recomputed signals now replace the
  old ones.
- **`_clean_data` substituted another security's price level for a missing MA.**
  The fallback was the universe's *median price*, which in a per-symbol
  deviation term manufactures a huge fake premium/discount purely from the
  price-level gap (a ₹50 name against a ₹1,200 median reads as a 96%
  discount). Not a rare path: `ma200 weekly` needs ~4 years of weekly bars and
  the fetch window is at most ~2 years, so it is NA for every symbol on every
  run and all 65 of its references consumed this fallback. Now falls back to
  the symbol's own price — deviation exactly 0, the correct "no information"
  value.
- **`MIN_TOTAL_DATES = 20` was vestigial.** It had been dominated by
  `min_calibration_dates()` (142 at the defaults) since v10.0.1 — two numbers
  describing one requirement, one of them wrong. Removed; the requirement is
  now derived in one place.

---

## [10.0.1] - 2026-07-06

### 🐛 Fixed

- **Calibration was mathematically unreachable — it can now actually happen.**
  Phase 1.5 built its harvest from the 100-day `_REGIME_LOOKBACK_FILES`
  display panel: at most 90 harvest dates → 45 validation dates → at most
  **5** non-overlapping paired validation dates, while the paired
  significance gate requires **8** (`MIN_PAIRED_VAL_DATES`). Every
  calibration therefore burned 100 Optuna trials and then failed the gate,
  by construction — the display window and the statistical gate had never
  been reconciled. The fix sizes the data supply from the inference
  requirement instead of weakening any gate:
  - `intelligence.min_calibration_dates()` derives the in-family date count
    the gate implies (142 at the defaults: 8 paired dates × horizon 10 under
    a 50/50 split) — the documented data-supply contract.
  - New `app._CALIBRATION_LOOKBACK_FILES = 375` (~18 months): a dedicated,
    cached estimation panel fetched **only** when a scope actually needs
    calibrating (reused passports never pay for it). The regime card, chart,
    and curation stay on the fast 100-day panel. Regime-family labels for
    the harvest are computed over the estimation panel itself.
  - `calibrate()` now **fails fast on reachability** before the Optuna
    search: if the validation partition cannot possibly yield 8 paired
    dates, it reports the shortfall as the data requirement it is (with the
    family's actual date count and the required minimum) instead of burning
    100 trials and reporting what looked like sampling bad luck. All
    integrity rails (paired t-test, positive val-IR, shrinkage, embargo,
    non-overlapping stride) are unchanged — a regime family that genuinely
    lacks history still honestly refuses to calibrate.
- **Sidebar regime card (and passport card) froze on pre-run state after a
  completed analysis.** The sidebar paints before `_run_analysis` executes,
  and the only post-run repaint path was the calibration-success rerun —
  which never fired (see above). `main()` now issues one `st.rerun()` after
  the run flags are popped (cannot loop; the repaint pass is fully
  cache-hit), so the regime card, passport card, and result page always
  reflect the run that just finished.
- Beats-default failure message now quotes the actual gate threshold
  (`MIN_PAIRED_T_STAT = 1.895`); it previously said `t>=1.645`.
- **Manual Calibrate button (Intelligence tab) harvested from the 100-day run
  panel**, which the reachability gate makes a guaranteed fail — it now
  fetches the same `_CALIBRATION_LOOKBACK_FILES` estimation panel Phase 1.5
  uses (regime-conditioned over that panel), falling back to the run panel
  only if the estimation fetch comes up short.
- **Execution summary's "Total Duration" reported session age, not run
  time**: the per-session metrics tracker's `start_time` was never reset
  between runs. `_run_analysis` now resets the run clock alongside
  phases/errors/warnings.

- **F&O universe fetch always fell to the NIFTY 500 proxy**: NSE removed the
  "SECURITIES IN F&O" JSON index (hard 404), and the nsepython fallback used
  `nse_get_advances_declines()` — advance/decline breadth data, not the F&O
  list — silently mislabeled as F&O. The canonical **derivatives market-lots
  file** (`fo_mktlots.csv`, nsearchives host) is now the primary source, with
  structural validation of the payload (the legacy archives host answers
  HTTP 200 with a PDF error page) and a ≥100-symbol plausibility floor. The
  wrong-source nsepython fallback was removed; the NIFTY 500 last resort now
  labels itself honestly as a depth proxy.
- **Plot containers were clipped at the bottom with a phantom scrollbar**:
  `.stPlotlyChart` drew a real 1px border while Streamlit sizes that box to
  the exact figure height, so every chart overflowed by 2px — bottom corners
  cut square while the top rounded fine. The stroke is now an inset
  box-shadow ring (zero layout cost) and the inner wrapper clips rather than
  scrolls.
- **Section vertical rhythm was structurally broken**:
  `.section-hdr:first-child { margin-top: 0 }` matched EVERY header (each is
  the only child of its own stMarkdownContainer), silently zeroing the sp-10
  section break app-wide — real breaks degraded to Streamlit's ~1rem flex
  gap sitting next to 4–5rem divider/gap breaks (the "random dividers,
  uneven rhythm" symptom). The collapse now happens at the element-container
  level, so only a header that opens its tab panel/column sheds the margin.
  The divider-adjacency guard used `:has(> .section-divider)` — a
  direct-child combinator that can never match Streamlit's nested DOM —
  corrected to descendant form.

- **Analytics: chart legend and Benchmark card disagreed** — the Relative
  Performance chart's benchmark series was a bare `(1+r).cumprod()`, which
  starts at (1+r₁) on the first *return* date: the plotted line began one
  trading day after the portfolio line and the legend's `last/first − 1`
  silently dropped day 1's benchmark return, while the Benchmark Comparison
  card compounded the full series. The display series now anchors a 1.0 at
  the portfolio's base date, making the line, legend %, and card one number
  (verified to float precision).
- **Analytics: "CAGR" was not annualized for 20–251-day windows** — the
  annualization exponent was capped at 1 (`min(252/n_days, 1)`), so the
  "CAGR" subtext just repeated the raw period return under the wrong label,
  Calmar's numerator wasn't annualized, and the Info Ratio divided a
  period-return spread by an *annualized* tracking error (systematically
  understated for sub-year windows). CAGR/Alpha/Calmar/Info-Ratio now use
  true geometric annualization (252/n_days exponent) in both the headline
  and the aligned-alpha paths; the existing `cagr_meaningful` 60-day gate
  still keeps sub-quarter annualizations off the UI.

### 🎨 Improved

- **One rhythm doctrine — the section header owns the break** (documented on
  `_section_divider`). Removed the pre-header dividers (Portfolio →
  Conviction Signals, Position Guide table, Regime Score History, System
  Methodology, Analytics Returns) and pre-header `section_gap()`s (Analytics
  Benchmark Comparison, Risk Metrics), so every section boundary is the same
  sp-10 break. Dividers remain only at non-headered boundaries: KPI band →
  tab strip, heatmap → CSV action, tabs → footer, and the landing page's
  card blocks.
- **Single-bar, monotonic progress timeline.** All run milestones render into
  the one `progress_container` bar with strictly non-decreasing percentages,
  banded by phase: Phase 1 (Data & Regime) 0–20, Phase 1.5 (Intelligence)
  20–35 — every branch (ready/skipped/calibrated/failed) lands on 35 — and
  Phase 2 (Strategies & Curation) 35–100. Previously the bar jumped
  backwards (25 → 21 entering calibration, 28 → 25 entering Phase 2).
- **Milestones now state only what is true when shown, in Title Case.**
  "Running strategies · 95 strategies" (hardcoded, shown before discovery)
  became "Discovering Strategies" → "Running Strategies · {n} strategies";
  "Aggregating holdings" (shown *before* the strategy loop) was replaced by
  live in-loop updates ("Strategy {i}/{n} · {k} candidates", sweeping
  38→65); "Phase 1 Complete" now reports the detected regime and confidence
  instead of "Data acquisition ready".
- **Terminal log now mirrors the milestone trace.** Each phase logs a section
  with its load-bearing facts (panel size, detected regime, strategy /
  candidate / position counts), and the Phase 1.5 intelligence outcome —
  including the skip/fail *reason*, previously never printed — is logged via
  `_log_intel_outcome`. Execution-summary polish: phase timings print in
  Title Case (was raw `snake_case`), `total_execution` no longer double-lists
  inside its own breakdown, the backtest-only "Rebalances: 0" row is hidden
  on live runs, and Errors/Warnings section headers no longer render as
  "⚠️: Errors".

---

## [10.0.0] - 2026-07-02

### 🔍 Full-System Correctness & Rigor Audit

A comprehensive audit of every module (see `AUDIT_DIRECTIVES.md` for the full
finding-by-finding record) surfaced and resolved issues spanning calibration
integrity, data correctness, portfolio construction, analytics, infrastructure,
and UI truth-in-labeling. Every fix was empirically validated (statistical
false/true-positive rate tests, bit-identical numerical comparisons, or
end-to-end pipeline runs), not merely reviewed.

**Breaking / behavioral changes**

- `PASSPORT_VERSION` bumped to `v7-pragyam-conviction-strat`, auto-invalidating
  all prior passports (v4/v5/v6). Recalibration is required for every scope.
- Intelligence Mode will calibrate **less often** than before: a paired
  significance test now gates every passport save (see below), so a scope
  without a genuine, statistically-demonstrable edge over the 1/6×6 default
  will honestly report a skip reason instead of deploying a calibration.
- `portfolio.compute_conviction_based_weights`'s `dispersion_params` now
  expects a bare `gamma` float; a legacy `(boost, penalty)` tuple is still
  accepted for backward compatibility (only its first element is used).
- The dark/light theme toggle (never functional — see below) has been removed
  entirely; Obsidian Quant dark is now the only theme.

### ✨ Added

- **Strategy Endorsement** — a sixth conviction signal. Each of the 95
  strategies' own top-quartile picks (by its internal weighting) casts an
  "endorsement vote"; a symbol's cross-sectional percentile rank of votes
  becomes `strat_signal`. Previously every strategy's computed weights were
  discarded after aggregation and the union of "candidates" across 95
  strategies was ~= the entire data-valid universe, so the strategy layer
  contributed zero information to selection. `w_strat` cannot be calibrated
  historically (no historical vote data exists) and stays fixed at its
  default weight; the calibrator learns the other five signals on a 5-simplex
  scaled to fill the remaining mass.
- **Regime-family-conditioned calibration** — the calibration harvest is now
  filtered to dates that actually occurred in the target regime's FAMILY
  (Bull/Chop/Bear Mix) before any learning happens. Previously a passport
  keyed "BEAR" was estimated on the entire trailing window regardless of
  regime; the label distinguished only when a calibration happened to run.
- **Statistically-significant beats-default gate** — a passport is saved only
  when the learned weights beat the default baseline by a paired one-sample
  t-test on per-date IC differences (not a naive point-estimate IR
  comparison, which was found to accept ~40% of pure-noise calibrations at
  realistic validation-date counts). Deployed weights are shrunk toward the
  default in proportion to out-of-sample confidence.
- **Purged, non-overlapping IC estimation** — embargoes the train/val
  boundary and samples Information Coefficients on non-overlapping dates
  only, removing the serial-correlation bias that inflated the naive
  overlapping-window IR estimate.
- **Continuous power-law position dispersion** — `adjusted = conviction **
  gamma` replaces the median-step boost/penalty formula, which created up to
  a ~13x weight ratio between two candidates one conviction point apart.
- **Position-bound feasibility** — the 1%/10% bounds are automatically
  relaxed to the minimal value that restores feasibility when `num_positions`
  makes the nominal bounds mathematically unsatisfiable (e.g. 5 positions
  cannot all satisfy a 10% cap).
- **Frozen run context** — result tabs read the exact (universe, index,
  regime, mode, anchor date) a curated portfolio was produced under, not live
  sidebar state, so browsing the sidebar after a run can no longer re-score
  an already-curated portfolio under a different scope or resolve Analytics
  against the wrong benchmark.
- **Per-session execution metrics** — `metrics.get_metrics()` now returns a
  tracker scoped to `st.session_state` under Streamlit, so concurrent users
  no longer share/interleave phase timings, errors, and run IDs.
- Volume-dependent-signal coverage warning on the Portfolio tab, and an
  upfront warning when selecting the Currency universe (FX pairs report zero
  volume, so Oscillator/Z-Score/Value Area are structurally unavailable).
- `analytics.resolve_risk_free_rate` — resolves the risk-free rate to the
  benchmark's currency zone (6.5% INR vs 4.5% USD) instead of always using
  the INR rate.
- `AUDIT_DIRECTIVES.md` — the full audit record with literature citations.

### 🔧 Fixed

- **Benchmark resolution** for non-NIFTY universes (US Indexes, Commodities,
  Crypto, Currency) — the universe-level fallback map's keys never matched
  real universe strings, so every non-NIFTY book was silently benchmarked
  against NIFTY 50 in the Analytics tab.
- **Trading-day vs calendar-day warm-up** — indicator warm-up was measured in
  calendar days where trading days were required, leaving ~30% of every
  historical panel with NaN `ma200`/`ma90 weekly` still emitted as usable
  snapshots.
- **RSI warm-up mis-fill** — the "all-gains → RSI=100" backfill also stamped
  genuine warm-up NaN rows as a maximally-overbought 100.
- **Liquidity Oscillator warm-up contamination** — `fillna(1.0)` on the
  volume-moving-average and price-range guards fabricated large synthetic
  values instead of propagating NaN, contaminating roughly bars 20-40 of
  every symbol's oscillator.
- **Volume-profile NaN-bar crash** — a bar with valid close/volume but NaN
  high/low raised an uncaught `ValueError`, aborting the entire data-fetch
  phase for every symbol in the run, not just the offending one.
- **Volume-profile performance** — the per-window histogram build is now
  vectorized via a difference-array + cumsum (~4-5x faster, validated
  bit-identical to the original per-bar loop).
- Zero-signal symbols (absent from the live indicator snapshot) are excluded
  from top-N selection instead of competing at a neutral 50 conviction score.
- Weight-renormalization over available signals only, so a universe missing
  volume-dependent signals (FX, some futures) doesn't have its conviction
  range compressed toward 50 by structurally-dead weight slots.
- BBW volatility classification switched from absolute thresholds to
  percentile-within-window, so FX (tiny absolute BBW) and crypto (large
  absolute BBW) are read relative to their own normal range instead of being
  permanently mis-classified.
- CAGR/Alpha/Calmar cards are hidden (not silently mislabeled) when the
  return window is under 60 trading days — annualizing a sub-quarter window
  linearly extrapolates a few days of noise into a full year.
- Passport import now validates weights numerically and as a simplex
  (previously only checked key presence — `{"w_rsi": 37, ...}` imported
  without error) and rejects re-importing a defaults-shape export.
- India-index constituent fetching is now cached (`@st.cache_data`), fixing
  repeated NSE HTTP round-trips on every sidebar rerun.
- TLS verification restored by default on NSE archive requests (was
  unconditionally disabled); only relaxed as a last-resort retry on a genuine
  SSL failure.
- Removed the NIFTY 200 Wikipedia fallback that fabricated a "top 200" from
  an alphabetically-ordered constituent table.
- Single source of truth for the default ETF universe (`universe.ETF_UNIVERSE`;
  a divergent third hardcoded copy in `backdata.py` is gone).
- Broker Sync no longer zeroes a template's existing quantity when a matched
  holding was curated at 0 units — left untouched, like a non-match.
- Retry-with-backoff is now actually applied to the yfinance download (was
  imported but never wired in).
- Removed a 1.5s blocking `time.sleep` from the end of every successful run;
  strategy failures are now logged instead of silently swallowed.

### 🗑️ Removed

- Dead UI components with zero call sites: `render_theme_toggle` (ran inside
  a zero-height sandboxed iframe — was never clickable), `render_info_box`,
  `render_warning_box`, `render_chart_skeleton`, `render_collapsible_section`
  (+ `_close`), `render_export_button_row`, plus their corresponding dead CSS.
- The `[data-theme="light"]` CSS token/override blocks (unreachable given the
  removed toggle, and most components hard-code dark colors inline anyway).

---

## [9.3.0] - 2026-07-01

### 🎯 Regime Detector — Fixed Weights (No Calibration)

**Changed**

- The market-regime detector now uses **fixed 8-factor weights** (`regime.FACTOR_WEIGHTS`)
  — it is no longer calibrated. This adopts the legacy hardcoded-weighting design,
  retaining the current 8th `acceptance` (volume-profile) factor at a fixed weight.
  Only the **conviction blend** is calibrated (unchanged). Factor math, thresholds,
  and the regime hierarchy are identical to before.

**Removed**

- The entire regime-factor calibration layer: `intelligence.RegimeFactorPassport`,
  `calibrate_regime_factors`, `get_active_factor_weights`, `build_regime_harvest`,
  `_regime_ir`, `_softmaxN`, `regime_passport_filename`, `REGIME_PASSPORT_VERSION`,
  `REGIME_FACTOR_NAMES`, `DEFAULT_FACTOR_WEIGHTS`, `MIN_REGIME_DATES`;
  `regime.build_regime_factor_history` + `_resolve_factor_weights`; the Phase 1.4
  calibration step; and the `.passports/regimefactors_*.json` passport type.
- `MarketRegimeDetector.detect()` simplified — dropped the `(universe, index, mode)`
  parameters (regime is no longer scope/mode-dependent).

---

## [9.2.0] - 2026-07-01

### 📈 Analytics — Track the Curated Book vs Benchmark

**Added**

- **Analytics tab** — measures the LIVE curated portfolio's performance against a
  **universe-matched benchmark** (NIFTY 500 for nifty500, S&P 500 for us_sp500,
  NIFTY 50 default, etc.). Adapts the standalone SWING Analysis engine into a new
  `analytics.py` module. Core scope: a timeframe selector (1M…MAX / YTD), a
  normalized portfolio-vs-benchmark chart (indexed to 100), and metric-card rows
  for risk-adjusted (Period Return, CAGR, Alpha, Sharpe, Sortino, Calmar, Info
  Ratio), risk (Volatility, Max Drawdown, VaR/CVaR, Beta, Tracking Error) and
  benchmark comparison (Benchmark/Excess return, Up/Down capture, Correlation, R²).
- `analytics.py` — `resolve_benchmark`, `fetch_analysis_data`, `compute_metrics`
  (behaviour-preserving port of the SWING engine), and `build_return_series`
  (maps the curated `symbol`/`units` book → aligned return series). No CSV/Excel
  upload — reads `st.session_state.portfolio` directly.
- `charts.create_benchmark_comparison_chart` — the normalized comparison line
  chart, re-themed to Obsidian Quant (amber portfolio, dotted cyan benchmark).

**Changed**

- Result tabs are now seven: Portfolio · Position Guide · **Analytics** · Regime ·
  Intelligence · Broker Sync · System.
- Regime tab hero row rebuilt as one self-contained HTML flex block (factor scores
  left, regime badge right, flush height) — reliable centring/alignment. Regime
  factor bars render as center-anchored diverging bars (signed [-2,+2]); badge
  background dimmed to a soft state-hue tint.

---

## [9.1.0] - 2026-07-01

### 🔗 Broker Sync — Curate → Sync → Execute

**Added**

- **Broker Sync tab** — writes the live curated portfolio's per-symbol units into
  broker order-template JSONs (e.g. Kite `ETF.json` → `params.quantity`), producing
  import-ready order files. Reads `st.session_state.portfolio` directly (no CSV
  re-upload); the natural final step of the flow. Absorbs the former standalone
  "Broker JSON Sync" utility. Result tabs are now six: Portfolio · Position Guide ·
  Regime · Intelligence · Broker Sync · System.
- The tab mirrors the Intelligence tab's layout exactly — a balanced two-column
  block (status card + uploader | results table + downloads) plus a full-width
  "How the Sync Works" method card — and reuses its CSS, so it reads as native
  Obsidian Quant chrome with no new styling primitives.

**Changed**

- Regime tab factor list now renders all eight factors (incl. Acceptance and
  Correlation) as a single deterministic block, and the regime badge card
  auto-sizes to sit level with it — fixing the height misalignment that appeared
  once the 7th/8th factors were surfaced. Badge content scaled up to fill the card.

**Fixed**

- File-uploader dropzone rendered unstyled on Streamlit 1.5x because the theme
  targeted the legacy `stFileUploadDropzone` test-id; now targets both the legacy
  and current (`stFileUploaderDropzone`) ids with a light-touch re-skin that
  preserves the native compact layout (fixes the oversized box, duplicated button
  label, and enlarged delete icons).

---

## [9.0.0] - 2026-07-01

### 📊 Value-Area Position (VAP) — Volume Profile as a Fifth Conviction Signal

**Architectural Thesis**

PRAGYAM had no notion of *where volume actually traded* — its only value anchor was
the rolling mean baked into the oscillator z-score. v9.0.0 ports the measured volume-
profile geometry from the Inferred-Delta indicator (POC + value area, no order-flow
inference) into a cross-sectional EOD feature and threads it through the whole engine.

**Added**

- **`backdata.compute_volume_profile()`** — rolling proxy-binned volume profile per
  symbol → `poc latest`, `vap latest` (volatility-normalised premium/discount to
  value), `va_pos latest` (position inside the value area). Added to `COLUMN_ORDER`.
- **Fifth conviction signal `vap_signal`** ∈ [-2, +2], in both `intelligence._signals_from_row`
  and `regime.compute_conviction_signals`. `DEFAULT_WEIGHTS` is now an even 5-way
  `0.20 ×5`; the conviction calibrator optimises the **5-simplex** (`_softmax5`).
- **Learned regime-factor weights** — the 8 regime factors (incl. the new volume-
  profile **`acceptance`** factor) are no longer hardcoded. `intelligence.calibrate_regime_factors`
  learns them per `(universe, index)` by maximising the rank correlation of the
  composite regime score vs forward universe return, stored in a `RegimeFactorPassport`.
- **Structural selection** — `portfolio.compute_conviction_based_weights` breaks
  top-N conviction ties by value-area position (prefer discount to value).

**Changed**

- Regime detector is now **8-factor** (was 7); `MarketRegimeDetector.detect` accepts
  `(universe, selected_index, mode)` and resolves learned-or-default factor weights.
- UI swept end-to-end: Position Guide table gains a VAP column; conviction heatmap
  gains a Value Area row; Intelligence tab shows 5 active weights + the 5-simplex /
  regime-factor method copy; Regime tab shows the Acceptance factor with live
  (learned) weight percentages; System/landing cards, sidebar toggle help, README,
  and module docstrings updated.
- `PASSPORT_VERSION → v5-pragyam-conviction-vap` (auto-invalidates v4 passports).

**Fixed**

- `ui/theme.py` reads `theme.css` as UTF-8 (was crashing on Windows cp1252 default).

---

## [8.0.0] - 2026-05-11

### 🧠 Intelligence Mode — Per-(Universe, Index, Regime) Bayesian Calibration

**Architectural Thesis**

The four conviction signals (RSI, Oscillator, Z-Score, MA-alignment) were previously
combined with hard-coded weights `0.30 / 0.30 / 0.20 / 0.20`. v8.0.0 introduces a
self-tuning calibration layer that learns these four weights — on the 4-simplex
(sum-to-1, non-negative) — by maximising the cross-sectional Spearman Information
Ratio of the weighted conviction score against forward 10-day returns. Calibration
is keyed by the `(universe, selected_index, regime)` tuple, so a passport learned
on `India Indexes · NIFTY 500 · BEAR` is never silently applied to
`Commodities · GOLD · BEAR`.

### ✨ Added

**Intelligence Engine** (`intelligence.py`, new module — ~340 lines)
- 4-dim Bayesian search via Optuna TPE (seed=42 for reproducibility) over the
  conviction-weight simplex, parameterised through softmax of four unconstrained
  scalars
- Objective: mean per-date Spearman IC across all training dates, divided by IC
  std → Information Ratio (IR)
- Train / validation split by date (chronological, 70 / 30) — passports are saved
  only when validation IR is measurable on the held-out split
- Cross-sectional minimum (`MIN_XSECT = 5`) and total-dates minimum
  (`MIN_TOTAL_DATES = 20`) gates prevent calibrating on degenerate panels
- `IntelligencePassport(universe, selected_index, regime)` — JSON persistence at
  `.passports/passport_<universe>__<index>__<regime>.json`. Engine version
  (`v4-pragyam-conviction`) is recorded so future schema changes invalidate stale
  passports automatically
- `build_harvest(history_window, horizon)` — converts the Phase 1 indicator
  history into a flat (date, symbol) panel of signal values + forward returns
- Public API: `get_active_weights`, `calibrate`, `IntelligencePassport`,
  `passport_filename`, `DEFAULT_WEIGHTS`, `DEFAULT_HORIZON`, `PASSPORT_VERSION`

**Phase 1.5 — Auto-Calibration**
- New phase between Phase 1 (data fetching) and Phase 2 (curation): when
  `intelligence_mode` is on and no passport exists for the current
  `(universe, index, regime)` tuple, the engine harvests the historical window
  and runs 100 Optuna trials before Phase 2 begins
- Subsequent runs skip calibration and reuse the saved passport
- Outcome (calibrated / reused / skipped / failed + reason + IRs) is mirrored to
  `st.session_state.last_intel_outcome` for surface in the UI
- Progress bar reports trial-by-trial: best-IR-so-far, dates / observation counts,
  and the final train/val IR + passport-save confirmation

**Sidebar — Model Passport Card**
- New panel below the **Run Analysis** button (mirrors Sanket's sidebar layout):
  - Profile state (`Default` / `Calibrated` / `Default · Off`) with `metric-card`
    success / warning / neutral accents
  - **Trained on** (universe or index, trimmed to 22 chars)
  - **Regime** (Pragyam analogue of Sanket's `Depth`)
  - **Train IR** and **Val IR** with emerald / rose colour coding
  - **Updated** timestamp
- **↑ Import Profile** — `st.file_uploader` accepts a passport JSON (full payload
  or a bare `{"weights": {...}}` dict) and writes it through `IntelligencePassport.save`
- **↓ Export Profile** — `st.download_button` serialising the active passport
  (or a defaults-shape envelope when none exists). Filename:
  `pragyam_profile_<universe>__<index>__<regime>__<YYYYMMDD>.json`
- **↺ Reset to Defaults** — deletes the passport file for the current scope only
  (other scopes' passports are untouched)
- **Intelligence Mode toggle** — turns the calibration layer on/off; when off the
  card greys to neutral and conviction reverts to canonical defaults

**Intelligence Tab** (Result page)
- Calibration status card with full metrics (train IR · val IR · n_train_dates ·
  n_val_dates · horizon · n_trials · engine version)
- Manual **Calibrate** / **Reset** controls
- **Explicit fallback messaging**: when calibration was attempted but skipped or
  failed (e.g., insufficient history, sparse harvest, validation IR not
  measurable), the tab shows the specific reason instead of silently reverting to
  defaults

**Persistence**
- `.passports/` directory holds one JSON per `(universe, index, regime)` scope
- Passport schema includes calibrated weights, train / val IR, n dates, horizon,
  n_trials, ISO timestamp, engine version, and the scope tuple itself

### 🔧 Changed

**`regime.compute_conviction_signals(...)`**
- New signature: `compute_conviction_signals(portfolio, current_df, universe,
  selected_index, regime_name, mode)` — was `(portfolio, current_df, regime_name,
  mode)`
- Reads weights via `intelligence.get_active_weights(universe, selected_index,
  regime_name, mode)`. Standard mode returns canonical 0.30 / 0.30 / 0.20 / 0.20;
  Intelligence mode returns per-scope calibrated weights, falling back to defaults
  when no passport exists

**`portfolio.compute_conviction_based_weights(...)`**
- New `universe` and `selected_index` keyword parameters threaded through to
  `compute_conviction_signals`

**Phase 1.5 → automatic `st.rerun()` after first calibration**
- The sidebar Model Passport card paints before Phase 1.5 runs. To avoid the
  card showing stale "NOT CALIBRATED" pixels after a passport is saved mid-run,
  Phase 1.5 issues a single `st.rerun()` on first calibration. The script
  re-enters with `run_analysis` still True, the data cache is hit instantly,
  Phase 1.5 takes the reuse path, and Phase 2 curates the portfolio with the
  freshly-saved passport active. Adds ~2–4s of cache-hit work, eliminates the
  stale-sidebar surprise. Subsequent runs (passport already exists) skip the
  rerun entirely

**Conviction dispersion is no longer overridden by passports**
- Earlier prototypes attempted to "calibrate" the dispersion multipliers
  (`boost_mult`, `penalty_mult`) through the passport. Those values are a
  user-facing risk preference (SIP vs Swing concentration), not something to
  learn from forward returns; v8.0.0 keeps dispersion strictly style-aware

### 🚀 Performance

- Calibration runs in ~5–10s for typical lookbacks (100 days × 50–500 symbols ×
  100 Optuna trials), then never again for the same `(universe, index, regime)`
- Reuse-path Run Analysis is unchanged from v7.x (~20–40s)
- First-time-on-a-scope Run Analysis adds calibration time on top

### 📦 Dependencies

- **Added:** `optuna>=3.5.0` (Bayesian hyperparameter optimisation, TPE sampler)

### 🗂 Module Structure

- **New:** `intelligence.py` — calibration engine and passport persistence
- **New runtime artefact:** `.passports/` (one JSON per `(universe, index, regime)`)

### ⚠️ Migration Notes

- **Breaking signature change** for `regime.compute_conviction_signals` and
  `portfolio.compute_conviction_based_weights`. Callers must pass `universe` and
  `selected_index`. The default values (`"default"` / `None`) mean code that
  hasn't been updated still runs but will route all calibrations to a single
  generic scope. Update callers to thread the real universe context for proper
  per-universe isolation
- **Stale passports from earlier prototypes are auto-rejected.** The
  `IntelligencePassport.exists()` check verifies `engine_version ==
  PASSPORT_VERSION`, so any v3.0-sanket-fidelity or unkeyed
  `passport_<regime>.json` files are ignored at load time. Safe to delete

---

## [7.2.0] - 2026-04-13

### 🎨 "Terminal Glass" Design System — Complete Card & Table Overhaul

**Design Thesis**
- New "Terminal Glass" aesthetic: institutional trading terminal with glass morphism, semantic colors, and sophisticated micro-interactions
- Bold maximalism meets refined minimalism: layered transparency, diagonal accents, gradient sweeps, corner dots

### ✨ Added

**Position Card System (Position Guide Tab)**
- Replaced simple signal rows with full "Signal Ticket" cards
- Each card features:
  - Header: Symbol + conviction score + tier badge
  - Signals grid: 4-column responsive layout (RSI, Oscillator, Z-Score, MA)
  - Footer: Price + weight information
  - Progress bar: Animated conviction score visualization with shimmer effect
- Tier grouping system:
  - Strong Buy (≥65): Emerald gradient accent
  - Buy (50-64): Light emerald accent
  - Hold (35-49): Amber gradient accent
  - Caution (<35): Rose gradient accent
- Staggered entry animations (50ms delays up to 10 cards)
- Hover states: slide right 4px + enhanced shadow

**Custom Portfolio Table**
- Replaced styled DataFrame with custom HTML "Position Ticket" table
- Features:
  - Glass morphism container with gradient background
  - Sticky header with gradient background and amber accent border
  - Alternating row tints (odd/even)
  - Hover states: gradient sweep left-to-right + 3px left accent bar with glow
  - Semantic column classes (symbol, numeric, currency, percentage)
  - Tabular-nums for all numeric values
  - Right-aligned numeric and currency columns

**Conviction Progress Bars**
- New inline progress bar component
- Color variants by tier (emerald/amber/rose gradients)
- Animated shimmer overlay effect
- Rounded corners with glow shadows

### 🔧 Changed

**System Cards (Landing Page)**
- Complete visual redesign:
  - Background: Linear gradient (135deg) instead of flat glass
  - Accent: Diagonal line (25° rotation) replaces left border
  - Top bar: Gradient with glow effect
  - Icons: Rounded badge backgrounds with borders + hover rotation
- Enhanced hover states:
  - Lift: `translateY(-4px)`
  - Dual-layer shadows (12px + 4px offsets)
  - Icon rotation: `-5deg` with scale
  - Border color transitions
- Variant-specific enhancements:
  - Portfolio: Amber gold diagonal accent
  - Regime: Cyan diagonal accent
  - Strategies: Emerald diagonal accent

**Metric Cards**
- Corner dot accent system replaces left bars:
  - Top-right corner dot (6px circle)
  - Hover: dot scales 1.5x with glow
  - Hover: bottom gradient sweeps up (60% height)
- Staggered entry animations (50ms, 100ms, 150ms, 200ms)
- Enhanced color variants with gradient hover sweeps
- Bright color variants for values (emerald-bright, amber-bright, rose-bright)

**Section Headers**
- Icon badge system with gradient backgrounds:
  - Icon containers: 32x32px (up from 28px)
  - Gradient backgrounds (135deg angle)
  - Borders with 20% opacity accent colors
  - Box shadows for depth
- Animated accent bars:
  - Width animates from 0 to 40px
  - Gradient (color → glow)
  - 0.6s duration with 0.3s delay
- Enhanced hover states:
  - Icon scale 1.1 + rotate -5°
  - Shadow increases to 16px
  - SVG gets drop-shadow glow effect
- All color variants enhanced (cyan, emerald, rose, violet)

**Landing Prompt**
- Multi-layer background system:
  1. Linear gradient (glass → darker)
  2. Radial gradient (amber, 25% position)
  3. Radial gradient (cyan, 75% position)
- Animated gradient top border:
  - 3px height with 6s color loop
  - Colors: amber → cyan → emerald → violet → amber
  - Box shadow glow
- Subtle dot pattern background:
  - 30px grid of 1px dots
  - 3% white opacity at 50% overall opacity
- Enhanced typography and spacing
- Entry animation: FadeInUp (0.6s, 0.3s delay)

**DataFrames/Tables**
- Enhanced Streamlit DataFrame styling:
  - Gradient backgrounds with backdrop blur
  - Sticky header positioning
  - Amber accent borders (30% opacity)
  - Gradient sweep hover effects
  - Better padding and transitions

### 🎨 Color System

**New Color Variants**
- Added bright variants: `--amber-bright`, `--emerald-bright`, `--rose-bright`
- Better border opacity system (15-25% for subtle depth)
- Layered shadows: dual-shadow system on hover states
- Gradient consistency: 135deg angle throughout

**Semantic Color Usage**
- Success: Emerald (#34D399)
- Danger: Rose (#FB7185)
- Warning: Amber (#D4A853)
- Info: Cyan (#22D3EE)
- Neutral: Slate (#94A3B8)
- Accent: Violet (#A78BFA)

### 📊 Technical Details

**CSS Architecture**
- ~600 lines of new/enhanced CSS
- Total: ~3,500 lines (up from ~2,900)
- 15+ new components
- 12 animation keyframes total
- 30+ micro-interaction hover states

**Performance**
- Hardware-accelerated transforms
- Will-change declarations on animated elements
- Overflow containment where possible
- Respects `prefers-reduced-motion`

### 📄 Documentation

- Created `UI_UX_TERMINAL_GLASS.md` — comprehensive 350+ line design system documentation
- Detailed component specifications
- Visual structure diagrams
- Technical implementation details
- Design philosophy alignment

### 🎯 Impact

**Before → After**
- System cards: Flat glass → Diagonal gradient accents
- Metric cards: Left bars → Corner dot system
- Position guide: Simple rows → Full ticket cards with tier grouping
- Portfolio table: Styled DataFrame → Custom HTML table
- Section headers: Flat icons → Gradient badge system
- Landing prompt: Simple card → Multi-layer pattern background

---

## [7.1.0] - 2026-04-13

### 🎨 UI/UX Enhancements (frontend.md Implementation)

**Typography Overhaul**
- Changed primary display font from `Syne` to `Space Grotesk` (more distinctive geometric sans-serif)
- Added `Instrument Serif` for Devanagari accent text (प्रज्ञम) in header
- Changed data font from `JetBrains Mono` to `IBM Plex Mono` (better financial data legibility)
- Enhanced font loading with optimized @import statements

**Color & Theme Improvements**
- Added orange accent color (`#FB923C`) for additional visual variety
- Added SVG-based noise texture overlay for atmospheric depth
- Added subtle 50px grid pattern overlay (technical aesthetic)
- Enhanced radial gradient intensity for more dramatic backgrounds
- Added box-shadow glow effects to borders and underlines

**Motion & Animations**
- Added 10 custom keyframe animations:
  - `fadeInDown`, `fadeInUp`, `fadeIn` — entrance animations
  - `slideInLeft`, `slideInRight` — directional reveals
  - `pulse`, `shimmer`, `glow` — attention and loading effects
  - `gradientShift`, `countUp` — dynamic transitions
- Implemented staggered page load animations (50ms delays for sequential reveals)
- Added 15+ micro-interaction hover states:
  - Section header icons scale and rotate with glow
  - Signal rows slide with amber left border
  - System cards lift with enhanced shadows
  - Buttons have ripple effect from center
  - Tabs lift and change color on hover
  - Theme toggle scales with glow and icon rotation

**Spatial Composition**
- Added Hindi text (प्रज्ञम) to masthead with serif font (asymmetric design)
- Enhanced tagline with left decorative amber line
- Masthead underline increased to 2px with glow effect
- Added conviction progress bars to signal display rows
- Enhanced landing page system cards with additional specification details
- Added animated gradient border to landing prompt (amber → cyan → emerald)

**Visual Details**
- Enhanced glass morphism with improved hover states
- Added gradient border glows to chart containers
- Added gradient left borders to info/warning/interpretation cards
- Added shimmer effect overlay to progress bars
- Enhanced footer with gradient top border
- Improved table row hover states with subtle slide effect

**Data Visualization**
- Enhanced conviction heatmap:
  - Better colorbar positioning and styling (amber border, 18px thickness)
  - Added 1px cell gaps for clarity
  - Enhanced hover templates with subtitles
  - Added subtle grid lines (3% opacity)
- Enhanced regime history chart:
  - Increased line width to 2px with spline interpolation
  - Added circle markers with white borders
  - Added 5% opacity fill to zero for depth
  - Enhanced reference lines (thicker, better opacity)
  - Improved hover templates with date formatting

**Landing Page**
- Enhanced system card specifications:
  - Portfolio: Added "Dispersion: SIP + Swing modes"
  - Regime: Added factor details and "30-day rolling window"
  - Strategies: Added "95 parallel engines"
- Added shimmer animation to system card top borders
- Enhanced landing prompt with gradient animated border
- Added context subtitle to landing prompt

### 📁 Files Modified

**ui/theme.css**
- +569 lines (2180 → 2749 lines)
- New font imports (Space Grotesk, Instrument Serif, IBM Plex Mono)
- Enhanced design tokens (orange accent, --r-xl radius)
- 10 new keyframe animations
- Comprehensive component enhancements
- Responsive improvements

**ui/components.py**
- Enhanced `render_conviction_signal()` with progress bars
- Better visual hierarchy with labeled indicators
- Gradient backgrounds based on conviction levels

**app.py**
- Enhanced landing page system cards with additional specs
- Better landing prompt content with subtitle
- More compelling call-to-action

**charts.py**
- Enhanced heatmap styling with better colorbar
- Improved regime history chart with spline interpolation
- Better hover templates and grid styling
- Changed font references to IBM Plex Mono

### 📄 Documentation

- Created `UI_UX_ENHANCEMENTS.md` — comprehensive enhancement documentation
- Updated this CHANGELOG with detailed v7.1.0 entry

### 🎯 Design Philosophy

Following frontend.md guidelines:
- ✅ Bold aesthetic: Institutional terminal with refined maximalism
- ✅ Distinctive typography: 3 unique font families
- ✅ Cohesive colors: 7 accent colors with amber gold primary
- ✅ Intentional motion: 10 animations with staggered reveals
- ✅ Spatial composition: Asymmetric headers, layered effects
- ✅ Visual depth: Noise textures, grid patterns, glass morphism
- ✅ No generic AI aesthetics: Completely custom design
- ✅ Production-grade: All code functional and tested

---

## [7.0.5] - 2026-04-05

### 🧹 Removed

**Dead Code & Stale Files**
- Removed `docs/PROCESS_ARCHITECTURE.md` — described obsolete v6.0.0 4-phase architecture
- Removed `docs/STRATEGY_GUIDE.md` — described TOPSIS optimization removed in v7.0.0
- Removed 11 unused chart functions from `charts.py` (~1,000 lines):
  `create_equity_drawdown_chart`, `create_rolling_metrics_chart`, `create_correlation_heatmap`,
  `create_tier_sharpe_heatmap`, `create_risk_return_scatter`, `create_factor_radar`,
  `create_weight_evolution_chart`, `create_signal_heatmap`, `create_bar_chart`,
  `create_regime_factor_bars`, `create_portfolio_breakdown_chart`
- Removed dead functions from `circuit_breaker.py`:
  `google_sheets_circuit`, `get_yfinance_circuit()`, `protect_with_circuit()`
- Removed unused `import plotly.graph_objects as go` from `app.py`

### ✨ Added

**Enhanced Terminal Logging**
- Added main run header with analysis date, investment style, capital, positions, Run ID, and timestamp
- Added detailed checkpoints for every critical step in Phase 1 and Phase 2
- Per-run unique Run ID generated on each "Run Analysis" click (previously session-scoped)
- Signal Distribution card counts now based on raw conviction scores instead of fragile string parsing

**Position Guide Tab**
- Moved Position Guide section from Portfolio tab into dedicated tab
- Added signal distribution summary with conviction breakdown metrics

**Market Regime Auto-Detection**
- Sidebar regime display now updates automatically when analysis date changes (no "Run Analysis" required)

### 🔧 Changed

- Simplified section headers from `P1: PHASE 1: DATA FETCHING` → `Phase 1: Data Fetching` (eliminated redundancy)
- Removed redundant "Regime Analysis" text section from Regime tab
- Updated `metrics.py` counters to populate correctly (symbols, strategies, portfolios)
- Fixed `conviction_curation` phase timing (previously showed 0.00s)
- Removed redundant `EXECUTION METRICS` header from `metrics.print_summary()`
- Replaced deprecated `use_container_width=True` with `width='stretch'` (Streamlit compatibility)

### 🐛 Fixed

- Investment style selector default index always evaluated to 1 (SIP) — now correctly defaults to 0 (Swing Trading)
- Signal Distribution card counts misclassified positions due to emoji-prefixed signal strings

---

## [7.0.4] - 2026-04-02

### ✨ Added

**Style-Aware Conviction Dispersion**

Different dispersion profiles for SIP vs Swing Trading investment styles:

| Style | Boost | Penalty | Top Pick Advantage | Use Case |
|-------|-------|---------|-------------------|----------|
| **SIP Investment** | +125% (×2.25) | -50% (×0.50) | ~350% more weight | Long-term wealth building |
| **Swing Trading** | +225% (×3.25) | -75% (×0.25) | ~1200% more weight | Active trading, alpha capture |

**Formula:**
```python
# Auto-selected based on investment_style parameter

# SIP Mode (conservative concentration)
if score > median:
    adjusted = score × 2.25  # +125% boost
else:
    adjusted = score × 0.50  # -50% penalty

# Swing Mode (aggressive, 2σ more concentration)
if score > median:
    adjusted = score × 3.25  # +225% boost
else:
    adjusted = score × 0.25  # -75% penalty

weight = (adjusted / Σ all_adjusted) × 100
```

**Effect:**
- SIP: Strong concentration with moderate risk (~350% tilt to top picks)
- Swing: Maximum concentration in best ideas (~1200% tilt) for alpha capture
- Both maintain 30-position diversification with 1-10% bounds

### 🔧 Changed

- `portfolio.py::compute_conviction_based_weights()` now accepts `investment_style` parameter
- Dispersion auto-selects based on style when `dispersion_params=None`

---

## [7.0.3] - 2026-04-02

### 🔧 Changed

**Aggressive Conviction Dispersion**

Maximum concentration in high-conviction picks:
- Symbols with conviction **above median**: **+75% boost** (was +40%)
- Symbols with conviction **at/below median**: **-50% penalty** (was -30%)

**Formula:**
```python
median = median(all_conviction_scores)

if score > median:
    adjusted = score × 1.75  # +75% boost
else:
    adjusted = score × 0.50  # -50% penalty

weight = (adjusted / Σ all_adjusted) × 100
```

**Effect:**
- High-conviction symbols receive ~250% more weight vs linear allocation
- Aggressive concentration in best ideas while maintaining 30-position diversification
- Configurable via `dispersion_params` tuple in `portfolio.py`

---

## [7.0.2] - 2026-04-02

### 🔧 Changed

**Increased Conviction Dispersion**

Stronger concentration in high-conviction picks:
- Symbols with conviction **above median**: **+40% boost** (was +15%)
- Symbols with conviction **at/below median**: **-30% penalty** (was -10%)

**Formula:**
```python
median = median(all_conviction_scores)

if score > median:
    adjusted = score × 1.40  # +40% boost
else:
    adjusted = score × 0.70  # -30% penalty

weight = (adjusted / Σ all_adjusted) × 100
```

**Effect:**
- High-conviction symbols receive ~100% more weight vs linear allocation
- Strong concentration in best ideas while maintaining 30-position diversification
- Configurable via `dispersion_params` tuple in `portfolio.py`

---

## [7.0.1] - 2026-04-02

### ✨ Added

**Conviction Dispersion Weighting**

To concentrate capital in high-conviction picks:
- Symbols with conviction **above median**: **+15% boost**
- Symbols with conviction **at/below median**: **-10% penalty**

**Formula:**
```python
median = median(all_conviction_scores)

if score > median:
    adjusted = score × 1.15  # Boost
else:
    adjusted = score × 0.90  # Penalty

weight = (adjusted / Σ all_adjusted) × 100
```

**Effect:**
- High-conviction symbols receive ~28% more weight vs linear allocation
- Maintains diversification (still 30 positions)
- Preserves bounds (1% min, 10% max)

### 🔧 Changed

- `portfolio.py::compute_conviction_based_weights()` now has `apply_dispersion` parameter (default: `True`)
- Version bumped to 7.0.1 across all files

---

## [7.0.0] - 2026-04-02

### 🎯 Major Changes

**Complete system refactoring to implement pure conviction-based portfolio curation.**

### ✨ Added

- Pure conviction-based portfolio weighting formula: `weight_i = (conviction_score_i / Σ all_conviction_scores) × 100`
- No conviction threshold filter — all symbols eligible for portfolio inclusion
- Top 30 positions selected by conviction score (0-100 range)
- Position bounds: 1% minimum, 10% maximum per position
- 2-phase architecture (Data Fetching + Conviction-Based Curation)

### 🚀 Performance Improvements

- **6-10x faster execution**: 20-40 seconds vs 2-5 minutes (v6.0.0)
- **5x larger candidate pool**: ~200-400 symbols vs ~40-80 symbols
- **Maximum diversification**: All 80+ strategies run (no filtering)
- **30% code reduction**: ~3,500 lines vs ~5,000+ lines

### 🔧 Technical Changes

- Removed walk-forward evaluation (Phase 3)
- Removed strategy selection meta-weighting (Phase 2 old)
- Removed tier-based allocation logic
- Removed SLSQP portfolio optimization
- Unified conviction scoring: single source of truth in `regime.py::compute_conviction_signals()`
- Simplified `walk_forward.py`: 1,308 lines → 95 lines (-93%)
- Simplified `app.py`: 1,608 lines → 815 lines (-49%)

### ❌ Removed

- Walk-forward performance tracking
- Strategy selection competition
- Meta-weighting (6-method competition)
- Tier-based portfolio allocation
- Conviction threshold filter (>50)
- `strategy_selector.py` module
- `backup_refactor_20260328/` directory

### 📝 Documentation

- Updated `README.md` with v7.0.0 architecture
- Added `REFACTORING_SUMMARY.md` with migration guide
- Added `CHANGELOG.md` (this file)

### 🐛 Bug Fixes

- Fixed duplicate conviction scoring logic (now single source of truth)
- Removed dead code and unused imports
- Cleaned up session state variables

---

## [6.0.0] - Previous Version (Walk-Forward with Meta-Weighting)

### Features

- 4-phase architecture (Data Fetching, Strategy Selection, Walk-Forward Evaluation, Portfolio Curation)
- Strategy selection via meta-weighting competition
- Walk-forward performance evaluation
- SLSQP optimization for portfolio weights
- Tier-based allocation
- Conviction threshold filter (>50)

### Known Issues

- Slow execution (2-5 minutes)
- Complex architecture (4 phases)
- Duplicate conviction scoring logic
- Limited candidate pool (~40-80 symbols)

---

## Version History Summary

| Version | Date | Architecture | Execution Time | Key Feature |
|---------|------|--------------|----------------|-------------|
| 7.0.0 | 2026-04-02 | 2 phases | 20-40 sec | Conviction-based curation |
| 6.0.0 | Previous | 4 phases | 2-5 min | Walk-forward evaluation |

---

## Upcoming (Future Versions)

### Recommended Enhancements

- [ ] Optional walk-forward tracking (advanced mode)
- [ ] Conviction threshold slider (user-configurable)
- [ ] Strategy filtering UI (manual selection)
- [ ] Portfolio performance tracking over time
- [ ] Parallel strategy execution
- [ ] Improved caching for strategy outputs
- [ ] Conviction explainability breakdown

---

## Migration Notes

### From v6.0.0 to v7.0.0

**Breaking Changes:**
- Walk-forward evaluation removed — Tab 2 (Performance) now shows methodology explanation
- Strategy selection removed — All 80+ strategies run by default
- Meta-weighting removed — Simple conviction-based formula used instead

**Migration Path:**
If you need walk-forward evaluation:
1. Restore `walk_forward.py` from backup
2. Restore `strategy_selector.py` from backup
3. Re-add imports in `app.py`
4. Re-enable Phase 3 in `_run_analysis()` function

---

**PRAGYAM** — Portfolio Intelligence | @thebullishvalue
