# ADR-0050: Cost uncertainty surface around the placeholder execution costs

- Status: Accepted (definition fixed before any surface point was computed)
- Date: 2026-11-21
- Phase: pre-Phase 4 fixes (brief item 8)

## Context
The base case's cost headroom rests on three placeholders: square-root impact coefficient Y = 1 (ADR-0033),
participation 0.5% of the latest completed 4h bar (ADR-0035) and the 1.5x address gross cap (ADR-0034). The brief
asks for the surface around them and for its lower bound, not only the central value.

## Decision
- Scope: base scenario at its 10 s delay, the four development test windows only (no training windows, no delay
  grid), all-gate passers at each origin (worst-case gate included). Everything else is the full stack of ADR-0052.
  The surface is computed for both sizing variants (dynamic and frozen `E_ref`) so it does not wait on the policy
  choice; the chosen policy's surface is the one reported as the result.
- One-at-a-time points around (Y 1, participation 0.5%, cap 1.5x): Y in {0.5, 2}; participation in {0.25%, 1%,
  none}; cap in {1.0x, 2.0x}; plus the centre. "None" removes the volume budget only: the ADR-0037 order budget at
  the triggering leader batch's notional stays.
- Corners: the most favourable combination takes, for each parameter, the value with the highest pooled mean funded
  return among its one-at-a-time points (the centre counts); the least favourable takes each parameter's lowest.
  Ties go to the centre value.
- Per point: pooled mean funded return over the measurable gate-passing address-windows, the number positive,
  profit in USDC, filled turnover and the extra cost per filled side that would absorb the profit
  (profit / turnover x 10,000 bps), and the same per test origin.
- The lower bound is the least favourable point of the surface (the lowest pooled mean among all points,
  corners included).

## Consequences
Output `research/replay_sizing/cost_surface.csv` (`python -m arkstream replay --cost-surface`), reported in
`decision/pre-phase-4-results.md`. The surface varies costs, not the copy signals; the delay and spread
placeholders stay at their base values.
