# 0x6ecd4ae1b8c35756ed8eaba235bded5d9e8cbba0

as of 2026-01-04T23:59:42.020000+00:00 · grade **C** · too_many_unusable_days

## Flags

| field | value |
| --- | --- |
| n_snapshots | 52 |
| first_snapshot | 2025-07-14 22:11:02.454000+00:00 |
| last_snapshot | 2025-11-21 22:24:25.905000+00:00 |
| days_present | 52 |
| first_date | 2025-07-14 |
| last_date | 2025-11-21 |
| n_snapshot_gaps | 2 |
| max_gap_days | 53.33868885416666 |
| snapshot_gap_first_src_row | 57321 |
| outage_exact | False |
| outage_spanned | False |
| outage_first_src_row | None |
| stale_equity_rows | 48 |
| stale_equity_first_src_row | 57286 |
| zero_equity_rows | 0 |
| zero_equity_first_src_row | None |
| near_zero_equity_share | 0.0 |
| median_equity | 15141.17261 |
| frozen_rows | 0 |
| frozen_first_src_row | None |
| usable_days | 52 |
| dropped_out | True |
| joined_date | 2025-07-14 |
| calendar_days | 175 |
| days_present_share | 0.29714285714285715 |
| unusable_day_share | 0.7028571428571428 |
| days_to_asof | 175 |
| zero_equity_holding_rows | 0 |
| zero_equity_holding_first_src_row | None |
| n_fills | 105 |
| n_perp_fills | 105 |
| eligible_notional_share | 1.0 |
| maker_share | 0.0 |
| first_fill | 2025-08-04 06:05:45.556000+00:00 |
| last_fill | 2025-10-10 21:35:30.566000+00:00 |
| non_trade_events | 0 |
| continuity_breaks | 0 |
| continuity_break_first_src_row | None |
| unresolved_chains | 0 |
| mixed_ms_groups | 0 |
| pnl_match_share | 1.0 |
| pnl_rows_gt_tight | 0 |
| pnl_rows_gt_loose | 0 |
| pnl_diff_mean | 2.361188168064333e-13 |
| pnl_offset_cv | 1.1749283848102163 |
| pnl_larger_when_loose | True |
| pnl_mismatch_first_src_row | None |
| closed_pnl_total | 1528.0686759999996 |
| rebuilt_realized_known | 1527.9596399998422 |
| closed_pnl_known | 1528.068676 |
| realized_diff | -0.10903600015785742 |
| realized_diff_rel | 7.135543177501625e-05 |
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
| snapshot_gap | 2 | traders.csv | 57321, 57336 |
| stale_equity | 48 | traders.csv | 57286, 57287, 57288, 57289, 57290, 57291, 57292, 57294, 57295, 57296 |
