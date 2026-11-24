# ADR-0035: Limit each follower order to a share of the latest completed 4h volume

- Status: Accepted (sensitivity variant; threshold PLACEHOLDER). For the Phase 5 multi-sleeve engine only, the
  budget becomes per coin per 4h bar summed over sleeves (ADR-0087, proposed); single-sleeve replays keep this rule
- Date: 2026-11-20
- Phase: Phase 3, cost sensitivities

## Context
Under the linear impact rule the top 100 base orders carried 60% of the $484k of impact, some at over 100% of the
latest 4h bar (ETC, HYPER, BABY). Square-root impact and the 1.5x address cap (ADRs 0033, 0034) cut notional-weighted
impact to 4.2 bps per side but left a mean funded base return of only +0.039% across gate-passers.

## Decision
- Variant `part` = ADRs 0033 + 0034 + this rule. Each follower order, including basket resize legs, has a USDC
  budget of `max_participation` (0.005, PLACEHOLDER, `config/execution.yaml`) times the USDC volume of the latest
  completed traded Hyperliquid 4h bar known at the decision (the bar is usable only after it closes).
- At the decision the quantity is clipped to budget / decision mark. At acknowledgement, if the filled notional
  including its own square-root impact still exceeds the budget, the order is shrunk by bisection and repriced.
- Minimum-size checks apply after clipping. A missing bar skips the order (`missing_participation_volume`).
- Per order the budget, the requested quantity and the submitted quantity are recorded (`order_budget_usdc`,
  `requested_qty`, `submitted_qty`). Clipped residuals stay as unmet targets for later signals.

## Consequences
Results in `decision/phase-3-sensitivity-results.md` (section "Sizing limits and leader impact"). Code:
`replay_orders.execute`, `replay_sensitivity` (`SPEC`); tests in `tests/test_sensitivity_limits.py`.
