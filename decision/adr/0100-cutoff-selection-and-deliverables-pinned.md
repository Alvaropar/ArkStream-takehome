# ADR-0100: The cutoff selection and the cutoff deliverables: entry point, inputs and order, pinned before computing

- Status: Accepted (pinned on development data on 2026-11-24, before the entry point was run; recorded in
  `provenance/trial_log.md`, "Phase 5 cutoff selection, check mode"). Built on the user's instruction of
  2026-11-24 to build it before the hash ("Yes, build it first").
- Date: 2026-11-24
- Phase: Phase 5 (revision 4), built before P5-7 (joint freeze), run at P5-8 and P5-9
- Refines: ADR-0094 items 3-4 (the cutoff selection, the cutoff deliverables), ADR-0092 items 1 and 3 (the partial
  day, the G\* rerun), ADR-0093 (D5), ADR-0099 item 11 (the holdout entry point's order)
- Source: `src/arkstream/cutoff.py`, `src/arkstream/holdout.py`, and default-preserving parameters in
  `replay.py`, `replay_market.py`, `replay_sensitivity.py`, `replay_capture.py`, `selection_v2.py`,
  `selection.py`, `config.py` and `freeze.py`

## Context
ADR-0094 item 3 runs "the frozen rules on data to the cutoff (2026-01-04T23:59:42.020Z), at the cutoff origin". Its
hand-off decides D5 (ADR-0093) and, when it differs from 3 Dec, the G\* rerun (ADR-0092 item 3). ADR-0094 item 4
lists the cutoff deliverables. No code computed any of these.

The frozen pipeline computes an origin from its configured list:
- Phase 2 tables at the origin (`leader.compute`);
- the drift tables (`drift.estimate`);
- the all-priced tree's shared inputs and every window's universe (`replay.run`, prepare only);
- the frozen stack on the origin's training window, all-priced and tradable (`run_sensitivities`), with capture
  (`replay_capture`);
- the selection (`selection_v2.run`).

Three facts from the code shaped the items below:
- Every origin is a UTC midnight with data strictly before it.
- The replay refuses an origin after the data end ("invalid replay boundary": `stop > ctx.cutoff`).
- The development drift and Phase 2 tables were built from the unbounded package inputs (`load_inputs`); the trees
  were built from inputs bounded at the holdout start (`bounded_inputs`).

## Decision
1. **The cutoff origin is 2026-01-04 00:00 UTC,** the last midnight at or before the cutoff and the last origin the
   frozen replay admits. Every input of the cutoff selection is bounded at it.
   - **The 4 Jan partial day (00:00 to 23:59:42) is not used.** It has no closing daily mark inside the data
     (ADR-0092 item 1). This reads ADR-0094 item 3's "data to the cutoff" as data to the cutoff origin, and it
     corrects ADR-0092 item 1's note that 4 Jan data is used by the cutoff selection: no 4 Jan data is used anywhere.
2. **The cutoff context:** the configuration with the origins extended by 4 Jan, the estimation window ending 3 Jan
   and the replay boundary at 4 Jan. No rule or parameter changes.
   - `freeze_holdout_start` keeps the real holdout start (3 Dec) for `freeze.guard`, so every guard inside the
     pipeline still requires the freeze.
   - `research_dirs` sends the Phase 2 and drift tables to the cutoff folders (`config.research_dir`; without it
     every run reads the published trees, as before).
3. **The inputs and the order of computation**, all by the frozen functions, into `research/cutoff/`:
   1. **drift tables** at the six origins (`drift.estimate`, the code of `make drift`) → `drift/`. The five
      development origins' rows must equal the published ones.
   2. **Phase 2 tables** at 4 Jan (`leader.compute`, with the panels `leader.run` shares over the six origins) →
      `leader/origin=2026-01-04/`. The five development origins' `evidence` and `daily_twr` are copied from
      `research/leader`, because the replay's prepare step reads every origin's.
   3. **The all-priced tree:** `replay.run` prepare only, under the cutoff context (shared inputs; every window's
      universe and leader series) → `replay_allpriced/`. Then the cutoff training window only
      (`run_sensitivities(training=4 Jan)`), and capture for that window (`replay_capture.run(only=...)`).
   4. **The tradable tree:** the 4 Jan tradable sets (`selection_v2_coins.wallet_sets`), the cutoff training window
      on them, the shared inputs copied, and capture → `replay_tradable/`.
   5. **The selection at 4 Jan only** (`selection_v2.run(only=[4 Jan])`) → `selection_v2/origin=2026-01-04/`. Its
      `eligible.parquet` is the cutoff hand-off.
4. **Outputs for P5-8** (`research/cutoff/cutoff_handoff.json`):
   - the hand-off addresses, and D5: true when the hand-off is non-empty (ADR-0093);
   - for each address other than the 3 Dec hand-off, whether it can be replayed from the 3 Dec inputs: it must be
     in the 3 Dec all-priced universe and hold a tradable set there. If it can, the holdout entry point runs its
     G\* (ADR-0092 item 3); if not, D2b is unmeasured, which fails (ADR-0068).
5. **The P5-8 order, enforced by the entry points:**
   1. run A on the holdout (`phase5 holdout --stage a`), which writes `research/holdout/run_A.json`;
   2. the cutoff selection (`phase5 cutoff`), which refuses until that file exists;
   3. D5, the G\* rerun for a differing hand-off, the report and the D1-D5 decision entry (`--stage decision`),
      which refuse until `cutoff_handoff.json` exists;
   4. runs B and C (`--stage bc`), which refuse until `decision_A.json` exists.

   The P5-9 deliverables (`phase5 cutoff --deliverables`) refuse until `decision_A.json` exists.
   Every step is refused by `freeze.guard` until `provenance/HOLDOUT_FREEZE.txt` holds.
6. **The cutoff deliverables** (ADR-0094 item 4), in `research/cutoff/deliverables/`:
   - **`trader_decisions.csv`:** one row for every address in the package's trader table.
     - **Grade:** at the cutoff origin (`pipeline.build`).
     - **Category:** the selection's, for an A/B address; empty for any other.
     - **First failed gate,** checked in this order:
       1. S1, the grade;
       2. S2, the first of Phase 2's `gates_failed`;
       3. S3, in the order `sel_equity_band`, `sel_break_even`, `sel_tradable_share`, `sel_direction`,
          `sel_copier`. An unmeasured gate fails, as in S3;
       4. the category, when it is not E1 or E2;
       5. `near_duplicate`.

       An address that fails none of them is recorded as `none`.
     - **Role:** `hand-off` (in `eligible.parquet`); `observation` (a declared observation sleeve, `risk.yaml`
       `scheme.observation_sleeves`, not in the hand-off); otherwise `none`.
   - **`target_allocations.csv`:** one row for each hand-off address, one for each observation sleeve, and one for
     the reserve. The protocol follows run A's decision (`decision_A.json`).
     - **NO-GO (paper):** every row is deployed at 0, and the hand-off addresses run in paper at the sleeve notional
       (10,000). The observation sleeve is zero-capital. The reserve is `capital_usdc` (100,000).
     - **CONDITIONAL GO (gray):**
       - The live sleeves are the hand-off addresses at 2,500 each, up to 5,000 live, so at most two (ADR-0090
         item 3).
       - If more than two qualify, they are ordered by category (E2 before E1), then by D4's statistic at the cutoff
         origin (`m`, or the own-data α when `m` is constant), descending, then by address. The rest stay in paper.
       - The observation sleeve is zero-capital, and the reserve is `capital_usdc` minus the live amount.
7. **Check mode** (`--check`): the same code at the 3 Dec origin with the real configuration, into
   `research/cutoff_check/`. It reads nothing at or after 3 Dec 00:00.
   - **The builders** (inputs bounded at 3 Dec):
     - the drift tables, against `research/drift`, to 1e-9;
     - the Phase 2 tables, against `research/leader`: the two engine tables byte for byte, the others to 1e-12.

     The published tables came from unbounded inputs, so polars may sum in a different order (results
     section 9.6).
   - **Everything downstream, byte for byte,** with the published drift and Phase 2 tables as inputs, as the trees
     were built:
     - the prepare outputs (shared inputs, every window's universe and leader series);
     - the 3 Dec training window of both trees, and their capture rows;
     - the tradable sets;
     - the selection outputs at 3 Dec, `eligible.parquet` included.
   - **The deliverables at 3 Dec:**
     - every A/B address appears once;
     - the roles match `eligible.parquet` and `risk.yaml`;
     - the counts match `funnel_v2.csv`.
   - **An earlier development origin is not checked.** Its selection needs its test window's outcomes, and so its
     test-window trees, which the single training-window path does not build.
   - `--resume` reuses finished steps of a check run; it is refused outside check mode.

## Consequences
- **The frozen set grows** by `cutoff.py` and this ADR. The parameters added to the replay and selection modules
  default to their old behaviour; run A and the development selection are re-checked unchanged.
- **The 4 Jan partial day is outside every holdout computation** (item 1). If the user prefers 4 Jan 23:59:42 as the
  bound, the frozen replay's boundary rule and the partial day's missing marks need their own ADR before the hash.
- **Not exercised before the freeze:** the cutoff context's branch past 3 Dec in each function (the guard holds it).
  Check mode exercises the same code at 3 Dec.
- **Tests:** `tests/test_cutoff.py` (the guards, the order, the first-failed-gate rule, the allocations, the
  cutoff context).
