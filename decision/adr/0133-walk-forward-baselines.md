# ADR-0133: Development walk-forward, baselines and the reported statistics

- Status: Accepted. Pre-registered before any test outcome of the rule
- Date: 2026-11-22
- Phase: Phase 4 (selection)

## Decision
1. At each development origin (8 Oct, 22 Oct, 5 Nov, 19 Nov) the rule uses data up to the origin
   (ADRs 0130-0132). The basket is scored on the next 14-day test window of the frozen replay in base, optimistic
   and stress (ADR-0122 coverage), funded, on 10,000 USDC per sleeve.
2. **Baselines on the same window**, 1,000 seeded draws each (seed `[20251203, origin ordinal, 1 or 2]`):
   - **matched random-k**: k addresses from the eligible pool (after all gates);
   - **all-A/B random-k**: k addresses from every A/B address;
   - **equal weight** of the eligible pool;
   - **cash** (0).
   Addresses with no complete test return are left out of a pool and counted.
3. **Win** = basket base return above the median of the matched random-k draws. A window with k = 0 is reported as
   "no basket" and is not a win. Where the pool has only one possible pick (pool = basket), the ranking is not
   testable: the percentile is 0.5 and it is not a win. Every window reports the pool size and the number of
   possible picks.
4. **Robust summaries.** Mean, median and 20% trimmed mean of sleeves and draws. Each window is also reported
   without 10-11 Oct: the daily TWR is chained over the other days, and the random-k comparison is repeated on that
   return.
5. **Stress.** Each sleeve's ADR-0122 stress check (measured, not exhausted, max drawdown >= -10%), and the
   basket's: all sleeves measured, and the drawdown of the summed sleeve equity >= -10%.
6. **Exact intervals** (reported, not tests): Clopper-Pearson on wins out of windows, two-sided 95% and one-sided
   lower, for matched random-k, all-A/B random-k, beating equal weight, and matched random-k without the crash.
   **MinTRL** (Bailey and Lopez de Prado), alpha 0.05, SR* = 0, on the basket's daily base returns over the
   development test windows, at the observed Sharpe and at half of it. It is labelled optimistic because those
   windows were used for tuning. The holdout version comes at item 8. Standard library only
   (`selection_stats`).

## Consequences
Outputs: `research/selection/walk_forward.csv`, `baselines.csv`, `intervals.csv`, `min_trl.csv`. With eligible pools
of 2-5 (ADR-0130), the matched test is weak, and the all-A/B random-k is the main test of whether the gates add
value.
