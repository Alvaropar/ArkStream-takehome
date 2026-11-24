# ADR-0019: Profiles; order size against Binance daily quote volume

- Status: Accepted
- Date: 2026-11-19
- Phase: Phase 2

## Context
The plan profiles holding time, frequency, maker share, fee rate, equity band and impact risk.

## Decision
- Median hold over closed, uncensored trips; band from `drift.BAND_EDGES_S` / `BAND_LABELS`.
- Orders per day = distinct oids / days from first fill to asof. Maker share over fills; `maker_heavy` > 70%.
- Fee rate = sum fee / sum notional (USDC-fee fills), bps. Median equity of snapshots to asof; band 20k-2M.
- Impact: order notional / the coin's median daily Binance quote volume (sum close x volume of 1m bars from
  `data/lake`, the same verified kline zips as the reference, inside the coin's validity window) over the 30
  days before the origin; address median and p95 in bps. No volume -> counted as `orders_without_volume`.

## Consequences
Profiles are features for Phase 4 gates (maker-heavy, band); no threshold is applied here.
