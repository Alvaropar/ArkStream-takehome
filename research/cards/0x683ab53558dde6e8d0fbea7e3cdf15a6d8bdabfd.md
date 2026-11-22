# 0x683ab53558dde6e8d0fbea7e3cdf15a6d8bdabfd

as of 2026-01-04T23:59:42.020000+00:00 · grade **C** · too_many_unusable_days

## Flags

| field | value |
| --- | --- |
| n_snapshots | 66 |
| first_snapshot | 2025-10-13 22:44:29.232000+00:00 |
| last_snapshot | 2026-01-04 20:06:22.573000+00:00 |
| days_present | 66 |
| first_date | 2025-10-13 |
| last_date | 2026-01-04 |
| n_snapshot_gaps | 3 |
| max_gap_days | 10.916474467592593 |
| snapshot_gap_first_src_row | 53045 |
| outage_exact | True |
| outage_spanned | True |
| outage_first_src_row | 53045 |
| stale_equity_rows | 61 |
| stale_equity_first_src_row | 53006 |
| zero_equity_rows | 0 |
| zero_equity_first_src_row | None |
| near_zero_equity_share | 0.0 |
| median_equity | 3053.224738 |
| frozen_rows | 0 |
| frozen_first_src_row | None |
| usable_days | 66 |
| dropped_out | False |
| joined_date | 2025-10-13 |
| calendar_days | 84 |
| days_present_share | 0.7857142857142857 |
| unusable_day_share | 0.2142857142857143 |
| days_to_asof | 84 |
| zero_equity_holding_rows | 0 |
| zero_equity_holding_first_src_row | None |
| n_fills | 49 |
| n_perp_fills | 49 |
| eligible_notional_share | 1.0 |
| maker_share | 0.3469387755102041 |
| first_fill | 2025-11-04 11:38:27.251000+00:00 |
| last_fill | 2026-01-02 16:49:24.890000+00:00 |
| non_trade_events | 0 |
| continuity_breaks | 0 |
| continuity_break_first_src_row | None |
| unresolved_chains | 0 |
| mixed_ms_groups | 0 |
| pnl_match_share | 1.0 |
| pnl_rows_gt_tight | 0 |
| pnl_rows_gt_loose | 0 |
| pnl_diff_mean | 4.2740222135872696e-14 |
| pnl_offset_cv | 1.0603439498631284 |
| pnl_larger_when_loose | True |
| pnl_mismatch_first_src_row | None |
| closed_pnl_total | 173.620943 |
| rebuilt_realized_known | 175.20326499999928 |
| closed_pnl_known | 173.620943 |
| realized_diff | 1.582321999999266 |
| realized_diff_rel | 0.00911365859819841 |
| fills_unknown_entry | 0 |
| fills_pnl_mismatch | 12 |
| realized_mismatch_first_src_row | 373341 |
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
| outage_exact | 1 | traders.csv | 53045 |
| outage_spanned | 1 | traders.csv | 53045 |
| snapshot_gap | 3 | traders.csv | 53045, 53054, 53069 |
| stale_equity | 61 | traders.csv | 53006, 53007, 53008, 53009, 53010, 53011, 53012, 53013, 53014, 53015 |
