# 0xbdc6e3dccb4375a3132fedb8215d48ccdd0a93ac

as of 2026-01-04T23:59:42.020000+00:00 · grade **C** · unstable_scope_mismatch

## Flags

| field | value |
| --- | --- |
| n_snapshots | 39 |
| first_snapshot | 2025-11-22 11:57:53.271000+00:00 |
| last_snapshot | 2026-01-04 20:25:53.068000+00:00 |
| days_present | 39 |
| first_date | 2025-11-22 |
| last_date | 2026-01-04 |
| n_snapshot_gaps | 1 |
| max_gap_days | 6.381000266203704 |
| snapshot_gap_first_src_row | 96490 |
| outage_exact | True |
| outage_spanned | True |
| outage_first_src_row | 96490 |
| stale_equity_rows | 36 |
| stale_equity_first_src_row | 96491 |
| zero_equity_rows | 0 |
| zero_equity_first_src_row | None |
| near_zero_equity_share | 0.0 |
| median_equity | 1620.33863 |
| frozen_rows | 0 |
| frozen_first_src_row | None |
| usable_days | 39 |
| dropped_out | False |
| joined_date | 2025-11-22 |
| calendar_days | 44 |
| days_present_share | 0.8863636363636364 |
| unusable_day_share | 0.11363636363636365 |
| days_to_asof | 44 |
| zero_equity_holding_rows | 0 |
| zero_equity_holding_first_src_row | None |
| n_fills | 7 |
| n_perp_fills | 7 |
| eligible_notional_share | 1.0 |
| maker_share | 0.0 |
| first_fill | 2025-11-23 18:15:44.642000+00:00 |
| last_fill | 2025-12-01 11:24:07.646000+00:00 |
| non_trade_events | 0 |
| continuity_breaks | 0 |
| continuity_break_first_src_row | None |
| unresolved_chains | 0 |
| mixed_ms_groups | 0 |
| pnl_match_share | 0.9743589743589743 |
| pnl_rows_gt_tight | 1 |
| pnl_rows_gt_loose | 1 |
| pnl_diff_mean | 34.29750905128206 |
| pnl_offset_cv | 6.2449979983983965 |
| pnl_larger_when_loose | True |
| pnl_mismatch_first_src_row | 96489 |
| closed_pnl_total | 29.956628000000002 |
| rebuilt_realized_known | 9.8857 |
| closed_pnl_known | 9.8857 |
| realized_diff | 0.0 |
| realized_diff_rel | 0.0 |
| fills_unknown_entry | 5 |
| fills_pnl_mismatch | 0 |
| realized_mismatch_first_src_row | None |
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
| outage_exact | 1 | traders.csv | 96490 |
| outage_spanned | 1 | traders.csv | 96490 |
| pnl_identity_mismatch | 1 | traders.csv | 96489 |
| snapshot_gap | 1 | traders.csv | 96490 |
| stale_equity | 36 | traders.csv | 96491, 96492, 96494, 96495, 96496, 96497, 96498, 96499, 96500, 96501 |
