# ADR-0049: Report a stress result with less than 80% priced intents as unmeasured

- Status: Accepted (threshold PLACEHOLDER); amended by ADR-0055 (only pricing failures count as unpriced)
- Date: 2026-11-20
- Phase: pre-Phase 4 fixes (brief item 6)
- Amends: ADR-0032 (how stress results are reported)

## Context
At the 8 Oct origin the 10-11 Oct crash sample that prices parameterised stress orders did not exist yet, so
1,306 of 2,000 stress intents of gate-passers had no price (65.3%), yet the stress result was reported as a return
(`research/replay/economic_screen.csv`). Skipped orders leave cash idle, so such a number is mostly the
untraded allocation, not a stress outcome.

## Decision
- Priced share of an address-window = 1 - `unpriced_share` (the address summary's count: intents, i.e. orders
  not already at target, that got no fill for any reason other than the minimum size or unusable leader equity).
  An address with no intents has a priced share of 1 (a flat book is measured).
- A **stress** result (the main stress run and every point of the stress delay grid) with priced share below
  0.80 (`replay.stress_min_priced_share`, PLACEHOLDER) is `unmeasured`: `copy_return`, `before_funding`,
  `max_drawdown`, `daily_sharpe`, copy efficiency and the break-even fields are null and
  `measurement = unmeasured_low_coverage`. It is never counted as positive or negative (nor in the drawdown counts);
  window and pooled tables count measured and unmeasured results separately and average only measured ones.
  Every summary also reports `priced_share`.
- Optimistic and base are unchanged (`measurement = measured`).

## Consequences
The 8 Oct stress test is mostly unmeasured instead of a misleading return. Tests: `tests/test_pre_phase4.py`.
