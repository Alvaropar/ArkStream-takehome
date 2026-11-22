# ADR-0138: The selection rule in force is rule_b_coin_filter (chosen by the ADR-0137 criterion)

- Status: Accepted; the rule is unchanged by ADR-0140 (filter executed in the replay, numbers rerun), frozen by ADR-0141
- Date: 2026-11-22
- Phase: Phase 4 (selection), item 6

## Context
The three variants of ADR-0137 were run on the four development windows (`research/selection/walk_forward.csv`,
`variant_choice.csv`; trial log). Wins are windows with the basket's base return above the median of 1,000 matched
random-k draws:

| Variant | Matched wins | All-A/B wins | Mean basket base return |
| --- | ---: | ---: | ---: |
| rule_a | 1 of 4 | 1 of 4 | -2.55% |
| rule_c_p10 | 1 of 4 (the same selections as rule_a at every origin) | 1 of 4 | -2.55% |
| rule_b_coin_filter | **3 of 4** | 2 of 4 | **+0.72%** |

## Decision
1. `selection.rule: rule_b_coin_filter`: ADRs 0130-0132 with the ADR-0136 coin filter (key on kept-coin trips; the
   follower copies only the origin's kept coins).
2. Its 3 Dec shortlist (`research/selection/shortlist_2025-12-03.csv`) is the rule applied at 3 Dec: 0x2cd9...946e,
   0x971f...77fa and 0xd2f0...e9e1 are selected. 0x4c6e...f8b3 is rejected: its key is unmeasured with 8 kept-coin
   trips, below the 10 minimum.

## Consequences and caveats (stated before the holdout)
- **The win count is weak evidence.** The eligible pools are 3 / 2 / 3 / 5, with 3, 2, 3 and 10 possible matched
  picks, so each "win" is a choice among a handful of addresses. Clopper-Pearson on 3 of 4 is 0.19-0.99 (two-sided
  95%). The choice was made on these same windows, so the figures are optimistic.
- **The filter is an attribution, not a re-run** (ADR-0136): dropped coins are removed from the existing ledgers,
  and the 1.5x cap is not re-solved. The holdout (item 8) must score the same way, from the 3 Dec coin set.
- The gates' audit is unfavourable on the unfiltered copy: eligible address-windows averaged -4.3% base against
  +1.1% for the rest (`diagnostics/gate_audit.csv`), and the key does not persist (Spearman -0.16 to +0.18).
  Selection rests mostly on the gates and the coin filter, not on the ranking.
