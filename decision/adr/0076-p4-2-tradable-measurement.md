# ADR-0076: P4-2 details: the all-priced rerun on the current universes, how T1-T5 are measured, per-wallet tradable sets, `not_tradable` in the replay

- Status: Accepted (placeholders); written before any T1-T5 value, tradable replay or leader share was computed
- Date: 2026-11-23
- Phase: Phase 4 v2, step P4-2 (stage S3)
- Pins details ADR-0073 leaves open. Relates to ADR-0066 (universes), ADR-0044 (price check), ADR-0052 (frozen
  sizing), ADR-A0140 (the executable filter it replaces), ADR-0061 (alt drift), ADR-0063 (benchmark and capture)
- **Decided after seeing results**, like ADRs 0070-0075: the protocol of ADR-0070 applies (written before computing,
  applied at all five origins, logged, never reverted on the address or return it produces)

## Context
ADR-0073 says the tradable universe is computed "from the unfiltered frozen replay's training window (all A/B)".
The existing trees cannot be used as they are: `research/replay_frozen/` and `research/replay_coinfilter/` were built
on the A/B universes **before ADR-0066** (300 / 327 / 330 / 358 / 354 addresses), while the current universes are
302 / 332 / 335 / 361 / 358 (5-6 addresses added and 1-3 removed per origin). ADR-0066 already requires the replays to
be rerun. ADR-0073 also leaves open how each of T1-T5 is read off a replay, what "full book" means for a cap book
that can only value priced coins, how the leave-one-wallet-out T4 is applied, and how `sel_tradable_share` and
`sel_direction` measure the leader's book.

## Decision
1. **Two new trees, both on the current A/B universes** (`research/leader/origin=*/evidence.parquet`, after
   ADRs 0066, 0067 and 0069):
   - `research/replay_allpriced/`: the frozen full stack (`*_sqrt_cap_part_ns_sweep_frozen`, all scenarios, the
     ADR-0063 benchmark, ADR-0055 stress coverage and capture) copying **every coin that passes the price check**,
     exactly as `research/replay_frozen/` was built (shared inputs prepared by `replay.run(simulate=False)`). It is the
     "unfiltered frozen replay" of ADR-0073 item 2 and the "all priced coins" copy of ADR-0073 item 5.
   - `research/replay_tradable/`: the same stack on the tradable sets (item 4), all A/B, nine windows.

   `research/replay_frozen/`, `research/replay_coinfilter/` and `research/selection/` stay untouched as the v1
   record. The `all_gates_pass` column the replay copies into its universes is informational: S2 is joined at the
   hand-off from the Phase 2 evidence (ADR-0079).
2. **Inputs to T2-T5:** the base scenario of `replay_allpriced`, training window at the origin (from the first fill
   day to the origin, the replay's own training window). As in ADR-A0140 item 2, the training window at an origin and
   the test window starting at it both copy that origin's set. No PnL or capture enters any condition.
3. **The five conditions,** per coin c at origin o:
   - **T1 priced:** price-check outcome `pass` at o (ADR-0044) **and** a drift source at o for the base delay
     (1,200 ms): BTC, ETH, HYPE and SOL (aggTrades); any other coin when `Parameters.lookup` at vintage o, period
     `development`, band `all`, base (conservative) returns a value for at least one liquidity bucket (the ADR-0061
     split-order estimate, else the ADR-0048 floor).
   - **T2 valued:** over the follower's held hours (one row per held hour in `funding_payments`), notional
     `|pos| x` the hour's oracle-proxy price (the lot's fill price when the proxy is missing). Valued = the funding
     payment is known **and** the coin has a Hyperliquid daily mark at the boundary closing that day. Share of
     valued notional-hours ≥ 0.95.
   - **T3 liquid:** over orders that reached the participation check (status not excluded and not `at_target`,
     `requested_qty` non-zero): fits when `|requested_qty| x decision_mark ≤ 0.005 x bar_volume_usdc` (the ADR-0035
     participation limit alone; the ADR-0037 leader-batch budget is a sizing rule, not liquidity). A missing volume
     or mark does not fit. Share of orders that fit ≥ 0.95.
   - **T4 affordable:** per filled order, `IS = half_bps + impact_bps + shortfall_bps + fee_bps` (fee_bps = fee /
     traded notional x 10^4; the sweep anchor is the leader's own price, not our cost, and is left out as ADR-0073
     lists). The coin's value is the **traded-notional-weighted median** (the lower weighted median) over all
     wallets' filled orders; it must be ≤ 25 bps.
   - **T5 wallets:** `1 / HHI` of filled traded notional across wallets ≥ 5.
   - A coin with no observation for a condition is **unmeasured and not tradable** (ADR-0068).
