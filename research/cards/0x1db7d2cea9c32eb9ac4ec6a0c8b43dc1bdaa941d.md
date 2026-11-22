# 0x1db7d2cea9c32eb9ac4ec6a0c8b43dc1bdaa941d

as of 2026-01-04T23:59:42.020000+00:00 · grade **C** · too_many_unusable_days

## Flags

| field | value |
| --- | --- |
| n_snapshots | 53 |
| first_snapshot | 2025-08-01 09:52:58.425000+00:00 |
| last_snapshot | 2026-01-04 23:42:55.724000+00:00 |
| days_present | 53 |
| first_date | 2025-08-01 |
| last_date | 2026-01-04 |
| n_snapshot_gaps | 1 |
| max_gap_days | 105.51396645833333 |
| snapshot_gap_first_src_row | 15337 |
| outage_exact | False |
| outage_spanned | False |
| outage_first_src_row | None |
| stale_equity_rows | 51 |
| stale_equity_first_src_row | 15338 |
| zero_equity_rows | 1 |
| zero_equity_first_src_row | 15336 |
| near_zero_equity_share | 0.018867924528301886 |
| median_equity | 1943.09 |
| frozen_rows | 0 |
| frozen_first_src_row | None |
| usable_days | 52 |
| dropped_out | False |
| joined_date | 2025-08-01 |
| calendar_days | 157 |
| days_present_share | 0.3375796178343949 |
| unusable_day_share | 0.6687898089171975 |
| days_to_asof | 157 |
| zero_equity_holding_rows | 0 |
| zero_equity_holding_first_src_row | None |
| n_fills | 1 |
| n_perp_fills | 0 |
| eligible_notional_share | 0.0 |
| maker_share | 0.0 |
| first_fill | 2025-11-14 16:51:55.197000+00:00 |
| last_fill | 2025-11-14 16:51:55.197000+00:00 |
| non_trade_events | 0 |
| continuity_breaks | 0 |
| continuity_break_first_src_row | None |
| unresolved_chains | 0 |
| mixed_ms_groups | 0 |
| pnl_match_share | 1.0 |
| pnl_rows_gt_tight | 0 |
| pnl_rows_gt_loose | 0 |
| pnl_diff_mean | 1.1154180304762327e-13 |
| pnl_offset_cv | 0.1400021132553946 |
| pnl_larger_when_loose | True |
| pnl_mismatch_first_src_row | None |
| closed_pnl_total | None |
| rebuilt_realized_known | None |
| closed_pnl_known | None |
| realized_diff | None |
| realized_diff_rel | None |
| fills_unknown_entry | None |
| fills_pnl_mismatch | None |
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
| snapshot_gap | 1 | traders.csv | 15337 |
| stale_equity | 51 | traders.csv | 15338, 15339, 15340, 15341, 15342, 15343, 15344, 15345, 15346, 15347 |
| zero_equity | 1 | traders.csv | 15336 |
