# 0x24a44aef48aeb27c7708dabfccda14b41fbf0ae1

as of 2026-01-04T23:59:42.020000+00:00 · grade **C** · unstable_scope_mismatch

## Flags

| field | value |
| --- | --- |
| n_snapshots | 174 |
| first_snapshot | 2025-07-10 22:20:22.345000+00:00 |
| last_snapshot | 2026-01-04 20:03:12.845000+00:00 |
| days_present | 174 |
| first_date | 2025-07-10 |
| last_date | 2026-01-04 |
| n_snapshot_gaps | 1 |
| max_gap_days | 6.817397824074074 |
| snapshot_gap_first_src_row | 18348 |
| outage_exact | True |
| outage_spanned | True |
| outage_first_src_row | 18348 |
| stale_equity_rows | 0 |
| stale_equity_first_src_row | None |
| zero_equity_rows | 0 |
| zero_equity_first_src_row | None |
| near_zero_equity_share | 0.0 |
| median_equity | 601389.3779195 |
| frozen_rows | 0 |
| frozen_first_src_row | None |
| usable_days | 174 |
| dropped_out | False |
| joined_date | 2025-07-10 |
| calendar_days | 179 |
| days_present_share | 0.9720670391061452 |
| unusable_day_share | 0.027932960893854775 |
| days_to_asof | 179 |
| zero_equity_holding_rows | 0 |
| zero_equity_holding_first_src_row | None |
| n_fills | 1591 |
| n_perp_fills | 1544 |
| eligible_notional_share | 0.9828400411613251 |
| maker_share | 0.8340666247642992 |
| first_fill | 2025-07-28 13:37:50.878000+00:00 |
| last_fill | 2025-11-22 17:46:10.125000+00:00 |
| non_trade_events | 0 |
| continuity_breaks | 0 |
| continuity_break_first_src_row | None |
| unresolved_chains | 0 |
| mixed_ms_groups | 0 |
| pnl_match_share | 0.8160919540229885 |
| pnl_rows_gt_tight | 32 |
| pnl_rows_gt_loose | 32 |
| pnl_diff_mean | 2685.684737040251 |
| pnl_offset_cv | 2.1917302675130697 |
| pnl_larger_when_loose | True |
| pnl_mismatch_first_src_row | 18272 |
| closed_pnl_total | 289145.855196 |
| rebuilt_realized_known | -49204.97853358845 |
| closed_pnl_known | -49204.76492 |
| realized_diff | -0.2136135884502437 |
| realized_diff_rel | 4.341319154710915e-06 |
| fills_unknown_entry | 521 |
| fills_pnl_mismatch | 13 |
| realized_mismatch_first_src_row | 158297 |
| copier_cluster | None |
| copier_cluster_size | None |
| copier_is_original | False |
| no_snapshots | False |
| copier_flag | False |
| no_fills | False |
| grade | C |
| grade_reason | unstable_scope_mismatch |
| asof | 2026-01-04 23:59:42.020000+00:00 |
| config_version | 0.1.0-m1 |

## Evidence (raw rows; first 10 per flag)

| flag | rows | file | src_row |
| --- | --- | --- | --- |
| outage_exact | 1 | traders.csv | 18348 |
| outage_spanned | 1 | traders.csv | 18348 |
| pnl_identity_mismatch | 32 | traders.csv | 18272, 18273, 18274, 18275, 18276, 18277, 18278, 18279, 18280, 18281 |
| snapshot_gap | 1 | traders.csv | 18348 |
