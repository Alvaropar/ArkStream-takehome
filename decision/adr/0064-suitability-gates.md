# ADR-0064: Count address suitability gates at each origin

- Status: Accepted
- Date: 2026-11-19
- Phase: Phase 2 rework

## Context

ADR-0009 adds recency, execution style and rebuild quality to the existing evidence and risk gates.

## Decision

PLACEHOLDER thresholds fixed for this rework before evaluation: median completed uncensored hold at least one minute, at most 24 distinct orders per day of observed history, maker share at most 70%, and at least one eligible trade during the trailing 14 days (inclusive). Count each condition separately. The active gate uses fills. A minimum of ten fit intervals is needed for a measured rebuild gate, and at least 90% must be within 1% of opening equity. Keep the existing agreement gate with the exact-interval inputs, the 20 completed usable round trips and all tail-risk gates. An absent measurement cannot pass. Count all-pass only when every component passes. No cutoffs were optimized on the counts.

## Consequences

The smaller A/B universes and stricter accounting change both the numerator and denominator of gate comparisons. Per-origin pass, fail and unmeasured counts are reported. See the Phase 2 rework report and trial log.
