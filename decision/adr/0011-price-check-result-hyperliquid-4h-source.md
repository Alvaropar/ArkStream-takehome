# ADR-0011: Price check result; Hyperliquid 4h closes as a second reference for 32 coins

- Status: Accepted (proposal for Phase 2 marks; Phase 2 owns its use); amended by ADR-0044 (applied as of each origin)
- Date: 2026-11-19
- Phase: follower replay inputs (A13)

## Context
Rule pre-registered in ADR-0010 and applied unchanged. Data: Hyperliquid 4h candles for the 195 eligible core
perps (`data/reference/hyperliquid/candles_4h/`, 195 requests, 0 failures, own `MANIFEST.csv`). 2,223 bars with
no trades and 187 bars closing after CUTOFF dropped (`research/hyperliquid/candles_dropped.csv`); 6,605 bars
without a Binance price known at the close (outside a validity window, or no 1m bar with volume) are not
compared. Outputs: `research/hyperliquid/price_check.csv`, `price_check_bars.parquet`. Notional shares are of
eligible fills ($3.876B).

| Outcome | Coins | Notional | Share |
| --- | --- | --- | --- |
| pass | 163 | $3,786M | 97.7% |
| fail | 22 | $74M | 1.9% |
| no_binance | 10 | $16M | 0.4% |
| insufficient | 0 | | |

Passing coins: median of the per-coin median |gap| 5.4 bps; largest p95 29.6 bps. On 10-11 Oct (reported
apart, not in the rule) passing coins have median |gap| 7.9 bps and p95 26.4 bps (medians across coins).

Failing coins, largest first: XPL, WLFI, MON, LIT, MERL, LINEA, MET, SNX, STABLE, HMSTR, VVV, MAVIA, ZEREBRO,
CC, NOT, OMNI, TST, NEIROETH, CELO, DYDX, BOME, STG. Two kinds:
- **Large gaps after listing** (seen after the results, so it does not change the rule): XPL (p95 2,027 bps;
  gaps > 100 bps from 23 Aug to 25 Sep, then ~4 bps), WLFI (to 1 Sep), LINEA (to 8 Sep), CC (to 10 Nov), MET
  (to 20 Oct); MON and LIT differ by 200-400 bps for most of their sample.
- **Thin coins just over the bounds**: median 7-20 bps or p95 30-76 bps (SNX, MERL, HMSTR, CELO, DYDX, ...).

## Decision
1. **pass (163 coins)**: the Binance reference stands (ADR-0002) at every resolution.
2. **fail (22) and no_binance (10)**: these 32 coins are `hl_4h` coins. Their marks come from Hyperliquid 4h
   closes (`arkstream.hlprices.load_candles`), known at the bar close (open + 4 h), only bars with trades.
   This is a separate source (`source = hyperliquid_4h`, its own manifest and `src_file`), never written into
   or mixed with the Binance rows.
3. **Proposal for Phase 2**: for `hl_4h` coins use 4h closes for 4-hourly and daily marks (daily = last 4h close
   known at the day boundary). Hourly marks, intraday drawdown and MAE are **unavailable** for them and are
   reported as such, never filled from Binance or from package prints. For a failing coin the Binance rows
   remain on disk but are not used to value positions; the package's own fills stay usable as execution prices.
4. **Funding payments** (ADR-0009) for `hl_4h` coins use the last 4h close known at the hour as oracle proxy,
   labelled `oracle_proxy = hyperliquid_4h` (an approximation at most 4 h old).
5. Step 5 of the brief is therefore done by the same fetcher (`--kind candles_4h`); no finer Hyperliquid
   history exists for 2025 (ADR-0008). The requester-pays S3 archive is not used.

## Consequences
2.3% of notional is valued at 4h resolution only. Phase 2 must carry a `mark_resolution` per coin (1m Binance /
4h Hyperliquid) and must not compare intraday risk across the two. The post-listing observation could justify
a later rule like "Binance from N weeks after listing"; that would need a new ADR stating it was made after
seeing these results. Tests: `tests/test_funding.py` (4h alignment, no-trade and cutoff drops).
