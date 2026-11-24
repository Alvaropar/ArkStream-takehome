# ADR-0091: Joint freeze of the Phase 4 v2 specification and the Phase 5 rules in one hash

- Status: Accepted (the user approved ADRs 0086-0095 on 2026-11-24). Defines what the freeze covers. The freeze itself (P5-7) runs only on the
  user's explicit go (given on 2026-11-24), and the user sends the hash to the reviewers. The mechanism details are
  pinned in ADR-0097.
  Amended by ADR-0098 item 8: the frozen set also holds the cost rebuild, run C's refit, the v2 holdout entry
  point and their tests; the hash is computed once, after they are built and tested on development data
- Date: 2026-11-23
- Phase: Phase 5 (revision 4), step P5-7
- Builds on: ADR-0065 (the freeze mechanism, `src/arkstream/freeze.py`; the hashes recorded under ADRs A0139 and
  A0141 are void), `decision/pre-holdout-checks.md` Checks 3 and 4
- Source: `decision/phase-5-methodology.md` sections 8 and 13 (revision 4)

## Context
ADR-0065 freezes selection and Phase 5 together, so the holdout tests one mechanical scheme. The current
`freeze.py` was written for Phase 4 v1:
- it hashes the v1 shortlist (`research/selection/shortlist_2025-12-03.csv`);
- it pins code and configuration but not the data;
- it does not cover the report module.

Pre-holdout Check 3 found 454 holdout inputs covered by no manifest. Check 4 asked for the report module to be fixed
and run on the development windows before the holdout.

## Decision
1. **The frozen Phase 4 specification** is the one decided in the freeze-decision trial-log entry of 2026-11-23,
   which settles methodology section 15 item 5:
   - **In force:** ADRs 0066-0084 as published (`select-v2` run 4, with ADR-0084: funding out of α). The 3 Dec
     hand-off is 0x2cd9 only.
   - **Diagnostics, not adopted:**
     - the ADR-0082 entry-day beta variants (`entry_end`, `mean_exposure`);
     - the loosened evidence gates;
     - **gate 7b without flow intervals**, so 0x971f stays outside the hand-off;
     - the Binance aggTrades what-if.
   - **P4-9 is not triggered** (ADR-0086 item 6). The 10k trees are the ones frozen.
2. **One hash covers:**
   - the Phase 4 specification above: its ADRs, `decision/phase-4-v2-methodology.md` and the selection sources;
   - the Phase 5 rules: ADRs 0086-0096 and `decision/phase-5-methodology.md`, including the observation-sleeve
     declaration;
   - `config/decision_context.yaml`, `config/risk.yaml` (v3, with no `OPEN` value left), `config/execution.yaml` and
     `config/instruments.yaml`;
   - every source under `src/arkstream/` that the holdout path imports, including `portfolio_replay.py`, the risk
     model and `holdout_report.py`;
   - the data, replay and selection manifests (Check 3): the raw-input and reference-price checksums, the aggTrades,
     kline and Hyperliquid manifests, and an output manifest of `research/replay_tradable/`,
     `research/replay_allpriced/`, `research/selection_v2/` and the Phase 5 development trees;
   - the environment block: Python, polars, numpy and pyarrow versions, the `uv.lock` hash, the OS and
     POLARS_MAX_THREADS;
   - the window-report module, already run on all four development windows with its schema fixed (Check 4,
     step P5-6);
   - the pre-registered outputs and decision rule (ADRs 0092 and 0093).
3. **Mechanism changes, made in P5-7 before hashing:**
   - `freeze.SHORTLIST` becomes the v2 hand-off, `research/selection_v2/origin=2025-12-03/eligible.parquet`;
   - the source globs gain the Phase 5 modules;
   - the manifests and the environment block are added;
   - the 56 stale kline-manifest entries (Check 3) are dropped or annotated;
   - `scripts/verify_holdout_inputs.py` is rerun immediately before the holdout, and its output is kept.
4. **Order:**
   - every `OPEN` and PLACEHOLDER in `risk.yaml` is settled or kept as labelled;
   - the user approves;
   - `select --freeze` writes `provenance/HOLDOUT_FREEZE.txt`;
   - the user sends the hash.

   No `HOLDOUT_FREEZE.txt` exists before then. `decision_context.yaml` already has `frozen: true` (set for the void
   v1 freeze); the guard also needs the new file.
5. **After the freeze,** `freeze.guard` refuses any window after 3 Dec 00:00 unless every recorded hash matches. Any
   change to a hashed file needs a new ADR and a new hash before the holdout. Once the holdout is open, no change can
   be tested on it.

## Consequences
- **The holdout is opened once** (ADR-0092), under this hash.
- **Tests:**
  - a hashed file changed after the freeze is refused;
  - the freeze refuses while `risk.yaml` holds an `OPEN` value;
  - `verify_holdout_inputs.py` passes on a clean checkout.
- **This ADR changes nothing until P5-7.** Until then, the v1 freeze code stays as it is.
