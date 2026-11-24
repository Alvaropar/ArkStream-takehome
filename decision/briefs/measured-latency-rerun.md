# Brief: rerun Phase 3 with the measured copy delay

> ADR numbers below follow the renumbering of 2026-11-23 (ADR-0085; old numbers in
> `decision/adr/RENUMBERING.md`), except the reserved number blocks, which are quoted as they were reserved.

Written 2026-11-21. Project: `C:\Projects\quant-task-arkstream` (ArkStream Hyperliquid copy pilot, take-home).
ADR numbers reserved for this session: **0150-0159**. Run this **before** the Phase 4 session starts; no other
session edits the project meanwhile.

## Why

The replay's delay scenarios were assumptions: optimistic 1 s, base 10 s, stress 60 s (300 s for thin coins). The
delay is now measured (ADR-0038, ADR-0056): Hyperliquid `userFills` receive delay (pooled 284 fills: p50 392 ms,
p99 1,218 ms) + 250 ms debounce + ~120 ms compute + Binance USD-M Demo acknowledgement (p50 354 ms, p99 2,767 ms)
gives a total of about 1.1-1.2 s at the median and 3.5-4.4 s at the 99th percentile. The user's decision
(2026-11-21), made from the measurement and before any selection result:

| Scenario | New delay | Basis |
| --- | --- | --- |
| optimistic | 1 s (unchanged) | about the measured 10th percentile total |
| **base** | **1.2 s** | the measured median total (from a home laptop on Wi-Fi; a professional setup would be faster) |
| **stress** | **5 s, all coins** | the measured 99th percentile total (4.4 s summing quantiles), rounded up |
| severe (new, labelled sensitivity) | 60 s, 300 s for thin coins | the old stress delays, kept because the recordings show disconnects of 2-17 s that the 99th percentile of delivered messages does not capture |

Costs other than the delay (fees, half-spreads, impact, the stress multipliers, the stress fallback) are unchanged:
stress keeps its 3/15 bps half-spreads, triple impact and stress-period drift; severe uses the same stress costs with
the old delays.

## What has to change (a config edit is not enough)

- **Delays are whole seconds in the code.** `replay_orders.order_inputs` casts the delay to an integer
  (`h.cast(pl.Int64)`, line ~178), drift cells are keyed by an integer `horizon_s` (`drift.py`, `replay_market.py`),
  and the aggTrades lookups use `h * 1000` offsets from `drift.horizons_s`. 1.2 s would silently become 1 s. Move
  delays and drift horizons to milliseconds end to end (`delay_ms`, `horizon_ms`), keeping the existing integer
  outputs readable (a `horizon_s` float column is fine), and add a test that 1.2 s is not truncated.
- **Drift horizons.** Add 1.2 s and 5 s to `drift.horizons_s` (keep 1, 10, 60, 300 for the delay grid and the
  approximate method), rerun `python -m arkstream drift`, and check the new cells exist at every origin for the
  four aggTrades coins and the four-coin proxy.
- **The severe scenario.** The replay's stress logic is keyed on the name `stress` (stress-period drift pool,
  thin-coin delay, the stress fallback, the ADR-0055 coverage rule and stress check). Add `severe` as a scenario that
  reuses all of that with the old delays, without changing what `stress` means elsewhere.
- **Delay grid.** Add 1.2 s and 5 s to the break-even delay grid (1, 1.2, 5, 10, 60, 300 s).
- **Config:** `config/execution.yaml` scenarios (base 1.2 s, stress 5 s with no thin-coin override, severe 60 s /
  300 s), with comments citing ADR-0056 and the new ADR.

## Then rerun (frozen policy only, ADR-0052)

1. `python -m arkstream drift`.
2. `python -m arkstream replay --frozen` (all nine windows; holdout never computed).
3. The cost surface (ADR-0050) on the new base.
4. The size study only if its horizons changed (they should not).
5. `make figures`; refresh `research/replay_frozen/stress_coverage.csv` under ADR-0055.
6. Two independent runs byte-identical at `POLARS_MAX_THREADS=8`; update the output checksum record, `VERIFY.md` and
   the package.

Report, before vs after, on the 56 gate-passing test address-windows: base, optimistic, stress and severe mean,
positives, headroom per side, the stress check (pass / fail on loss / fail unmeasured), the cost-surface lower bound,
and the holding-band table. State plainly how much the measured delay changed the result.

## Rules

- Phase 2 does not depend on the copy delay: do not rerun it.
- "Point in time", "Never invent missing inputs", "Determinism" and "Traceability" as in the project spec; drift cells
  at the new horizons are estimated only from data before each origin, as before (ADR-0004).
- The holdout test window (2025-12-03..2026-01-04) is never computed; selection does not start.
- Record the decision in an ADR (numbers 0150-0159) that amends ADR-0038 and the scenario table of the plan's
  "Follower replay" section; it states that the delays come from measurement and were chosen before Phase 4.
- Do not touch the latency session's files (`src/arkstream_fetch/hl_ws_latency.py`, `src/arkstream/latency.py`,
  `data/reference/latency/`, `research/latency/`).

## Done when

ruff, mypy, pytest and the audit pass; the new tests cover millisecond delays and the severe scenario; the reruns
are byte-identical; `decision/pre-phase-4-results.md` (or a new `decision/measured-latency-results.md`) has the
before/after tables.

---

## Prompt to start the session

> Read `decision/briefs/measured-latency-rerun.md` in `C:\Projects\quant-task-arkstream` and carry it out: switch the
> follower replay to the measured copy delay (base 1.2 s, stress 5 s for all coins, optimistic 1 s unchanged, and a
> new labelled `severe` scenario with the old 60 s / 300 s delays), which needs delays and drift horizons in
> milliseconds end to end, new drift horizons at 1.2 s and 5 s, and the delay grid extended. Then rerun drift, the
> frozen replay and the cost surface, verify two byte-identical runs, and report before/after on the 56 gate-passing
> test windows. Read ADRs 0038, 0056, 0052 and 0055, `config/execution.yaml`, `config/decision_context.yaml`, and
> `src/arkstream/replay_orders.py`, `replay_market.py`, `replay_frozen.py` and `drift.py` first. Frozen sizing only,
> no Phase 2 rerun, holdout never computed, no selection. Record decisions as ADRs numbered 0150-0159.
