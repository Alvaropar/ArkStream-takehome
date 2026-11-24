# ADR-0065: New Phase 5 designs the capital arrangement, risk limits, pause and exit rules after basket selection

- Status: Accepted (scope and order); contents designed in ADRs 0086-0095 (proposed 2026-11-23; item 2's
  weighting deferred by ADR-0086 while there are two sleeves)
- Date: 2026-11-22
- Phase: Phase 5 (redefined)
- Amends: ADR-0064 (decision items 1, 3 and 4); replaces the plan v2 Phase 5 (shared-account replay)

## Context
ADR-0064 dropped the plan v2 Phase 5 (shared 100k account replay) and left the capital arrangement to be written
into the memo after the holdout. The user ruled on 2026-11-22 that:
- the capital distribution, unallocated-capital handling, risk limits, pause conditions and exit conditions are
  not to be decided directly: they must be designed, like the selection rule;
- they must be fixed before the holdout and tested on it, so the holdout evaluates the whole scheme, not the
  basket alone;
- the main concern now is basket selection; these points come after it.

## Decision
1. **Order of work.** (a) Basket selection is finished first (Phase 4 development, plus any further research the
   user runs before the holdout). (b) Phase 5 then designs the items below on development data only.
   (c) Everything is frozen together in one freeze hash. (d) The holdout is opened once and tests selection and
   Phase 5 rules together.
2. **Phase 5 scope** (design, not just a choice of numbers):
   - capital distribution of the 100k USDC across the selected addresses (sleeve structure, sizes, how sleeve size
     interacts with the no-scale-up multiplier, impact and participation);
   - unallocated capital: how much stays undeployed and how it is held;
   - risk limits per sleeve and for the portfolio;
   - pause conditions and exit conditions (what triggers them, how they are checked, how an exit is executed and
     costed), and the conditions for resuming or adding capital.
3. **Discipline** as for selection: point in time per origin; designed and evaluated on the four development
   windows only; every variant in the trial log; the choice criterion written down before results; no tuning on the
   holdout. The design questions (isolated sleeves vs a shared account, thresholds from a risk budget vs fitted,
   day-end vs intraday checks) are open and belong to Phase 5.
4. **The holdout stays closed until Phase 5 is frozen.** ADR-A0141's freeze does not cover Phase 5 and will be
   re-cut (new ADR, new hash) once Phase 5 is done.
5. Phase 6 (live engine, runbook, reconciliation code) stays out of scope (ADR-0064). The written operating answers
   the test asks for are still given in the memo.

### The freeze mechanism (from ADRs A0139 and A0141, archived)
`src/arkstream/freeze.py` stays the mechanism:
- `provenance/HOLDOUT_FREEZE.txt` records the SHA-256 of the configuration and the rule sources, plus one combined
  hash;
- every selection and replay entry point refuses a window that ends after the holdout start unless every recorded
  hash matches.

The hashes recorded under ADRs A0139 and A0141 were never sent and are void. The joint Phase 4 + Phase 5 freeze will be a
new ADR, with the data manifests and the environment added (pre-holdout Check 3).

## Consequences
The memo's capital arrangement and limits become tested results, not post-holdout text. Opening the holdout waits
for Phase 5. If Phase 5 chooses a structure the replay does not simulate (for example one shared account), it must
build that simulation before the freeze.
