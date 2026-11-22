# ADR-0110: Apply the price check as of each origin

- Status: Accepted
- Date: 2026-11-20
- Phase: pre-Phase 4 fixes (brief `decision/briefs/pre-phase-4-fixes.md`, item 1)
- Amends: ADR-0013 (how its classification is consumed), ADR-0040 items 3-4, ADR-0060 (passing panel of the
  frozen-snapshot diagnosis), ADR-0080 (which coins are copied at each origin). The ADR-0012 rule is unchanged.

## Context
ADR-0013 applied the pre-registered ADR-0012 rule once, to every Hyperliquid 4h bar closing by the CUTOFF, and
every consumer read that single list (`research/hyperliquid/price_check.csv`) at every origin: the replay
(`replay_orders.order_inputs`, `replay_market.vintages`), Phase 2 (`leader.py`, `leader_worstcase`) and the M1
build's frozen-snapshot diagnosis (`pipeline.build`). A coin's outcome at 8 Oct therefore depended on bars up to
4 Jan. The external review (validated 2026-11-20) reran the rule with only the bars known at each origin: 2-14
coins classify differently, worth 0.02-0.98% of the next window's notional.

## Decision
1. **Rule unchanged.** ADR-0012 as configured in `config/decision_context.yaml: funding.price_check` (at least 30
   compared bars; median |gap| <= 10 bps and 95th percentile <= 30 bps; closes in [10 Oct, 12 Oct) reported
   apart and left out of the rule; `no_binance` for coins whose mapping is never valid).
2. **Sample at time t** = the rows of `research/hyperliquid/price_check_bars.parquet` whose close `ts <= t`. Each
   row compares a Hyperliquid close with the Binance price known at that same close, so the sample is point in
   time. `hlprices.price_check_asof` is the one implementation; `research/hyperliquid/price_check_by_origin.csv`
   holds it at the five origins (origin, coin, outcome and the ADR-0012 statistics), written by
   `python -m arkstream funding --step price-check-origins`.
3. **`insufficient` (fewer than 30 bars) is not passing**: no intraday price and not copied. The replay records
   it as `insufficient_price_check`, next to `failed_price_check` and `no_binance_mapping`.
4. **Every consumer uses the classification as of its own time:**
   - replay: the training window at origin o and the test window [o, next origin) use the origin-o list for the
     copy decision, the cap basket, the funding-price source and the frozen-snapshot diagnosis;
   - drift vintages: a coin's drift cells exist at a vintage only if the coin passes as of that vintage (the
     daily warm-up vintages before 8 Oct and the five origins);
   - Phase 2 at origin o: Binance hourly marks, validation flags, funding-price source, snapshot-time book
     values, the worst-case Binance check and the order-to-volume profile use the origin-o list;
   - the M1 build at `asof` t uses the list as of t for the ADR-0060 frozen diagnosis. At the CUTOFF this is the
     ADR-0013 list, so the audit fixture (`provenance/expected_counts.yaml`) is unchanged.
5. `research/hyperliquid/price_check.csv` stays as the CUTOFF record of ADR-0013. No code reads its outcome
   column any more; it supplies only the coin list.

## Consequences
- A coin listed shortly before an origin is now `insufficient` there, so it is neither marked intraday nor copied
  until 30 bars exist. Grades at an origin can move through the frozen diagnosis (ADR-0060 uses the passing
  panel). Per origin, the coins that change status and the leader orders and notional of the following window on
  those coins are reported in `research/hyperliquid/price_check_changes.csv`; the 3 Dec origin's following window
  is the holdout and is not counted.
- Tests: `tests/test_price_check_pit.py`, including a seeded leak (a bar after the origin that would flip the
  outcome must leave the point-in-time result unchanged, and an implementation that reads it is caught).
