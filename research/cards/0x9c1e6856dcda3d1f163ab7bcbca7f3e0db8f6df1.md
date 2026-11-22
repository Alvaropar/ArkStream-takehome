# 0x9c1e6856dcda3d1f163ab7bcbca7f3e0db8f6df1

as of 2026-01-04T23:59:42.020000+00:00 · grade **C** · too_many_unusable_days;unstable_scope_mismatch

## Flags

| field | value |
| --- | --- |
| n_snapshots | 119 |
| first_snapshot | 2025-08-01 09:27:40.431000+00:00 |
| last_snapshot | 2026-01-04 23:40:05.148000+00:00 |
| days_present | 119 |
| first_date | 2025-08-01 |
| last_date | 2026-01-04 |
| n_snapshot_gaps | 1 |
| max_gap_days | 39.53502332175926 |
| snapshot_gap_first_src_row | 78538 |
| outage_exact | False |
| outage_spanned | False |
| outage_first_src_row | None |
| stale_equity_rows | 74 |
| stale_equity_first_src_row | 78543 |
| zero_equity_rows | 0 |
| zero_equity_first_src_row | None |
| near_zero_equity_share | 0.0 |
| median_equity | 10933.687513 |
| frozen_rows | 0 |
| frozen_first_src_row | None |
| usable_days | 119 |
| dropped_out | False |
| joined_date | 2025-08-01 |
| calendar_days | 157 |
| days_present_share | 0.7579617834394905 |
| unusable_day_share | 0.2420382165605095 |
| days_to_asof | 157 |
| zero_equity_holding_rows | 0 |
| zero_equity_holding_first_src_row | None |
| n_fills | 876 |
| n_perp_fills | 876 |
| eligible_notional_share | 1.0 |
| maker_share | 0.003424657534246575 |
| first_fill | 2025-09-09 08:30:21.970000+00:00 |
| last_fill | 2025-11-06 18:08:16.883000+00:00 |
| non_trade_events | 0 |
| continuity_breaks | 0 |
| continuity_break_first_src_row | None |
| unresolved_chains | 0 |
| mixed_ms_groups | 0 |
| pnl_match_share | 0.9747899159663865 |
| pnl_rows_gt_tight | 3 |
| pnl_rows_gt_loose | 3 |
| pnl_diff_mean | 37.84133342016799 |
| pnl_offset_cv | 7.052616653912115 |
| pnl_larger_when_loose | True |
| pnl_mismatch_first_src_row | 78579 |
| closed_pnl_total | -867.1841089999998 |
| rebuilt_realized_known | -868.482192000037 |
| closed_pnl_known | -867.184109 |
| realized_diff | -1.2980830000369679 |
| realized_diff_rel | 0.0014968943579165238 |
| fills_unknown_entry | 0 |
| fills_pnl_mismatch | 11 |
| realized_mismatch_first_src_row | 558566 |
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
| pnl_identity_mismatch | 3 | traders.csv | 78579, 78583, 78586 |
| snapshot_gap | 1 | traders.csv | 78538 |
| stale_equity | 74 | traders.csv | 78543, 78551, 78552, 78559, 78563, 78570, 78571, 78572, 78576, 78577 |
