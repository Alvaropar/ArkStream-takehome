# ADR-0120: Price parameterised stress orders without their own crash-sample cell

- Status: Accepted (rule and placeholders fixed before any result under it was computed)
- Date: 2026-11-21
- Phase: pre-Phase 4 fixes (the user's change 2 before item 10)
- Amends: ADR-0080 (stress path of parameterised coins), ADR-0114 (stress unchanged there)

## Context
A parameterised stress order needs the coin's own 300 s estimate from the 10-11 Oct crash sample. After forced fills
left the sample (ADR-0112) many thin coins have fewer than 30 voluntary orders there, and before 10 Oct there is no
sample at all, so those orders stay unpriced. With ADR-0115 this left 25 of the 56 gate-passing stress results
unmeasured (14, 4, 5 and 2 at the four test origins). The user asked for a pre-stated rule instead, with the target
that no gate-passing test window falls below 80% priced intents.

## Decision
For parameterised coins only (the four direct coins keep their observed aggTrades move):

1. **Own stress estimate missing.** Where the coin has no stress-period 300 s cell at the vintage (band row, else the
   coin's `all` row), use F = max(B, 3 x max(D, 0), 0):
   - B is the stress-period 300 s estimate of the order's **liquidity bucket**: the mean signed drift of all
     parameterised-coin leader orders in the 10-11 Oct sample (forced fills excluded, coins passing the price check
     as of the vintage, the approximate method of ADR-0005, observations ending before the vintage) whose coin's
     latest completed Hyperliquid 4h bar at the order time falls in the same USDC volume bucket as the follower
     order's latest completed bar at its decision. Buckets: below 250k, 250k-1M, 1M-5M, 5M and above (PLACEHOLDER).
     A bucket needs at least 30 measured orders (the cell minimum).
   - D is the coin's own development-period 300 s estimate (same lookup); the multiple 3 (PLACEHOLDER) is the
     stress-to-base ratio already used for half-spreads (15/5 bps) and impact (ADR-0084), and the floor at zero
     keeps a favourable base drift from becoming a favourable stress drift.
   - With one of B and 3 x max(D, 0) missing the other is used; with both missing the order stays unpriced
     (`no_drift_cell`).
   - **Floor at zero (added 2026-11-21 after seeing the bucket estimates, before any replay result under this
     rule):** F = max(B, 3 x max(D, 0), 0). The crash-sample bucket means are strongly negative for mid-liquidity
     coins (about -160 bps for 1M-5M and -80 to -90 bps for 250k-1M at 300 s: leaders bought into the fall and the
     price kept falling), so without the floor a coin lacking its own base estimate would get a large favourable
     stress drift. A fallback is an assumption, not a measurement of the coin, so it is never favourable; a coin's
     own measured stress cell keeps its sign (ADR-0080).
2. **No crash sample yet** (vintages before the stress period, including 8 Oct and the warm-up days): the four-coin
   stress proxy below 300 s is replaced by 3 x max(P, 0), with P the development four-coin proxy at the same
   horizon, and the own estimate by item 1 (B does not exist there, so F = 3 x max(D, 0)).
3. The stress drift is then, as before, max(proxy, own) below 300 s and the own estimate at 300 s. `method` records
   which part fell back and `parameter_cells` the cells used (bucket cells are `coin = bucket:<label>`).
4. Configuration: `config/execution.yaml: replay.stress_fallback` (multiple, bucket edges, minimum orders).

## Consequences
Stress coverage before and after, per gate-passing test window, is reported in `decision/pre-phase-4-results.md`;
the 80% target is reported, not enforced (ADR-0115 still marks any window below it unmeasured). Stress results now
rest partly on a stated assumption (bucket pooling, a 3x multiple) for thin coins; base and optimistic are
unaffected. Tests: `tests/test_pre_phase4.py` (each fallback branch, bucket assignment and pooling).
