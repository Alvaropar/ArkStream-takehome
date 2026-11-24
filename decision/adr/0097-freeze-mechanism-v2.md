# ADR-0097: The freeze mechanism for the joint freeze: what is hashed, the manifests and the environment block

- Status: Accepted (pinned on 2026-11-24 for P5-7, on the user's go for the joint freeze, before the hash is
  computed)
- Date: 2026-11-24
- Phase: Phase 5 (revision 4), step P5-7
- Refines: ADR-0091 items 2-4 (what one hash covers, the mechanism changes, the order); ADR-0065 (the freeze
  mechanism)
- Source: `src/arkstream/freeze.py`, `scripts/verify_holdout_inputs.py`, `tests/test_selection.py`

## Context
ADR-0091 lists what the joint freeze covers and the changes `freeze.py` needs. Building them needed details it does
not give:
- how "every source the holdout path imports" is found;
- which documents are hashed;
- how the output trees, which are mostly untracked Parquet, are pinned;
- what the environment block holds, and what the guard compares;
- how line endings are hashed;
- what to do with the 56 stale kline-manifest entries, and with the 111 pre-Phase 4 entries that a verification run
  on 2026-11-24 found stale.

## Decision
1. **The 3 Dec hand-off:** `freeze.SHORTLIST` is `research/selection_v2/origin=2025-12-03/eligible.parquet`.
2. **Sources.**
   - The source globs of the v1 freeze, plus the Phase 5 modules: `risk_model.py`, `portfolio_*.py`, `phase5_*.py`,
     `holdout_report.py`.
   - Their static import closure within `src/arkstream`, found from every `import` statement, top-level or inside a
     function. Today it adds `ingest`, `instruments`, `provenance` and `reconcile`.
   - The command-line entry point: `__init__.py`, `__main__.py` and `cli.py`, without following `cli.py`'s imports.
     `latency.py`, `hyperliquid.py` and `audit.py` are not on the holdout path, and they are not hashed.
3. **Documents:**
   - ADRs 0065-0084: the freeze principle and the Phase 4 v2 specification;
   - ADRs 0086-0097: the Phase 5 rules and this mechanism;
   - `decision/phase-4-v2-methodology.md`, `decision/phase-5-methodology.md` (revision 4) and
     `decision/phase-5-results.md`.

   They are listed by number, so a later ADR (0098 onward) does not break the freeze. `decision/adr/README.md` and
   `provenance/trial_log.md` grow after the freeze, so they are not hashed.
4. **Manifests.** The eight existing manifests are hashed as files, and the data they list is checked by
   `verify_holdout_inputs.py`. The eight are:
   - `provenance/CHECKSUMS.txt`;
   - `data/reference/prices/MANIFEST.yaml`;
   - `data/reference/binance/CHECKSUMS.txt`;
   - the aggTrades and three Hyperliquid `MANIFEST.csv` files;
   - `provenance/PRE_PHASE4_OUTPUT_CHECKSUMS.txt`.

   The output manifest is new: **`provenance/HOLDOUT_OUTPUT_MANIFEST.txt`**, the SHA-256 and size of every file
   under the trees the holdout path reads. They are:
   - `research/replay_tradable/`, `research/replay_allpriced/` and `research/selection_v2/`;
   - `research/leader/`: the Phase 2 tables at every origin, not only 3 Dec (item 8);
   - the Phase 5 development trees: `research/replay_gray/`, `research/risk_model/`, `research/phase5_population/`,
     `research/portfolio_replay/` and `research/window_report/`.

   `select --output-manifest` writes it, and the manifest is committed. The freeze refuses unless every listed file
   matches the disk and no file under those trees is missing from the list. That closes the Check 3 gap.
5. **The environment block** is written into the freeze file and into the combined hash. It holds:
   - the Python version, and the versions of polars, numpy, pyarrow and pyyaml (and of scipy, if installed);
   - the SHA-256 of `uv.lock`;
   - the OS;
   - `POLARS_MAX_THREADS`.

   The freeze refuses unless `POLARS_MAX_THREADS` is set (ADR-0051 item 5: byte comparisons use 8). The guard
   compares every line except the OS, which is recorded but not compared, so that an OS update cannot block the
   holdout.
