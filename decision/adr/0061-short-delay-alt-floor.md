# ADR-0061: Bound base alt drift below 300 s by a point-in-time Hyperliquid split-order estimate

- Status: Accepted. **Decided after seeing results**: the measured-latency rerun (ADR-0058, ADR-0059) showed that
  the ADR-0048 floor sets the base cost of parameterised coins (3.68 bps per side at 1.2 s exactly as at 10 s). The
  rule below was fixed in this file on 2026-11-21 **before any replay result under it was computed**; only the
  evidence counts in "Consequences" were filled in afterwards, from the estimate itself.
- Date: 2026-11-21
- Phase: Phase 3 (follower replay), rerun before Phase 4
- Amends: ADR-0048 (base drift of parameterised coins below 300 s). Unchanged: ADR-0029 (direct coins, >= 300 s),
  ADR-0053 (stress), ADR-0060 (severe), ADR-0004 (point in time), ADR-0046 (forced fills excluded).

## Context
ADR-0048 bounds the base drift of a parameterised coin (no aggTrades) below 300 s by max(four-coin proxy, the coin's
own 300 s estimate, 0). At a 1.2 s copy delay this charges five minutes of the coin's drift. A short-delay
measurement exists on the venue itself: `research/split_orders/` (`scripts/split_orders.py`) reads the Hyperliquid
price at a known time after a leader order from the same leader's next taker order on the same coin and side. On
other coins the next order's best fill is about at the first order's VWAP at 1-2 s (mean -0.4 bps, 70 orders), at
+3.8 bps within 1 s (215 orders), and several bps beyond the VWAP over 5-30 s. That table pools all development
data, so it cannot price a test window; it has to be turned into per-vintage estimates.

## Decision
1. **Evidence (one row per later child order).** From `fills`: eligible core perps, `event_kind = trade`, taker
   (`is_maker` false), forced fills excluded (ADL, liquidation, settlement; ADR-0046). One order = one `(trader, oid)`
   with its first fill time, side, best (first) fill price and VWAP. A **sequence** is consecutive orders of the same
   trader and coin on the same side, each at most 60 s after the previous one (as in `scripts/split_orders.py`). Every
   later order of a sequence (k >= 1) gives one observation: elapsed = its time minus the first order's time, and
   move = sign x (its best fill / the first order's VWAP - 1) x 10,000 (positive = worse for a copier on the
   leader's side). The best fill of a taker order is the touch when it arrived, so this compares with the replay's
   base fill before impact: base anchors at the batch VWAP (ADR-0036), removes and re-adds the same half-spread, and
   moves the mid by the drift parameter; the move is therefore read as the drift parameter itself.
2. **Point in time (ADR-0004).** At vintage v (every warm-up day and every origin, as the drift cells): only sequences
   whose first order and the observed later order are both strictly before v 00:00 UTC; development data only: orders from `drift.estimate_window.start` (2025-09-08, as the drift cells), and an
   observation whose first order or own order falls on an excluded day (10-11 Oct, `drift.exclude_dates`) is left out; only coins that are not
   BTC/ETH/HYPE/SOL and pass the price check as of v (ADR-0044). Nothing from the holdout window can enter (the last
   vintage is 2025-12-03, and only orders before it count).
3. **Bins.** Elapsed time, right-closed: (0, 1], (1, 2], (2, 5], (5, 10] s, keyed by their upper edge in ms (1000,
   2000, 5000, 10000). A delay d uses the bin with lo < d <= hi: 1 s -> (0, 1], 1.2 s -> (1, 2], 5 s -> (2, 5],
   10 s -> (5, 10]. A delay above 10 s and below 300 s (the 60 s grid point) has no bin.
4. **Estimate.** Per vintage and bin, the mean move. Pooling: by the ADR-0053 liquidity bucket of the first order
   (the coin's latest completed Hyperliquid 4h bar at the first order's time, `stress_fallback.bucket_edges_usdc`)
   only if **every** bucket has at least 30 observations in that bin at that vintage; otherwise one pooled estimate
   over all parameterised coins (all buckets, including no bar). A cell (bucket or pooled) with fewer than 30
   observations has no estimate (30 = the existing cell minimum, PLACEHOLDER). The mean is not trimmed: the cost is in
   the tail (90th percentile 20-60 bps), and a trimmed mean would drop it. Cells are written with the drift cells
   (`drift_cells.parquet`): `period = development`, `source = hl_split_orders`, `coin = hlsplit:<bucket>` or
   `hlsplit:all`, `band = all`, `horizon_ms` = the bin's upper edge, `measured` = observations.
5. **Rule (base, parameterised coin, delay below 300 s).** P = the four-coin proxy at the delay (ADR-0029, required
   as before). E = the estimate for the bin containing the delay: the order's bucket cell (bucket at its decision,
   as ADR-0053) if the vintage has bucket cells for that bin (an order with no completed bar then has none), else
   the pooled cell.
   - E exists: drift = **max(P, E, 0)**, method `base_max_proxy_hlsplit_zero`. The coin's own 300 s cell is not
     needed.
   - E missing (no bin, or fewer than 30 observations): the ADR-0048 floor, drift = max(P, own 300 s, 0), method
     `base_max_proxy_coin_300s_zero`, both required as before.
   - The zero floor stays: the base drift of a parameterised coin is never favourable.
   - The cells used are in `parameter_cells`, as for every other parameter.
6. **Unchanged.** Optimistic keeps the four-coin proxy; stress keeps ADR-0053 and severe ADR-0060 (they read the
   stress regime, not this rule); at 300 s and above every scenario keeps the coin's own estimate; the four direct
   coins keep their aggTrades move. The rule applies wherever base prices a parameterised order below 300 s: the main
   run, the base delay grid (1, 1.2, 5, 10 s use bins; 60 s falls back), the cost surface (ADR-0050).
7. **One variant only.** No second variant (such as the own 300 s estimate scaled by delay / 300) is run: the brief
   allows one, chosen only by agreement with the measured short-delay path, and the direct estimate of that path
   needs no such choice. The rule is logged in `provenance/trial_log.md` with its result whether better or worse.
8. **Configuration.** `config/execution.yaml: replay.alt_short_floor`: `rule` (`hl_split_orders`, or `own_300s` for
   the ADR-0048 rule, kept only to reproduce the before/after report), `bins_ms` [1000, 2000, 5000, 10000],
   `sequence_gap_ms` 60000, `min_orders` 30. Code: `replay_market.split_order_cells` (evidence and cells),
   `replay_orders.Parameters.lookup` (rule).

## Consequences
- The base cost of parameterised coins below 300 s rests on the venue's own short-delay prices instead of a five
  minute drift, where there is evidence; elsewhere it is the ADR-0048 floor. Base results change in both directions:
  an estimate below the own 300 s cell lowers the cost, one above raises it.
- The evidence is conditional: an observation exists only when the leader trades again on the same side within
  60 s, and such leaders are often chasing a move (`research/split_orders/summary.md`). This leans conservative for
  the copier. Samples under 2 s are small; the per-vintage counts are reported in
  `decision/alt-floor-receive-results.md`.
- Tests: `tests/test_alt_floor_receive.py` (seeded leak: a later order after the vintage does not enter it; the
  bins; the bucket/pooled choice and the 30 minimum; the rule with an estimate, its fallback, the zero floor; stress,
  severe and optimistic unchanged).
