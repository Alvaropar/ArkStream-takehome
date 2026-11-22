# 0xbde7d5dc6eeae1b0cac8d10edb030b2a274fa3dc

as of 2026-01-04T23:59:42.020000+00:00 · grade **C** · unstable_scope_mismatch

## Flags

| field | value |
| --- | --- |
| n_snapshots | 111 |
| first_snapshot | 2025-09-10 22:33:01.877000+00:00 |
| last_snapshot | 2026-01-04 20:09:38.062000+00:00 |
| days_present | 111 |
| first_date | 2025-09-10 |
| last_date | 2026-01-04 |
| n_snapshot_gaps | 1 |
| max_gap_days | 6.6932893402777776 |
| snapshot_gap_first_src_row | 96601 |
| outage_exact | True |
| outage_spanned | True |
| outage_first_src_row | 96601 |
| stale_equity_rows | 24 |
| stale_equity_first_src_row | 96529 |
| zero_equity_rows | 0 |
| zero_equity_first_src_row | None |
| near_zero_equity_share | 0.0 |
| median_equity | 10449.782211 |
| frozen_rows | 0 |
| frozen_first_src_row | None |
| usable_days | 111 |
| dropped_out | False |
| joined_date | 2025-09-10 |
| calendar_days | 117 |
| days_present_share | 0.9487179487179487 |
| unusable_day_share | 0.05128205128205132 |
| days_to_asof | 117 |
| zero_equity_holding_rows | 0 |
| zero_equity_holding_first_src_row | None |
| n_fills | 509 |
| n_perp_fills | 509 |
| eligible_notional_share | 1.0 |
| maker_share | 0.5029469548133595 |
| first_fill | 2025-09-10 09:07:51.136000+00:00 |
| last_fill | 2025-12-17 19:08:18.065000+00:00 |
| non_trade_events | 0 |
| continuity_breaks | 0 |
| continuity_break_first_src_row | None |
| unresolved_chains | 0 |
| mixed_ms_groups | 0 |
| pnl_match_share | 0.963963963963964 |
| pnl_rows_gt_tight | 4 |
| pnl_rows_gt_loose | 4 |
| pnl_diff_mean | 62.63280258558586 |
| pnl_offset_cv | 5.452559384610077 |
| pnl_larger_when_loose | True |
| pnl_mismatch_first_src_row | 96552 |
| closed_pnl_total | 15120.946594000001 |
| rebuilt_realized_known | 15120.970619999965 |
| closed_pnl_known | 15120.946594000001 |
| realized_diff | 0.02402599996457866 |
| realized_diff_rel | 1.5889216865637358e-06 |
| fills_unknown_entry | 0 |
| fills_pnl_mismatch | 4 |
| realized_mismatch_first_src_row | 667275 |
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
| outage_exact | 1 | traders.csv | 96601 |
| outage_spanned | 1 | traders.csv | 96601 |
| pnl_identity_mismatch | 4 | traders.csv | 96552, 96555, 96556, 96557 |
| snapshot_gap | 1 | traders.csv | 96601 |
| stale_equity | 24 | traders.csv | 96529, 96531, 96532, 96533, 96534, 96536, 96538, 96539, 96540, 96541 |
