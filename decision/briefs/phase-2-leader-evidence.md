# Brief: Phase 2, leader evidence

> ADR numbers below follow the renumbering of 2026-11-23 (ADR-0085; old numbers in
> `decision/adr/RENUMBERING.md`), except the reserved number blocks, which are quoted as they were reserved.

Written 2026-11-19. Project: `C:\Projects\quant-task-arkstream` (ArkStream Hyperliquid copy pilot, take-home).
ADR numbers reserved for this session: **0020-0039**.

## Why

Phase 2 is Day 2 of the plan's work plan: measure every grade A and B address at two levels, so that Phase 3
(follower replay) and Phase 4 (selection) start from per-address evidence that is point in time. The method is
fixed by the plan's section **Leader evidence**; this brief only says what to build first and with which data.

## Data to use (Binance first)

- Reference prices: `data/reference/prices/` through `prices.load_reference` / `scan_reference` and
  `prices.price_asof` (Binance 1m closes, known at bar close, 60 s tolerance, package print fallback, else
  unpriced; ADR-0002). Hourly valuation is possible from these.
- Fills, snapshots, positions, grades: `pipeline.load_inputs`, `pipeline.positions_asof`,
  `positions.order_fills / continuity / rebuild` (round trips flat to flat), `quality` (grades A/B/C at asof),
  `copiers.screen`. Reuse them; do not re-derive positions.
- **No Hyperliquid data yet.** A separate session is fetching Hyperliquid funding and checking prices
  (`decision/briefs/hyperliquid-data.md`). Until it lands: book returns and round-trip returns are **ex-funding**
  and labelled so; account returns from snapshots include funding implicitly (equity is total account value,
  ADR-A0007), so the account-vs-book cross-check gap is reported with that caveat, not "fixed". The 10 coins
  without a Binance reference (APEX, BLAST, LAUNCHCOIN, MNT, PURR, REQ, YZY, FTT, FOGO, MEGA) are valued at
  package prints where `price_asof` finds one, else unpriced and flagged per address (share of exposure
  unpriced). Design the interfaces so a funding table (`ts, coin, funding_rate`) and a second price source can
  be added later without changing outputs that do not use them.

## Scope (in order)

1. **Account returns** from snapshots, flow-adjusted, start-of-day (base) and end-of-day (sensitivity)
   conventions as in the plan; exclude days where they differ by more than a threshold or opening equity is
   below 500 USDC; a snapshot gap gives one return over the gap, never interpolated; coverage reported.
2. **Book returns**: positions rebuilt from fills, valued daily and hourly at reference prices; cross-checked
   against account returns per address (correlation, tracking gap), flagged where they disagree.
3. **Round trips** (flat to flat per coin): return, return per day held, MAE and best unrealised gain (from
   hourly marks, labelled with their resolution), win rate, win/loss size, mean without the top 1%, open
   positions at the test date valued at the reference price and counted. Leader's own prices and fees, no
   follower delay (that is Phase 3).
4. **Tail-risk gates**: intraday drawdown from the hourly book; worst day, worst 3 days, max drawdown; stress
   shock = the largest observed move per coin **before the origin** applied to typical and peak exposure (for
   the 8 Oct origin the 10 Oct crash is not yet known: say so, do not use it); leverage p95 and distance to
   liquidation where computable (state the margin assumption); liquidations and ADL from fill `dir`; top-1%
   dependence.
5. **Profiles**: median holding time and band (same bands as `drift.BAND_LABELS`), orders per day, maker
   share (the 92 addresses above 70% maker), fee rate from the fee column, median equity band (20k-2M start),
   typical order size against Binance traded volume for that coin (impact risk).
6. **Evidence count**: completed round trips per address at each origin; the minimum (20-30) is a placeholder
   set on development data only, by ADR.

Every value is computed **as of each origin** in `config/decision_context.yaml: drift.origins`
(2025-10-08, 10-22, 11-05, 11-19, and 12-03 for the holdout), from data up to that origin only. Gates are
computed, not applied to select anyone: Phase 4 does selection.

