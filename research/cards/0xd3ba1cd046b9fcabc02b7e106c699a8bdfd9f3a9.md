# 0xd3ba1cd046b9fcabc02b7e106c699a8bdfd9f3a9

as of 2026-01-04T23:59:42.020000+00:00 · grade **C** · too_many_unusable_days

## Flags

| field | value |
| --- | --- |
| n_snapshots | 24 |
| first_snapshot | 2025-09-23 22:10:08.019000+00:00 |
| last_snapshot | 2025-11-21 11:44:41.475000+00:00 |
| days_present | 24 |
| first_date | 2025-09-23 |
| last_date | 2025-11-21 |
| n_snapshot_gaps | 1 |
| max_gap_days | 37.119844479166666 |
| snapshot_gap_first_src_row | 106787 |
| outage_exact | False |
| outage_spanned | False |
| outage_first_src_row | None |
| stale_equity_rows | 16 |
| stale_equity_first_src_row | 106773 |
| zero_equity_rows | 0 |
| zero_equity_first_src_row | None |
| near_zero_equity_share | 0.0 |
| median_equity | 2875.957113 |
| frozen_rows | 0 |
| frozen_first_src_row | None |
| usable_days | 24 |
| dropped_out | True |
| joined_date | 2025-09-23 |
| calendar_days | 104 |
| days_present_share | 0.23076923076923078 |
| unusable_day_share | 0.7692307692307692 |
| days_to_asof | 104 |
| zero_equity_holding_rows | 0 |
| zero_equity_holding_first_src_row | None |
| n_fills | 16 |
| n_perp_fills | 16 |
| eligible_notional_share | 1.0 |
| maker_share | 0.0 |
| first_fill | 2025-09-23 13:00:53.516000+00:00 |
| last_fill | 2025-09-30 12:56:06.173000+00:00 |
| non_trade_events | 0 |
| continuity_breaks | 0 |
| continuity_break_first_src_row | None |
| unresolved_chains | 0 |
| mixed_ms_groups | 0 |
| pnl_match_share | 1.0 |
| pnl_rows_gt_tight | 0 |
| pnl_rows_gt_loose | 0 |
| pnl_diff_mean | 2.3684757858670005e-15 |
| pnl_offset_cv | 30.423103349121114 |
| pnl_larger_when_loose | True |
| pnl_mismatch_first_src_row | None |
| closed_pnl_total | 1492.164 |
| rebuilt_realized_known | 1492.1653000000001 |
| closed_pnl_known | 1492.164 |
| realized_diff | 0.0013000000001284207 |
| realized_diff_rel | 8.712179091094683e-07 |
| fills_unknown_entry | 0 |
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
| snapshot_gap | 1 | traders.csv | 106787 |
| stale_equity | 16 | traders.csv | 106773, 106774, 106775, 106776, 106777, 106778, 106779, 106780, 106781, 106782 |
