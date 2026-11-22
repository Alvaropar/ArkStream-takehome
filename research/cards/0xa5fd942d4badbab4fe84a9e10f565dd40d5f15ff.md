# 0xa5fd942d4badbab4fe84a9e10f565dd40d5f15ff

as of 2026-01-04T23:59:42.020000+00:00 · grade **C** · unstable_scope_mismatch

## Flags

| field | value |
| --- | --- |
| n_snapshots | 179 |
| first_snapshot | 2025-07-10 22:27:31.630000+00:00 |
| last_snapshot | 2026-01-04 19:48:38.340000+00:00 |
| days_present | 179 |
| first_date | 2025-07-10 |
| last_date | 2026-01-04 |
| n_snapshot_gaps | 0 |
| max_gap_days | 1.1343001041666667 |
| snapshot_gap_first_src_row | None |
| outage_exact | False |
| outage_spanned | False |
| outage_first_src_row | None |
| stale_equity_rows | 0 |
| stale_equity_first_src_row | None |
| zero_equity_rows | 0 |
| zero_equity_first_src_row | None |
| near_zero_equity_share | 0.0 |
| median_equity | 591283.721031 |
| frozen_rows | 0 |
| frozen_first_src_row | None |
| usable_days | 179 |
| dropped_out | False |
| joined_date | 2025-07-10 |
| calendar_days | 179 |
| days_present_share | 1.0 |
| unusable_day_share | 0.0 |
| days_to_asof | 179 |
| zero_equity_holding_rows | 0 |
| zero_equity_holding_first_src_row | None |
| n_fills | 7444 |
| n_perp_fills | 7435 |
| eligible_notional_share | 0.9600161899004166 |
| maker_share | 0.856931757119828 |
| first_fill | 2025-07-27 16:08:04.413000+00:00 |
| last_fill | 2026-01-04 18:31:25.150000+00:00 |
| non_trade_events | 1 |
| continuity_breaks | 0 |
| continuity_break_first_src_row | None |
| unresolved_chains | 0 |
| mixed_ms_groups | 0 |
| pnl_match_share | 0.0 |
| pnl_rows_gt_tight | 179 |
| pnl_rows_gt_loose | 179 |
| pnl_diff_mean | 44689.406594435764 |
| pnl_offset_cv | 1.6583488950772436 |
| pnl_larger_when_loose | True |
| pnl_mismatch_first_src_row | 82576 |
| closed_pnl_total | 110909.87034100003 |
| rebuilt_realized_known | 197015.46005948493 |
| closed_pnl_known | 197026.34524700002 |
| realized_diff | -10.885187515086727 |
| realized_diff_rel | 5.524737060640609e-05 |
| fills_unknown_entry | 714 |
| fills_pnl_mismatch | 346 |
| realized_mismatch_first_src_row | 589044 |
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
| non_trade_event | 1 | fills.csv | 594656 |
| pnl_identity_mismatch | 179 | traders.csv | 82576, 82577, 82578, 82579, 82580, 82581, 82582, 82583, 82584, 82585 |
