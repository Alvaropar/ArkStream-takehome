# ADR-0072: Evidence: clustered uncertainty, DerSimonian-Laird shrinkage, own-data robustness and evidence categories

- Status: Accepted (placeholders); fixed before any rerun under it. Item 5's E1 consequence amended by ADR-0090
  (2026-11-23: gray money as an execution measurement)
- Date: 2026-11-23
- Phase: Phase 4 v2, stage S5 (binding by category)
- Replaces: ADR-A0131/A0051's "key > 0 is selectable" and the `single_event` flag
- Source: `decision/phase-4-v2-methodology.md` section 6 (amendment A4)

## Context
**Finding 2:** across 312 A/B copies at 3 Dec, the variance of mean copy returns (1.44e-5) is about the mean squared
standard error (1.48e-5). So noise alone explains the dispersion.
**Finding 3:** the top-ranked copy is positive only because of 10-11 Oct.

A forced positive pick on such evidence is not defensible. Robustness checked on a shrunk quantity is empty when
everything shrinks to the prior.

## Decision
1. **Uncertainty.**
   - `s_i` is the standard error of the ratio `α_i` (ADR-0071), by the delta method with residuals
     `U_{i,t} - α_i G_{i,t}`, clustered by calendar week. It uses a small-sample t (df = weeks with exposure - 1)
     converted to a normal-equivalent by scaling.
   - A check runs beside it: a synchronized moving-block bootstrap with **7-day blocks** and the same calendar blocks
     for every address, 2,000 draws, seed `[20251203, origin ordinal]`.
   - 5- and 10-day blocks are run only if τ² > 0 at that origin.
2. **Is there skill dispersion? DerSimonian-Laird first.** At each origin, over every A/B address with a measured
   `α_i`, with `w_i = 1 / s_i²`:
   - `ᾱ_FE = Σ w α / Σ w` and `Q = Σ w (α - ᾱ_FE)²`;
   - `τ² = max(0, (Q - (k - 1)) / (Σ w - Σ w² / Σ w))`.

   **τ² is robustly 0** when τ² = 0 and Cochran's Q does not reject homogeneity at p = 0.20. Then:
   - the report states that the data shows no measurable differences in skill;
   - nobody can reach E2;
   - the placebo and the extra bootstrap block lengths are skipped.
3. **Shrinkage (normal-normal).**
   - Prior `α ~ N(μ0, τ²)`, with `μ0 = min(0, ᾱ_RE)`, the random-effects mean with weights `1 / (s² + τ²)`. The
     prior never assumes skill.
   - Posterior: `w* = τ² / (τ² + s²)`, mean `m = w* α + (1 - w*) μ0`, sd `v = √w* · s`, and `P(α > 0) = Φ(m / v)`.
   - Behaviour clusters (defined below) serve as prior groups only if each has at least 30 addresses and τ² > 0.
     Otherwise there is one pool.
4. **Robustness, on the address's own unshrunk data.**
   - **Binding:** `α_i` without its best calendar week (the week of largest residual PnL, both sums recomputed) must
     be **> 0**.
   - **Reported:**
     - the own-data `P(α > 0)` without the best week (not binding, so confidence is not demanded twice on about
       12 weeks);
     - α without 10-11 Oct, without the best 1 and 3 weeks, and without the best trip;
     - the best week's share of summed weekly residual PnL, and the top-5 trips' share of positive trip profit.
5. **Evidence categories:**

   | Category | Condition | Consequence |
   | --- | --- | --- |
   | E0 Insufficient | unmeasured (ADR-0070 item 5) | no claim; not handed to Phase 5 |
   | E- No evidence | measured, own `α_i ≤ 0` | not handed to Phase 5 |
   | E1 Weak | own `α_i > 0`, and posterior `P(α > 0) < 0.8` or robustness fails | shadow-only; may serve as the signal source of an ADR-0090 execution measurement |
   | E2 Positive | posterior `P(α > 0) ≥ 0.8`, τ² not robustly 0, robustness holds | eligible for the Phase 5 capital scheme |
   | E3 Persistent | E2 plus a positive `α` in later out-of-sample windows (holdout, then live shadow) | eligible to scale; not reachable inside Phase 4 |

   0.8 is the confidence level of gates 6 and 7 and the former key.

### Carried over from ADR-A0132 (archived): the behaviour clusters used as prior groups
Ward clustering on z-scored features of every A/B address at the origin, cut at **6 clusters**, with no outcome
measure among the features:
- log10 median hold and the IQR of log10 hold over closed leader trips;
- log10 orders per day; log10 median order notional / median equity;
- median and 95th-percentile hourly gross leverage; the share of held hours net long;
- coin concentration (HHI of trip peak notional) and the BTC+ETH share; leader beta to BTC;
- maker share and fills per order; log10 turnover per active day / median equity.

An address with a missing feature is its own group (`unclustered`). The rest of ADR-A0132 (the walk, the pairwise
thresholds, K = 5) is superseded by ADR-0074.

## Consequences
- **Output:** `evidence.parquet` per origin, and a τ² / Q table by origin.
- **Tests:**
  - equal true α gives τ² ≈ 0 and no E2;
  - a one-week record fails robustness;
  - seeds are fixed.
- **The most likely result**, given finding 2, is τ² robustly 0, so no E2: a shadow scheme or a CONDITIONAL GO. That is
  reported as such and never loosened.
