# 0xfa5c99b30becf1623ecd23ddf5f79e81bbdccd2e

as of 2026-01-04T23:59:42.020000+00:00 · grade **C** · too_many_unusable_days

## Flags

| field | value |
| --- | --- |
| n_snapshots | 18 |
| first_snapshot | 2025-11-04 22:25:11.821000+00:00 |
| last_snapshot | 2025-11-22 08:09:34.832000+00:00 |
| days_present | 18 |
| first_date | 2025-11-04 |
| last_date | 2025-11-22 |
| n_snapshot_gaps | 1 |
| max_gap_days | 1.5139816898148148 |
| snapshot_gap_first_src_row | 125596 |
| outage_exact | False |
| outage_spanned | False |
| outage_first_src_row | None |
| stale_equity_rows | 16 |
| stale_equity_first_src_row | 125581 |
| zero_equity_rows | 0 |
| zero_equity_first_src_row | None |
| near_zero_equity_share | 0.0 |
| median_equity | 2475.63848 |
| frozen_rows | 0 |
| frozen_first_src_row | None |
| usable_days | 18 |
| dropped_out | True |
| joined_date | 2025-11-04 |
| calendar_days | 62 |
| days_present_share | 0.2903225806451613 |
| unusable_day_share | 0.7096774193548387 |
| days_to_asof | 62 |
| zero_equity_holding_rows | 0 |
| zero_equity_holding_first_src_row | None |
| n_fills | 4 |
| n_perp_fills | 4 |
| eligible_notional_share | 1.0 |
| maker_share | 0.0 |
| first_fill | 2025-11-04 21:01:07.285000+00:00 |
| last_fill | 2025-11-05 22:04:19.556000+00:00 |
| non_trade_events | 0 |
| continuity_breaks | 0 |
| continuity_break_first_src_row | None |
| unresolved_chains | 0 |
| mixed_ms_groups | 0 |
| pnl_match_share | 1.0 |
| pnl_rows_gt_tight | 0 |
| pnl_rows_gt_loose | 0 |
| pnl_diff_mean | -5.4474943074941016e-14 |
| pnl_offset_cv | 0.1844626385704037 |
| pnl_larger_when_loose | True |
| pnl_mismatch_first_src_row | None |
| closed_pnl_total | 506.188832 |
| rebuilt_realized_known | 506.1772399999978 |
| closed_pnl_known | 506.188832 |
| realized_diff | -0.011592000002167424 |
| realized_diff_rel | 2.2900544755928996e-05 |
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
| snapshot_gap | 1 | traders.csv | 125596 |
| stale_equity | 16 | traders.csv | 125581, 125582, 125583, 125584, 125585, 125586, 125587, 125588, 125589, 125590 |
