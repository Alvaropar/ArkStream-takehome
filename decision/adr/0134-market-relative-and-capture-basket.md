# ADR-0134: Market-relative results and copy capture for the basket, sleeves and baselines

- Status: Accepted. Pre-registered before any test outcome of the rule
- Date: 2026-11-22
- Phase: Phase 4 (selection), items 5a and 5b; definitions of ADR-0162 reused

## Decision
1. **Market-relative** (`market_relative.csv`), per development test window and scenario:
   - **Basket and equal weight.** The daily return is the change in summed sleeve equity, regressed on BTC and ETH
     daily returns from the Hyperliquid daily marks with `replay_capture.market_relative` (Phase 2's regression,
     Bartlett HAC, 95% intervals, days).
   - **Each selected sleeve:** its row from `research/replay_frozen/market_relative.parquet`.
   - **Random-k medians:** their return beside BTC / ETH buy-and-hold.
   Each row reports the return over cash and over BTC and ETH.
2. **Capture** (`capture.csv`), from `capture_summary.parquet`:
   - **Per sleeve:** the ADR-0162 rows.
   - **Basket and equal weight:** total follower PnL / total benchmark PnL. The gap parts are summed, so they still
     close to the gap.
   - **Not meaningful** when |benchmark PnL| is below 1% of the group's allocation (100 USDC per sleeve).
   - **Leader-fee benchmark:** the benchmark PnL minus each leader's own fee rate (Phase 2 `fee_rate_bps`) on the
     benchmark's filled turnover, with capture against it beside.
3. **Medians and spread** (`capture_medians.csv`) of per-sleeve ratios, **separately where the benchmark won and
   lost**, for the selected sleeves and the eligible pool. The leader's own return is shown, never divided into a
   ratio.
4. **Daily cumulative series** (`capture_daily.csv`): follower PnL, benchmark PnL and the mean leader TWR, for the
   basket and the equal-weight pool.

## Consequences
Tests: a group's ratio and its closure, and the near-zero rule for a group. The holdout version comes at item 8.
