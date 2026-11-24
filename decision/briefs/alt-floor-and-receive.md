# Brief: revise the alt-drift floor and the receive placeholder, then rerun the frozen replay

> ADR numbers below follow the renumbering of 2026-11-23 (ADR-0085; old numbers in
> `decision/adr/RENUMBERING.md`), except the reserved number blocks, which are quoted as they were reserved.

Written 2026-11-21. Project: `C:\Projects\quant-task-arkstream`. ADR numbers reserved: **0160-0169**. Run this
**before** the Phase 4 session; no other session edits the project meanwhile.

## Why

1. **Alt-drift floor (ADR-0048).** For parameterised coins (no aggTrades, about 37% of filled notional) the base drift
   below 300 s may not fall under the coin's own 300 s estimate. After the measured-latency rerun (ADRs 0058-0060) this
   floor sets the cost: 3.68 bps per side at 1.2 s exactly as at 10 s. A measurement now exists for short delays:
   `research/split_orders/` (script `scripts/split_orders.py`) reads Hyperliquid prices from leaders' own next orders.
   At 1-2 s after a leader order, other coins trade at about the leader's VWAP (median 0, mean -0.4 bps vs VWAP; 70
   orders), within 1 s near the deepest fill (215 orders), and over 5-30 s several bps beyond VWAP (conditional on the
   leader trading again). The 300 s floor charges a 1.2 s copy for five minutes of drift.
2. **Receive placeholder.** `replay.receive_ms` is 250 ms; the measured Hyperliquid `userFills` median is 392 ms
   (ADR-0056). It changes which leader fills are grouped into one copy decision, not the total delay.

**This change is decided after seeing that the floor dominates base costs, and it will likely raise returns.** It must
therefore rest on the measurement alone, be fixed in an ADR before any replay result under it is computed, and be
labelled "decided after seeing results".

## Scope

1. **Point-in-time short-delay evidence for alts.** Turn the split-order measurement into per-vintage estimates using
   only sequences whose later order is before the vintage (ADR-0004 discipline; development data only; forced fills
   excluded): for parameterised coins pooled (by liquidity bucket of ADR-0053 if each bucket has at least 30 later
   orders, else pooled), the mean signed move of the next leader order vs the first order's VWAP, in elapsed-time bins
   that bracket the scenario delays (0-1 s, 1-2 s, 2-5 s, 5-10 s). Report counts; a bin below 30 orders has no estimate.
2. **New floor rule, fixed in the ADR before running.** Base, parameterised coins, delay below 300 s:
   drift = max(four-coin proxy at the delay, short-delay HL estimate for the bin containing the delay, 0), where the
   short-delay estimate is the item-1 value; if the bin has no estimate, fall back to the current ADR-0048 floor (the
   coin's own 300 s estimate). Keep the floor at zero: never a favourable drift for alts. Stress keeps its rule
   (ADR-0053) and severe its rule (ADR-0060); optimistic keeps the proxy. If you consider a second variant (for example
   the own 300 s estimate scaled by delay/300), state it and the choice criterion in the ADR **before** running: the
   choice is by agreement with the measured short-delay path, never by replay returns. At most two variants; log both.
3. **Receive placeholder.** Set `replay.receive_ms` to 392 (the measured pooled median, ADR-0056), cite it, and keep the
   250 ms debounce. Report how many copy decisions change grouping.
4. **Rerun** (frozen sizing only, ADR-0052; Phase 2 not rerun): the frozen replay for all nine windows and every
   scenario, the delay grid, the cost surface, `stress_coverage.csv`, figures; two independent runs byte-identical at
   `POLARS_MAX_THREADS=8`; checksum record, `VERIFY.md` and the package updated.
5. **Report** before/after on the 56 gate-passing test windows, separately for each change (floor only, receive only,
   both): base, optimistic, stress and severe means and positives, headroom per side, stress check, cost-surface lower
   bound, holding bands, and parameterised-coin drift per side. Also report base with the old floor beside the new one,
   so the memo can show both.

## Rules

- "Point in time", "Never invent missing inputs", "Determinism", "Traceability" as in the project spec; a seeded-leak
  test for item 1 (a split order after the vintage must not enter its estimate).
- Holdout test window (2025-12-03..2026-01-04) never computed; no selection.
- Record decisions as ADRs 0061-0063: one amending ADR-0048 (floor), one amending ADR-0030/0056 (receive). Trial log
  entries for every variant, including any that look worse.
- Do not touch the latency session's files (`src/arkstream_fetch/hl_ws_latency.py`, `src/arkstream/latency.py`,
  `data/reference/latency/`, `research/latency/`).

## Done when

ruff, mypy, pytest and the audit pass; new tests cover the per-vintage short-delay estimate, the floor rule and its
fallback, and receive grouping; reruns byte-identical; results in `decision/alt-floor-receive-results.md`.

---

## Prompt to start the session

> Read `decision/briefs/alt-floor-and-receive.md` in `C:\Projects\quant-task-arkstream` and carry it out: replace the
> ADR-0048 alt-drift floor below 300 s with a point-in-time short-delay estimate built from leaders' own split-order
> Hyperliquid fills (falling back to the current floor where evidence is thin, never favourable), set the receive
> placeholder to the measured 392 ms, then rerun the frozen replay, delay grid and cost surface and report before/after
> for each change separately and together. The rule must be fixed in an ADR before any result under it is computed and
> labelled as decided after seeing results; choose between variants only by agreement with the measurement, never by
> returns. Read ADRs 0004, 0029, 0056, 0048, 0052, 0053 and 0058-0060, `research/split_orders/summary.md`,
> `scripts/split_orders.py`, `config/execution.yaml` and `src/arkstream/replay_orders.py` first. Frozen sizing only,
> no Phase 2 rerun, holdout never computed, no selection. Record decisions as ADRs numbered 0160-0169.
