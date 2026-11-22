# Data dictionary — Milestone 1 (data contract)

All timestamps are UTC, millisecond precision. Every derived row keeps `src_row`, the 1-based line number
of its source row in the raw file (header = line 1), plus the natural keys (trader, tid, oid, ts). To
see a raw row: `sed -n '<src_row>p' data/raw/fills.csv`.

Counts below are as of the confirmed CUTOFF 2026-01-04T23:59:42.020Z and are enforced by
`provenance/expected_counts.yaml` (`make audit`).

## Raw inputs (read-only)

| file | origin in package | sha256 (first 12) | rows | notes |
| --- | --- | --- | --- | --- |
| `data/raw/traders.csv` | `笔试题数据包-traders.csv` (byte copy) | `56228fab8b3c` | 129,665 | 1,500 addresses, 2025-07-10 22:04:24.927 → 2026-01-04 23:59:31.671 |
| `data/raw/fills.csv` | `笔试题数据包-fills/笔试题数据包-fills` (byte copy) | `8eff40ef33a2` | 899,330 | 1,200 addresses, 325 symbols, 2025-07-27 08:52:47.550 → 2026-01-04 23:59:42.020 |
| `data/reference/prices/` | Binance USD-M 1m kline closes (A13), read only through `MANIFEST.yaml` | per file in the manifest | 47,400,103 | 185 coins, 2025-07-01 → 2026-01-04 23:59:00 (known times); source note `data/reference/binance/SOURCE.md` |

The fills file is described as `fills.gz` but its bytes are plain CSV (no gzip magic). The reader sniffs
the magic bytes, so a genuinely gzipped file also works. Full hashes: `provenance/CHECKSUMS.txt`.

### traders.csv — daily account snapshots

| column | type | meaning / observed facts |
| --- | --- | --- |
| timestamp | UTC ms | snapshot time. Formats: `.fff` 116,671 rows; `.ff` 11,663; `.f` 1,186; none 145. No offset suffix → UTC |
| user | str | identical to `trader` on every row |
| cross_margin_summary_account_value | f64 | identical to `equity` on every row |
| net_deposit | f64 | cumulative deposits − withdrawals |
| pnl | f64 | venue-reported PnL. ≠ equity − net_deposit on 10,696 rows (>0.01) |
| trader | str | address (lower-case hex) |
| date | date | equals `timestamp`'s UTC date on every row; (trader, date) is unique |
| equity | f64 | **cross-margin account value, not NAV** (A04). 2,539 rows are exactly 0 |

### fills.csv — fills

| column | type | meaning / observed facts |
| --- | --- | --- |
| timestamp | UTC ms | fill time. Formats: `.fff+00` 807,853; `.ff+00` 82,030; `.f+00` 8,150; `+00` only 1,297 |
| trader | str | address |
| symbol | str | coin. Core perp (`BTC`), spot (`@n`, `PURR/USDC`), HIP-3 (`dex:SYMBOL`: xyz, vntl, hyna, flx) |
| side | buy/sell | signed delta = +size (buy) / −size (sell) |
| dir | str | Open/Close Long/Short, Long > Short, Short > Long, Buy/Sell (spot), Auto-Deleveraging (656), Settlement (37), Liquidated Isolated/Cross (34), Spot Dust Conversion (785) |
| price, size, notional | f64 | notional = price × size |
| fee, fee_token | f64, str | 62 fee tokens (USDC mostly; spot fees in the bought token) |
| closed_pnl | f64 | venue realized PnL on the closed part, **excluding fees** (matches average-cost rebuild on 97.1% of fills with known entry) |
| start_position | f64 | signed position *before* the fill |
| is_maker | bool | 330,896 maker / 568,434 taker |
| tid | i64 | trade id. **Not unique**: 785 rows with tid = 0, all Spot Dust Conversion |
| oid | i64 | order id |

**Key.** `(trader, tid, oid, ts, symbol, dir)` is unique (0 duplicates). (trader, tid) repeats in 127
pairs covering 678 rows (551 surplus rows), all Spot Dust Conversion with tid = 0. Dust conversions are
kept as `event_kind = non_trade`, never deleted, never traded.

## Instrument classes (`config/instruments.yaml`)

| class | rule | fills | eligible |
| --- | --- | --- | --- |
| core_perp | default | 854,315 | **yes** (195 coins traded) |
| hip3 | `^[a-z0-9]+:.+$` | 10,308 (1.2% of perp fills) | no |
| spot | `^@\d+$` or `PURR/USDC` | 34,707 (incl. 785 dust) | no |

