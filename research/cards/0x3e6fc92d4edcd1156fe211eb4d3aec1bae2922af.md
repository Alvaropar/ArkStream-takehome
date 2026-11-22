# 0x3e6fc92d4edcd1156fe211eb4d3aec1bae2922af

as of 2026-01-04T23:59:42.020000+00:00 · grade **C** · unstable_scope_mismatch

## Flags

| field | value |
| --- | --- |
| n_snapshots | 173 |
| first_snapshot | 2025-07-10 22:26:42.246000+00:00 |
| last_snapshot | 2026-01-04 20:22:08.513000+00:00 |
| days_present | 173 |
| first_date | 2025-07-10 |
| last_date | 2026-01-04 |
| n_snapshot_gaps | 2 |
| max_gap_days | 6.444642604166667 |
| snapshot_gap_first_src_row | 33605 |
| outage_exact | True |
| outage_spanned | True |
| outage_first_src_row | 33606 |
| stale_equity_rows | 0 |
| stale_equity_first_src_row | None |
| zero_equity_rows | 0 |
| zero_equity_first_src_row | None |
| near_zero_equity_share | 0.0 |
| median_equity | 4005.123899 |
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
| n_fills | 1729 |
| n_perp_fills | 1715 |
| eligible_notional_share | 0.9964289630756341 |
| maker_share | 0.9346443030653557 |
| first_fill | 2025-07-27 10:49:37.104000+00:00 |
| last_fill | 2026-01-04 17:31:22.435000+00:00 |
| non_trade_events | 1 |
| continuity_breaks | 0 |
| continuity_break_first_src_row | None |
| unresolved_chains | 0 |
| mixed_ms_groups | 0 |
| pnl_match_share | 0.6705202312138728 |
| pnl_rows_gt_tight | 57 |
| pnl_rows_gt_loose | 57 |
| pnl_diff_mean | 94.11937249132947 |
| pnl_offset_cv | 1.875940136888273 |
| pnl_larger_when_loose | True |
| pnl_mismatch_first_src_row | 33473 |
| closed_pnl_total | 286.8926350000002 |
| rebuilt_realized_known | 332.0894767756734 |
| closed_pnl_known | 332.587749 |
| realized_diff | -0.4982722243265698 |
| realized_diff_rel | 0.0014981677040863278 |
| fills_unknown_entry | 226 |
| fills_pnl_mismatch | 22 |
| realized_mismatch_first_src_row | 247905 |
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
| non_trade_event | 1 | fills.csv | 247747 |
| outage_exact | 1 | traders.csv | 33606 |
| outage_spanned | 1 | traders.csv | 33606 |
| pnl_identity_mismatch | 57 | traders.csv | 33473, 33474, 33475, 33476, 33477, 33478, 33479, 33480, 33481, 33482 |
| snapshot_gap | 2 | traders.csv | 33605, 33606 |
