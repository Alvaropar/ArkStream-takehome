# ADR-0074: Phase 4 removes only near-duplicates; co-movement is measured and handed to Phase 5; the walk and K are retired

- Status: Accepted (placeholders); fixed before any rerun under it
- Date: 2026-11-23
- Phase: Phase 4 v2, stage S7
- Supersedes: ADR-A0132 items 2-5 (walk order, the pairwise 0.5 thresholds, K = 5, equal sleeves). ADR-A0132 item 1
  (behaviour clusters) is kept for the ADR-0072 prior groups. ADR-0068 is kept: no credit for an unmeasured pair.
- Source: `decision/phase-4-v2-methodology.md` section 8 (amendment A5 for Σ)

## Context
**Finding 8 and pre-holdout Check 2:**
- the walk's correlation counted flat days;
- on days both copies held exposure, two 3 Dec pairs sat at 0.50-0.51, mostly from 10 Oct; without 10-11 Oct the
  0x2cd9/0x971f pair is 0.10-0.13;
- the overlap measure scores long BNB and long HYPE as 0;
- effective independent bets were 1 to 2.2.

A 0.50 correlation on 20 days has a 95% interval of 0.07-0.77. A hard pairwise filter at this sample size is not
reliable.

## Decision
1. **Copier screen:** unchanged (`copiers.py`).
2. **Near-duplicate:** a pair is a near-duplicate when all three hold:
   - same-coin position overlap ≥ 0.7;
   - the 95% Fisher lower bound of their daily copy-return correlation, on days both copies hold exposure and
     **without 10-11 Oct**, is ≥ 0.5;
   - there are at least 20 such days.

   The weaker member (lower category, then lower posterior mean `m`) is removed, and the pair is named.
3. **Co-movement handed to Phase 5,** for every eligible pair:
   - correlation on the full calendar, on both-exposed days, and on both-exposed days without the crash, each with
     its Fisher 95% interval;
   - downside correlation, on days the ALT factor is in its bottom 20%;
   - joint large-loss frequency: both copies below their own 10th percentile;
   - same-coin overlap and the share of it in the same direction;
   - the **exposure-based risk correlation** `ρ_ij = e_i'Σe_j / √(e_i'Σe_i · e_j'Σe_j)`, with Σ the coin covariance
     estimated **once at the origin** from Hyperliquid daily marks over the 90 days before it, shrunk toward its
     diagonal (Ledoit-Wolf constant-correlation target).
4. **An unmeasured pair gets no diversification credit** (ADR-0068). Phase 5 treats it at correlation 1 for risk.
5. **Retired:** the walk order, the pairwise 0.5 thresholds and fixed K = 5. Basket size and weights belong to
   Phase 5.

## Consequences
- **Output:** `comovement.parquet` and the duplicate decisions per origin.
- **Tests:**
  - an unmeasured pair gets no credit;
  - crash days are excluded where stated;
  - Σ has one fit date before the origin.
- **Check 2 is settled.** Correlation is measured on both-exposed days, and diversification is no longer claimed from
  pairwise thresholds.
