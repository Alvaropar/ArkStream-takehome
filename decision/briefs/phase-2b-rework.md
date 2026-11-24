# Brief: Phase 2 rework (addresses as assets, Hyperliquid daily prices, grading fix)

> ADR numbers below follow the renumbering of 2026-11-23 (ADR-0085; old numbers in
> `decision/adr/RENUMBERING.md`), except the reserved number blocks, which are quoted as they were reserved.

Written 2026-11-19. Project: `C:\Projects\quant-task-arkstream` (ArkStream Hyperliquid copy pilot, take-home).
ADR numbers reserved for this session: **0060-0079**. No other session is editing the project while this one runs.

## Why

Phase 2 (ADRs 0013-0019, outputs in `research/leader/`) was built before four decisions and findings:

1. **ADR-0007, addresses as assets.** Each address is an asset with a daily time-weighted return (TWR), a set of
   suitability gates, and market exposure measured; Phase 3 will turn it into a copy series.
2. **ADR-0020, price sources.** Daily metrics use Hyperliquid 4h closes for every coin; Binance 1m validates the
   163 coins that passed the price check (ADR-0011) and stays the intraday source for them; the 22 failing coins use
   Hyperliquid only; the 10 without a Binance contract use Hyperliquid, labelled `unvalidated`. Intraday metrics
   for those 32 coins are unavailable.
3. **A grading flaw (Milestone 1, `src/arkstream/quality.py`).** Coverage is measured from an address's first to
   its last snapshot, so the gap after the last snapshot is ignored. At the first four origins 12-20% of A/B
   addresses had no snapshot for more than 3 days before the origin (53, 68, 94, 77 addresses; median 26-63 days
   silent), almost all still holding positions. When their snapshots resumed around 22 Nov the same gap moved
   inside the span and 96 addresses fell from A/B (19 Nov) to C (3 Dec). Snapshot gaps are common in this feed
   (only 33.6% of addresses have a snapshot every day of their span; 73.6% of snapshot days have no fill), so
   silence is a coverage problem, not inactivity.
4. **A validated fills rebuild.** Marking rebuilt positions at the exact snapshot times (Binance 1m), adding
   Hyperliquid funding, and taking fills that share a timestamp in chain order reproduces the snapshots for
   core-perp-only accounts: grade A median miss 0.037% of equity, 98.3% of active intervals within 1%,
   correlation 0.9995 (B: 0.053%, 97.5%). Phase 2's hourly book-vs-account check reached only correlation 0.89
   because it marks on the hour and has no funding. Reference prototype: `decision/briefs/prototypes/rebuild_exact.py`
   (not tested, not point in time as written: it joins funding on `ts_hour`; production code must use
   `known_at`). It also found 1,315 intervals where snapshot equity did not change while positions moved (frozen
   snapshots), and 3,649 intervals before fills start (2025-07-27) that cannot be checked.

5. **Recruiter answers (ADR-0021).** `equity` is the cross-margin account equity, not the total account value
   (ADR-A0007 is superseded). So the snapshot TWR is a cross-margin account return. Transfers between the cross
   account and spot, isolated margin or HIP-3 can move `equity` without a change in `net_deposit`. Where the pnl
   identity fails or shows a scope offset, use the rebuilt core-perp book as the address's return series and report
   the snapshot TWR only as a check. Correct the "total account value" wording in `leader_returns.py` and add an
   ADR in your block that amends ADR-0014. HIP-3 stays excluded (ADR-0022). The cutoff is
   confirmed as the last fill.

## Scope (in order)

1. **Grading fix.** In `quality.py`, measure snapshot coverage (`days_present_share`, `unusable_day_share`) from
   the first snapshot to the origin, not to the last snapshot, so a trailing gap counts exactly like an inside gap.
   Do not make "dropped out" an automatic C. Flag frozen snapshots (equity unchanged while the rebuilt book
   moved) as unusable days. This changes Milestone 1 headline counts: write an ADR with the before/after counts,
   update `provenance/expected_counts.yaml` in the same change, and keep the audit passing.
2. **Funding in the book.** Point `leader.funding` at the Hyperliquid funding table
   (`research/hyperliquid/funding.parquet` via `arkstream.funding`; columns `ts_hour, known_at, coin,
   funding_rate`). A rate is usable only when `known_at <= asof`; it accrues to the position held at `ts_hour`.
   Payment = -position x price x rate (ADR-0009); price = Binance at the hour for the 163 coins, the latest
   Hyperliquid 4h close at most 4 h old for the 32 coins (ADR-0020). Book and round-trip outputs drop the
   `ex_funding` label.
3. **Exact-time rebuild check.** Replace the hourly book-vs-account comparison with a check at the exact snapshot
   times (Binance 1m for the 163 coins), using `positions.order_fills` chain order. Per address: share of active
   intervals within 0.1% and 1% of equity, median miss, and the stale-snapshot count. This fit score is a new
   quality measure in the evidence table. Addresses with spot, HIP-3 or non-USDC fees get the score only for
   intervals where every position is priced; the rest are reported as not checkable.
