# 0x2fa0b8a5dfbdbb71a7aa148d4cc45dee9ddfd3f3

as of 2026-01-04T23:59:42.020000+00:00 · grade **B** · snapshot_gaps:use_multi_day_returns

## Flags

| field | value |
| --- | --- |
| n_snapshots | 164 |
| first_snapshot | 2025-07-15 22:39:57.095000+00:00 |
| last_snapshot | 2026-01-04 20:08:31.427000+00:00 |
| days_present | 164 |
| first_date | 2025-07-15 |
| last_date | 2026-01-04 |
| n_snapshot_gaps | 3 |
| max_gap_days | 6.70180375 |
| snapshot_gap_first_src_row | 24623 |
| outage_exact | True |
| outage_spanned | True |
| outage_first_src_row | 24734 |
| stale_equity_rows | 0 |
| stale_equity_first_src_row | None |
| zero_equity_rows | 0 |
| zero_equity_first_src_row | None |
| near_zero_equity_share | 0.0 |
| median_equity | 1983.917341 |
| frozen_rows | 0 |
| frozen_first_src_row | None |
| usable_days | 164 |
| dropped_out | False |
| joined_date | 2025-07-15 |
| calendar_days | 174 |
| days_present_share | 0.9425287356321839 |
| unusable_day_share | 0.05747126436781613 |
| days_to_asof | 174 |
| zero_equity_holding_rows | 0 |
| zero_equity_holding_first_src_row | None |
| n_fills | 178 |
| n_perp_fills | 134 |
| eligible_notional_share | 0.7097778167846652 |
| maker_share | 0.2303370786516854 |
| first_fill | 2025-08-07 10:54:05.372000+00:00 |
| last_fill | 2026-01-03 10:55:23.254000+00:00 |
| non_trade_events | 6 |
| continuity_breaks | 0 |
| continuity_break_first_src_row | None |
| unresolved_chains | 0 |
| mixed_ms_groups | 0 |
| pnl_match_share | 1.0 |
| pnl_rows_gt_tight | 0 |
| pnl_rows_gt_loose | 0 |
| pnl_diff_mean | -3.795338027596633e-14 |
| pnl_offset_cv | 5.0082525715221085 |
| pnl_larger_when_loose | True |
| pnl_mismatch_first_src_row | None |
| closed_pnl_total | 771.507351 |
| rebuilt_realized_known | 807.2865666684271 |
| closed_pnl_known | 807.276855 |
| realized_diff | 0.009711668427144104 |
| realized_diff_rel | 1.2030158386176084e-05 |
| fills_unknown_entry | 1 |
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
| non_trade_event | 6 | fills.csv | 180498, 180506, 180525, 180534, 180542, 180619 |
| outage_exact | 1 | traders.csv | 24734 |
| outage_spanned | 1 | traders.csv | 24734 |
| snapshot_gap | 3 | traders.csv | 24623, 24716, 24734 |