Perp fills (core + HIP-3, trades) = **864,623**; these are reconstructed.

## Processed (`data/processed/`, rebuilt by `make data`; git-ignored)

* `traders/date=YYYY-MM-DD/part-0.parquet`, `fills/date=…/part-0.parquet`: typed copies, sorted by
  `src_row` within date, plus `raw_timestamp` (original string) and `src_row`.
* `derived/asof=<YYYYMMDDTHHMMSSZ>/*.parquet`: every table below, computed only from rows with
  `ts <= asof` (asof capped at CUTOFF).

## Derived tables

### ledger — one row per perp fill, in reconstructed order
Raw fill columns plus: `instrument_class, eligible, is_perp, event_kind, delta`;
`group_kind` (single / one_sided / mixed: fills sharing trader, symbol, ms); `chain_resolved`;
`seq` (order within trader × symbol); `prev_end` (previous fill's end position);
`continuity_break` (start_position ≠ prev_end, tolerance 1e-9 abs + 1e-9 rel);
`pos_before, pos_after`; `trip_no`; `avg_entry_before` (average-cost entry, null if unknown);
`rebuilt_realized` (average-cost realized PnL; **null when the entry is unknown**, never imputed).

Ordering rule within a millisecond: one-sided groups by signed start_position; mixed groups by a
depth-first feasible chain that must start at the previous fill's end. No look-ahead (the next fill is
never used). Result: 0 breaks; 10 fills in 3 mixed groups, all resolved.

### round_trips — flat → flat per (trader, symbol)
`trip_no, side, open_ts, close_ts, entry_/exit_ src_row, tid, oid, n_fills, max_abs_pos, closed_pnl,
fees, rebuilt_realized, rebuilt_known, notional, left_censored, open_at_asof, holding_s (closed),
age_at_asof_s (open)`. A zero-crossing fill closes one trip and opens the next (its PnL and fee go to
the closing trip). `left_censored`: the series' first observed position was non-zero (A06), so entry
and hold time are unknown. 49,457 trips: 47,247 closed, 2,210 open at cutoff, 1,868 left-censored.

### open_positions — non-zero positions at asof
`trader, symbol, position, last_ts, last_src_row, last_tid, last_oid, instrument_class, trip_no, open_ts,
left_censored, asof`.

### recon_snapshots — pnl vs equity − net_deposit, per address
`pnl_rows_gt_tight` (>0.01), `pnl_rows_gt_loose` (>1), `pnl_match_share`, `pnl_diff_mean/std/last`,
`pnl_offset_cv` (std/|mean|, "stable offset" test), `pnl_larger_when_loose`, `first_mismatch_src_row/ts`.

### recon_fills — closed_pnl vs rebuilt realized PnL, per address
`closed_pnl_total`, `closed_pnl_known` and `rebuilt_realized_known` (fills with known entry),
`realized_diff(_rel)`, `fills_unknown_entry`, `fills_pnl_mismatch` (|diff| > 0.01 + 1e-6 × notional),
`first_pnl_mismatch_src_row`. Differences are **unexplained reconciliation differences** (entry-price
rounding, scope, pricing), never a funding estimate.

### price_coverage / price_compare / price_unpriced
Reference files: listed in `data/reference/prices/MANIFEST.yaml` (path, sha256, bytes, rows); columns
`ts` (UTC ms, the time the price became known: the 1m bar close), `coin` (Hyperliquid name), `price`
(Binance close × `price_factor_hl_per_binance`), `source_symbol`. Only bars inside the coin's validity window
(`data/reference/binance/hl_binance_map.csv`: `valid_from`, `valid_to`, `status`) and with volume > 0.
`price_coverage`: per eligible coin, `ref_first, ref_last, ref_rows, ref_flag`
(`ok` / `no_reference_coverage` / `reference_ends_early`), `ref_reason`.
`price_compare`: each eligible package print joined to the latest reference price known at or before it,
at most `print_match_window_s` (60 s) old: `coin, print_ts, print_px, print_src_row, ref_ts, ref_px, ref_file,
diff_bps` (print/ref − 1), `cmp_flag` (`ok` / `disagree` beyond `disagreement_tolerance_bps` /
`no_reference_in_window`).
`open_positions` adds the mark at asof: `mark_price, mark_ts, mark_source` (`reference` = known within
`max_age_s` 60 s; `package_print` = the package's own print within `fallback_print_window_s` 60 s;
`unpriced`), `mark_ref_file`, `mark_print_src_row`, `unpriced_reason`, `mark_notional`. Nothing is carried
forward. `price_unpriced` lists the unpriced open positions with the reason.