4. **Per-wallet sets (leave-one-wallet-out).** The published, pooled set is T1 ∧ T2 ∧ T3 ∧ T4 ∧ T5. For wallet w the
   set uses T4 recomputed **without w's own orders** (T1, T2, T3 and T5 pooled); a coin with no other wallet's fill is
   not tradable for w. The wallet's set decides its replay and its `sel_tradable_share`. The pooled set defines the
   ALT factor membership (ADR-0071). Every coin row in `coins.parquet` carries its coverage columns (observations,
   valued and unvalued notional-hours by reason, orders, wallets) and the per-wallet flips.
5. **The replay (`replay_tradable`).** The plan is built exactly as in the all-priced replay: `cap_legs` solves the
   1.5x scale over the leader's whole priced book (every coin passing the price check, the only coins with minute
   marks; this is the "full book", so the scale equals the all-priced scale by construction). Then every leg in a
   coin outside the wallet's set gets status **`not_tradable`**: it joins the excluded statuses (never submitted,
   never reserved, never filled) and is a measured policy outcome (ADR-0055). A coin failing the price check keeps
   its own status. The ADR-0063 benchmark never trades a non-tradable coin. Capture counts `not_tradable` as
   `uncopyable_coin`. Leader-side inputs (frozen-snapshot diagnosis, marks, funding, `E_ref`) keep the unfiltered
   price-check list.
   - A leader position in a coin without a price cannot be valued at decision time in either replay. It is outside
     both cap books, as before, and is bounded for eligible leaders by `sel_tradable_share`.
6. **`sel_tradable_share`** (≤ 10%): on the leader's own rebuilt book (fills known by the origin, core perps and
   HIP-3; spot is in neither numerator nor denominator, as ADR-0047), notional-hours over the training window =
   Σ over hour marks of `|pos| x` the leader's latest fill price in the coin (the gate-18 convention,
   `leader_returns`). The share in coins outside the wallet's set (HIP-3 is never tradable) must be ≤ 0.10. No
   notional-hours: unmeasured, fails.
7. **`sel_direction`** (`|Δβ|` ≤ 0.25): on the same notional-hours, per factor f, `β_f = Σ_h Σ_c e_{c,h} β_{c,f} /
   Σ_h Σ_c |e_{c,h}|` for the full book and for its tradable legs, with the ADR-0071 coin betas at the origin
   (ADR-0077; a coin without a fit takes the prior). It fails if `max_f |β_f(tradable) - β_f(full)| > 0.25`. No
   tradable notional: unmeasured, fails.
8. **Checks:** a non-tradable (wallet, coin) is never filled by the follower or the benchmark; the cap scale of every
   leg equals the all-priced tree's; the leave-one-wallet-out sets are reproduced from `coins.parquet`; two
   independent runs are byte-identical (POLARS_MAX_THREADS=8).

## Consequences
- Two full replays (about 17 minutes each) and one verification run.
- Config (`selection_v2`): `allpriced_dir`, `tradable_dir`, `out_dir`. Code: `replay_tradable.py`,
  `selection_v2_coins.py`, `replay_sensitivity.run_sensitivities(tradable=...)`, `replay_orders.quotes`
  (`not_tradable`), `replay_cap.cap_legs` unchanged (it already solves the scale on every passing coin).
- Tests: `tests/test_selection_v2.py` (T1-T5 on constructed tables, leave-one-wallet-out flip, `not_tradable`
  never filled or reserved, scale equality) and the data checks in item 8.
