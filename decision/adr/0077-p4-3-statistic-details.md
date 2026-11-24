# ADR-0077: P4-3 details: day indexing, valid days, the beta fit, the clustered standard error, the static replica and the reported statistics

- Status: Accepted (placeholders); written before any beta, factor or statistic was computed. Items 1 and 3 amended by ADR-0082
- Date: 2026-11-23
- Phase: Phase 4 v2, step P4-3 (stage S4)
- Pins details ADRs 0070-0072 leave open. Protocol of ADR-0070 (decided after seeing results; written before
  computing; applied at all five origins; logged; never reverted on its outcome)

## Decision
1. **Days and the ledger.** Day t is a UTC calendar day and boundary t the midnight that starts it. The mark at a
   boundary is the Hyperliquid daily close the replay values its ledger at (`valuation_marks`).
   - `e_{c,t}` = position held through boundary t × mark(t); `G_t = Σ_c |e_{c,t}|`.
   - `r_{c,t}` = mark(t + 1) / mark(t) - 1.
   - `PnL_{c,t}` = cash of fills acknowledged on day t + funding posted on day t + `H_{c,t} - H_{c,t-1}`, with
     `H_{c,t}` = position held through boundary t + 1 × mark(t + 1). Summed over coins this is the replay's own
     daily equity change (`replay_book.value_book`).
   - Series: the tradable replay (ADR-0076), base scenario, training window at the origin, restricted to the common
     window `max(2025-09-08, origin - 12 weeks)` .. origin - 1 (ADR-0070).
2. **Valid days.** A day is valid when every coin held at its start or end has both marks, every funding payment
   posted that day is known, and (on a day with exposure) the three factor returns exist. An invalid day enters
   neither sum and is counted (`days_invalid`); it does not count as an exposed day for measurability. The replay's
   own `equity` stays null after an unknown payment; the per-day PnL here does not need earlier payments, so later
   days remain measurable.
3. **Flat days** (`G_t = 0`) enter neither sum (ADR-0070 item 4). Stated consequence: the PnL of a day that opens from
   flat, including that entry's costs, is not counted, while a day that starts exposed counts its exit costs. The
   PnL dropped this way is reported per address (`pnl_flat_days`).
4. **Factors.** BTC and ETH are those coins' daily returns. ALT is the equal-weight mean of the returns valid that
   day of the **pooled** tradable coins at the origin other than BTC and ETH (ADR-0076 item 4); null when none is
   valid. The same membership serves the beta fit and every window of that origin (training and test).
5. **Betas, fitted once per origin.** Fit date = the origin; returns of days origin - 90 .. origin - 1 (the last
   uses the mark at the origin's midnight, the mark the training ledger closes at; nothing later is read).
   - OLS with intercept of `r_c` on (BTC, ETH, ALT) over the days all four are valid; n = those days.
   - OLS only when n ≥ **10** and the design has full rank; otherwise the weight is 0.
   - Shrunk beta = `w β_OLS + (1 - w) median`, `w = n / (n + 30)`; the median is per factor over the coins with an
     OLS fit, excluding BTC and ETH.
   - **BTC and ETH carry identity betas** (1 on their own factor, 0 on the others): their regression on themselves
     is exact, so shrinking it would only add error.
   - A coin with no marks (any coin a leader holds, for `sel_direction`) takes the prior (n = 0).
6. **Primary statistic.** `α = Σ U_t / Σ G_t` over valid exposed days, reported ×10^4 (bps per day per USDC of
   gross). Measurable with ≥ 20 valid exposed days in ≥ 4 calendar weeks (Monday, UTC) with exposure (ADR-0070).
7. **Standard error (ADR-0072 item 1).** With `d_t = U_t - α G_t` and W weeks with exposure:
   `V = W / (W - 1) · Σ_w (Σ_{t∈w} d_t)² / (Σ G_t)²` (CR1 week clusters), and
   `s = √V · t_{0.80, W-1} / z_{0.80}`: the t-based one-sided 80% bound converted to a normal-equivalent standard
   error at the category level (0.80). Also reported: `se_cluster = √V` and `t_stat = α / s`.
8. **Static replica (ADR-0071 item 3).** Window mix `w_c = Σ_t e_{c,t} / Σ_c |Σ_t e_{c,t}|` over valid exposed days;
   replica exposure `G_t w_c`; replica residual `U^R_t = Σ_c G_t w_c (r_{c,t} - Σ_f β_{c,f} r_{f,t})` with no costs
   or funding; `α_static = Σ U^R / Σ G` over the valid exposed days where every replica coin has a return;
   `α_timing = α - α_static`, which therefore **includes costs and funding** (stated). Null when Σ_c |Σ_t e| = 0.
   Top-3 coin-day share = the three largest `U_{c,t}` / Σ U, when Σ U > 0.
9. **Reported set** (`statistics.parquet`):
   - information ratio = mean(U_t) / sd(U_t) over valid exposed days (daily, not annualised; scale-free);
   - utilisation over all valid window days: `ū = mean G_t / A`, p50 and p95 of `G_t / A` (A = 10,000);
   - residual return on sleeve NAV = Σ U / (A × valid window days); CT (total) = Σ PnL / Σ G on the α days;
   - from the replay's daily NAV over the window: raw return (null if any day is null), geometric mean daily,
     volatility, max drawdown, 95% expected shortfall (mean of the days at or below the 5th percentile);
   - copy trips closed inside the window (`selection.follower_trips`): count, expectancy (mean PnL), PnL / peak
     notional;
   - holdings-based copy betas `Σ_t Σ_c e_{c,t} β_{c,f} / Σ_t G_t` and the mean signed exposure by coin;
   - from the tradable tree: training capture and gap shares (ADR-0063), break-even delay, stress and optimistic
     training returns and stress drawdown, fill rate, max copy leverage, and the BTC/ETH regression cross-check
     (`market_relative`, training, base);
   - the hold band and its pooled training average, as the `sel_hold_band` diagnostic (ADR-0073 item 4).
10. **Outputs** under `research/selection_v2/origin=<date>/`: `statistics.parquet`, `betas.parquet`,
    `factors.parquet`, `residual_daily.parquet` (per address and day: PnL, U, G, validity), and `coins.parquet` /
    `coins_loo.parquet` / `leader_shares.parquet` from P4-2.
11. **Tests:** a planted post-origin mark changes no beta, factor or statistic; every beta has fit date = origin and
    last day = origin - 1; a synthetic one-coin book reproduces α exactly; α, s and α_static are unchanged when every
    position (and so every PnL) is scaled by 0.5.
