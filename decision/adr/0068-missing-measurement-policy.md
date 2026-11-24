# ADR-0068: One policy for missing measurements: no credit for what was not measured

- Status: Accepted
- Date: 2026-11-23
- Phase: Phase 2 gates, Phase 4 selection (walk, key)
- Amends: ADR-A0132 item 4 ("an unmeasured pair does not block")
- **Decided after seeing results.** A review noted the inconsistency, and pre-holdout Check 2 found the basket's
  diversification unverified.

## Context
Phase 2 gates treat a missing measurement as a failure. The ADR-A0132 walk did the opposite: a pair without a measured
correlation or overlap did not block a candidate. A missing input cannot be disqualifying for data quality and
harmless for diversification at the same time.

## Decision
| Missing measurement | Treatment |
| --- | --- |
| Data-quality or evidence condition | cannot pass (unchanged) |
| Risk condition | no risk credit: the gate fails as unmeasured (unchanged) |
| **Co-movement of a candidate with a chosen address** (correlation under `min_common_days`, or no overlap measurable) | **blocks the candidate.** Reason: "pair unmeasured: diversification not verified". The basket is never described as diversified on an unmeasured pair. |
| Return condition (the key) | not evidence of a positive return: an unmeasured key is not selectable (unchanged) |
| Style diagnostics (ADR-0067) | reported as unmeasured; they bind nothing, so no credit is claimed |

The walk change is in `selection.walk`. Co-movement continues to be defined as in ADR-A0132. Whether correlation
should be measured only on days when both copies hold positions (pre-holdout Check 2) is a separate open decision.

## Consequences
At 3 Dec every pair among the eligible addresses is measured (129 common days), so the 3 Dec walk is unchanged by
this rule alone. It binds where copy series are short. Tests: an unmeasured pair blocks, and a measured
low-correlation pair still passes.
