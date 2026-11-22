# ADR-0131: Ranking key = 20th percentile of a week-block bootstrap of the follower's net return per trip

- Status: Accepted (percentile, draws and minimums PLACEHOLDER). Pre-registered before any test outcome of the rule
- Date: 2026-11-22
- Phase: Phase 4 (selection)

## Context
The plan ranks on the follower's training-window result, not the leader's (ADR-0009). The brief fixes the default
statistic, mean net return per completed follower round trip after costs and funding (frozen policy, base 1.2 s),
and its lower bound from a calendar-week block bootstrap that keeps overlapping trades together.

## Decision
1. **Trips** (`selection.follower_trips`). These are completed follower round trips in the frozen replay's training
   window ending at the origin (base scenario), formed exactly as `replay_book.completed_trips` forms them:
   reversals are split at zero, fees are apportioned, accruals are attached to the holding lot, and trips with an
   unknown accrual are dropped. Net return = (gross at the anchor - execution cost - fees + funding) / peak notional.
   Each trip keeps the leader source keys of its opening and closing orders (`oid`, first `src_row`, first `tid`).
2. **Blocks: the calendar week (Monday, UTC) in which the trip opened.** The literal reading, merging weeks linked by
   a trip that spans them, was tried on the training windows first, before any outcome. Under frozen sizing with
   netting the follower rarely goes flat, so one multi-week trip chained every week into one block: the median was
   1-2 blocks per address at every origin, and an address with 165 trips had 1 block. By entry week the median is
   2-5. A trip is then one observation in one block however long it is held, and trades opened in the same week stay
   together. `selection_stats.week_blocks` keeps the merged alternative for this disclosure.
3. **Bootstrap.** 2,000 draws per address. Each draw samples whole blocks with replacement, as many as observed,
   and takes the trip-weighted mean. The seed is `[20251008, address prefix, origin ordinal]`, so the result does
   not depend on which other addresses are present.
4. **Key = the 20th percentile** of the 2,000 means (one-sided 80% lower bound). It is unmeasured, and the address
   is not selectable, with fewer than 10 completed trips or fewer than 4 blocks. **An address needs key > 0 to be
   selectable.**
5. **Flag, do not drop:** `single_event` is set when the key is positive but the same bound without the block of
   largest PnL (`key_ex_best`, 2,000 draws, salt 1) is not positive. Flagged addresses stay ranked, and the flag is
   printed in their reason. `best_block_share` = that block's share of the training PnL.
6. Reported beside the key: training daily copy TWR return, its maximum drawdown and daily Sharpe; the training
   stress return and its ADR-0122 measurement; the optimistic return.

## Consequences
Capture is not a ranking input. Tests (`tests/test_selection.py`): the bootstrap is seeded and reproducible; entry
blocks; the minimums; the flag; and a seeded leak, in which a test-window return planted in the trips changes the
shortlist.
