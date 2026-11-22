# 0x6e9989debf991affd8dfe4a73efcbfc8cb658473

as of 2026-01-04T23:59:42.020000+00:00 · grade **B** · snapshot_gaps:use_multi_day_returns

## Flags

| field | value |
| --- | --- |
| n_snapshots | 167 |
| first_snapshot | 2025-07-10 22:23:41.201000+00:00 |
| last_snapshot | 2026-01-04 20:04:35.512000+00:00 |
| days_present | 167 |
| first_date | 2025-07-10 |
| last_date | 2026-01-04 |
| n_snapshot_gaps | 2 |
| max_gap_days | 8.335467280092592 |
| snapshot_gap_first_src_row | 57193 |
| outage_exact | True |
| outage_spanned | True |
| outage_first_src_row | 57247 |
| stale_equity_rows | 42 |
| stale_equity_first_src_row | 57126 |
| zero_equity_rows | 0 |
| zero_equity_first_src_row | None |
| near_zero_equity_share | 0.0 |
| median_equity | 350519.384414 |
| frozen_rows | 0 |
| frozen_first_src_row | None |
| usable_days | 167 |
| dropped_out | False |
| joined_date | 2025-07-10 |
| calendar_days | 179 |
| days_present_share | 0.9329608938547486 |
| unusable_day_share | 0.06703910614525144 |
| days_to_asof | 179 |
| zero_equity_holding_rows | 0 |
| zero_equity_holding_first_src_row | None |
| n_fills | 5587 |
| n_perp_fills | 4511 |
| eligible_notional_share | 0.8721602359859567 |
| maker_share | 0.39162341149096114 |
| first_fill | 2025-07-27 10:41:26.695000+00:00 |
| last_fill | 2026-01-04 17:04:03.426000+00:00 |
| non_trade_events | 12 |
| continuity_breaks | 0 |
| continuity_break_first_src_row | None |
| unresolved_chains | 0 |
| mixed_ms_groups | 0 |
| pnl_match_share | 1.0 |
| pnl_rows_gt_tight | 0 |
| pnl_rows_gt_loose | 0 |
| pnl_diff_mean | 2.091293206471883e-12 |
| pnl_offset_cv | 18.806205361717584 |
| pnl_larger_when_loose | True |
| pnl_mismatch_first_src_row | None |
| closed_pnl_total | 53284.22168 |
| rebuilt_realized_known | 55055.52052399991 |
| closed_pnl_known | 55051.023135999996 |
| realized_diff | 4.4973879999161 |
| realized_diff_rel | 8.16949030866437e-05 |
| fills_unknown_entry | 8 |
| fills_pnl_mismatch | 105 |
| realized_mismatch_first_src_row | 400297 |
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
| non_trade_event | 12 | fills.csv | 400259, 400260, 400817, 400818, 401001, 401858, 401920, 403206, 404183, 404535 |
| outage_exact | 1 | traders.csv | 57247 |
| outage_spanned | 1 | traders.csv | 57247 |
| snapshot_gap | 2 | traders.csv | 57193, 57247 |
| stale_equity | 42 | traders.csv | 57126, 57127, 57128, 57129, 57130, 57131, 57143, 57144, 57148, 57151 |
