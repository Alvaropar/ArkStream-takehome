# 0xe6784abec0aec3aaf52cadffe6d281b5a48bce24

as of 2026-01-04T23:59:42.020000+00:00 · grade **C** · too_many_unusable_days

## Flags

| field | value |
| --- | --- |
| n_snapshots | 107 |
| first_snapshot | 2025-07-10 22:14:15.421000+00:00 |
| last_snapshot | 2026-01-04 23:41:34.857000+00:00 |
| days_present | 107 |
| first_date | 2025-07-10 |
| last_date | 2026-01-04 |
| n_snapshot_gaps | 3 |
| max_gap_days | 33.24800841435185 |
| snapshot_gap_first_src_row | 117957 |
| outage_exact | False |
| outage_spanned | False |
| outage_first_src_row | None |
| stale_equity_rows | 14 |
| stale_equity_first_src_row | 117980 |
| zero_equity_rows | 0 |
| zero_equity_first_src_row | None |
| near_zero_equity_share | 0.0 |
| median_equity | 18177.426105 |
| frozen_rows | 0 |
| frozen_first_src_row | None |
| usable_days | 107 |
| dropped_out | False |
| joined_date | 2025-07-10 |
| calendar_days | 179 |
| days_present_share | 0.5977653631284916 |
| unusable_day_share | 0.4022346368715084 |
| days_to_asof | 179 |
| zero_equity_holding_rows | 0 |
| zero_equity_holding_first_src_row | None |
| n_fills | 35 |
| n_perp_fills | 35 |
| eligible_notional_share | 1.0 |
| maker_share | 0.14285714285714285 |
| first_fill | 2025-08-12 12:21:30.820000+00:00 |
| last_fill | 2025-11-22 18:54:24.640000+00:00 |
| non_trade_events | 0 |
| continuity_breaks | 0 |
| continuity_break_first_src_row | None |
| unresolved_chains | 0 |
| mixed_ms_groups | 0 |
| pnl_match_share | 1.0 |
| pnl_rows_gt_tight | 0 |
| pnl_rows_gt_loose | 0 |
| pnl_diff_mean | 1.5469909880623639e-12 |
| pnl_offset_cv | 1.2697312930077536 |
| pnl_larger_when_loose | True |
| pnl_mismatch_first_src_row | None |
| closed_pnl_total | 21243.802531999998 |
| rebuilt_realized_known | 1119.2140005191661 |
| closed_pnl_known | 1119.204616 |
| realized_diff | 0.009384519166133032 |
| realized_diff_rel | 8.38498968997554e-06 |
| fills_unknown_entry | 10 |
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
| snapshot_gap | 3 | traders.csv | 117957, 117979, 117994 |
| stale_equity | 14 | traders.csv | 117980, 117981, 117982, 117983, 117984, 117985, 117986, 117987, 117988, 117989 |
