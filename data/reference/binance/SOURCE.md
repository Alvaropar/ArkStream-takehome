# Reference prices: source note (A13)

## What and where

| item | location |
| --- | --- |
| Reference prices (what the build reads) | `data/reference/prices/binance_um_1m_YYYY-MM.parquet`, listed with SHA-256 in `data/reference/prices/MANIFEST.yaml` |
| Coin mapping with validity windows | `data/reference/binance/hl_binance_map.csv` |
| Window overrides (requested dates, with kind and reason) | `data/reference/binance/window_overrides.yaml` |
| Evidence behind every window | `data/reference/binance/window_evidence.csv` (one row per coin) |
| SHA-256 of the original Binance zips | `data/reference/binance/CHECKSUMS.txt` |
| Fetch and dry-run logs (klines, aggTrades sample) | `data/reference/binance/logs/` |
| Binance symbol list; Hyperliquid symbol profile | `binance_um_symbols.txt`, `hl_symbols_all.csv` |
| Trade-level prices for drift | `data/reference/binance/aggtrades/<SYM>/` + `MANIFEST.csv` (written by `src/arkstream_fetch/fetch_aggtrades.py`) |

Regenerate prices, mapping windows, evidence and checksums: `uv run python -m arkstream refprices`
(about 1 minute; reads `data/lake`). Rebuild Milestone 1: `make build`. The build needs only
`data/reference/prices/`, not the lake.

## Source

* **Binance USD-M futures 1m klines**, monthly archive at `https://data.binance.vision/data/futures/um/monthly/klines/<SYM>/1m/`,
  186 symbols, July 2025 to January 2026. Every zip was checked against Binance's published `.CHECKSUM`
  when fetched (retrieved and verified 2026-11-18); `CHECKSUMS.txt` lists the 1,326 original zips as of
  2026-11-18 (1,270 kline months + 56 aggTrades days) and marks each `verified`. The kline zips are kept,
  unchanged, in `data/lake/_raw/data/futures/um/monthly/`. The 56 aggTrades zips were removed from
  `data/lake/_raw` on 2026-11-19 after byte-identical copies were verified into
  `data/reference/binance/aggtrades/` (listed in its MANIFEST.csv with source `seed`); a rerun of `refprices`
  rewrites CHECKSUMS.txt without them; the lake (`data/lake/venue=binance/dataset=binance.um.klines/`) holds
  the same rows as Parquet, and the kline copy is complete.
* Columns used: bar open time, close, volume. The lake stamps each bar at its close (`ts_known` = open + 60 s);
  that is the reference `ts`, the time the price became known.
* Not used, and deleted on 2026-11-19: the lake's aggTrades copy (its `_manifest.sqlite` rows for `binance.um.agg_trades` still describe it). It was missing 0.4-9% of rows (whole minutes whose volume did not match
  the kline exactly, concentrated in the 10 Oct 2025 crash). Drift reads the original aggTrades zips.

## Rules applied (`src/arkstream/refprices.py`)

1. **Cutoff.** Only bars known at or before 2026-01-04 23:59:59 UTC. The January 2026 monthly zip holds the whole
   month; everything after the cutoff is dropped, including the 23:59 bar of 4 Jan (known at 00:00:00 on 5 Jan).
2. **Validity window.** A bar is kept only if the date of its known time lies in [valid_from, valid_to]
   (UTC, inclusive).
3. **Zero-volume bars dropped.** Binance's archive prints flat bars at the last price for contracts that are not
   trading (1.2M of the 48.6M bars to the cutoff). They are never written, so no price is carried forward
   through them: a reference price answers (coin, t) only if known in [t - 60 s, t].
