# ADR-0011: Hyperliquid hourly funding rates: fetcher, table, Phase 3 convention

- Status: Accepted
- Date: 2026-11-19
- Phase: follower replay inputs (A07)

## Context
Held positions pay or receive funding every hour; the package has no funding ledger (A07). ADR-0010 found
`fundingHistory` complete for 2025. ADR-0007 allows public market data.

## Decision
**Fetch.** `src/arkstream_fetch/fetch_hyperliquid.py` (standard library; only `POST https://api.hyperliquid.xyz/info`,
tested; HIP-3 names and non-hex addresses refused; >= 1.2 s between requests; 5 retries with backoff on 429/5xx;
resumable from verified pages without network). Coins = `data/reference/hyperliquid/coins.csv`, the core perps
traded in eligible fills (`python -m arkstream funding --step coins`). Range 2025-07-27T00:00Z to CUTOFF (read
from the config). Raw responses saved unchanged, one file per request, each in `funding/MANIFEST.csv` with
the request body, bytes, SHA-256, rows and first/last time. The shared safety test now allows exactly
`api.hyperliquid.xyz` besides `data.binance.vision` and still forbids `/exchange` and any order code.

**Table** (`src/arkstream/funding.py`, no network; read only through the manifest; a stray or changed file
stops the load). Rates only, one row per coin and hour, sorted `coin, ts_hour`:
`ts_hour, known_at, coin, funding_rate, premium, src_file`.
- `ts_hour` = raw `time` floored to the hour: the accrual hour; the rate applies to the position held then.
- `known_at` = raw `time` (the hour plus a few ms). A rate is usable only at `asof >= known_at`; tested with an
  asof between the two. Rows with `known_at` > CUTOFF are dropped.
- Nothing filled in. Missing hours are listed in `funding_gaps.csv` with a reason (`no_funding_rows`,
  `before_first_rate`, `internal_gap`, `after_last_rate`); `funding_coverage.csv` gives one row per coin.

**Phase 3 convention** (payments are computed there, not here): `funding_rate` is the hourly rate as a
fraction. Payment to the account at hour h = `-sign(position) x |size| x price x rate` = `-position x price x
rate`, position = signed size held at h (the last fill strictly before h). Longs pay when the rate is positive.
Hyperliquid computes it with its oracle price, which has no history here; the Binance reference price known at
h (1m close, <= 60 s old) stands in, labelled `oracle_proxy = binance_reference`, an approximation. Coins without
a Binance price use the Hyperliquid 4h close as proxy only where ADR-0013 says so.

**Check, never an input**: `userFunding` for the top 5 leaders by eligible fills (results in ADR-0014).

## Consequences
All 195 coins fetched (1,560 requests, 0 failures): 719,165 rows. 172 coins complete 2025-07-27..2026-01-04 23:00; 23 start later (listings; 38,995 hours `before_first_rate`); no internal gaps. In 17 of the 23 the first fill comes up to 0.9 h before the first funding hour (trading opened mid-hour), so no funding hour is missed. Publication lag: <= 0.11 s except 2025-07-27 12:00 (111 s for every coin), handled by `known_at`. Outputs in `research/hyperliquid/`. The userFunding check (ADR-0014) confirms the convention: 98.4% of computable daily records within 1%, total calc / actual 1.0014.
