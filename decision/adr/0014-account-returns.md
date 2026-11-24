# ADR-0014: Account returns: start convention base, end sensitivity, gaps as one return

- Status: Accepted (thresholds PLACEHOLDER)
- Amended by ADR-0026 and [ADR-0028](0028-cross-margin-return-source.md).
- Date: 2026-11-19
- Phase: Phase 2

## Context
Snapshots carry cross-margin account equity (ADR-0021) and reported net deposits. The plan estimates returns with the
flow at the start or end of the interval and excludes days where they differ, or where opening equity is
below 500 USDC. Snapshots are mostly at 22:00 UTC; 1,815 gaps exceed 1.5 days.

## Decision
- One return per consecutive snapshot pair: pnl = E_t - E_{t-1} - dND; r_start = pnl / (E_{t-1} + dND)
  (base), r_end = pnl / E_{t-1} (sensitivity).
- Excluded, with a reason: `opening_equity_below_min` (E_{t-1} < 500), `nonpositive_denominator`,
  `conventions_disagree` (|r_start - r_end| > `leader.returns.max_convention_gap` = 0.01, PLACEHOLDER).
- A gap gives one return over the whole gap (`period_days`, `multi_day`); nothing is interpolated.
- Coverage = days covered by usable returns / calendar days from the first snapshot to asof.
- Snapshot returns describe the cross-margin account. Transfers between that account and spot, isolated
  margin or HIP-3 may change its equity without a corresponding reported deposit. ADR-0028 makes the funded
  core-perp book primary for addresses with a PnL identity breach at the origin.

## Consequences
Median coverage 0.95-0.96 at every origin. `account_returns` keeps both snapshots' `src_row`.
