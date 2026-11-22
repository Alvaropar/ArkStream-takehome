# 0x0af94ca619cd5b18ba72aa1244bfaa8bcb1babd3

as of 2026-01-04T23:59:42.020000+00:00 · grade **C** · unstable_scope_mismatch

## Flags

| field | value |
| --- | --- |
| n_snapshots | 173 |
| first_snapshot | 2025-07-10 22:05:08.673000+00:00 |
| last_snapshot | 2026-01-04 20:11:03.597000+00:00 |
| days_present | 173 |
| first_date | 2025-07-10 |
| last_date | 2026-01-04 |
| n_snapshot_gaps | 1 |
| max_gap_days | 6.668579895833333 |
| snapshot_gap_first_src_row | 6149 |
| outage_exact | True |
| outage_spanned | True |
| outage_first_src_row | 6149 |
| stale_equity_rows | 0 |
| stale_equity_first_src_row | None |
| zero_equity_rows | 0 |
| zero_equity_first_src_row | None |
| near_zero_equity_share | 0.0 |
| median_equity | 14763.181431 |
| frozen_rows | 0 |
| frozen_first_src_row | None |
| usable_days | 173 |
| dropped_out | False |
| joined_date | 2025-07-10 |
| calendar_days | 179 |
| days_present_share | 0.9664804469273743 |
| unusable_day_share | 0.03351955307262566 |
| days_to_asof | 179 |
| zero_equity_holding_rows | 0 |
| zero_equity_holding_first_src_row | None |
| n_fills | 489 |
| n_perp_fills | 489 |
| eligible_notional_share | 1.0 |
| maker_share | 0.012269938650306749 |
| first_fill | 2025-07-31 10:05:43.628000+00:00 |
| last_fill | 2025-12-18 14:20:25.225000+00:00 |
| non_trade_events | 0 |
| continuity_breaks | 0 |
| continuity_break_first_src_row | None |
| unresolved_chains | 0 |
| mixed_ms_groups | 0 |
| pnl_match_share | 0.9595375722543352 |
| pnl_rows_gt_tight | 7 |
| pnl_rows_gt_loose | 7 |
| pnl_diff_mean | 82.72427897109799 |
| pnl_offset_cv | 5.084736226553732 |
| pnl_larger_when_loose | True |
| pnl_mismatch_first_src_row | 6094 |
| closed_pnl_total | 1588.6690889999998 |
| rebuilt_realized_known | -3759.2856459999903 |
| closed_pnl_known | -3758.2070949999998 |
| realized_diff | -1.0785509999905116 |
| realized_diff_rel | 0.0002869855153606195 |
| fills_unknown_entry | 9 |
| fills_pnl_mismatch | 15 |
| realized_mismatch_first_src_row | 71830 |
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
| outage_exact | 1 | traders.csv | 6149 |
| outage_spanned | 1 | traders.csv | 6149 |
| pnl_identity_mismatch | 7 | traders.csv | 6094, 6095, 6096, 6097, 6098, 6099, 6132 |
| snapshot_gap | 1 | traders.csv | 6149 |
