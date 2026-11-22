# 0x5bcba84cd697ebcd2fb4c1dfc7f3fa3dae12d53d

as of 2026-01-04T23:59:42.020000+00:00 · grade **C** · too_many_unusable_days;unstable_scope_mismatch

## Flags

| field | value |
| --- | --- |
| n_snapshots | 118 |
| first_snapshot | 2025-08-01 13:19:54.812000+00:00 |
| last_snapshot | 2026-01-04 19:53:17.619000+00:00 |
| days_present | 118 |
| first_date | 2025-08-01 |
| last_date | 2026-01-04 |
| n_snapshot_gaps | 3 |
| max_gap_days | 25.072035266203702 |
| snapshot_gap_first_src_row | 48406 |
| outage_exact | False |
| outage_spanned | True |
| outage_first_src_row | 48485 |
| stale_equity_rows | 72 |
| stale_equity_first_src_row | 48414 |
| zero_equity_rows | 0 |
| zero_equity_first_src_row | None |
| near_zero_equity_share | 0.0 |
| median_equity | 1802.282325 |
| frozen_rows | 0 |
| frozen_first_src_row | None |
| usable_days | 118 |
| dropped_out | False |
| joined_date | 2025-08-01 |
| calendar_days | 157 |
| days_present_share | 0.7515923566878981 |
| unusable_day_share | 0.24840764331210186 |
| days_to_asof | 157 |
| zero_equity_holding_rows | 0 |
| zero_equity_holding_first_src_row | None |
| n_fills | 498 |
| n_perp_fills | 497 |
| eligible_notional_share | 0.9976245543320773 |
| maker_share | 0.1706827309236948 |
| first_fill | 2025-08-11 00:46:38.772000+00:00 |
| last_fill | 2025-11-26 22:07:56.180000+00:00 |
| non_trade_events | 0 |
| continuity_breaks | 0 |
| continuity_break_first_src_row | None |
| unresolved_chains | 0 |
| mixed_ms_groups | 0 |
| pnl_match_share | 0.9745762711864406 |
| pnl_rows_gt_tight | 3 |
| pnl_rows_gt_loose | 3 |
| pnl_diff_mean | 9.975259525423713 |
| pnl_offset_cv | 8.918281398428125 |
| pnl_larger_when_loose | True |
| pnl_mismatch_first_src_row | 48425 |
| closed_pnl_total | 569.282074 |
| rebuilt_realized_known | 590.4784100000021 |
| closed_pnl_known | 590.333624 |
| realized_diff | 0.14478600000211372 |
| realized_diff_rel | 0.0002452613134604607 |
| fills_unknown_entry | 1 |
| fills_pnl_mismatch | 3 |
| realized_mismatch_first_src_row | 338632 |
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
| outage_spanned | 1 | traders.csv | 48485 |
| pnl_identity_mismatch | 3 | traders.csv | 48425, 48426, 48427 |
| snapshot_gap | 3 | traders.csv | 48406, 48483, 48485 |
| stale_equity | 72 | traders.csv | 48414, 48415, 48416, 48417, 48418, 48438, 48439, 48440, 48441, 48442 |
