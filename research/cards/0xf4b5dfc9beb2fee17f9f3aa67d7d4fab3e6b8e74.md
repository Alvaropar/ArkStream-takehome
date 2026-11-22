# 0xf4b5dfc9beb2fee17f9f3aa67d7d4fab3e6b8e74

as of 2026-01-04T23:59:42.020000+00:00 · grade **C** · too_many_unusable_days;unstable_scope_mismatch

## Flags

| field | value |
| --- | --- |
| n_snapshots | 130 |
| first_snapshot | 2025-08-01 17:40:28.840000+00:00 |
| last_snapshot | 2026-01-04 20:22:16.718000+00:00 |
| days_present | 130 |
| first_date | 2025-08-01 |
| last_date | 2026-01-04 |
| n_snapshot_gaps | 3 |
| max_gap_days | 22.210066319444444 |
| snapshot_gap_first_src_row | 123358 |
| outage_exact | True |
| outage_spanned | True |
| outage_first_src_row | 123449 |
| stale_equity_rows | 9 |
| stale_equity_first_src_row | 123358 |
| zero_equity_rows | 5 |
| zero_equity_first_src_row | 123357 |
| near_zero_equity_share | 0.038461538461538464 |
| median_equity | 17401.434476 |
| frozen_rows | 0 |
| frozen_first_src_row | None |
| usable_days | 125 |
| dropped_out | False |
| joined_date | 2025-08-01 |
| calendar_days | 157 |
| days_present_share | 0.8280254777070064 |
| unusable_day_share | 0.20382165605095537 |
| days_to_asof | 157 |
| zero_equity_holding_rows | 0 |
| zero_equity_holding_first_src_row | None |
| n_fills | 1562 |
| n_perp_fills | 1020 |
| eligible_notional_share | 0.6250342047106677 |
| maker_share | 0.6209987195902689 |
| first_fill | 2025-08-26 19:00:25.983000+00:00 |
| last_fill | 2026-01-04 19:08:54.072000+00:00 |
| non_trade_events | 4 |
| continuity_breaks | 0 |
| continuity_break_first_src_row | None |
| unresolved_chains | 0 |
| mixed_ms_groups | 0 |
| pnl_match_share | 0.9846153846153847 |
| pnl_rows_gt_tight | 2 |
| pnl_rows_gt_loose | 2 |
| pnl_diff_mean | 70.35993444615366 |
| pnl_offset_cv | 9.504006195445482 |
| pnl_larger_when_loose | True |
| pnl_mismatch_first_src_row | 123365 |
| closed_pnl_total | -10316.484404 |
| rebuilt_realized_known | -10318.359215754956 |
| closed_pnl_known | -10316.484403999999 |
| realized_diff | -1.8748117549566814 |
| realized_diff_rel | 0.00018172971348939012 |
| fills_unknown_entry | 0 |
| fills_pnl_mismatch | 21 |
| realized_mismatch_first_src_row | 850140 |
| copier_cluster | None |
| copier_cluster_size | None |
| copier_is_original | False |
| no_snapshots | False |
| copier_flag | False |
| no_fills | False |
| grade | C |
| grade_reason | too_many_unusable_days;unstable_scope_mismatch |
| asof | 2026-01-04 23:59:42.020000+00:00 |
| config_version | 0.1.0-m1 |

## Evidence (raw rows; first 10 per flag)

| flag | rows | file | src_row |
| --- | --- | --- | --- |
| non_trade_event | 4 | fills.csv | 851161, 851202, 851506, 851507 |
| outage_exact | 1 | traders.csv | 123449 |
| outage_spanned | 1 | traders.csv | 123449 |
| pnl_identity_mismatch | 2 | traders.csv | 123365, 123473 |
| snapshot_gap | 3 | traders.csv | 123358, 123448, 123449 |
| stale_equity | 9 | traders.csv | 123358, 123359, 123360, 123361, 123363, 123364, 123393, 123394, 123434 |
| zero_equity | 5 | traders.csv | 123357, 123358, 123359, 123360, 123361 |
