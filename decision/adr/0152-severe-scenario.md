# ADR-0152: Add `severe`: the stress costs and rules at the old 60 s / 300 s delays

- Status: Accepted (labelled sensitivity)
- Date: 2026-11-21
- Phase: Phase 3 (follower replay), rerun before Phase 4
- Implements: ADR-0150 item 1 (severe). Relates to: ADR-0080, ADR-0088, ADR-0115, ADR-0120, ADR-0122.

## Context
The replay's stress logic was keyed on the scenario name `stress`: the stress-period drift pool (10-11 Oct) and the
ADR-0120 fallback (`quotes`: `period = "stress" if scenario == "stress"`), the deepest-fill sweep anchor (ADR-0088,
`SWEEP_ANCHOR`), the thin-coin delay (`rules["stress_thin_s"]`, applied only to the delay-less stress run), the
ADR-0115/0122 coverage floor (`stress_floor`: `name.startswith("stress")`) and the stress coverage table and check
(`replay_frozen.STRESS`). With stress moved to 5 s (ADR-0150), the old 60 s / 300 s delays need a scenario that reuses
all of that without changing what `stress` means anywhere else.

## Decision
1. **Config:** `severe: {costs_of: stress, delay_ms: 60000, delay_thin_ms: 300000, label: sensitivity}`.
   `replay_orders.resolve_scenarios` copies stress's cost fields (fee, half-spreads, impact) into severe and records
   `costs: stress`; a `costs_of` scenario may not set a cost field itself (refused), so the two cannot drift apart.
2. **Cost regime instead of name.** Every rule that was keyed on `stress` now reads the scenario's regime
   (`regime(name, settings)`): severe gets the stress-period drift and fallback, the deepest sweep anchor, the 80%
   coverage floor and the unmeasured label. Optimistic, base and stress are unchanged (their regime is their name).
3. **Thin-coin rule.** A coin whose latest completed Hyperliquid 4h bar at the decision is below 1M USDC (or has
   none) gets 300 s, others 60 s, as the old stress did; it now applies to severe only.
4. **Delay grid.** At a fixed delay, severe and stress have the same costs, so severe's grid would be the stress grid
   point for point. Severe is simulated only at its own delays; its address summaries carry the break-even bracket
   from the stress grid, and its folder has no `delay_grid.parquet` (the stress folder has it).
5. **Coverage and stress check.** `research/replay_frozen/stress_coverage.csv` reports the ADR-0122 table (both
   coverage measures, the stress check, the worst-measured sensitivity) for `stress` and for `severe`, with a new
   leading `scenario` column. The economic gate's stress check is read on `stress`; severe is beside it as a labelled
   sensitivity (ADR-0150 item 5).
6. Outputs: `scenario=severe_sqrt_cap_part_ns_sweep_frozen` in every window; severe rows in `sensitivity_*.csv`.

## Consequences
Severe reproduces the previous stress result: with the same costs and delays it is the old stress run under a new
name, so its daily ledgers, funding and band tables are byte-identical to the previous `stress` ones in all nine
windows, and its orders differ only in units: `delay_ms` (+ `delay_s`) for the integer `delay_s`, and horizons in ms
inside `parameter_cells` (ADR-0151). The archived original model (`replay.run`) gains severe in the same way if it
is ever rerun. Tests: `tests/test_measured_latency.py` (severe takes the stress costs and floor, refused restated costs, one
main run per scenario, severe prices exactly as stress at the same delay, the thin-coin rule, the coverage
scenarios) and the published-output audit in `tests/test_pre_phase4.py` (severe ledgers).
