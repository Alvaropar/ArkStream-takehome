# ADR-0003: Trade-level drift from verified Binance aggTrades zips, from 2025-09-08

- Status: Accepted
- Date: 2026-11-19
- Phase: follower replay (A13, A16)

## Context
The lake's aggTrades Parquet dropped whole minutes that failed a volume reconciliation (0.4-8.9% of rows,
concentrated in the 10 Oct 2025 crash); the original zips were complete. 1m klines correlate only 0-0.35 with
trade-level drift at 10-60 s. The 8 Oct test date needs history before 8 Oct (ADR-0004).

## Decision
- Drift for BTC, ETH, HYPE, SOL from Binance USD-M daily aggTrades zips in
  `data/reference/binance/aggtrades/`, each verified against Binance's published `.CHECKSUM` and listed in
  `MANIFEST.csv`. The lake's aggTrades copy is refused by the reader.
- Downloaded by `src/arkstream_fetch/fetch_aggtrades.py` (standard library, only data.binance.vision, bounded
  retries, resumable), the only network code; `src/arkstream` has none (tested).
- Range 2025-09-08 to 2026-01-04: 476 files, 7.69 GB. Drift never reads a file after 2025-12-02.

## Consequences
All 476 files verified; no duplicate or missing trade IDs within or across days. Other coins use the
approximate method (ADR-0005), at 5 minutes or more only.
