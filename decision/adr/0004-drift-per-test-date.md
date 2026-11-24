# ADR-0004: Drift estimated per test date from earlier data only

- Status: Accepted; amended by ADR-0046 (forced fills left out of the drift sample)
- Date: 2026-11-19
- Phase: follower replay

## Context
One drift estimate pooled over 8 Oct-2 Dec would give the 8 Oct test window costs measured in November, a
look-ahead in the walk-forward (plan: "at every test date t, the whole procedure runs on data up to t only").

## Decision
- Origins: 2025-10-08, 10-22, 11-05, 11-19 and 12-03 (holdout). At each origin the estimate uses only orders
  whose t + h is before it, over an expanding history from 2025-09-08. Holding-time bands are recomputed as of
  each origin.
- 10-11 Oct is excluded from the development estimate and pooled separately as the stress estimate, which exists
  only at origins after it; the 8 Oct origin has none, and none is borrowed from later.
- Pooled by coin x holding-time band, never per leader (per-leader standard errors 5-25 bps).
- Config: `config/decision_context.yaml: drift` (`origins`, `estimate_window`); code `src/arkstream/drift.py`
  (`estimate`, `at_origin`); outputs `research/drift/`.

## Consequences
Results (all bands, development): within about +-2.6 bps on the four coins at 1 s-5 min at every origin; ETH
the only steady cost (+0.6 to +1.6 bps at 60 s-5 min). Stress 10-11 Oct: BTC +35 bps at 5 min, HYPE -58.
