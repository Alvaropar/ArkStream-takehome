# Brief: Phase 3, follower replay and copy series

Written 2026-11-19. Project: `C:\Projects\quant-task-arkstream` (ArkStream Hyperliquid copy pilot, take-home).
ADR numbers reserved for this session: **0080-0099**. No other session edits the project while this one runs.

## Why

ADR-0009 makes each address an asset whose investable "price" is its **copy series**: the return a follower would
have earned copying it, after delay, fees, spread, impact, drift and funding. Phase 3 builds that series and the
plan's first economic screen (the delay break-even study). Phase 4 ranks and Phase 5 allocates on its output, never
on the leader's own returns. Method: the plan's section **Follower replay**. This brief fixes the inputs and the
choices left open.

## Inputs already built (read the ADRs before using them)

- **Leader universe and evidence per origin:** `research/leader/origin=<date>/` (ADRs 0020-0027, 0060-0065): grades,
  suitability gates, daily TWR, rebuilt positions, funding payments, daily marks. Origins 2025-10-08, 10-22, 11-05,
  11-19, and 12-03 (holdout).
- **Drift:** per origin, by coin x holding-time band x horizon (1, 10, 60, 300 s), from Binance aggTrades for BTC,
  ETH, HYPE, SOL; approximate (fill price to reference, venue-basis corrected, >= 300 s only) for other coins;
  10-11 Oct apart as stress (ADRs 0003-0005; `research/drift/`, `src/arkstream/drift.py`). Means are within about
  +-2.6 bps outside the crash; stress at 5 min reaches +35 bps (BTC) and -58 bps (HYPE).
- **aggTrades zips** 2025-09-08..2026-01-04 for the four coins (`data/reference/binance/aggtrades/`, verified).
- **Prices:** Binance 1m reference for the 163 coins that pass the price check (intraday source); Hyperliquid 4h
  closes for every coin (daily marks); the 22 failing and 10 unmapped coins have no intraday price (ADR-0040).
- **Funding:** Hyperliquid hourly rates with `known_at` (ADR-0011); payment = -position x price x rate, checked
  against actual leader payments to about 0.05% (ADR-0014).
- **Scope:** core perps; HIP-3 and spot out (ADRs 0041, 0042). `equity` is cross-margin equity (ADR-0041).
- **Scenarios:** `config/execution.yaml` (optimistic 1 s, base 10 s, stress 60 s / 300 s thin; taker fee 4.5 bps;
  half-spread majors/other 0.5/2, 1/5, 3/15 bps; impact none / linear / 3x). `config/risk.yaml` is a proposal only.

## Scope (in order)

1. **Event model.** A leader fill is visible at event time + d_receive; the engine decides after d_decide; the order
   is acknowledged after d_ack; total delay per scenario from `execution.yaml`. Nothing is priced at or before its
   visibility time. Fills of one leader order inside the debounce are netted into one follower order. Write the
   event-time leak test from the plan: a seeded leak (a follower order priced at the leader's fill time, or using a
   fill not yet visible) must be caught.
2. **Sizing.** Proportional copy on a fixed allocation per address (state it, for example 10,000 USDC): follower
   target position = leader position x allocation / leader equity, with leader equity the latest cross-margin
   snapshot known at the decision time (point in time; ADR-0041). Where the address's return source is the rebuilt
   book (ADR-0065), say which equity is used. Orders below Hyperliquid's minimum notional (check the current docs;
   $10 is the planning value) are skipped and counted, never rounded up.
3. **Execution price.** Decide by ADR, in this order of preference:
   - BTC, ETH, HYPE, SOL: the actual Binance aggTrades price at order time (venue lead-lag A16 noted), so every
     order has its own drift;
   - other coins with a Binance reference: leader fill price adjusted by the per-origin drift parameter for its coin
     and holding band at that delay (ADR-0004), labelled `parameterised`; for delays under 300 s on coins without
     aggTrades there is no measured drift, so state what is used (the pooled four-coin value, the stress value, or
     a labelled assumption) and never read a 1m kline under 300 s;
   - the 32 coins without an intraday price (ADR-0040 item 5): either not copied, or copied under a stated
     conservative cost; decide by ADR and report how many orders and how much PnL that choice moves.
   Then add half-spread and impact per scenario, and the taker fee. A follower is always a taker.
4. **Spread estimate (plan).** Corwin-Schultz from one-minute high/low bars of the package's pooled prints, and
   Abdi-Ranaldo for comparison; minimum prints per bar set on development data; negative estimates set to zero; the
   random-walk bias simulation before calling anything a floor; fit on development data only, one frozen value per
   coin. Where it exceeds the scenario half-spread, raise the scenario and record it. Impact stays an assumption
   (linear in order size over traded volume; Hyperliquid 4h candle volume is available for every coin).
