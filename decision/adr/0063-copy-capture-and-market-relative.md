# ADR-0063: Copy capture against a same-sizing benchmark, and market-relative copy returns

- Status: Accepted (definitions fixed before the outputs were computed; the user's addition to the ADR-0061/0062
  rerun, 2026-11-21)
- Date: 2026-11-21
- Phase: Phase 3 (follower replay), rerun before Phase 4
- Relates to: ADR-0029 (price chain), ADR-0030 (event model), ADR-0035/A0087 (participation and leader budgets),
  ADR-0036 (sweep anchor), ADR-0052 (frozen sizing), ADR-0055 (pricing failures), Phase 2 market exposure
  (`leader_assets.exposure`).

## Context
Copy returns alone do not show how much of the leader's opportunity the follower keeps, or what the copy earns beyond
holding BTC or ETH. Both are wanted per address, window and scenario, from the frozen replay rerun itself (no extra
run), point in time, byte-identical on rerun, holdout never computed.

## Decision
1. **Benchmark** (one per window, shared by the four scenarios): the frozen follower's own plan, i.e. the same
   decisions, frozen multiplier `min(allocation / E_ref, 1)`, common 1.5x address cap and no scale-up (the
   leader-notional budget, ADR-0037), executed with **no delay** (acknowledged at the leader fill's event time), at
   the **leader's own first-fill price** (no sweep anchor, no drift; a cap resize leg on another coin has no leader fill
   and uses the minute mark at the decision, as in the follower), with **no half-spread, impact or fee**, no
   minimum size, no participation budget (ADR-0050 point `none`), on **every coin** (also those without a usable
   reference price), valued with the same Hyperliquid daily marks and funding as the follower. Written beside the
   scenarios as `benchmark=unattainable_frozen/` (orders, daily ledger, funding); labelled unattainable.
2. **Gap decomposition.** PnL = final equity - allocation, from each ledger. gap = benchmark PnL - follower PnL. For
   each filled follower order with quantity q (signed) and leader first fill L, the replay's price chain splits
   exactly: q(fill - L) = q(anchor - L) [**sweep anchor**] + q(ref - mid_L) [**delay drift**: aggTrades move or drift
   parameter] + q(mid_L - anchor) + q(fill - ref) - impact [**half-spread**, removed from and re-added to the anchor]
   + |q| ref impact_bps / 10^4 [**impact**]; **fees** are the follower's fees; **funding difference** = benchmark
   funding - follower funding. The rest, R = (benchmark PnL - benchmark funding) - sum over follower fills of
   q (M_end - L), is the PnL at leader prices of the quantity the follower did not trade (M_end = the closing
   Hyperliquid mark both ledgers use). R is split per address and coin:
   - **uncopyable coin**: all of R on a coin whose intents are `failed_price_check`, `no_binance_mapping` or
     `insufficient_price_check` (the follower never trades it);
   - on other coins, R is allocated to **below minimum** (`below_minimum`, `below_minimum_at_ack`), **cap
     deferral** (`cap_headroom`, `missing_cap_mark`), **pricing failure** (the other ADR-0055 failures and
     `invalid_scenario_price`) and **participation clip** (the clipped part of a filled order) in proportion to the
     notional each missed (intended notional at the anchor; for a clip, |requested - submitted| x anchor). This is an
     allocation, not a counterfactual run: a missed order is often caught up later at another price, so the
     category split is approximate while the total is exact;
   - **other**: R on a coin with no missed notional (orders acknowledged after the window end, netting and timing
     differences between the two books).
   The twelve parts sum to the gap exactly (`closure` = gap - sum of parts, tested to 1e-4 USDC: floating-point accumulation over books of thousands of fills; the largest published is 6e-6 USDC). Each part is
   reported in USDC and as a share of the benchmark PnL.
3. **Capture ratio** = follower PnL / benchmark PnL. If |benchmark PnL| < **1% of the allocation (100 USDC)** the
   ratio and shares are **not meaningful** (`status = not_meaningful`, ratio null); a ledger with a missing mark or
   funding rate is `incomplete`. A negative benchmark keeps its sign (a ratio above 1 then means the follower lost
   less). The leader's own return over the window (`leader_return`, the Phase 2/3 series of the address) is reported
   beside the ratio and never divided into it.
4. **Daily series**: per address and day, the cumulative follower PnL, benchmark PnL and the leader's cumulative TWR
   (the same leader series as `leader_return`, written as `leader_series.parquet` in each window folder).
5. **Market-relative**, per copy series (each scenario and the benchmark): BTC and ETH buy-and-hold over the window
   (Hyperliquid daily marks at the window's first and last boundary; the marks start on 28 Jul 2025, so a training
   window that opens earlier is measured from its first boundary with a mark, recorded as `buy_hold_from`), and the copy's daily alpha and betas from one
   regression of its daily TWR on the BTC and ETH daily returns from the same marks, with Bartlett HAC standard
   errors (at most 7 lags), 95% intervals and the number of days, exactly as Phase 2's market exposure
   (`leader_assets.exposure`; fewer than 4 days gives no fit). Alpha is per day.
6. **Outputs** (`research/replay_frozen/`): `capture_summary.parquet`, `capture_daily.parquet`,
   `market_relative.parquet`, keyed by origin, window, scenario, trader, for every A/B address and all nine
   windows. Code: `replay_capture` (run at the end of `replay --frozen`, or `replay --capture` on an existing tree).

## Consequences
The results file reports, by test window, gate-passers and all A/B: median capture ratio, the gap breakdown and the
median alpha. The benchmark adds one zero-cost simulation per window to the frozen run. Tests:
`tests/test_alt_floor_receive.py` (the parts sum exactly to the gap on a constructed ledger and on the published
output; the threshold; the regression).