### copier_pairs / copier_flagged / copier_clusters
Orders = (trader, oid) over perp trade fills, timed at the first fill. A leader order is matched when the
follower places an order in the same coin and side within (0, 30] s after it.
`match_share` = matched / leader orders inside the follower's active span [first order − 30 s, last
order]; `match_share_full` = matched / all leader orders. `lag_p10/p50/p90`,
`log_size_ratio_median/iqr` (follower size / leader size). `copier_flagged` adds the placebo (20 random
constant shifts of the follower, |shift| ∈ [300 s, 1 day], seeded per pair): `placebo_mean/p95/max`,
`confirmed` = match_share ≥ 0.25 and > 3 × placebo p95. `copier_clusters`: connected components of
confirmed pairs; `is_original` = member most followed by others (proposal).

### quality_report (`research/quality_report.parquet`) — one row per address, one column per flag
Coverage: `n_snapshots, first/last_snapshot, days_present, calendar_days, days_present_share,
n_snapshot_gaps (>1.5 d), max_gap_days, outage_exact (gap exactly 11-22 → 11-28), outage_spanned (gap
bridging 11-23..11-27), stale_equity_rows (equity = previous snapshot), zero_equity_rows,
near_zero_equity_share (<10 USDC), unusable_day_share, zero_equity_holding_rows (zero equity while the
rebuilt book holds a position), dropped_out (no snapshot in the last 3 days before asof), joined_date,
median_equity`. Fills: `n_fills, n_perp_fills, no_fills, eligible_notional_share, maker_share,
first/last_fill, non_trade_events, continuity_breaks, unresolved_chains, mixed_ms_groups`.
Reconciliation and copier columns as above. `grade` (A/B/C), `grade_reason`, `asof`, `config_version`.
Every flag has a `<flag>_first_src_row` pointer.

### quality_evidence (`research/quality_evidence.parquet`) — every raw row behind every flag
`trader, flag, file, src_row, ts, tid, oid, detail`. Flags: snapshot_gap, outage_exact, outage_spanned,
stale_equity, frozen_snapshot, zero_equity, zero_equity_while_holding, continuity_break, pnl_identity_mismatch,
non_trade_event.

### research/cards/<address>.md
Per-address card: grade, every flag value, and the first 10 raw rows per flag.

## Grades (placeholders, `config/decision_context.yaml`, fixed on development data only)

| grade | rule |
| --- | --- |
| C | any of: no snapshots; no fills; a continuity break; near-zero equity on >50% of snapshots; >20% of calendar days without a usable snapshot; pnl identity holds on <99% of rows with an unstable offset (CV > 0.25) |
| B | not C, and any of: <95% of days present (use multi-day returns); stable scope offset (use rebuilt book); zero equity while holding (use rebuilt book) |
| A | none of the above |


## Phase 2 rework

Coverage for grading counts both the first snapshot date and the origin date. A usable date has a non-frozen
snapshot above the near-zero floor. Frozen rows and their first source key are reported separately.

In each origin directory, `daily_marks` keys are coin and boundary time. `funding_payments` keys are trader,
coin and accrual hour, with rate publication time, proxy mark and source fill. `book_vs_account` joins to
`snapshot_marks` by trader and snapshot source row. `book_attribution` is its additive USDC bridge.
`book_daily.day` is the opening date of a UTC day. `daily_twr.return_source` identifies either cross-margin
snapshot returns (with both snapshot source rows) or funded core-perp book returns (with opening equity source row
and exact UTC boundaries). One source applies throughout an address's history at an origin. `account_returns`
keeps both snapshot indices and the role of the snapshot series. The evidence table pairs primary `twr` and
`return_coverage` with `snapshot_twr_check`, `snapshot_twr_end_check` and `account_coverage`.
The column `r_start` holds the primary subperiod return. Book returns use the opening equity denominator and have
no end-flow sensitivity. `gap_path.t` is an interim book observation with unknown deposit timing.
`market_sample` provides every joint regression observation and the matched factor close. `twr_summary`
and `market_exposure` report daily-unit statistics and coverage. `gates` lists all component statuses.

`unpriced` in the bridge includes intervals with unknown opening inventory or funding. `noncore` has priority
where both kinds of missing information occur. `pnl_with_known_funding` on an open round trip retains its
marked PnL even when the latest rate is unpublished. `net_pnl` requires every expected payment.
