# 0x9dffaaf1f97fd0a17ed02bddfc48843ccf7b6d8a

as of 2026-01-04T23:59:42.020000+00:00 · grade **C** · too_many_unusable_days

## Flags

| field | value |
| --- | --- |
| n_snapshots | 111 |
| first_snapshot | 2025-07-11 22:26:23.540000+00:00 |
| last_snapshot | 2026-01-04 20:05:36.959000+00:00 |
| days_present | 111 |
| first_date | 2025-07-11 |
| last_date | 2026-01-04 |
| n_snapshot_gaps | 4 |
| max_gap_days | 47.34181386574074 |
| snapshot_gap_first_src_row | 79575 |
| outage_exact | True |
| outage_spanned | True |
| outage_first_src_row | 79624 |
| stale_equity_rows | 96 |
| stale_equity_first_src_row | 79552 |
| zero_equity_rows | 0 |
| zero_equity_first_src_row | None |
| near_zero_equity_share | 0.0 |
| median_equity | 47872.547748 |
| frozen_rows | 74 |
| frozen_first_src_row | 79577 |
| usable_days | 37 |
| dropped_out | False |
| joined_date | 2025-07-11 |
| calendar_days | 178 |
| days_present_share | 0.6235955056179775 |
| unusable_day_share | 0.7921348314606742 |
| days_to_asof | 178 |
| zero_equity_holding_rows | 0 |
| zero_equity_holding_first_src_row | None |
| n_fills | 54 |
| n_perp_fills | 54 |
| eligible_notional_share | 1.0 |
| maker_share | 0.16666666666666666 |
| first_fill | 2025-08-10 02:00:57.496000+00:00 |
| last_fill | 2025-12-09 16:50:54.240000+00:00 |
| non_trade_events | 0 |
| continuity_breaks | 0 |
| continuity_break_first_src_row | None |
| unresolved_chains | 0 |
| mixed_ms_groups | 0 |
| pnl_match_share | 0.0 |
| pnl_rows_gt_tight | 111 |
| pnl_rows_gt_loose | 111 |
| pnl_diff_mean | 26048.590751792795 |
| pnl_offset_cv | 0.2114965002760958 |
| pnl_larger_when_loose | True |
| pnl_mismatch_first_src_row | 79551 |
| closed_pnl_total | 12406.233584999998 |
| rebuilt_realized_known | -1277.1277157956513 |
| closed_pnl_known | -1277.1275 |
| realized_diff | -0.0002157956512292003 |
| realized_diff_rel | 1.689695439407579e-07 |
| fills_unknown_entry | 13 |
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
| frozen_snapshot | 74 | traders.csv | 79577, 79578, 79579, 79580, 79581, 79582, 79583, 79584, 79585, 79586 |
| outage_exact | 1 | traders.csv | 79624 |
| outage_spanned | 1 | traders.csv | 79624 |
| pnl_identity_mismatch | 111 | traders.csv | 79551, 79552, 79553, 79554, 79555, 79556, 79557, 79558, 79559, 79560 |
| snapshot_gap | 4 | traders.csv | 79575, 79591, 79606, 79624 |
| stale_equity | 96 | traders.csv | 79552, 79553, 79554, 79555, 79556, 79557, 79558, 79559, 79561, 79562 |