## Out of scope

Follower replay, delays, drift, spread, impact, funding costs (Phase 3); selection, ranking, baselines, the
freeze hash and the holdout (Phase 4). Do not open holdout-period results beyond computing the 3 Dec origin's
inputs. HIP-3 and spot (ADR-A0007). Any order or network code.

## Rules (project spec, verbatim where quoted)

- "Inputs (read-only; never modify)".
- "Point in time: every function that produces values takes an `asof` timestamp and uses only rows with
  timestamp <= asof". CUTOFF from `config/decision_context.yaml` (the last fill, 2026-01-04T23:59:42.020Z).
- "Never invent missing inputs: no imputed prices, funding or quotes. Missing -> flag and exclude, with a reason".
- "Determinism: same inputs give byte-identical outputs" (every table with a total sort order; ADR-0006).
- "Traceability: every derived row keeps the source keys (trader, tid, oid, timestamp)".
- "No code path that sends real orders, now or later, unless explicitly enabled."
- Extend the leak tests: add the new tables to `tests/pit_check.py`'s invariance check and add at least one
  seeded leak for Phase 2 (for example a round trip closed after asof counted as closed) that the tests catch.
- Record every decision as an ADR in `decision/adr/` (numbers 0020-0039; update the index rows for yours).
  Trials and numbers go in `provenance/trial_log.md`. Thresholds marked PLACEHOLDER until set on development data.

## Shared files (another session runs at the same time, no git)

You own: `src/arkstream/leader*.py` (for example `leader_returns.py`, `leader_trips.py`, `leader_risk.py`),
`research/leader/`, `tests/test_leader*.py`. Shared: `config/decision_context.yaml` (add only a `leader:`
section), `src/arkstream/cli.py`, `Makefile`, `README.md`, `tests/pit_check.py`, `provenance/trial_log.md`,
`provenance/expected_counts.yaml`, `decision/adr/README.md`, the plan file. Re-read a shared file immediately
before each edit, make small additive edits, never rewrite or reformat it. Do not change the Milestone 1 headline
counts; if you add locked counts, add new keys.

## Done when

- `python -m arkstream leader` (or a `make leader` target) writes per-origin tables to `research/leader/`:
  account returns, book returns, round trips, gates, profiles, an evidence summary per address, each with source
  keys and coverage, plus a short markdown summary per origin.
- Two reruns are byte-identical; `uv run ruff check src tests`, `uv run mypy src`, `uv run pytest -q` and
  `uv run python -m arkstream audit` pass; new tests on synthetic data cover both return conventions, gap
  handling, round-trip boundaries, open trades at the test date, the stress shock using only pre-origin moves,
  and unpriced exposure.
- ADRs for every threshold and method choice; a report of how many A/B addresses pass each gate at each origin
  (counts only, no selection), and what waits for Hyperliquid funding.

---

## Prompt to start the session

> Read `decision/briefs/phase-2-leader-evidence.md` in `C:\Projects\quant-task-arkstream` and carry it out:
> Phase 2 of the ArkStream copy pilot, leader evidence (account and book returns, round trips, tail-risk gates,
> holding-time and size profiles) for every grade A and B address, computed point in time at each origin. Use
> the Binance reference prices only; Hyperliquid funding is being fetched by another session, so label returns
> ex-funding and leave a clean place to add it. Before writing code, read the plan's sections "Leader evidence"
> and "Selection and point-in-time validation" in
> `ArkStream Hyperliquid Pilot — Revised Research & Deployment Plan (v2).md`, plus `README.md`,
> `config/decision_context.yaml`, `decision/adr/README.md` with ADRs 0002, 0004 and A0007, and
> `src/arkstream/pipeline.py`, `positions.py` and `quality.py`, which you should reuse. Record decisions as ADRs
> numbered 0020-0039. Another session works in the same folder with no git, so keep to the file ownership in
> the brief. Do not start the follower replay or selection.
