# ADR-0151: Delays and drift horizons in whole milliseconds; 1.2 s and 5 s horizons; delay grid extended

- Status: Accepted
- Date: 2026-11-21
- Phase: Phase 3 (follower replay), rerun before Phase 4
- Implements: ADR-0150. Amends: ADR-0004 (horizon list only; the point-in-time rule is unchanged), ADR-0083 (delay
  grid and break-even columns), ADR-0088 (size-study horizons pinned).

## Context
Delays were whole seconds in the code, so the measured 1.2 s base (ADR-0150) would silently have become 1 s:
`replay_orders.order_inputs` cast the delay to an integer (`h.cast(pl.Int64)`) before `ack = event + delay x 1000`;
drift cells were keyed by an integer `horizon_s` (`drift.py`, `replay_market.py`, `Parameters`); the aggTrades
queries used `h * 1000` offsets from `drift.horizons_s`; the break-even bracket had integer `_s` columns. A config
edit alone was not enough.

## Decision
1. **Milliseconds end to end.** `DriftRules.horizons_ms`, `approx_horizons_ms`, `approx_min_horizon_ms`; every
   per-order drift row, pooled cell, warm-up cell and liquidity-bucket cell is keyed by `horizon_ms` (Int64);
   `Parameters` looks cells up by ms (the 300 s threshold is `LONG_MS` = 300,000); the aggTrades tape queries are
   event + each `horizon_ms`; `order_inputs` takes the delay as an int (ms) or `(normal_ms, thin_ms)` and sets
   `ack_ms = event_ms + delay_ms` exactly; a non-integer delay (for example 1.2 passed as seconds) is refused.
2. **Config.** `config/decision_context.yaml` keeps `drift.horizons_s` in seconds (1.2 allowed);
   `drift.seconds_to_ms` converts each value exactly (decimal arithmetic) and refuses a value finer than 1 ms or not
   positive. `config/execution.yaml` gives delays as `delay_ms` / `delay_thin_ms` integers; the old `delay_s` /
   `delay_thin_s` keys are refused so a stale config cannot be read in seconds.
3. **Readable outputs.** Integer ms columns, each with a float seconds copy: drift CSVs `horizon_ms` + `horizon_s`;
   `drift_cells.parquet` `horizon_ms`; follower orders `delay_ms` + `delay_s`; delay grids `delay_ms` + `delay_s`;
   address summaries `break_even_delay_lo_ms` / `_hi_ms` + `break_even_delay_lo_s` / `_hi_s` (floats, replacing the
   integer `_s` columns).
4. **Drift horizons**: 1, 1.2, 5, 10, 60, 300 s. The 1.2 s and 5 s cells are estimated exactly like the others:
   at each origin only from orders whose t + h is before it, over the expanding history without 10-11 Oct, the crash
   sample separately and only at origins after it (ADR-0004, ADR-0112). The approximate method keeps 300 s and
   3,600 s, never below 5 minutes.
5. **Delay grid** (ADR-0083 break-even) = the drift horizons: 1, 1.2, 5, 10, 60, 300 s, for every scenario that has
   its own costs (optimistic, base, stress; severe shares the stress grid, ADR-0152). Every scenario delay
   (including a thin-coin delay) must be a grid point, or the replay stops before any work (`delay_plan`): that is
   what guarantees the tape holds the acknowledgement print. A scenario's main run is its grid point when its delay
   is the same for every coin (optimistic 1 s, base 1.2 s, stress 5 s), so it is simulated once.
6. **Size study (ADR-0088)** keeps its own horizons, 1, 10, 60 and 300 s (`replay_size.HORIZONS_MS`): the new
   horizons serve the replay's delays, not the size study, whose result (no qualifying size term) is unchanged. Its
   outputs are byte-identical to the previous run.

## Consequences
The old cells reproduce exactly: all 16,278 development and stress rows at 1, 10, 60 and 300 s are equal to the
previous `research/drift` output (only the key column changed from `horizon_s` to `horizon_ms` plus a float
`horizon_s`); the hold bands and the coverage report are byte-identical. New: 358 development and 278 stress rows
(1.2 s and 5 s, aggTrades). The four aggTrades coins have an `ok` `all`-band cell at 1.2 s and 5 s at all five
origins (so the four-coin proxy exists for parameterised coins), and stress cells from 22 Oct on (none at 8 Oct, none
borrowed). Consumers of the changed columns: `scripts/make_figures.py` (none of them), Phase 4 (not started).
Tests: `tests/test_measured_latency.py` (exact conversion, the 1.2 s aggTrades print is used, ack at exactly
event + 1,200 ms, cells keyed by ms with no borrowing from 1 s, the bracket keeps 1.2 s, the grid check, the new
cells at every origin); existing drift and replay tests moved to ms.
