# 0xacec3accdb28be1e1e7fd2fd06e153e382fa6063

as of 2026-01-04T23:59:42.020000+00:00 · grade **C** · unstable_scope_mismatch

## Flags

| field | value |
| --- | --- |
| n_snapshots | 169 |
| first_snapshot | 2025-07-10 22:28:01.386000+00:00 |
| last_snapshot | 2026-01-04 20:06:20.813000+00:00 |
| days_present | 169 |
| first_date | 2025-07-10 |
| last_date | 2026-01-04 |
| n_snapshot_gaps | 2 |
| max_gap_days | 6.7422241666666665 |
| snapshot_gap_first_src_row | 87076 |
| outage_exact | True |
| outage_spanned | True |
| outage_first_src_row | 87191 |
| stale_equity_rows | 0 |
| stale_equity_first_src_row | None |
| zero_equity_rows | 0 |
| zero_equity_first_src_row | None |
| near_zero_equity_share | 0.0 |
| median_equity | 8835.049701 |
| frozen_rows | 0 |
| frozen_first_src_row | None |
| usable_days | 169 |
| dropped_out | False |
| joined_date | 2025-07-10 |
| calendar_days | 179 |
| days_present_share | 0.9441340782122905 |
| unusable_day_share | 0.05586592178770955 |
| days_to_asof | 179 |
| zero_equity_holding_rows | 0 |
| zero_equity_holding_first_src_row | None |
| n_fills | 1506 |
| n_perp_fills | 1506 |
| eligible_notional_share | 1.0 |
| maker_share | 0.6806108897742363 |
| first_fill | 2025-08-01 18:13:14.357000+00:00 |
| last_fill | 2026-01-04 21:06:05.667000+00:00 |
| non_trade_events | 0 |
| continuity_breaks | 0 |
| continuity_break_first_src_row | None |
| unresolved_chains | 0 |
| mixed_ms_groups | 0 |
| pnl_match_share | 0.9822485207100592 |
| pnl_rows_gt_tight | 3 |
| pnl_rows_gt_loose | 3 |
| pnl_diff_mean | 5.378199408283931 |
| pnl_offset_cv | 9.429404695581768 |
| pnl_larger_when_loose | True |
| pnl_mismatch_first_src_row | 87226 |
| closed_pnl_total | 11757.958352 |
| rebuilt_realized_known | 11428.775974000004 |
| closed_pnl_known | 11424.202034 |
| realized_diff | 4.573940000003859 |
| realized_diff_rel | 0.00040037282134815043 |
| fills_unknown_entry | 1 |
| fills_pnl_mismatch | 50 |
| realized_mismatch_first_src_row | 622209 |
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
| outage_exact | 1 | traders.csv | 87191 |
| outage_spanned | 1 | traders.csv | 87191 |
| pnl_identity_mismatch | 3 | traders.csv | 87226, 87227, 87228 |
| snapshot_gap | 2 | traders.csv | 87076, 87191 |
