# 0x84b5ffcb1d9abd86f4fd26a2c9e5a9b54c35c9be

as of 2026-01-04T23:59:42.020000+00:00 · grade **B** · snapshot_gaps:use_multi_day_returns

## Flags

| field | value |
| --- | --- |
| n_snapshots | 163 |
| first_snapshot | 2025-07-10 22:23:34.685000+00:00 |
| last_snapshot | 2026-01-04 20:20:16.416000+00:00 |
| days_present | 163 |
| first_date | 2025-07-10 |
| last_date | 2026-01-04 |
| n_snapshot_gaps | 3 |
| max_gap_days | 11.164011030092592 |
| snapshot_gap_first_src_row | 66788 |
| outage_exact | True |
| outage_spanned | True |
| outage_first_src_row | 66814 |
| stale_equity_rows | 61 |
| stale_equity_first_src_row | 66716 |
| zero_equity_rows | 0 |
| zero_equity_first_src_row | None |
| near_zero_equity_share | 0.0 |
| median_equity | 45703.929034 |
| frozen_rows | 0 |
| frozen_first_src_row | None |
| usable_days | 163 |
| dropped_out | False |
| joined_date | 2025-07-10 |
| calendar_days | 179 |
| days_present_share | 0.9106145251396648 |
| unusable_day_share | 0.08938547486033521 |
| days_to_asof | 179 |
| zero_equity_holding_rows | 0 |
| zero_equity_holding_first_src_row | None |
| n_fills | 3506 |
| n_perp_fills | 3132 |
| eligible_notional_share | 0.9653143576021863 |
| maker_share | 0.4132915002852253 |
| first_fill | 2025-07-27 10:42:31.783000+00:00 |
| last_fill | 2026-01-04 00:23:41.629000+00:00 |
| non_trade_events | 4 |
| continuity_breaks | 0 |
| continuity_break_first_src_row | None |
| unresolved_chains | 0 |
| mixed_ms_groups | 0 |
| pnl_match_share | 1.0 |
| pnl_rows_gt_tight | 0 |
| pnl_rows_gt_loose | 0 |
| pnl_diff_mean | -5.879632159467626e-13 |
| pnl_offset_cv | 8.381796433444563 |
| pnl_larger_when_loose | True |
| pnl_mismatch_first_src_row | None |
| closed_pnl_total | 58559.483610999996 |
| rebuilt_realized_known | 55550.307794000495 |
| closed_pnl_known | 55547.483611 |
| realized_diff | 2.8241830004917574 |
| realized_diff_rel | 5.0842681196317736e-05 |
| fills_unknown_entry | 1 |
| fills_pnl_mismatch | 121 |
| realized_mismatch_first_src_row | 467008 |
| copier_cluster | None |
| copier_cluster_size | None |
| copier_is_original | False |
| no_snapshots | False |
| copier_flag | False |
| no_fills | False |
| grade | B |
| grade_reason | snapshot_gaps:use_multi_day_returns |
| asof | 2026-01-04 23:59:42.020000+00:00 |
| config_version | 0.1.0-m1 |

## Evidence (raw rows; first 10 per flag)

| flag | rows | file | src_row |
| --- | --- | --- | --- |
| non_trade_event | 4 | fills.csv | 467656, 467811, 468329, 469444 |
| outage_exact | 1 | traders.csv | 66814 |
| outage_spanned | 1 | traders.csv | 66814 |
| snapshot_gap | 3 | traders.csv | 66788, 66813, 66814 |
| stale_equity | 61 | traders.csv | 66716, 66720, 66723, 66724, 66754, 66755, 66756, 66757, 66758, 66759 |
