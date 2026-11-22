# ADR-0006: Delete the redundant aggTrades copies

- Status: Accepted
- Date: 2026-11-19
- Phase: data housekeeping

## Context
After the full download, two folders duplicated or contradicted `data/reference/binance/aggtrades/`: the
lake's incomplete aggTrades Parquet (1.4 GB, never read) and the 56 seed zips in `data/lake/_raw/.../daily/
aggTrades` (1.2 GB, byte-identical to the copies, verified by SHA-256).

## Decision
Both deleted on the user's instruction. Klines (raw zips and lake Parquet) are kept: `refprices` rebuilds the
price files from them.

## Consequences
2.6 GB freed; tests, audit, download plan (476 reused) and drift reruns unchanged. `data/lake/_manifest.sqlite`
and `_raw/_verified.sqlite` (qh_data's records) still list the deleted items; a rerun of `refprices` rewrites
`data/reference/binance/CHECKSUMS.txt` without the 56 aggTrades zips, which `aggtrades/MANIFEST.csv` tracks.
