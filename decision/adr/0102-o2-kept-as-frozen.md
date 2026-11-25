# ADR-0102: O2 stays at its frozen bound for the gray

- Status: Accepted (the user's decision, 2026-11-25: "Yes, keep it", answering "Keep O2 as frozen and record that
  decision?"). ADRs 0088 and 0099 are in the frozen set (`freeze.FROZEN_ADRS`), so their status lines are not edited.
  The decision is recorded here and in the index row.
- Date: 2026-11-25
- Phase: Phase 5 (revision 4), P5-9, after the holdout

## Context
**What O2 is** (ADR-0088 item 1; `config/risk.yaml` `limits.O2_limit_price: stress_p99_shortfall_by_bucket`).
- Every order goes out as an IOC with a limit price away from the decision mark.
- The distance is the stress scenario's p99 price shortfall for the coin's liquidity bucket (ADR-0053 buckets).
- Whatever cannot fill inside the limit is cancelled. The next update recomputes from state (ADR-0087).

**The frozen bounds** (ADR-0099 item 5; `research/cost_runs/o2_bounds.csv`).
- They are measured on the development stress runs, filled trigger legs of every A/B address, without the fee,
  against the mid at the leader's fill.

| Bucket | Orders | p99 (the bound) | Median |
| --- | ---: | ---: | ---: |
| ≥ 5M | 32,350 | 430 bp | 6.8 bp |
| 1M-5M | 3,893 | 2,682 bp | 30.4 bp |
| 250k-1M | 1,832 | 436 bp | 26.5 bp |
| < 250k | 202 | 408 bp | 29.9 bp |

**In the holdout:**
- Run A does not simulate O2 (ADR-0098).
- In run B the frozen bound rejected no order.
- Run C's shadow O2 would have rejected 14 orders. Its bound is a per-order stress cost on C's refitted model, so it
  is not like-for-like with a bucket p99 (ADR-0099 item 9).

**The question.** The bounds are 4-27% from the mark, so O2 almost never binds. The user was asked whether to tighten
it for the gray or keep the frozen bound. No tighter value was computed.

## Decision
1. **O2 stays at its frozen bound for the gray:** the values in `research/cost_runs/o2_bounds.csv`, unchanged.
2. **Nothing in `config/risk.yaml`, the deliverables or the frozen set changes.**
3. **A change needs its own ADR, set on data not used here.** The holdout's shadow count (14) is reported and is not
   used to set a bound.

## Consequences
- **Live orders have almost no price protection from O2.** A gray order can fill far through a thin book or a fast
  move. What bounds the damage:
  - **the stress cap:** stress loss plus exit cost ≤ 750 USDC minus the loss to date, at every update and hourly;
  - **the loss cap:** revert to paper and flatten at 750 USDC;
  - **C1:** the 14-day median real shortfall against the stress scenario's;
  - **the revert rule:** back to paper when the live shortfall exceeds the stress scenario's at two consecutive
    reviews.

  These act after a bad fill, not on the order itself. The memo and the protocol say so.
- **The gray measures what a tighter O2 would have cost.** Every live fill's shortfall against the decision mark is
  recorded, so the reviews can show how many fills a tighter bound would have rejected.
- **The 1M-5M bound (2,682 bp) is out of line** with the other buckets (408-436 bp). Why is not checked here. It is
  recorded, not changed.
- **No other open item changes:**
  - the ordering at later origins and the standard-error floor in τ² (ADR-0101) stay open;
  - the limits' sign-off (A10) and the re-qualification on current data (A12) come before any live order.