6. **Refusals at the freeze:**
   - `frozen: true` is not set in `decision_context.yaml` (as before);
   - any value in `config/risk.yaml` is a string starting with `OPEN`;
   - `POLARS_MAX_THREADS` is unset;
   - the output manifest does not match the disk.
7. **The freeze file's rule line** names the frozen specification: Phase 4 v2 `select-v2` run 4 with ADR-0084 (ADRs
   0066-0084), and Phase 5 revision 4 (ADRs 0086-0097). It no longer names the v1 `selection.rule`.
8. **Stale manifest entries.** The manifests are not edited: `verify_holdout_inputs.py` annotates two sets of
   stale entries.
   - **The 56 stale kline-manifest entries** are the lake's aggTrades copies under
     `data/lake/_raw/data/futures/um/daily/aggTrades/`. They were deleted as redundant (action A0006,
     `decision/adr/RENUMBERING.md`), and drift reads the verified zips instead (ADR-0003). They are annotated as
     stale when missing; one that is present must still match.
   - **111 entries of `provenance/PRE_PHASE4_OUTPUT_CHECKSUMS.txt`** are the Phase 2 leader tables under
     `research/leader/`, 22 per origin plus `gate_counts.csv`. The ADR-0069 gate 7 v2 rerun regenerated them (P4-1,
     `make leader` at five origins, trial log 2026-11-23) after that record was written. An entry that differs is
     annotated as superseded only when the current file matches the output manifest. Otherwise it is a failure.
9. **`verify_holdout_inputs.py` (Check 3)** checks:
   - the freeze, if it exists, through `freeze.verify`; before the freeze, it reports the combined hash that a freeze
     written now would record;
   - every manifest's files;
   - the output manifest;
   - the coverage gap under the output trees;
   - that the shared inputs of each tradable window are byte-identical to the all-priced tree's;
   - the environment block.

   It writes `research/audit/holdout_inputs_verification.md`. It exits non-zero on any problem, and it is rerun
   immediately before the holdout.
10. **Line endings.** Git stores every frozen text file with LF line endings, and this checkout converts them on
    checkout (`core.autocrlf`). The working tree held 56 frozen text files with CRLF and 54 with LF on 2026-11-24.
    So every text file (`.py`, `.md`, `.yaml`, `.txt`, `.csv`, `.json`, `.toml`, `.lock`) is hashed with CRLF
    normalised to LF, as git stores it. Other files (the Parquet shortlist and outputs) are hashed byte for byte.
    - The same commit then gives the same freeze hash on a Windows or a Linux checkout, and a reviewer can check it
      from a clone.
    - The output manifest records sizes and hashes the same way.
    - A change in line endings alone is not a change; any other edit is.

## Consequences
- **Tests** (`tests/test_selection.py`). The freeze:
  - matches, then refuses an edited config, document, source or shortlist;
  - refuses an `OPEN` value in `risk.yaml`;
  - refuses an unset `POLARS_MAX_THREADS` and a stale output manifest;
  - gives the same hash whatever the line endings of the checkout;
  - detects a tampered freeze file.

  The guard refuses a changed environment line. The frozen set includes the Phase 5 modules and documents, and it
  excludes `latency.py`.
- **A change to any hashed file** after the freeze needs a new ADR and a new hash before the holdout (ADR-0091 item
  5). That includes a change to `cli.py`.
- **The v2 holdout entry point is not written yet.** No code replays the 3 Dec origin's holdout window on the
  tradable tree, computes the holdout outcomes for H5, or runs S\*, U\* and G\* on that window.
  - `replay_tradable.py` says the holdout window is never computed, and `portfolio_replay.dev_windows` skips
    origins at or after 3 Dec.
  - The v1 entry point (`replay_coinfilter.run_holdout`) runs the v1 stack.
  - Writing the v2 entry point changes hashed sources, so P5-8 needs a new hash first, unless that code is written
    and tested before the hash is sent.
