# ADR-0088: Anchor copies at the leader's own sweep; size-dependent drift tested, not applied

- Status: Accepted (sensitivity variant); amended by ADR-0112 (forced fills keep the first-fill anchor and leave the size study)
- Date: 2026-11-20
- Phase: Phase 3, cost sensitivities
- Amends: ADR-0080 (anchor for parameterised and direct copies in this variant)

## Context
Every leader taker order in the package fills within a single millisecond: one sweep through the book. Its
first-to-deepest spread averages 0.0-0.9 bps on BTC, ETH, HYPE and SOL at every size, but on other coins 0.6 bps
(<$1k), 2.6 ($1k-10k), 6.3 ($10k-100k) and 17.3 ($100k-1M) (134,995 taker orders). ADR-0080 anchors the copy at
the first fill, which assumes the book refilled completely before the copy arrives.

## Decision
1. **Anchor by scenario**, variant `part_ns_sweep` = `part_ns` (ADR-0087) + this rule, for native taker batches:
   optimistic = first fill (as before), base = the batch's quantity-weighted VWAP, stress = its deepest fill
   (highest buy, lowest sell). Makers keep the first fill; basket-only resize legs keep their ADR-0085 decision
   mark. The maker/taker mid adjustment, drift, spread and impact then apply as before; the direct path keeps its
   Binance price ratio. Per order: `leader_first_px`, `leader_vwap`, `leader_deepest`, `leader_notional`,
   `sweep_bps` (signed first-to-deepest) and `anchor_rule`, with the batch's source keys.
2. **Size-dependent drift, rule frozen before outcomes** (`src/arkstream/replay_size.py`). For the four aggTrades
   coins, at each origin and horizon, development data only, 10-11 Oct excluded, observations ending before the
   origin: signed drift of leader taker orders by notional (<1k ... >=1M) and by share of the latest completed 4h
   volume (<0.01% ... >=0.5%). A size term for other coins qualifies only if, in at least 3 of the 4 coins, both
   large (>=100k) > small (<1k) and high share (>=0.5%) > low share (<0.01%), with at least 30 observations per
   arm; it would add the median (high-share mean minus coin mean), floored at zero, to high-share parameterised
   native taker orders.
3. **Result of item 2: no term at any origin or horizon** (`research/replay/leader_size/leader_size_terms.csv`).
   The high-share arm has only 4-25 orders per coin at 3 Dec, below the 30 required: leader orders on the four
   liquid coins almost never reach 0.5% of a 4h bar. On the notional axis alone, HYPE's large orders show more
   drift than small ones (+4.0 to +7.3 bps against -0.5 to +0.3 at 1-300 s, 122-134 large orders), and ETH at 300 s
   (+1.7 vs -1.5). This is disclosed, not applied: the pre-registered rule did not qualify.

## Consequences
- The basket-resize anchor uses the minute mark known at the decision for all coins. Using the last aggTrade for
  BTC/ETH/HYPE/SOL resize legs was considered and left out of this variant; resize legs are a small share of
  orders and carry no leader sweep.
- An unfinished lookup in `replay_market.trade_queries` that searched forward in time for a print
  (`decision_offset`) was removed before any run: it was unused and would have been a look-ahead.
- Results in `decision/phase-3-sensitivity-results.md`.
