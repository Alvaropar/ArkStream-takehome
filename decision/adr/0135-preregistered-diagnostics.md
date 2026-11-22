# ADR-0135: Pre-registered Phase 4 diagnostics

- Status: Accepted. Listed before any diagnostic was computed
- Date: 2026-11-22
- Phase: Phase 4 (selection), item 5c

## Decision
These inform the rule; only ADRs 0130-0132 select. The predictor uses data up to each development origin and the
outcome is the next test window's base copy return, across all A/B addresses unless stated. One CSV each in
`research/selection/diagnostics/` (`selection_diagnostics`).
1. **persistence**: Spearman rank correlation of the key (also the mean net per trip and the training copy return)
   with the test return, and the top-quintile hit rate (share above the median test return).
2. **feature_screen**: the same for median hold, maker share, orders per day, leverage p95, worst-case drawdown,
   leader alpha and beta to BTC, training capture ratio, median sweep (bps, filled training orders), parameterised
   notional share, and completed follower trips. All are reported, including nulls.
3. **gate_audit**: per Phase 2 and selection gate, plus all-gates and eligible, the pass / fail / unmeasured
   counts, mean and median test return, positives, and mean and median test max drawdown, per origin and pooled.
4. **attribution**: completed test-window follower trips, all A/B and eligible, by coin group (BTC/ETH/HYPE/SOL vs
   other), side, holding band, leader opening-order size (<10k, 10k-100k, 100k-1M, >=1M) and regime (closed on
   10-11 Oct; else the sign of BTC's return over the closing calendar week). Open-at-end PnL is not attributed.
5. **capture_drivers**: Spearman of the item-2 traits with the training capture ratio.
6. **alpha_beta**: test-window regressions for all A/B, eligible and selected: median R^2, share with R^2 > 0.5,
   median |beta|, and alphas whose interval excludes zero.
7. **crowding**: for the eligible pool, the share of held (day, coin) slots where at least two candidates hold the
   same direction; for the eligible pool and the basket, the effective number of independent bets,
   (sum lambda)^2 / sum lambda^2 of the training daily copy-return correlation matrix.
8. **tail**: each eligible candidate's training copy return on 10-11 Oct, its worst and best calendar week, and
   the share of its trip PnL from its best week.
9. **decay**: the top quintile by key at each origin, and its test returns in that and every later development
   window, against the all-A/B median.

## Consequences
Four windows make every signal a hypothesis. If persistence is about zero, the report says plainly that ranking on
past copy results does not predict.
