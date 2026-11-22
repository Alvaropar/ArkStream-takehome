# 0x7dcf46fa4fc7cd89de5fd534f9833cb8da1e37fb

as of 2026-01-04T23:59:42.020000+00:00 · grade **A**

## Flags

| field | value |
| --- | --- |
| n_snapshots | 172 |
| first_snapshot | 2025-07-10 22:24:35.322000+00:00 |
| last_snapshot | 2026-01-04 20:20:33.989000+00:00 |
| days_present | 172 |
| first_date | 2025-07-10 |
| last_date | 2026-01-04 |
| n_snapshot_gaps | 4 |
| max_gap_days | 6.482435405092592 |
| snapshot_gap_first_src_row | 63121 |
| outage_exact | True |
| outage_spanned | True |
| outage_first_src_row | 63223 |
| stale_equity_rows | 0 |
| stale_equity_first_src_row | None |
| zero_equity_rows | 0 |
| zero_equity_first_src_row | None |
| near_zero_equity_share | 0.0 |
| median_equity | 713.8921365 |
| frozen_rows | 0 |
| frozen_first_src_row | None |
| usable_days | 172 |
| dropped_out | False |
| joined_date | 2025-07-10 |
| calendar_days | 179 |
| days_present_share | 0.9608938547486033 |
| unusable_day_share | 0.03910614525139666 |
| days_to_asof | 179 |
| zero_equity_holding_rows | 0 |
| zero_equity_holding_first_src_row | None |
| n_fills | 59 |
| n_perp_fills | 44 |
| eligible_notional_share | 0.889690202682695 |
| maker_share | 0.288135593220339 |
| first_fill | 2025-07-27 11:32:46.129000+00:00 |
| last_fill | 2025-12-22 15:19:56.361000+00:00 |
| non_trade_events | 2 |
| continuity_breaks | 0 |
| continuity_break_first_src_row | None |
| unresolved_chains | 0 |
| mixed_ms_groups | 0 |
| pnl_match_share | 1.0 |
| pnl_rows_gt_tight | 0 |
| pnl_rows_gt_loose | 0 |
| pnl_diff_mean | -2.51581701208082e-14 |
| pnl_offset_cv | 3.5602428004099083 |
| pnl_larger_when_loose | True |
| pnl_mismatch_first_src_row | None |
| closed_pnl_total | 281.97768499999995 |
| rebuilt_realized_known | 77.05332200000001 |
| closed_pnl_known | 77.050925 |
| realized_diff | 0.002397000000001981 |
| realized_diff_rel | 3.110929557305095e-05 |
| fills_unknown_entry | 1 |
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
| non_trade_event | 2 | fills.csv | 449560, 449584 |
| outage_exact | 1 | traders.csv | 63223 |
| outage_spanned | 1 | traders.csv | 63223 |
| snapshot_gap | 4 | traders.csv | 63121, 63203, 63222, 63223 |