4. **Price factor.** price = close x `price_factor_hl_per_binance` (1000 for kNEIRO/NEIROUSDT and kDOGS/DOGSUSDT,
   1 elsewhere; kPEPE, kBONK, kSHIB, kFLOKI, kLUNC map to Binance's 1000-prefixed contracts at factor 1).
5. **Fallback (A13).** Where no reference price is known within 60 s, the package's own latest print within
   60 s is used (`price_source = package_print`); otherwise the point stays unpriced and is logged
   (`price_unpriced`). Nothing is filled in.

Result: 47,400,103 rows for the 185 coins with a window, 114 MB in seven monthly files.

## Validity windows

Default rule, applied to every coin: from the date of its first Binance bar with volume > 0 (2025-07-01 for
contracts already listed when the archive window starts) to the cutoff, or to the date of its last bar with
volume > 0 if trading stopped more than a day before the cutoff. `status` is computed from the window and the
coin's Hyperliquid fill span: `full` (window covers every Hyperliquid fill date), `partial`, `never_valid`, or
`unmapped` (no Binance USD-M contract). It replaces the old status, which only knew listing dates.

Counts: 181 full, 4 partial (LIT, MET, MON, OMNI), 3 never valid (FTT, FOGO, MEGA), 7 unmapped (APEX, BLAST,
LAUNCHCOIN, MNT, PURR, REQ, YZY).

Requested windows, checked against the data (times are bar known times, UTC):

| coin | requested | data evidence | final window | status |
| --- | --- | --- | --- | --- |
| FTT | never valid | all 270,719 bars to the cutoff have zero volume, frozen at 1.59; Hyperliquid FTT trades at 0.55-1.00 (median basis -37% to -66%) | never | never_valid |
| LIT | from 2025-12-23 | 252,000 zero-volume bars at about 0.59 before 2025-12-23 (an unrelated old token); first bar with volume closes 2025-12-23 17:31; Hyperliquid LIT trades at about 3.9 on 22 Dec | 2025-12-23 .. 2026-01-04 | partial (Hyperliquid fills from 2025-12-22) |
| PUMP | from 2025-07-10 | earlier archive bars flat and zero-volume; first bar with volume closes 2025-07-10 07:31 | 2025-07-10 .. 2026-01-04 | full |
| MKR | to 2025-09-07 | normal trading continues into 8 Sep (4.9M USDT in the last three hours); last bar with volume closes 2025-09-08 09:00 | 2025-07-01 .. **2025-09-08** (corrected) | full |
| OMNI | to 2025-09-21 | last bar with volume closes 2025-09-22 09:01 (21.8M USDT traded 06:00-09:01); afterwards flat at 4.274 | 2025-07-01 .. **2025-09-22** (corrected) | partial (Hyperliquid fills to 2025-09-25) |
| NEIROETH | to 2025-09-25 | last bar with volume closes 2025-09-26 09:01 (21.5M USDT traded 06:00-09:01, price falling 0.0137 -> 0.0086) | 2025-07-01 .. **2025-09-26** (corrected) | full |
| AI16Z | to 2025-11-05 | last bar with volume closes 2025-11-06 09:01 (4.5M USDT traded 06:00-09:01) | 2025-07-01 .. **2025-11-06** (corrected) | full |

The four delisting dates were one day early: each contract traded until about 09:00 UTC on the following day,
Binance's delisting time, and its archive bars are flat and zero-volume after that. The final windows follow
the data; on the last day only bars before 09:01 carry volume, so only they enter the reference. Not requested
but found by the same rule: MON (first bar 2025-10-10 07:18) and MET (2025-10-11 12:31) list on Binance after
Hyperliquid's pre-launch markets start (2025-10-08 and 2025-10-10), and FOGO and MEGA list on Binance only after
the cutoff (no bars before it). No other coin's last bar with volume is before 2026-01-04 23:59.

## Validation against the package's prints (cutoff build)

`price_compare` takes, for every eligible package print, the latest reference price known at or before it
and at most 60 s old: 742,562 agree within 50 bps, 89,782 disagree, 21,971 have no reference price in the
window (coins without a window, or no Binance trade in that minute). Median |print/reference - 1|: 9 bps
(BTC 5, ETH 7, SOL 7, HYPE 12). Disagreement concentrates in thin or newly listed coins and fast markets.
Cases looked at:

* USTC: the 13 prints are all on 10-11 Oct; 9 of them sit at 0.005556 during the crash while Binance's
  minute closes fell to 0.0045 (2,446 bps). A crash dislocation, not a mapping error.
* HMSTR: a stable 1.4% gap in January at a price of 0.00025, where one Hyperliquid tick is 40 bps; tick size,
  not mapping.
* LIT: 120-280 bps above Binance in the first days after Binance's listing, falling to 20 bps by January.
* OMNI after 2025-09-22 09:01: Binance prints flat zero-volume bars at 4.274; they are dropped, so the
  Hyperliquid fills of 22-25 Sep fall back to package prints or stay unpriced.

## Point in time

Every bar is used only from its close. The mapping's `hl_first_fill`/`hl_last_fill` columns and the window
evidence span the whole period: they are data hygiene (which Binance contract is the same asset when), not a
value that feeds selection (A15). Holdout prices (2025-12-03 onward) are in the reference files because the
follower's holdout results need them; no drift or cost parameter is estimated from them (see
`config/decision_context.yaml: drift`).
