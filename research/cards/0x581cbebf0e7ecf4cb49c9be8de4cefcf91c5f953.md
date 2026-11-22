# 0x581cbebf0e7ecf4cb49c9be8de4cefcf91c5f953

as of 2026-01-04T23:59:42.020000+00:00 · grade **A**

## Flags

| field | value |
| --- | --- |
| n_snapshots | 167 |
| first_snapshot | 2025-07-16 22:09:14.136000+00:00 |
| last_snapshot | 2026-01-04 22:56:30.854000+00:00 |
| days_present | 167 |
| first_date | 2025-07-16 |
| last_date | 2026-01-04 |
| n_snapshot_gaps | 3 |
| max_gap_days | 4.666868807870371 |
| snapshot_gap_first_src_row | 45649 |
| outage_exact | False |
| outage_spanned | False |
| outage_first_src_row | None |
| stale_equity_rows | 17 |
| stale_equity_first_src_row | 45694 |
| zero_equity_rows | 0 |
| zero_equity_first_src_row | None |
| near_zero_equity_share | 0.0 |
| median_equity | 11802.966746 |
| frozen_rows | 0 |
| frozen_first_src_row | None |
| usable_days | 167 |
| dropped_out | False |
| joined_date | 2025-07-16 |
| calendar_days | 173 |
| days_present_share | 0.9653179190751445 |
| unusable_day_share | 0.034682080924855474 |
| days_to_asof | 173 |
| zero_equity_holding_rows | 0 |
| zero_equity_holding_first_src_row | None |
| n_fills | 134 |
| n_perp_fills | 134 |
| eligible_notional_share | 1.0 |
| maker_share | 0.1044776119402985 |
| first_fill | 2025-07-28 05:24:40.756000+00:00 |
| last_fill | 2026-01-03 08:51:37.126000+00:00 |
| non_trade_events | 0 |
| continuity_breaks | 0 |
| continuity_break_first_src_row | None |
| unresolved_chains | 0 |
| mixed_ms_groups | 0 |
| pnl_match_share | 1.0 |
| pnl_rows_gt_tight | 0 |
| pnl_rows_gt_loose | 0 |
| pnl_diff_mean | -1.225367113167119e-13 |
| pnl_offset_cv | 3.7652015252384823 |
| pnl_larger_when_loose | True |
| pnl_mismatch_first_src_row | None |
| closed_pnl_total | -3254.4507669999994 |
| rebuilt_realized_known | -2201.628204999999 |
| closed_pnl_known | -2201.611014 |
| realized_diff | -0.017190999999002088 |
| realized_diff_rel | 7.808373000355133e-06 |
| fills_unknown_entry | 58 |
| fills_pnl_mismatch | 0 |
| realized_mismatch_first_src_row | None |
| copier_cluster | None |
| copier_cluster_size | None |
| copier_is_original | False |
| no_snapshots | False |
| copier_flag | False |
| no_fills | False |
| grade | A |
| grade_reason |  |
| asof | 2026-01-04 23:59:42.020000+00:00 |
| config_version | 0.1.0-m1 |

## Evidence (raw rows; first 10 per flag)

| flag | rows | file | src_row |
| --- | --- | --- | --- |
| snapshot_gap | 3 | traders.csv | 45649, 45693, 45708 |
| stale_equity | 17 | traders.csv | 45694, 45695, 45696, 45697, 45698, 45699, 45700, 45701, 45702, 45703 |
