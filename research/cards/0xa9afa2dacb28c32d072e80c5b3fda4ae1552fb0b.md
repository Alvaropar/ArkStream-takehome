# 0xa9afa2dacb28c32d072e80c5b3fda4ae1552fb0b

as of 2026-01-04T23:59:42.020000+00:00 · grade **B** · snapshot_gaps:use_multi_day_returns

## Flags

| field | value |
| --- | --- |
| n_snapshots | 40 |
| first_snapshot | 2025-11-20 19:56:39.793000+00:00 |
| last_snapshot | 2026-01-04 20:25:42.112000+00:00 |
| days_present | 40 |
| first_date | 2025-11-20 |
| last_date | 2026-01-04 |
| n_snapshot_gaps | 2 |
| max_gap_days | 6.38382181712963 |
| snapshot_gap_first_src_row | 85185 |
| outage_exact | True |
| outage_spanned | True |
| outage_first_src_row | 85186 |
| stale_equity_rows | 35 |
| stale_equity_first_src_row | 85187 |
| zero_equity_rows | 0 |
| zero_equity_first_src_row | None |
| near_zero_equity_share | 0.0 |
| median_equity | 2706.60684 |
| frozen_rows | 0 |
| frozen_first_src_row | None |
| usable_days | 40 |
| dropped_out | False |
| joined_date | 2025-11-20 |
| calendar_days | 46 |
| days_present_share | 0.8695652173913043 |
| unusable_day_share | 0.13043478260869568 |
| days_to_asof | 46 |
| zero_equity_holding_rows | 0 |
| zero_equity_holding_first_src_row | None |
| n_fills | 162 |
| n_perp_fills | 162 |
| eligible_notional_share | 1.0 |
| maker_share | 0.0 |
| first_fill | 2025-11-20 08:19:28.701000+00:00 |
| last_fill | 2025-12-05 21:51:20.609000+00:00 |
| non_trade_events | 0 |
| continuity_breaks | 0 |
| continuity_break_first_src_row | None |
| unresolved_chains | 0 |
| mixed_ms_groups | 0 |
| pnl_match_share | 1.0 |
| pnl_rows_gt_tight | 0 |
| pnl_rows_gt_loose | 0 |
| pnl_diff_mean | 1.7053025658242404e-14 |
| pnl_offset_cv | 4.665445505670575 |
| pnl_larger_when_loose | True |
| pnl_mismatch_first_src_row | None |
| closed_pnl_total | 3038.166385 |
| rebuilt_realized_known | 1538.0460000001121 |
| closed_pnl_known | 1538.099785 |
| realized_diff | -0.05378499988796648 |
| realized_diff_rel | 3.496847240503741e-05 |
| fills_unknown_entry | 2 |
| fills_pnl_mismatch | 0 |
| realized_mismatch_first_src_row | None |
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
| outage_exact | 1 | traders.csv | 85186 |
| outage_spanned | 1 | traders.csv | 85186 |
| snapshot_gap | 2 | traders.csv | 85185, 85186 |
| stale_equity | 35 | traders.csv | 85187, 85188, 85189, 85191, 85192, 85194, 85195, 85196, 85197, 85198 |
