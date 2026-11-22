# ADR-0141: Holdout freeze re-cut on the executable coin filter

- Status: Accepted
- Date: 2026-11-22
- Phase: Phase 4 (selection), item 7
- Supersedes: ADR-0139 (its hash `ec6d0c22...fdfeae` was never sent to the reviewers and is void)

## Decision
1. `provenance/HOLDOUT_FREEZE.txt` (`select --freeze`, the ADR-0139 mechanism, unchanged) now hashes 45 files:
   - the four config files: `decision_context.yaml` with `frozen: true`, `selection.rule: rule_b_coin_filter` and
     the variant's `replay_dir: research/replay_coinfilter`;
   - the rule sources, now including `replay_coinfilter.py`, the coin filter in `replay_orders.py` /
     `replay_sensitivity.py` and the holdout path (single-window branch, guarded `trade_queries`);
   - the new 3 Dec shortlist, from the filtered replay.
   The timestamp is `frozen_at: 2026-11-21T19:33:09Z` (the machine's UTC clock).
2. **freeze_hash = `cbb44708d6569d55c809cff5daed3fc63004a97c2b3a3e409db79b84b00a2e8b`**.
3. The guard is unchanged: `selection.load_origin`, `replay.run`, `replay_coinfilter.run` / `run_holdout`,
   `run_sensitivities(window=...)` past 3 Dec, and `trade_queries(holdout=True)` all refuse a window ending after
   2025-12-03 unless every hash matches.
4. Item 8 may add only `src/arkstream/holdout_report.py` (outside the hashed set) to score the holdout tree written
   by `replay --coin-filter --holdout`. Any change to a hashed file needs a new ADR and a new hash sent before the
   run.
