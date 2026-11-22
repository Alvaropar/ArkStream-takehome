# 0x37de2f99bf85ebc078cfcfe6bbc6b58f5d8c0b65

as of 2026-01-04T23:59:42.020000+00:00 · grade **C** · too_many_unusable_days;unstable_scope_mismatch

## Flags

| field | value |
| --- | --- |
| n_snapshots | 98 |
| first_snapshot | 2025-07-10 22:11:33.535000+00:00 |
| last_snapshot | 2026-01-04 19:58:47.413000+00:00 |
| days_present | 98 |
| first_date | 2025-07-10 |
| last_date | 2026-01-04 |
| n_snapshot_gaps | 3 |
| max_gap_days | 59.16256601851852 |
| snapshot_gap_first_src_row | 29045 |
| outage_exact | False |
| outage_spanned | True |
| outage_first_src_row | 29061 |
| stale_equity_rows | 72 |
| stale_equity_first_src_row | 29020 |
| zero_equity_rows | 0 |
| zero_equity_first_src_row | None |
| near_zero_equity_share | 0.0 |
| median_equity | 316970.808226 |
| frozen_rows | 0 |
| frozen_first_src_row | None |
| usable_days | 98 |
| dropped_out | False |
| joined_date | 2025-07-10 |
| calendar_days | 179 |
| days_present_share | 0.547486033519553 |
| unusable_day_share | 0.45251396648044695 |
| days_to_asof | 179 |
| zero_equity_holding_rows | 0 |
| zero_equity_holding_first_src_row | None |
| n_fills | 2336 |
| n_perp_fills | 2336 |
| eligible_notional_share | 1.0 |
| maker_share | 0.1836472602739726 |
| first_fill | 2025-07-27 18:59:49.884000+00:00 |
| last_fill | 2025-11-24 23:34:22.551000+00:00 |
| non_trade_events | 0 |
| continuity_breaks | 0 |
| continuity_break_first_src_row | None |
| unresolved_chains | 0 |
| mixed_ms_groups | 0 |
| pnl_match_share | 0.9795918367346939 |
| pnl_rows_gt_tight | 2 |
| pnl_rows_gt_loose | 2 |
| pnl_diff_mean | 1065.993523867353 |
| pnl_offset_cv | 8.02771209611511 |
| pnl_larger_when_loose | True |
| pnl_mismatch_first_src_row | 29018 |
| closed_pnl_total | 33426.382857000004 |
| rebuilt_realized_known | 33437.819079998 |
| closed_pnl_known | 33441.956807 |
| realized_diff | -4.137727002002066 |
| realized_diff_rel | 0.00012372861510113445 |
| fills_unknown_entry | 3 |
| fills_pnl_mismatch | 7 |
| realized_mismatch_first_src_row | 203705 |
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
| outage_spanned | 1 | traders.csv | 29061 |
| pnl_identity_mismatch | 2 | traders.csv | 29018, 29060 |
| snapshot_gap | 3 | traders.csv | 29045, 29060, 29061 |
| stale_equity | 72 | traders.csv | 29020, 29021, 29023, 29024, 29025, 29027, 29029, 29031, 29032, 29033 |
