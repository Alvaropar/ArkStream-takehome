# 0x64baf69ab2fbf4abb1624bcd7fe7ac64feb0e245

as of 2026-01-04T23:59:42.020000+00:00 · grade **C** · too_many_unusable_days

## Flags

| field | value |
| --- | --- |
| n_snapshots | 17 |
| first_snapshot | 2025-09-24 22:07:48.180000+00:00 |
| last_snapshot | 2025-11-21 09:51:40.570000+00:00 |
| days_present | 17 |
| first_date | 2025-09-24 |
| last_date | 2025-11-21 |
| n_snapshot_gaps | 1 |
| max_gap_days | 42.79540359953704 |
| snapshot_gap_first_src_row | 51545 |
| outage_exact | False |
| outage_spanned | False |
| outage_first_src_row | None |
| stale_equity_rows | 16 |
| stale_equity_first_src_row | 51531 |
| zero_equity_rows | 0 |
| zero_equity_first_src_row | None |
| near_zero_equity_share | 0.0 |
| median_equity | 4357.155899 |
| frozen_rows | 0 |
| frozen_first_src_row | None |
| usable_days | 17 |
| dropped_out | True |
| joined_date | 2025-09-24 |
| calendar_days | 103 |
| days_present_share | 0.1650485436893204 |
| unusable_day_share | 0.8349514563106796 |
| days_to_asof | 103 |
| zero_equity_holding_rows | 0 |
| zero_equity_holding_first_src_row | None |
| n_fills | 29 |
| n_perp_fills | 29 |
| eligible_notional_share | 1.0 |
| maker_share | 0.0 |
| first_fill | 2025-09-24 09:57:51.484000+00:00 |
| last_fill | 2025-09-24 18:50:58.364000+00:00 |
| non_trade_events | 0 |
| continuity_breaks | 0 |
| continuity_break_first_src_row | None |
| unresolved_chains | 0 |
| mixed_ms_groups | 0 |
| pnl_match_share | 1.0 |
| pnl_rows_gt_tight | 0 |
| pnl_rows_gt_loose | 0 |
| pnl_diff_mean | -5.115907697472721e-13 |
| pnl_offset_cv | 0.0 |
| pnl_larger_when_loose | True |
| pnl_mismatch_first_src_row | None |
| closed_pnl_total | 404.06014799999997 |
| rebuilt_realized_known | 404.04953999999805 |
| closed_pnl_known | 404.06014799999997 |
| realized_diff | -0.010608000001923301 |
| realized_diff_rel | 2.6253517092517873e-05 |
| fills_unknown_entry | 0 |
| fills_pnl_mismatch | 0 |
| realized_mismatch_first_src_row | None |
| copier_cluster | None |
| copier_cluster_size | None |
| copier_is_original | False |
| no_snapshots | False |
| copier_flag | False |
| no_fills | False |
| grade | C |
| grade_reason | too_many_unusable_days |
| asof | 2026-01-04 23:59:42.020000+00:00 |
| config_version | 0.1.0-m1 |

## Evidence (raw rows; first 10 per flag)

| flag | rows | file | src_row |
| --- | --- | --- | --- |
| snapshot_gap | 1 | traders.csv | 51545 |
| stale_equity | 16 | traders.csv | 51531, 51532, 51533, 51534, 51535, 51536, 51537, 51538, 51539, 51540 |
