# ADR-0010: Hyperliquid public data: what the info endpoint serves for 2025

- Status: Accepted
- Date: 2026-11-19
- Phase: follower replay inputs (A07, A11)

## Context
Brief `decision/briefs/hyperliquid-data.md`, step 1. Docs read 2026-11-19:
https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint (and `/perpetuals`,
`/websocket`, `/websocket/subscriptions`, `/rate-limits-and-user-limits`). The docs say: history is served by
`POST https://api.hyperliquid.xyz/info`; time-range responses return at most 500 elements, paginate with the
last timestamp as the next `startTime`; candleSnapshot: "Only the most recent 5000 candles are available";
REST limit 1200 weight per minute per IP, info requests weight 20, plus extra weight per 20 items
(fundingHistory, userFunding) or per 60 items (candleSnapshot). The WebSocket is for real-time streaming; its
subscription acks carry a snapshot of unstated depth and no historical request type. WebSocket not used.

Probe run 2026-11-19, range 2025-07-27T00:00Z .. CUTOFF, BTC and PURR (thin, no Binance contract), one leader
(first address in `data/raw/traders.csv`), 1.5 s between requests, no rate-limit errors. Trial log row of this date.

| Request | BTC | PURR |
| --- | --- | --- |
| fundingHistory | 3,888 rows, 8 pages of <= 500; 2025-07-27 00:00 .. 2026-01-04 23:00; every hour present, no gaps | same: 3,888 rows, no gaps |
| candleSnapshot 1h | 0 rows for the range (all-time request: 5,001 rows, earliest 2026-04-24) | 0 rows (earliest 2026-04-24) |
| candleSnapshot 4h | 972 rows, 2025-07-27 00:00 .. 2026-01-04 20:00 (complete) | 972 rows (complete) |
| candleSnapshot 1d | 162 rows (complete) | 162 rows (complete) |

- fundingHistory `time` is the hour plus a few ms of jitter (offsets 0-4+ ms, e.g. ...400031); fields `coin,
  fundingRate, premium, time` as strings. Expected hourly count 3,888 = observed.
- userFunding: 810 rows in 2 pages, 5 coins, 2025-07-27 .. 2026-01-04; rows carry `usdc, szi, fundingRate,
  nSamples`, hash all zeros. Reaches back to the range start; completeness cannot be proved without the
  leader's positions.
- metaAndAssetCtxs: current snapshot only (235 assets), no history.

## Decision
- **fundingHistory: go.** The funding source for all eligible core perps, paginated by 500, under the rate limit.
  Funding time = `time` floored to the hour; the raw `time` is kept.
- **candleSnapshot 1h and finer: no-go** (the 5,000-candle window starts 2026-04-24). **4h: go** as the finest
  interval reaching 2025, for the price check (step 4) only. 1d not needed.
- **userFunding: conditional go**, as a cross-check of rate x position only, never as a funding input; its
  completeness is tested against the package snapshots before it is relied on.
- **metaAndAssetCtxs, WebSocket: no-go** for history. The requester-pays S3 archive is not used.

## Consequences
Funding fetch size: ~3,888 rows x coins, 8 requests per coin. Step 4 compares at 4h bar closes plus the package
prints; intraday 1h checks are impossible from this source. Open: the per-item extra weight is not quantified
in the docs; the fetcher throttles well under 1200/min.
