# ADR-0137: Three rule variants and the criterion that chooses between them

- Status: Accepted. Stated before any variant was evaluated
- Date: 2026-11-22
- Phase: Phase 4 (selection), item 6

## Decision
1. Variants, all logged in `provenance/trial_log.md`:
   - `rule_a`: ADRs 0130-0132 as stated;
   - `rule_b_coin_filter`: rule_a plus the ADR-0136 coin filter;
   - `rule_c_p10`: rule_a with the key at the 10th percentile.
   Only `key_percentile`, `max_k` and `coin_filter` may differ (enforced in `selection.Rules`).
2. **Criterion.** The most development windows above the matched random-k median (ADR-0133). Ties go to the simpler
   rule in the order rule_a, rule_c_p10, rule_b_coin_filter. No variant may be chosen by a holdout result.
3. Disclosed before evaluation, from training data only: rule_a and rule_c_p10 select the same addresses at all
   five origins, so they cannot differ on the criterion.
