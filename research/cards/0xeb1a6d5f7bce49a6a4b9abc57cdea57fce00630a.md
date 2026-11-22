# 0xeb1a6d5f7bce49a6a4b9abc57cdea57fce00630a

as of 2026-01-04T23:59:42.020000+00:00 · grade **C** · no_fills;unstable_scope_mismatch

## Flags

| field | value |
| --- | --- |
| n_snapshots | 173 |
| first_snapshot | 2025-07-10 22:32:38.286000+00:00 |
| last_snapshot | 2026-01-04 19:52:49.338000+00:00 |
| days_present | 173 |
| first_date | 2025-07-10 |
| last_date | 2026-01-04 |
| n_snapshot_gaps | 1 |
| max_gap_days | 7.003561643518518 |
| snapshot_gap_first_src_row | 119456 |
| outage_exact | False |
| outage_spanned | True |
| outage_first_src_row | 119456 |
| stale_equity_rows | 55 |
| stale_equity_first_src_row | 119416 |
| zero_equity_rows | 0 |
| zero_equity_first_src_row | None |
| near_zero_equity_share | 0.0 |
| median_equity | 101758.721426 |
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
| n_fills | 0 |
| n_perp_fills | 0 |
| eligible_notional_share | None |
| maker_share | None |
| first_fill | None |
| last_fill | None |
| non_trade_events | 0 |
| continuity_breaks | 0 |
| continuity_break_first_src_row | None |
| unresolved_chains | 0 |
| mixed_ms_groups | 0 |
| pnl_match_share | 0.9884393063583815 |
| pnl_rows_gt_tight | 2 |
| pnl_rows_gt_loose | 2 |
| pnl_diff_mean | 807.5510525317937 |
| pnl_offset_cv | 9.792793466432887 |
| pnl_larger_when_loose | True |
| pnl_mismatch_first_src_row | 119398 |
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
| no_fills | True |
| grade | C |
| grade_reason | no_fills;unstable_scope_mismatch |
| asof | 2026-01-04 23:59:42.020000+00:00 |
| config_version | 0.1.0-m1 |

## Evidence (raw rows; first 10 per flag)

| flag | rows | file | src_row |
| --- | --- | --- | --- |
| outage_spanned | 1 | traders.csv | 119456 |
| pnl_identity_mismatch | 2 | traders.csv | 119398, 119399 |
| snapshot_gap | 1 | traders.csv | 119456 |
| stale_equity | 55 | traders.csv | 119416, 119420, 119421, 119422, 119423, 119424, 119425, 119426, 119427, 119428 |
