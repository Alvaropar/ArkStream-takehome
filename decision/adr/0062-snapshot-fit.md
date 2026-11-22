# ADR-0062: Reconcile at exact snapshot times and disclose uncheckable intervals

- Status: Accepted
- Date: 2026-11-19
- Phase: Phase 2 rework

## Context

Hourly alignment was a source of tracking error. The prototype illustrated why ordering by raw row and joining an unpublished rate on accrual hour are insufficient.

## Decision

Compute the change in cumulative signed fill cash net of known USDC fees plus signed marked positions, adding actual hourly payments over the right-closed snapshot interval. Use the final chain-ordered fill at each timestamp. An inherited position before its first observed fill has an unknown opening value. Exclude intervals beginning before the fill-feed start. Track non-core events and outstanding inventory at both endpoints, including dust conversion. Non-core activity or a non-USDC fee during an interval makes it uncheckable. Other intervals of the same address remain eligible.

Fit uses active, fully priced intervals with opening equity of at least 500 USDC and a non-frozen closing snapshot. Active means a held position at either endpoint or a core fill in the interval. Report the number of eligible intervals, total and active intervals, median absolute miss divided by opening equity, and shares within 0.1% and 1%. Assess correlation and tracking dispersion on the usable-return subset. Frozen rows remain in the interval evidence and bridge.

The additive bridge starts from every account interval. Report the account PnL before the feed separately. For later intervals subtract identified core trading PnL where both endpoints are priced, and separately show the sum of known funding. Allocate the residual to non-core intervals first, then to intervals with unknown prices, positions or funding, then to unexplained on fully checkable intervals. These are disjoint interval buckets. An excluded interval's residual measures unresolved account PnL, not the market value of a missing coin. For a mixed interval with an unpriced core leg, no partial trading balance enters the bridge. The priced interval's book PnL, raw endpoint values, component changes and reasons remain available.

## Consequences

The per-origin fit distribution, missingness and bridge can be reproduced from book_vs_account. Snapshot marks retain the source fill and exact bar time. No non-core returns are inferred.
