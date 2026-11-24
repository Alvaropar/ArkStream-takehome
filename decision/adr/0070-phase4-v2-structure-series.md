# ADR-0070: Phase 4 v2: qualification only; the copy series, common window, exposed-day measurability and a provisional 10k sleeve

- Status: Accepted (placeholders); fixed before any rerun under it. Items 3-5 (`G`, exposed days) amended by ADR-0080 and ADR-0082. Item 6 (P4-9) applied by ADR-0086 item 6: not triggered by the Phase 5 design (proposed 2026-11-23)
- Date: 2026-11-23
- Phase: Phase 4 (selection), v2
- Amends: ADR-A0130 (the gate list, see ADR-0073), ADR-A0131 and ADR-A0051 (the key, see ADRs 0071, 0072), ADR-A0132 (the
  basket, see ADR-0074)
- Source: `decision/phase-4-v2-methodology.md` sections 0-2, 5.1, 9 and 12 (revision 2, amendments A1 and A3)
- **Decided after seeing results.** This is the fourth post-hoc change in two days. The protocol applies:
  - each definition is written before it is computed;
  - it is applied at all five origins;
  - it is logged in the trial log;
  - it is never reverted because of the address or the return it produces.

## Context
The development evidence (methodology section 0):
- ranking on past copy returns does not predict;
- the spread of mean copy returns across addresses is about what noise alone would produce;
- the top-ranked address rests on one crash day;
- the score was not market-relative and mixed skill with sleeve utilisation;
- the rule variants never compared selection;
- the coin filter selected on leaders' past profit;
- the pairwise walk measured diversification badly.

## Decision
1. **What Phase 4 answers:** "who is individually qualified, and how strong is the evidence?". Phase 5 builds the
   basket and its weights from Phase 4's hand-off. ADR-0065 freezes the two together, so the holdout still tests one
   mechanical rule.
2. **Pipeline:**

   | Stage | Content | Binding |
   | --- | --- | --- |
   | S1 | grades (ADR-0066) | yes |
   | S2 | Phase 2 binding gates (ADR-0067, gate 7 v2 ADR-0069) | yes |
   | S3 | copyability (ADR-0073) | yes |
   | S4 | copy economics (ADR-0071) | measurement only |
   | S5 | evidence and categories (ADR-0072) | yes, by category |
   | S6 | ranking validation (ADR-0075) | decides whether ordering is used |
   | S7 | duplicates and co-movement (ADR-0074) | duplicates only |

3. **Series:** the copy's daily mark-to-market ledger, base scenario, from the tradable-universe replay (ADR-0073) at
   the provisional sleeve. Each day gives the residual PnL `U_{i,t}` (ADR-0071) and the gross exposure `G_{i,t}`, the
   notional at the start-of-day mark.
4. **Common window:** every address is measured over the same calendar days, from `max(2025-09-08, origin - 12 weeks)`
   to the day before the origin. 8 Sep is the first day a copy can be priced. A day with `G = 0` enters neither sum of
   the statistic, so the window start does not change its value. This is consistent with ADR-A0051.
5. **Measurability:** at least **20 exposed days** (`G > 0`) in at least **4 calendar weeks with exposure**.
   Otherwise the address is unmeasured (category E0; no credit, ADR-0068). This keeps ADR-A0051's minimums, but counts
   exposed days.
   - Stated before the rerun: this can make sparse copies unmeasured. 0x4c6e has about 16 days with a non-zero copy
     return in the unfiltered 3 Dec series.
6. **Provisional sleeve: 10,000 USDC**, the size every existing replay uses. T3, the equity band and the statistics
   are computed at it.
   - **The one-pass loop with Phase 5:** Phase 5 chooses sleeve sizes from the 10k hand-off. If any chosen size
     differs from 10k, Phase 4 is recomputed **once** on replays at the chosen sizes (T3, the statistics, τ², the
     categories and the duplicates).
   - Phase 5's construction is then rerun **once**, with the sizes held fixed, and that result is what the joint
     freeze covers (step P4-9).
7. **Hand-off** (`research/selection_v2/origin=<date>/eligible.parquet`): one row per address in E1 or E2 that passed
   S1-S3 and the duplicate screen, with the columns in methodology section 9. Also handed off: `comovement.parquet`,
   `coins.parquet` (with coverage) and `ranking_validation.csv`.
8. **Development plan** P4-0 to P4-9 as in methodology section 12:
   - P4-1 (gate 7 v2) comes before every replay and statistic;
   - τ² is computed as early as possible;
   - P4-9 comes before the joint freeze (a new ADR, with Phase 5).

## Consequences
- **The rule is replaced, not tuned.** The 3 Dec basket of ADR-A0138 is superseded. Phase 4 no longer outputs a
  basket.
- **New outputs** live under `research/selection_v2/` and `research/replay_tradable/`. The v1 outputs stay as the
  record of ADRs A0130-A0141.
- **"No address qualifies" is a valid result.** It leads to a shadow scheme or a CONDITIONAL GO, never to looser
  thresholds.
