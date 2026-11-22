# ADR-0113: Report each address's notional in coins that cannot be copied

- Status: Accepted (reported, not a gate)
- Date: 2026-11-20
- Phase: pre-Phase 4 fixes (brief item 4)

## Context
The replay copies only core perps that pass the price check at the window's origin (ADR-0110) and never HIP-3
(ADR-0042). An address that trades mostly such coins can pass every Phase 2 gate while its copy series holds
little of its activity.

## Decision
Phase 2 `evidence` (and `gates`) add, per address and origin, over its perp trade fills with timestamp <= origin
(core perps and HIP-3; spot is not a perp exposure and is left out of both numerator and denominator):
`perp_notional_to_origin`, `share_not_passing` (core-perp notional in coins not passing at that origin, including
`fail`, `no_binance` and `insufficient`), `share_hip3`, and `share_not_copyable` (their sum). No gate uses them.

## Consequences
Phase 4 can read how much of each address's trading its copy series can represent. The distribution across
gate-passers is reported in `decision/pre-phase-4-results.md`.
