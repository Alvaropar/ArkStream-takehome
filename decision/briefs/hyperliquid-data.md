# Brief: Hyperliquid public data (funding, price check)

Written 2026-11-19. Project: `C:\Projects\quant-task-arkstream` (ArkStream Hyperliquid copy pilot, take-home).
ADR numbers reserved for this session: **0010-0019**.

## Why

The follower replay (Phase 3) must cost held positions, and Hyperliquid perps pay or receive funding every
hour. The package has no funding ledger (plan A07). ADR-0007 now allows public market data. Second, every
price used so far is a Binance price (ADR-0002); before relying on it for Hyperliquid positions we want
evidence that it matches Hyperliquid closely enough, coin by coin, and a decision on the coins it does not
cover.

## What is already known (check, do not assume)

- **History comes from the REST info endpoint, not the WebSocket.** `POST https://api.hyperliquid.xyz/info` is
  public and free, with weight-based rate limits per IP. The WebSocket (`wss://api.hyperliquid.xyz/ws`) streams
  live data only, so it cannot serve July 2025-January 2026. Confirm both against the current official docs and
  record the doc URL and date (A11).
- Request types to evaluate: `fundingHistory` (per coin, startTime/endTime, paginated), `candleSnapshot`
  (believed limited to the most recent 5,000 candles per interval: at 1h that reaches back only about 208 days
  from today, so not to 2025; at 4h about 833 days, at 1d further), `userFunding` (per address funding
  payments), `metaAndAssetCtxs` (current only). Verify each limit with a real request.
- The package's own fills are Hyperliquid prices already; `prices.compare_to_prints` compares them with the
  Binance reference (median |gap| 9 bps; BTC 5, ETH 7, SOL 7, HYPE 12; 10.5% beyond 50 bps, mostly intraminute
  movement against a bar close up to 60 s old).
- 10 traded core-perp coins have no Binance reference: APEX, BLAST, LAUNCHCOIN, MNT, PURR, REQ, YZY (no Binance
  contract), FTT, FOGO, MEGA (never valid). Together under 0.5% of notional.
- There is no Hyperliquid fetcher in `C:\Projects\quant-ai-harness\packages\qh-data` (it has Binance only). The
  model to follow is this project's `src/arkstream_fetch/fetch_aggtrades.py`.

## Scope

1. **Feasibility first (half a day at most).** One small script run that fetches, for BTC and one thin coin:
   funding for 2025-07-27..2026-01-04, candles at 1h/4h/1d for the same range, and `userFunding` for one leader
   address from `data/raw/traders.csv`. Report what each returns (rows, earliest time, gaps, pagination, rate
   limit). Write ADR-0010 with the findings and the go/no-go for each source.
2. **Funding fetcher** `src/arkstream_fetch/fetch_hyperliquid.py`: funding history for every core perp traded
   in eligible fills (`symbol` where `eligible`), 2025-07-27 to CUTOFF. Same rules as `fetch_aggtrades.py`:
   standard library only, host allowlist (`api.hyperliquid.xyz`), bounded retries with backoff, a rate limiter
   under the published limit, resumable, raw responses saved unchanged with SHA-256 in a `MANIFEST.csv`,
   `--dry-run`, Windows-safe renames (`_replace`). Output `data/reference/hyperliquid/funding/`.
3. **Funding table** in `src/arkstream/funding.py` (no network): parse the saved responses into
   `ts, coin, funding_rate, premium, src_file`, point in time (a rate is known at its funding time), filtered to
   CUTOFF, never filled in. A gap is flagged with a reason. Coverage per coin reported. Optional and only if
   step 1 says `userFunding` is complete: per-leader actual funding as a cross-check of rate x position.
