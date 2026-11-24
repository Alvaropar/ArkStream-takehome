# ADR-0028: Choose the address return source using the cross-margin PnL identity

- Status: Accepted; amended by ADR-0045 (material, persistent breaches only)
- Date: 2026-11-19
- Phase: Phase 2
- Amends: ADR-0014 and ADR-0026. Implements ADR-0021.

## Context

The recruiter confirmed that snapshot equity measures the cross-margin account. A transfer between cross
margin and another account can change this balance independently of reported net deposits. The prior asset
table used snapshot TWR even for an address graded B with a documented scope offset.

## Decision

For each A/B address at each origin, read the point-in-time reconciliation count `pnl_rows_gt_tight`.
A single observed snapshot with `abs(pnl - (equity - net_deposit)) > 0.01 USDC` selects the funded
core-perp book for the address's entire history at that origin. The tolerance comes from
`reconcile.pnl_tolerance_tight`. This catches a stable offset and an isolated breach on an otherwise
well-covered address. The 99% match-share threshold continues to govern data grades.

With zero breaches, the primary series is the cross-margin snapshot TWR under ADR-0014, including its
end-flow sensitivity and covered gap drawdowns. With a breach, each primary observation is a UTC day
from `book_daily`. The numerator is rebuilt core-perp trading PnL after fees and funding. The denominator
is the latest cross-margin equity known at the opening midnight. A change in cross-margin equity alone
cannot enter the numerator. This return still depends on the reported equity used to scale exposure.

Exclude incomplete book valuations and missing, frozen or sub-500 USDC opening equity. Preserve nulls and
reasons on the daily rows. Missing book days do not borrow snapshot returns. Compound the usable book days
and use that same series for volatility, Sharpe, drawdown and the BTC/ETH regression. The end-flow
sensitivity applies only to the snapshot calculation. Recompute the choice independently at the next origin.

## Consequences

`daily_twr`, `twr_summary`, `market_sample`, `market_exposure` and `evidence` identify the primary
`return_source`. `return_coverage` describes the primary observations. `account_coverage` describes the
cross-margin observations. For book-sourced addresses, `account_returns.return_role` is `check_only`;
`snapshot_twr_check` and `snapshot_twr_end_check` preserve both cumulative snapshot measures.
Book rows trace to `book_daily` by trader and boundary time and to the denominator by `equity_src_row`.
The existing core-perp universe excludes spot and HIP-3. Per-origin counts are in the
[Phase 2 report](../phase-2b-results.md).
