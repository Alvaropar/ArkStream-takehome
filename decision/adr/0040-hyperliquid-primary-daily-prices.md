# ADR-0040: Hyperliquid prices for daily metrics, Binance as validator; the 32 coins

- Status: Accepted; amended by ADR-0110 (passing list as of each origin)
- Date: 2026-11-19
- Phase: Phase 2 onward
- Amends: ADR-0002 (role of the Binance reference) and ADR-0013 item 3 (proposal adopted, extended)

## Context
The positions being valued trade on Hyperliquid, so Hyperliquid's own prices are the right marks; Binance was
used first because it was the only history available. ADR-0010: Hyperliquid's public history reaches 2025 only at
4h and coarser (1h starts 2026-04-24). Hyperliquid 4h candles for all 195 eligible core perps are on disk
(`data/reference/hyperliquid/candles_4h/`, own `MANIFEST.csv`). ADR-0013: 163 coins pass the pre-registered
Binance match rule, 22 fail, 10 have no Binance contract.

## Decision
1. **Daily metrics use Hyperliquid prices for every coin.** A daily mark is the Hyperliquid 4h close known at the
   UTC day boundary (the bar opening at 20:00, known at 00:00). This applies to daily book valuation, daily
   drawdown, the open-trade mark at the origin, the BTC/ETH returns in ADR-0009, and the funding payment price for
   the 32 coins (item 4). A bar without trades gives no mark: the point is unpriced and flagged, never carried
   forward from an earlier bar. Equity and TWR come from the snapshots, which are Hyperliquid data already.
2. **Binance validates the 163 passing coins.** Each daily Hyperliquid mark is compared with the Binance reference
   known at the same instant; a gap beyond the ADR-0012 bounds is flagged per (coin, day) and reported, not
   silently replaced.
3. **The 32 problem coins.**
   - **22 that fail the Binance match**: Hyperliquid prices only. Binance is not used for them anywhere.
   - **10 with no Binance contract** (APEX, BLAST, LAUNCHCOIN, MNT, PURR, REQ, YZY, FTT, FOGO, MEGA): Hyperliquid
     prices, labelled `unvalidated`. The only check available is against the package's own prints, which come
     from the same venue and so are not independent.
   - Both groups are used in leader metrics. They are not removed, and the addresses that trade them are not
     dropped for it.
4. **Intraday metrics stay on Binance 1m, where it is valid.** Hourly book marks, intraday drawdown, MAE, the
   exact snapshot-time rebuild check and drift use the Binance reference for the 163 passing coins (labelled
   `binance_1m`). For the 32 coins these are unavailable and reported as such: Hyperliquid has no history below
   4h for 2025, and filling from 4h closes or from Binance would be an imputation. The funding payment price uses
   the Binance price at the hour for passing coins and the latest Hyperliquid 4h close at most 4 h old for the 32
   coins, labelled as an approximation of the oracle price.
5. **Copying the 32 coins is open (Phase 3).** Their drift and spread cannot be measured below 4h, so the replay
   must either exclude them from copying or apply a stated conservative cost scenario. Phase 3 decides by ADR.

## Consequences
Every price column carries its source (`hyperliquid_4h`, `binance_1m`, `package_print`) and validation status.
Phase 2 is rerun with daily marks from Hyperliquid; outputs that need intraday resolution keep Binance for the 163
coins and report the 32 coins as unavailable. The ADR-0012 bounds become the per-day validation tolerance.
