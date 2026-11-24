# ADR-0079: P4-6 to P4-8 details: which pairs, the co-movement measures and Σ, the S3 gates in v2, the qualification tests and the hand-off columns

- Status: Accepted (placeholders); written before any pair, set, test or hand-off row was computed
- Date: 2026-11-23
- Phase: Phase 4 v2, steps P4-6 (stage S7), P4-7 (development evaluation) and P4-8 (hand-off)
- Pins details ADRs 0073-0075 and methodology sections 8-10 leave open. Protocol of ADR-0070

## Decision
1. **S1-S3 at the origin** (all from data before it):
   - S1: grade A/B (the universe);
   - S2: `all_gates_pass` from `research/leader/origin=<o>/evidence.parquet` after the ADR-0069 rerun (checked in
     the trial log before the join);
   - S3: `sel_equity_band` (Phase 2 median equity in [5k, 2M], ADR-A0130), `sel_break_even` (the tradable tree's
     training delay grid, the ADR-A0130 rule), `sel_tradable_share` and `sel_direction` (ADR-0076 items 6-7) and
     `sel_copier` (the copier screen at the origin, `copiers.screen`; weaker member = lower evidence category
     (E2 > E1 > E- > E0), then lower posterior mean m (unmeasured last), then address). `sel_hold_band` is a
     diagnostic (ADR-0073 item 4).
2. **Pairs (P4-6):** every pair among the addresses in E1 ∪ E2 that pass S1-S3 at the origin, on the common window
   (ADR-0070) and the tradable training replay.
   - Daily copy return: the replay's daily NAV return (`daily_copy_twr`). "Both exposed" = both copies have
     `G_t > 0` at the start of the day (ADR-0077) on a valid day.
   - Correlations: full calendar (≥ 4 common days), both exposed (≥ 4), both exposed without 10-11 Oct (≥ 20, the
     duplicate minimum), each with its two-sided Fisher 95% interval.
   - Downside correlation: days whose ALT return (origin membership) is at or below its 20th percentile over the
     window; at least 10 such days with both returns, else null.
   - Joint large-loss frequency: share of common days on which both copies are below their own 10th percentile of
     daily NAV return over the window.
   - Overlap: cosine of the signed start-of-day exposures over (day, coin) on valid days; direction share = the
     same-sign part of Σ |e_i e_j| over shared (day, coin).
   - **Σ for the risk correlation:** daily Hyperliquid returns of the origin's pooled tradable coins over the 90
     days before it, coins with a return on at least 60 of those days, complete-case days (at least 30), Ledoit-Wolf
     (2004) constant-correlation shrinkage with its estimated intensity; fit date = the origin. `e_i` = the copy's
     mean signed exposure by coin over the window's valid days. A copy that held a coin outside Σ, or Σ unmeasured,
     gives a null risk correlation.
   - **No credit when unmeasured:** a pair without the ex-crash both-exposed correlation is `measured = false`;
     `corr_for_phase5` and `risk_corr_for_phase5` are 1 whenever the measure is missing (ADR-0068).
3. **Duplicate screen:** near-duplicate as ADR-0074 item 2. Resolution is greedy from the strongest member (E2
   before E1, then higher m, then address): an address is removed when it is a near-duplicate of one already kept,
   and the pair is named.
4. **Qualification tests (P4-7), on the four development test windows** (flat start, tradable replay, base):
   - sets: the hand-off E2 set and E1 ∪ E2 set at the origin (after S1-S3 and the duplicate screen);
   - set α at equal weight = Σ_i Σ_t U / Σ_i Σ_t G (pooled sleeves, the origin's betas); set raw return = mean of
     the sleeves' test copy returns (`address_summary.copy_return`); without 10-11 Oct: those days removed from α's
     sums, and the raw return compounded over the other days;
   - random baseline: subsets of the same size k from every A/B address with a defined value of that statistic,
     exact enumeration when C(n, k) ≤ 10,000, else 1,000 draws with
     `numpy.random.default_rng([20251203, origin ordinal, k, statistic index])`; win = set value above the random
     median; pooled = the mean over windows and the win count with its Clopper-Pearson 95% interval;
   - category calibration: mean next α by category (E-, E1, E2) per origin and pooled over address-windows;
     "ordered" means mean(E-) < mean(E1) < mean(E2) wherever both sides exist;
   - gate audit (ADR-A0135): for each S3 gate, measurability, robustness and S2, the mean next α and next raw return
     of passing against failing address-windows, pooled;
   - coin policy as an execution policy (ADR-0073 item 5): per address-window, the tradable copy against the
     all-priced copy (raw return and α with the same betas), for all A/B and for the hand-off sets. Never used to
     select.
   - Outputs: `walk_forward_v2.csv`, `calibration_v2.csv`, `gate_audit_v2.csv`, `coin_policy_v2.csv`.
5. **Hand-off (P4-8)** `research/selection_v2/origin=<o>/eligible.parquet`, one row per E1/E2 address passing
   S1-S3 and the duplicate screen, with: category, α, s, m, v, P(α > 0), τ² and the robustly-0 flag; the robustness
   columns; α_static, α_timing, top-3 share; utilisation mean, p50, p95; capacity inputs (median equity, `E_ref` =
   the equity of the latest snapshot known by the origin (Phase 2 `snapshot_src_row`; the ADR-0052 frozen check is
   not repeated here, stated), the order-size profile (median and p95 filled copy order notional in the training
   window, the leader's median order notional and order-to-volume p50 / p95), the non-tradable share); the exposure
   profile (mean signed exposure by coin, copy betas); training stress return and drawdown; the evidence keys
   (`snapshot_src_row`, `last_fill_src_row`, `tid`, `oid`). Also `comovement.parquet`, `coins.parquet` and
   `ranking_validation.csv` (ADR-0078).
6. **The 3 Dec origin** has no development test window (the holdout is never computed), so it enters the hand-off,
   not the tests.
7. **Tests:** an unmeasured pair gets no credit; crash days are excluded where stated; Σ has one fit date before
   the origin; the hand-off schema is fixed (`tests/test_selection_v2.py`).
