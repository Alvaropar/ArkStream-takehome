# ADR-0066: Grade the PnL-identity residual by economic size, not by a cent tolerance and a CV

- Status: Accepted (placeholders); fixed before any grade under it was computed
- Date: 2026-11-22
- Phase: Milestone 1 grades (feeds Phase 2-4 universes at every origin)
- Amends: the `grades` rules (plan v2, ADR-0023), A's `min_pnl_match_share` tolerance and B's `max_offset_cv`
- Aligns with: ADR-0045 (material breach = |residual| > max(10 USDC, 0.5% of equity))
- **Decided after seeing results.** A review pointed out the offset-CV rule. The cutoff quality report then showed that
  it excludes economically small residuals and admits offsets larger than equity (numbers below). The rule and its
  thresholds are fixed here, from the materiality scale already in ADR-0045, before any grade under them is computed.

## Context
Per snapshot, residual `ε_t = pnl_t - (equity_t - net_deposit_t)`. The rule in force:
- **A** needs at least 99% of snapshots with |ε_t| ≤ **0.01 USDC** (`reconcile.pnl_tolerance_tight`).
- Otherwise **B** ("stable scope offset, use the rebuilt book") if `CV = std(ε) / |mean(ε)| ≤ 0.25`, else **C**
  ("unstable_scope_mismatch").

Evidence at the cutoff (`research/quality_report.parquet`):
- **366 addresses are C for unstable scope mismatch, 201 of them for that reason alone.** Their median mean
  residual is 210 USDC, 1.1% of median equity. The 10th and 25th percentiles are 0.08% and 0.34% of equity, so
  addresses are excluded for residuals far below anything that moves a return.
- **The CV is unstable near a zero mean.** A residual that scatters around zero has an exploding CV, so it fails as
  "unstable" however small it is.
- **The 6 B "stable offset" addresses have offsets of 0.04x, 0.35x, 1.2x, 1.3x, 4.8x and 6.6x their median equity.**
  A stable residual larger than the account is not a small scope correction: most of the activity sits outside cross
  margin.
- **The cent tolerance contradicts ADR-0045.** ADR-0045 already calls a breach material only above
  max(10 USDC, 0.5% of equity) when it chooses the return series.

## Decision
Per address, over its snapshots known by the origin (point in time, as before):

