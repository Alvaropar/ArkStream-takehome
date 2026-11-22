# ADR-0130: Selection-level gates, with the equity band at 5k-2M

- Status: Accepted (thresholds PLACEHOLDER). Fixed before any test-window outcome of the rule was computed
- Date: 2026-11-22
- Phase: Phase 4 (selection)

## Context
The brief's item 1 adds selection gates on top of grade A/B and the 18 Phase 2 gates. A training-only dry run
(no test window read) showed that the plan's median-equity band of 20k-2M leaves eligible pools of 2 / 1 / 1 / 2
at the four development origins (2 at 3 Dec) and baskets of 1 / 1 / 1 / 2. In 3 of 4 windows the pool would equal
the basket, so the matched random-k baseline could not judge the ranking. Pools under other lower edges (training
only): 5k gives 3 / 2 / 3 / 5 (3 Dec: 4); no lower edge gives 4 / 5 / 8 / 9 (3 Dec: 7).

## Decision
All gates are computed at the origin from data up to it (`selection.candidate_table`, config `selection.gates`):
1. `sel_history`: at least 90 distinct snapshot dates known by the origin and at least 60 usable return days.
2. `sel_equity_band`: median equity in **[5,000, 2,000,000] USDC**. This is the user's choice (2026-11-22), made from
   the capital before any test outcome. Under no scale-up (ADR-0043) a leader can absorb capital only up to its own
   equity. A stage-1 sleeve is about 30,000 / 5 = 6,000 USDC, so 5k is the smallest leader that can use a real sleeve.
   The plan proposed 20k.
3. `sel_copyable_notional`: `share_not_copyable` (ADR-0113) at most 10%.
4. `sel_hold_band`: the leader's holding band is copyable at the origin. A band is copyable when the training-window
   completed follower trips (all A/B, base) net > 0 per trip over at least 100 trips.
5. `sel_break_even`: the training-window break-even delay is above the base delay (1.2 s). The status must be
   `positive_through_grid`, or `crossing_bracket` with the last positive delay at least 1,200 ms.
6. `sel_copier`: the address is not the weaker member of a confirmed copier cluster in the copier screen as of the
   origin. The weaker member is the one with the lower key; an unmeasured key ranks lowest.
Maker-heavy and high-frequency accounts are already gated in Phase 2 (`gate_maker`, `gate_order_rate`, `gate_hold`).
Duplicates by co-movement are handled in the diversification walk (ADR-0132).

## Consequences
With eligible pools of 2-5, the matched random-k test can barely judge the ranking. Selection therefore rests
mostly on the gates, and the all-A/B random-k baseline is the main test of whether the gates add value. Every result
reports the pool size per origin and the number of possible random picks beside it.