4. **Daily marks from Hyperliquid.** Daily book valuation, daily drawdown, and the open-trade mark at the origin
   use the Hyperliquid 4h close known at the UTC day boundary (`arkstream.hlprices`), for every coin. A bar
   without trades gives no mark (unpriced, flagged, never carried forward). For the 163 coins compare each daily
   mark with Binance at the same instant and flag (coin, day) beyond the ADR-0010 bounds. Hourly marks, intraday
   drawdown and MAE stay on Binance 1m for the 163 coins and are reported `unavailable` for the 32 coins. Every
   price column carries `price_source` and `validation` (`validated`, `flagged`, `unvalidated`).
5. **Daily TWR per address** (ADR-0007 item 2, amended by ADR-0021: a cross-margin account return): chained daily sub-period returns from the snapshots, start-of-day
   flow as base and end-of-day as sensitivity, the existing exclusion rules, a gap as one sub-period. Inside a gap
   use the rebuilt book's trading PnL path for drawdowns and state that deposit timing is unknown. Output the
   series and its summary (TWR, volatility, Sharpe with a confidence interval, max drawdown, coverage).
6. **Market exposure** (ADR-0007 item 4): regress each address's daily TWR on BTC and ETH daily returns
   (Hyperliquid daily marks) over the data up to the origin; report beta, residual return (alpha) and their
   confidence intervals, R², and the number of days.
7. **Suitability gates** (ADR-0007 item 1), added to the existing gates, all PLACEHOLDER: not high-frequency
   (median holding-time band, orders per day, maker share), active (at least one fill in the last N days before
   the origin; snapshot silence alone does not fail it), rebuild fit score above a minimum, and the existing
   minimum round trips and tail-risk gates. Report counts per gate and per origin; select no one.
8. **Rerun and compare.** Rerun `python -m arkstream leader` for all five origins. Report, per origin: A/B counts
   before and after the grading fix, gate counts before and after, and the book-vs-account totals with the
   remaining gap split into funding, unpriced coins, non-core activity and unexplained.

Optional, only if cheap: Hyperliquid per-coin maintenance margin from the public `meta` request, to replace the
2.5% placeholder in ADR-0018. It is current-only, not historical: record that in an ADR and label it.

## Out of scope

The follower replay and copy series (Phase 3), selection, ranking and baselines (Phase 4), the freeze hash and
the holdout. Do not compute any holdout-period result beyond the 3 Dec origin's inputs. Spot and HIP-3 markets
(ADR-A0007). Any order or network code in `src/arkstream` (fetches belong in `src/arkstream_fetch`).

## Rules (project spec, verbatim where quoted)

- "Inputs (read-only; never modify)".
- "Point in time: every function that produces values takes an `asof` timestamp and uses only rows with
  timestamp <= asof". CUTOFF from `config/decision_context.yaml` (the last fill, 2026-01-04T23:59:42.020Z).
- "Never invent missing inputs: no imputed prices, funding or quotes. Missing -> flag and exclude, with a reason".
- "Determinism: same inputs give byte-identical outputs" (every table with a total sort order; ADR-0006).
- "Traceability: every derived row keeps the source keys (trader, tid, oid, timestamp)".
- "No code path that sends real orders, now or later, unless explicitly enabled."
- Keep `tests/pit_check.py` covering every new table, and add a seeded leak for this rework (for example a funding
  rate used before its `known_at`, or a Hyperliquid 4h close used before the bar closes) that the tests catch.
- Record every decision as an ADR in `decision/adr/` (numbers 0060-0079; update the index rows for yours). Trials
  and numbers go in `provenance/trial_log.md`. Thresholds marked PLACEHOLDER until set on development data.

## Done when

- The grading fix, funding, exact-time rebuild check, Hyperliquid daily marks with Binance validation, daily TWR,
  market exposure and suitability gates are in the per-origin outputs under `research/leader/`, each with source
  keys, `price_source`, validation status and coverage.
- `uv run ruff check src tests`, `uv run mypy src`, `uv run pytest -q` and `uv run python -m arkstream audit` pass
  (with the updated expected counts); two reruns of `python -m arkstream leader` are byte-identical.
- New tests on synthetic data cover: coverage to the origin with a trailing gap; frozen snapshots; same-timestamp
  fills in chain order; funding used only after `known_at`; a 4h close used only after its close; daily TWR with a
  deposit and a withdrawal under both conventions; beta and alpha on a constructed series; unpriced points never
  carried forward.
- ADRs for every method and threshold choice, and a short report with the before/after counts in step 8.

---

## Prompt to start the session

> Read `decision/briefs/phase-2b-rework.md` in `C:\Projects\quant-task-arkstream` and carry it out: rework Phase 2
> of the ArkStream copy pilot so that each address is treated as an asset (daily TWR, market exposure, suitability
> gates), daily metrics use Hyperliquid prices with Binance as validator, funding is in the book, the rebuilt book
> is checked at the exact snapshot times, and the grading measures coverage up to each origin. Before writing code,
> read `decision/adr/README.md` and ADRs 0007, 0009, 0010, 0011, 0013-0019, 0020 and 0021, the plan's sections "Leader
> evidence" and "Selection and point-in-time validation" in
> `ArkStream Hyperliquid Pilot — Revised Research & Deployment Plan (v2).md`, `README.md`,
> `config/decision_context.yaml`, `src/arkstream/quality.py`, `positions.py`, `leader*.py`, `funding.py` and
> `hlprices.py`, and the prototype `decision/briefs/prototypes/rebuild_exact.py`. Start with the grading fix and
> report its before/after counts before moving on. Record decisions as ADRs numbered 0060-0079. Do not start the
> follower replay or selection.
