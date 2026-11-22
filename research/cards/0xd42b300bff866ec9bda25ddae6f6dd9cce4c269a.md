# 0xd42b300bff866ec9bda25ddae6f6dd9cce4c269a

as of 2026-01-04T23:59:42.020000+00:00 · grade **C** · equity_near_zero;too_many_unusable_days

## Flags

| field | value |
| --- | --- |
| n_snapshots | 18 |
| first_snapshot | 2025-08-01 14:08:58.339000+00:00 |
| last_snapshot | 2026-01-04 20:00:04.964000+00:00 |
| days_present | 18 |
| first_date | 2025-08-01 |
| last_date | 2026-01-04 |
| n_snapshot_gaps | 3 |
| max_gap_days | 81.34119362268518 |
| snapshot_gap_first_src_row | 107056 |
| outage_exact | False |
| outage_spanned | True |
| outage_first_src_row | 107072 |
| stale_equity_rows | 16 |
| stale_equity_first_src_row | 107056 |
| zero_equity_rows | 17 |
| zero_equity_first_src_row | 107055 |
| near_zero_equity_share | 0.9444444444444444 |
| median_equity | 0.0 |
| frozen_rows | 1 |
| frozen_first_src_row | 107056 |
| usable_days | 1 |
| dropped_out | False |
| joined_date | 2025-08-01 |
| calendar_days | 157 |
| days_present_share | 0.11464968152866242 |
| unusable_day_share | 0.9936305732484076 |
| days_to_asof | 157 |
| zero_equity_holding_rows | 0 |
| zero_equity_holding_first_src_row | None |
| n_fills | 113 |
| n_perp_fills | 113 |
| eligible_notional_share | 1.0 |
| maker_share | 0.0 |
| first_fill | 2025-10-21 09:43:41.419000+00:00 |
| last_fill | 2026-01-04 11:04:25.638000+00:00 |
| non_trade_events | 0 |
| continuity_breaks | 0 |
| continuity_break_first_src_row | None |
| unresolved_chains | 0 |
| mixed_ms_groups | 0 |
| pnl_match_share | 1.0 |
| pnl_rows_gt_tight | 0 |
| pnl_rows_gt_loose | 0 |
| pnl_diff_mean | 1.0105496686365869e-13 |
| pnl_offset_cv | 4.242640687119286 |
| pnl_larger_when_loose | True |
| pnl_mismatch_first_src_row | None |
| closed_pnl_total | 1271.529533 |
| rebuilt_realized_known | 1271.5831699998496 |
| closed_pnl_known | 1271.529533 |
| realized_diff | 0.05363699984968662 |
| realized_diff_rel | 4.218305470509793e-05 |
| fills_unknown_entry | 0 |
| fills_pnl_mismatch | 1 |
| realized_mismatch_first_src_row | 734164 |
| copier_cluster | None |
| copier_cluster_size | None |
| copier_is_original | False |
| no_snapshots | False |
| copier_flag | False |
| no_fills | False |
| grade | C |
| grade_reason | equity_near_zero;too_many_unusable_days |
| asof | 2026-01-04 23:59:42.020000+00:00 |
| config_version | 0.1.0-m1 |

## Evidence (raw rows; first 10 per flag)

| flag | rows | file | src_row |
| --- | --- | --- | --- |
| frozen_snapshot | 1 | traders.csv | 107056 |
| outage_spanned | 1 | traders.csv | 107072 |
| snapshot_gap | 3 | traders.csv | 107056, 107071, 107072 |
| stale_equity | 16 | traders.csv | 107056, 107057, 107058, 107059, 107060, 107061, 107062, 107063, 107064, 107065 |
| zero_equity | 17 | traders.csv | 107055, 107056, 107057, 107058, 107059, 107060, 107061, 107062, 107063, 107064 |
