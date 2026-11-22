# 0x4c6eacc86bd4cee8f41cf257f054ca53b2cef8b3

as of 2026-01-04T23:59:42.020000+00:00 · grade **B** · snapshot_gaps:use_multi_day_returns

## Flags

| field | value |
| --- | --- |
| n_snapshots | 149 |
| first_snapshot | 2025-07-21 22:23:07.956000+00:00 |
| last_snapshot | 2026-01-04 19:52:09.823000+00:00 |
| days_present | 149 |
| first_date | 2025-07-21 |
| last_date | 2026-01-04 |
| n_snapshot_gaps | 3 |
| max_gap_days | 10.331641712962963 |
| snapshot_gap_first_src_row | 39014 |
| outage_exact | False |
| outage_spanned | True |
| outage_first_src_row | 39079 |
| stale_equity_rows | 82 |
| stale_equity_first_src_row | 38971 |
| zero_equity_rows | 0 |
| zero_equity_first_src_row | None |
| near_zero_equity_share | 0.0 |
| median_equity | 8239.81105 |
| frozen_rows | 0 |
| frozen_first_src_row | None |
| usable_days | 149 |
| dropped_out | False |
| joined_date | 2025-07-21 |
| calendar_days | 168 |
| days_present_share | 0.8869047619047619 |
| unusable_day_share | 0.11309523809523814 |
| days_to_asof | 168 |
| zero_equity_holding_rows | 0 |
| zero_equity_holding_first_src_row | None |
| n_fills | 604 |
| n_perp_fills | 604 |
| eligible_notional_share | 1.0 |
| maker_share | 0.04304635761589404 |
| first_fill | 2025-08-01 22:20:42.061000+00:00 |
| last_fill | 2026-01-04 17:16:27.973000+00:00 |
| non_trade_events | 0 |
| continuity_breaks | 0 |
| continuity_break_first_src_row | None |
| unresolved_chains | 0 |
| mixed_ms_groups | 0 |
| pnl_match_share | 1.0 |
| pnl_rows_gt_tight | 0 |
| pnl_rows_gt_loose | 0 |
| pnl_diff_mean | 1.0071585623659944e-13 |
| pnl_offset_cv | 5.244704403457982 |
| pnl_larger_when_loose | True |
| pnl_mismatch_first_src_row | None |
| closed_pnl_total | 6561.298857999999 |
| rebuilt_realized_known | 6561.112060000013 |
| closed_pnl_known | 6561.298858 |
| realized_diff | -0.1867979999869931 |
| realized_diff_rel | 2.8469667977284062e-05 |
| fills_unknown_entry | 0 |
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
| outage_spanned | 1 | traders.csv | 39079 |
| snapshot_gap | 3 | traders.csv | 39014, 39056, 39079 |
| stale_equity | 82 | traders.csv | 38971, 38972, 38973, 38974, 38975, 38976, 38977, 38978, 38997, 38999 |
