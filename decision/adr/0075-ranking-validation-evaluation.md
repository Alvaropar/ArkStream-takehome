# ADR-0075: Ranking is used only if it predicts (pre-declared IC rule); Phase 4 is evaluated as qualification

- Status: Accepted; the criterion is fixed before it is measured
- Date: 2026-11-23
- Phase: Phase 4 v2, stage S6 and the development evaluation
- Supersedes: ADR-A0137's variant criterion (most windows above the matched random-k median). ADR-A0133's baselines are
  kept in an adapted form.
- Source: `decision/phase-4-v2-methodology.md` sections 7 and 10 (amendment A4)

## Context
**Finding 1:** neither the trip key nor the NAV key predicted the next window. Spearman with the next window's copy
return: trip -0.16 / -0.07 / +0.07 / +0.17, NAV -0.01 / +0.27 / +0.31 / -0.19.

**Finding 5:** the variant choice compared coin execution, not selection.

## Decision
1. **IC test.** At each development origin: the Spearman IC between the posterior mean `m_i` (ADR-0072) and the next
   14-day `α` (ADR-0071, same definition), across every A/B address with both values. The outcome comes from the
   **flat-start** test-window replays, which carry no positions in.
2. **Pre-declared rule.** Phase 5 may use `m_i` to order or tilt the eligible set only if:
   - the mean IC over the four development origins is **≥ 0.05**, **and**
   - the IC is positive at **3 or more** origins.

   Otherwise every eligible address gets the same expected α in Phase 5, and the categories still gate. If τ² is
   robustly 0 at an origin, `m_i = μ0` for everyone there, the IC is undefined, and that origin counts as not
   positive. At about 300 addresses the IC's standard error is about 0.06 per origin, so the 0.05 mean threshold is
   about 1.7 standard errors over four origins.
3. **Reported beside it:**
   - the IC of the unshrunk `α_i`, of the former trip and NAV keys, of the information ratio and of the t-statistic;
   - top-quintile hit rates.
4. **Placebo,** only if τ² is not robustly 0 and E2 addresses exist: replay each E2 copy with the leader's fill times
   shifted by a random 1-7 days (same coins, sizes and costs; seed `[20251203, address prefix, origin]`, 20 shifts).
   If the real copy's `α` does not beat the shifted copies' median, the leader adds nothing beyond exposure and costs.
5. **Development evaluation of the qualification:**
   - **The equal-weight sets.** The E2 set and the E1 ∪ E2 set at equal weight, against all-A/B random draws of the
     same size:
     - draws are an exact enumeration where the pool allows (at most 10,000 subsets), else 1,000 seeded draws;
     - measured on `α` and on the raw base return, with and without 10-11 Oct;
     - per window and pooled.
   - **Category calibration:** the mean next-window `α` by category (E-, E1, E2). The categories must come out in
     order, or the report says they do not.
   - **The gate audit** (first defined in ADR-A0135): per gate, the next-window outcome of passing against
     failing address-windows, on the new gates (detail in ADR-0079 item 4).
   - **The coin policy as an execution policy** (ADR-0073 item 5).
   - **Kept, descriptive only:** Clopper-Pearson on win counts.
   - **Not computed:** deflated Sharpe, White's Reality Check and PBO. Four windows and pools of this size cannot
     support them. The trial log carries the trial count.

### Carried over from ADR-A0133 (archived)
The random baselines use `selection.baselines` in the config: 1,000 draws, seed 20251203. The ADR-A0133 statistics
kept as descriptive (Clopper-Pearson on win counts, MinTRL) are reported as stated in item 5. The rest of ADR-A0133
(the matched random-k win criterion) is superseded by this ADR.

## Consequences
- **Outputs:** `ranking_validation.csv` (with the "ordering used" decision), `walk_forward_v2.csv` and
  `decision/phase-4-v2-results.md`.
- **Determinism:** two runs are byte-identical.
- **Weak ranking evidence becomes a stated result,** "ordering not used", instead of a hidden assumption.
