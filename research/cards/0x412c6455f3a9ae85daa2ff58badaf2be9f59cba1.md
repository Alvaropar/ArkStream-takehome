# 0x412c6455f3a9ae85daa2ff58badaf2be9f59cba1

as of 2026-01-04T23:59:42.020000+00:00 · grade **B** · snapshot_gaps:use_multi_day_returns

## Flags

| field | value |
| --- | --- |
| n_snapshots | 24 |
| first_snapshot | 2025-12-08 23:10:25.129000+00:00 |
| last_snapshot | 2025-12-31 19:59:55.839000+00:00 |
| days_present | 24 |
| first_date | 2025-12-08 |
| last_date | 2025-12-31 |
| n_snapshot_gaps | 0 |
| max_gap_days | 1.0880126388888889 |
| snapshot_gap_first_src_row | None |
| outage_exact | False |
| outage_spanned | False |
| outage_first_src_row | None |
| stale_equity_rows | 18 |
| stale_equity_first_src_row | 35432 |
| zero_equity_rows | 0 |
| zero_equity_first_src_row | None |
| near_zero_equity_share | 0.0 |
| median_equity | 1696.809572 |
| frozen_rows | 0 |
| frozen_first_src_row | None |
| usable_days | 24 |
| dropped_out | True |
| joined_date | 2025-12-08 |
| calendar_days | 28 |
| days_present_share | 0.8571428571428571 |
| unusable_day_share | 0.1428571428571429 |
| days_to_asof | 28 |
| zero_equity_holding_rows | 0 |
| zero_equity_holding_first_src_row | None |
| n_fills | 75 |
| n_perp_fills | 75 |
| eligible_notional_share | 1.0 |
| maker_share | 0.22666666666666666 |
| first_fill | 2025-12-08 17:45:08.269000+00:00 |
| last_fill | 2025-12-17 19:35:01.020000+00:00 |
| non_trade_events | 0 |
| continuity_breaks | 0 |
| continuity_break_first_src_row | None |
| unresolved_chains | 0 |
| mixed_ms_groups | 0 |
| pnl_match_share | 1.0 |
| pnl_rows_gt_tight | 0 |
| pnl_rows_gt_loose | 0 |
| pnl_diff_mean | 1.342629711113356e-13 |
| pnl_offset_cv | 0.3943335328384907 |
| pnl_larger_when_loose | True |
| pnl_mismatch_first_src_row | None |
| closed_pnl_total | 484.18131800000003 |
| rebuilt_realized_known | 483.6971330000009 |
| closed_pnl_known | 484.181318 |
| realized_diff | -0.4841849999990586 |
| realized_diff_rel | 0.001000007604587211 |
| fills_unknown_entry | 0 |
| fills_pnl_mismatch | 15 |
| realized_mismatch_first_src_row | 263951 |
| copier_cluster | None |
| copier_cluster_size | None |
| copier_is_original | False |
| no_snapshots | False |
| copier_flag | False |
| no_fills | False |
| grade | B |
| grade_reason | snapshot_gaps:use_multi_day_returns |
| asof | 2026-01-04 23:59:42.020000+00:00 |
| config_version | 0.1.0-m1 |

## Evidence (raw rows; first 10 per flag)

| flag | rows | file | src_row |
| --- | --- | --- | --- |
| stale_equity | 18 | traders.csv | 35432, 35433, 35434, 35435, 35437, 35438, 35439, 35440, 35441, 35442 |
