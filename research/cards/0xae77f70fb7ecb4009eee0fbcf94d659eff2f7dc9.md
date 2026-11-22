# 0xae77f70fb7ecb4009eee0fbcf94d659eff2f7dc9

as of 2026-01-04T23:59:42.020000+00:00 · grade **C** · too_many_unusable_days

## Flags

| field | value |
| --- | --- |
| n_snapshots | 18 |
| first_snapshot | 2025-07-31 22:19:39.847000+00:00 |
| last_snapshot | 2025-11-21 18:52:54.300000+00:00 |
| days_present | 18 |
| first_date | 2025-07-31 |
| last_date | 2025-11-21 |
| n_snapshot_gaps | 1 |
| max_gap_days | 97.16044523148148 |
| snapshot_gap_first_src_row | 87748 |
| outage_exact | False |
| outage_spanned | False |
| outage_first_src_row | None |
| stale_equity_rows | 16 |
| stale_equity_first_src_row | 87734 |
| zero_equity_rows | 0 |
| zero_equity_first_src_row | None |
| near_zero_equity_share | 0.0 |
| median_equity | 22983.106491 |
| frozen_rows | 0 |
| frozen_first_src_row | None |
| usable_days | 18 |
| dropped_out | True |
| joined_date | 2025-07-31 |
| calendar_days | 158 |
| days_present_share | 0.11392405063291139 |
| unusable_day_share | 0.8860759493670887 |
| days_to_asof | 158 |
| zero_equity_holding_rows | 0 |
| zero_equity_holding_first_src_row | None |
| n_fills | 90 |
| n_perp_fills | 90 |
| eligible_notional_share | 1.0 |
| maker_share | 0.1 |
| first_fill | 2025-07-31 17:05:09.596000+00:00 |
| last_fill | 2025-08-01 19:24:17.114000+00:00 |
| non_trade_events | 0 |
| continuity_breaks | 0 |
| continuity_break_first_src_row | None |
| unresolved_chains | 0 |
| mixed_ms_groups | 0 |
| pnl_match_share | 1.0 |
| pnl_rows_gt_tight | 0 |
| pnl_rows_gt_loose | 0 |
| pnl_diff_mean | 8.31433687330395e-13 |
| pnl_offset_cv | 0.3983298259360658 |
| pnl_larger_when_loose | True |
| pnl_mismatch_first_src_row | None |
| closed_pnl_total | 3537.0 |
| rebuilt_realized_known | 3537.5605400000723 |
| closed_pnl_known | 3537.0 |
| realized_diff | 0.5605400000722511 |
| realized_diff_rel | 0.00015847893697264664 |
| fills_unknown_entry | 0 |
| fills_pnl_mismatch | 5 |
| realized_mismatch_first_src_row | 625038 |
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
| snapshot_gap | 1 | traders.csv | 87748 |
| stale_equity | 16 | traders.csv | 87734, 87735, 87736, 87737, 87738, 87739, 87740, 87741, 87742, 87743 |
