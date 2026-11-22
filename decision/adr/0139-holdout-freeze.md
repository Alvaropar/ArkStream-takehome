# ADR-0139: Holdout freeze hash and the guard on post-3-Dec windows

- Status: Superseded by ADR-0141 (the hash below was never sent; the freeze was re-cut after ADR-0140)
- Date: 2026-11-22
- Phase: Phase 4 (selection), item 7

## Decision
1. `config/decision_context.yaml` says `frozen: true` and `selection.rule: rule_b_coin_filter` (ADR-0138).
2. `provenance/HOLDOUT_FREEZE.txt` (`python -m arkstream select --freeze`, `freeze.write_freeze`) records the
   SHA-256 of 44 files, with a timestamp (`frozen_at: 2026-11-21T18:34:31Z`, the machine's UTC clock) and one
   **freeze_hash = `ec6d0c22d4f90df5290f8b752c4da9fae791e17e79e83bcfc3f59dfca8fdfeae`** over the sorted list. The files are:
   - the four config files;
   - the selection, freeze, replay, drift, price, leader, copier, quality, positions, book-state, funding, pipeline,
     config and time-parsing sources (`src/arkstream/`);
   - `research/selection/shortlist_2025-12-03.csv`.
   It refuses to write unless `frozen: true` is already set.
3. **Guard.** `freeze.guard(ctx, window_end)` is called by `selection.load_origin` and `replay.run`. A window ending
   at or before 2025-12-03 00:00 UTC runs freely. A later one runs only if the file exists, the config says
   `frozen: true`, the file's own hash is intact and every listed file's hash matches: a moved cutoff, an edited
   threshold, a changed rule source or shortlist, or a new rule source is refused, each one named.
4. The repository has no git. The hash proves the holdout used the frozen rules; only a message sent to the
   reviewers before the run proves the order of events. The user sends the hash before saying "open the holdout".

## Consequences
The holdout path (item 8) must add its replay window behind this guard without editing a hashed file, or the
freeze must be re-cut, with a new ADR and a new hash sent before the run. Tests in `tests/test_selection.py` cover
the guard without a freeze, the frozen flag, an edited threshold, a moved cutoff, an edited shortlist, a tampered
freeze file and a guarded selection load.
