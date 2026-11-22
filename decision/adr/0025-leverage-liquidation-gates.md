# ADR-0025: Leverage, liquidation distance (stated margin), liquidations; gates as pass/fail/unmeasured

- Status: Accepted (all thresholds PLACEHOLDER)
- Amended by ADR-0064 for the Phase 2 rework.
- Date: 2026-11-19
- Phase: Phase 2

## Context
Per-coin Hyperliquid margin tiers are not in the package. Gates are computed, not applied (Phase 4).

## Decision
- Leverage = gross exposure at the mark / latest snapshot equity; p95 and max over marks with exposure.
- Distance to liquidation, cross margin, one uniform adverse move = 1 / leverage - MMR, with MMR = 2.5%
  (`leader.risk.maintenance_margin_rate`, an assumption until Hyperliquid metadata).
- Liquidations: fills with `dir` starting "Liquidated"; ADL: `dir` = "Auto-Deleveraging" (both counted, first
  `src_row` kept).
- Gates (`leader.gates`): evidence, intraday DD, worst day, worst 3 days, max DD, stress peak, leverage p95,
  liquidation distance, liquidations, top-1% dependence, unpriced exposure, book-vs-account. Each is `pass`,
  `fail` or `unmeasured`; a missing metric never passes.

## Consequences
Counts per origin in `research/leader/gate_counts.csv`: 19 / 18 / 21 / 24 / 23 addresses pass every gate
(placeholders). Revisit MMR when Hyperliquid metadata lands.