1. **Material breach** (ADR-0045's definition): `|ε_t| > max(10 USDC, 0.005 × E_t)`, with the 10 USDC floor when
   `E_t ≤ 0`. `material_match_share` = 1 - material breaches / snapshots.
2. **Equity scale:** `S = max(median E_t, 500 USDC)` (the floor is `leader.returns.min_open_equity_usdc`).
3. **Offset statistics,** all relative to S:
   - `offset_level` = |median ε_t| / S;
   - `offset_mad` = median(|ε_t - median ε|) / S (raw MAD, not rescaled);
   - `offset_shift` = |median ε of the later half - median ε of the earlier half| / S. Halves are by snapshot time:
     the first ⌊n/2⌋ and the rest. It is null with fewer than 4 snapshots.
4. **Rules:**

   | Grade | Condition |
   | --- | --- |
   | A | `material_match_share ≥ 0.99` (and the other A conditions, unchanged) |
   | B, `stable_scope_offset:use_rebuilt_book` | `material_match_share < 0.99` and the offset is **stable** (`offset_mad ≤ 0.005` and `offset_shift ≤ 0.005`) and **bounded** (`offset_level ≤ 0.10`) |
   | C, `scope_offset_too_large` | stable, but `offset_level > 0.10` |
   | C, `unstable_scope_mismatch` | `material_match_share < 0.99` and not stable (including `offset_shift` null) |

   All other A, B and C conditions are unchanged.
5. **Thresholds** (config `grades`, PLACEHOLDER):
   - 0.99 is the existing share;
   - 10 USDC and 0.5% are ADR-0045's materiality, reused for the "stable" dispersion and shift;
   - 500 USDC is the existing opening-equity floor;
   - the 10% cap is new. Up to a tenth of the account's PnL may sit outside the cross-margin scope that we observe
     and copy. Beyond that, cross-margin equity does not describe the trader's capital, and the copy is sized on it.
6. The old columns stay in the report (`pnl_match_share` at 0.01 USDC, `pnl_offset_cv`) for audit; they no longer
   set a grade. The ADR-0045 return-source switch is unchanged.

## Amendment (same day, after computing grades, before anything downstream)
**What happened.** The first version measured stability with `offset_mad ≤ 0.005` (median absolute deviation /
S). Computing grades under it moved 121 addresses from C to B at 3 Dec, and every origin moved by a similar number.
Their median residual was exactly 0, and so was their MAD. They are not stable offsets: they reconcile on most
snapshots and break materially on the rest. At 3 Dec, across those 121:
- the share of snapshots with a material breach was 4% / 9% / 27% (25th / 50th / 90th percentile);
- the typical breach was 4% / 11% / 32% of equity;
- for 9 of them, the largest breach exceeded equity.

A median-based dispersion ignores such outliers by design. The first version therefore contradicted this ADR's own
principle, that a residual is judged by its economic size.

**Correction.** "Stable" now means that, around its median, the residual passes **the same materiality test as A**:
`offset_match_share` = share of snapshots with `|ε_t - median ε| ≤ max(10, 0.005 × E_t)`, required `≥ 0.99`
(`grades.B.min_offset_match_share`, replacing `max_offset_mad`). It is combined with the unchanged `offset_shift ≤ 0.005`
and `offset_level ≤ 0.10`. `offset_mad` stays in the report.

The correction is decided after seeing grade counts. No Phase 2 evidence, replay, selection or return was computed
under either version. The trial log records both. Test:
`test_episodic_material_breaches_are_not_a_stable_offset`.

## Result (amended rule; `scripts/audit_grade_change.py` → `research/audit/grade_change*.csv`)
The old rule, re-derived from the same reports, reproduces the published counts exactly at every origin.

| As of | A / B / C before | A / B / C after | Moves |
| --- | --- | --- | --- |
| 8 Oct | 196 / 104 / 772 | 200 / 102 / 770 | C→A 4, C→B 1, B→C 3 |
| 22 Oct | 217 / 110 / 791 | 223 / 109 / 786 | C→A 6, B→C 1 |
| 5 Nov | 205 / 125 / 836 | 211 / 124 / 831 | C→A 6, B→C 1 |
| 19 Nov | 246 / 112 / 856 | 250 / 111 / 853 | C→A 4, C→B 1, B→C 2 |
| 3 Dec | 178 / 176 / 959 | 182 / 176 / 955 | C→A 4, C→B 1, B→C 1 |
| cutoff | 344 / 158 / 998 | 350 / 153 / 997 | C→A 6, C→B 1, B→C 6 |

**Who moves:**
- **C→A:** addresses whose residual misses the 0.01 USDC tolerance on 1-12% of snapshots, but never by a material
  amount (material match share 0.99-1.0).
- **B→C:** the old "stable offsets" that are large relative to equity or not stable around their median. Their
  material match share is 0. None of them passed the Phase 2 gates at any origin, so no past selection used them.

**The review's premise was only partly right.** Most of the 366 "unstable scope mismatch" exclusions are material
episodic breaches, not small noise, and they remain C. The mean residual quoted in the review (median 1.1% of equity)
averages large breaches with clean snapshots.

## Consequences
- **Every universe changes.** Grades feed every origin's A/B universe, so Phase 2 evidence, the frozen and
  coin-filter replays and the Phase 4 selection must be rerun at all five origins (development data only) before the
  next freeze. The audit's pinned grade counts (344 / 158 / 998 at the cutoff) are replaced by the new ones, recorded
  with this ADR.
- **The freeze is void.** `quality.py` and `config/decision_context.yaml` are hashed files, so the freeze `cbb44708…`
  no longer matches. The holdout already waits for the Phase 5 freeze (ADR-0065), which will include this change.
- **The rule may change the 3 Dec basket.** It is applied at every origin and logged in the trial log whatever the
  outcome; it is not reverted on the basis of selection or development returns.
- **Tests:** residuals near zero with a high CV grade A; a stable offset above 10% of equity grades C; a drifting
  offset grades C; the thresholds scale with equity; point in time.