5. **Funding** on the follower's own positions, hourly, using a rate only after `known_at`.
6. **Copy series.** Per address, origin and scenario: the follower's daily TWR on its allocation (the investable
   series, ADR-0009), before and after funding; copy efficiency (copy return / leader return); break-even delay and
   break-even cost (where copy return reaches zero); share of orders skipped for minimum size; share unpriced; the
   zero-delay, zero-cost upper bound labelled unattainable.
7. **Delay break-even study (first go/no-go screen).** By holding-time band: average gross result per round trip
   against the cost per round trip (about 2 x (fee + half-spread), 11-20 bps in the base scenario). Report which
   bands are copyable, and how many addresses passing the suitability gates survive the base scenario at each
   origin. If almost none survive, say so plainly: economic feasibility fails before any ranking.
8. **Windows.** For each development origin compute the copy series both over the training data (up to the origin,
   which feeds Phase 4 ranking) and over the following test window (origin to the next origin, the outcome Phase 4
   scores), stored and labelled separately. **Do not compute the holdout test window (2025-12-03..2026-01-04).**
   The plan opens it once, after the Phase 4 freeze hash. The 3 Dec origin gets its training-side series only.

Optional, only with the user's explicit go-ahead: Hyperliquid historical L2 data (requester-pays archive, needs an
AWS account and costs money; ADR-0041) for the few coins the candidates trade most, to replace assumed spread and
impact. Do not fetch it without that go-ahead.

## Out of scope

Selection, ranking, random-k and equal-weight baselines, the freeze hash, the holdout test window (Phase 4);
portfolio allocation and limits (Phase 5); any order-sending code ("No code path that sends real orders, now or
later, unless explicitly enabled"; `live_trading_enabled` stays false).

## Rules (project spec, verbatim where quoted)

- "Inputs (read-only; never modify)".
- "Point in time: every function that produces values takes an `asof` timestamp and uses only rows with
  timestamp <= asof". For the replay this means: a decision uses only fills visible by its decision time, equity
  known by then, drift and spread parameters estimated before the origin, and funding rates after `known_at`.
- "Never invent missing inputs: no imputed prices, funding or quotes. Missing -> flag and exclude, with a reason".
- "Determinism: same inputs give byte-identical outputs" (total sort order on every table; ADR-0008).
- "Traceability: every derived row keeps the source keys (trader, tid, oid, timestamp)": each follower order keeps
  the leader fills it copies.
- Extend `tests/pit_check.py` to the replay tables, and add the event-time seeded leak.
- Record every decision as an ADR in `decision/adr/` (numbers 0080-0099; update the index rows for yours). Trials
  and numbers go in `provenance/trial_log.md`. Thresholds marked PLACEHOLDER until set on development data.

## Done when

- `python -m arkstream replay` (and a `make replay` target) writes per-origin, per-scenario tables to
  `research/replay/`: follower orders with source keys, daily copy TWR (training and test windows), per-address
  summary (copy efficiency, break-even delay and cost, skipped and unpriced shares), the band break-even table, and
  the spread estimates with their bias-simulation result; plus a short summary per origin.
- Two reruns are byte-identical; `uv run ruff check src tests`, `uv run mypy src`, `uv run pytest -q` and
  `uv run python -m arkstream audit` pass; new synthetic tests cover visibility and debounce, sizing and minimum
  size, each execution-price path, funding after `known_at`, the zero-cost upper bound, and the event-time leak.
- ADRs for the execution-price rule, the 32-coin decision, the allocation, the debounce and every threshold.
- A short report: per origin, how many gate-passing addresses have positive copy return under optimistic, base and
  stress; the copyable holding-time bands; and whether the first economic screen passes.

---

## Prompt to start the session

> Read `decision/briefs/phase-3-follower-replay.md` in `C:\Projects\quant-task-arkstream` and carry it out: Phase 3
> of the ArkStream copy pilot, the follower replay that turns each leader address into its copy series (follower
> daily TWR after delay, fees, spread, impact, drift and funding) under the optimistic, base and stress scenarios,
> plus the delay break-even study. Before writing code, read the plan's sections "Follower replay" and "Decision
> gates" in `ArkStream Hyperliquid Pilot — Revised Research & Deployment Plan (v2).md`, `decision/adr/README.md` and
> ADRs 0003-0005, 0009, 0011, 0014, 0040-0042 and 0060-0065, `config/execution.yaml`, `config/decision_context.yaml`,
> and `src/arkstream/drift.py`, `funding.py`, `hlprices.py`, `positions.py` and `leader*.py`. Start by writing the
> execution-price ADR and stop to report it before building the replay. Never compute the holdout test window
> (2025-12-03..2026-01-04). Record decisions as ADRs numbered 0080-0099. Do not start selection.