4. **Price check (the user's question): do we need Hyperliquid price history?** Compare Hyperliquid prices with
   the Binance reference per coin, using what history allows: the package prints (all coins, all dates) and
   Hyperliquid candles at the finest interval that reaches 2025 (likely 4h). Pre-register the rule in an ADR
   before looking at results, for example: a coin passes if the median |gap| <= 10 bps and the 95th percentile
   <= 30 bps over its sample, with the 10-11 Oct crash reported apart. "Exactly equal" is not a usable test:
   the venues differ by a few bps by construction. Outcome per coin: pass (Binance reference stands), fail
   (needs Hyperliquid prices or exclusion), no Binance (decide: Hyperliquid candles, package prints only, or
   excluded). Write the decision as an ADR.
5. If step 4 shows Hyperliquid prices are needed and available, fetch them with the same fetcher and add them
   as a second reference source with its own manifest, never mixed silently with Binance rows.

## Out of scope

Selection, the follower replay, and Phase 2 (another session is doing leader evidence). HIP-3 and spot
(ADR-0007). Any code that places orders. Any paid source (the Hyperliquid S3 archive is requester-pays: note it
in an ADR if relevant, do not use it).

## Rules (project spec, verbatim where quoted)

- "Inputs (read-only; never modify)".
- "Point in time: every function that produces values takes an `asof` timestamp and uses only rows with
  timestamp <= asof". CUTOFF is read from `config/decision_context.yaml` (now the last fill,
  2026-01-04T23:59:42.020Z), never hard-coded.
- "Never invent missing inputs: no imputed prices, funding or quotes. Missing -> flag and exclude, with a reason".
- "Determinism: same inputs give byte-identical outputs". Every table written with a total sort order.
- "Traceability: every derived row keeps the source keys".
- Network code only in `src/arkstream_fetch`; the existing test that `src/arkstream` has none must keep passing.
- Record every decision as an ADR in `decision/adr/` (numbers 0010-0019, update the index rows for yours).
  Trials and numbers go in `provenance/trial_log.md`.

## Shared files (another session runs at the same time, no git)

You own: `src/arkstream_fetch/fetch_hyperliquid.py`, `src/arkstream/funding.py`, `data/reference/hyperliquid/`,
`tests/test_fetch_hyperliquid.py`, `tests/test_funding.py`. Shared: `config/decision_context.yaml` (add only an
`inputs.hyperliquid_dir` entry and a `funding:` section), `src/arkstream/cli.py`, `Makefile`, `README.md`,
`provenance/trial_log.md`, `decision/adr/README.md`, the plan file. Re-read a shared file immediately before
each edit, make small additive edits, never rewrite or reformat it.

## Done when

- ADR-0010 (feasibility) and the price-check ADR written; the index updated.
- Funding for every eligible core perp 2025-07-27..CUTOFF on disk, verified, with a coverage table and every gap
  explained.
- `uv run ruff check src tests`, `uv run mypy src`, `uv run pytest -q` and `uv run python -m arkstream audit`
  pass; new tests cover parsing, point in time, the cutoff, gaps never filled, resume without network, and the
  host allowlist.
- A short report: what is available, the price-check result per coin, and what Phase 3 can now use.

---

## Prompt to start the session

> Read `decision/briefs/hyperliquid-data.md` in `C:\Projects\quant-task-arkstream` and carry it out. It covers
> fetching Hyperliquid public data for the copy pilot: hourly funding history for every eligible core perp, and
> a pre-registered check of whether the Binance reference prices match Hyperliquid closely enough that we do not
> need Hyperliquid price history. Start with the feasibility step and stop after it to report what each
> Hyperliquid endpoint actually returns for 2025 (history comes from the REST info endpoint; the WebSocket is
> live-only, so confirm that first). Also read `decision/adr/README.md` and ADRs 0002, 0003 and 0007, the
> `README.md`, `config/decision_context.yaml` and `src/arkstream_fetch/fetch_aggtrades.py`, which is the
> pattern to follow. Record decisions as ADRs numbered 0010-0019. Another session is working on Phase 2 in
> the same folder with no git, so keep to the file ownership in the brief.
