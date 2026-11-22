# 0xfa7afda0dbdf010d00466209664eca6c0bfebe9c

as of 2026-01-04T23:59:42.020000+00:00 · grade **A**

## Flags

| field | value |
| --- | --- |
| n_snapshots | 173 |
| first_snapshot | 2025-07-10 22:17:27.387000+00:00 |
| last_snapshot | 2026-01-04 20:16:18.475000+00:00 |
| days_present | 173 |
| first_date | 2025-07-10 |
| last_date | 2026-01-04 |
| n_snapshot_gaps | 1 |
| max_gap_days | 6.557229780092593 |
| snapshot_gap_first_src_row | 125732 |
| outage_exact | True |
| outage_spanned | True |
| outage_first_src_row | 125732 |
| stale_equity_rows | 129 |
| stale_equity_first_src_row | 125598 |
| zero_equity_rows | 0 |
| zero_equity_first_src_row | None |
| near_zero_equity_share | 0.0 |
| median_equity | 11641.570995 |
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
| n_fills | 654 |
| n_perp_fills | 654 |
| eligible_notional_share | 1.0 |
| maker_share | 0.8746177370030581 |
| first_fill | 2025-08-11 21:49:34.578000+00:00 |
| last_fill | 2026-01-02 14:13:53.512000+00:00 |
| non_trade_events | 0 |
| continuity_breaks | 0 |
| continuity_break_first_src_row | None |
| unresolved_chains | 0 |
| mixed_ms_groups | 0 |
| pnl_match_share | 0.9942196531791907 |
| pnl_rows_gt_tight | 1 |
| pnl_rows_gt_loose | 1 |
| pnl_diff_mean | 10.509921011560973 |
| pnl_offset_cv | 13.152946437965557 |
| pnl_larger_when_loose | True |
| pnl_mismatch_first_src_row | 125644 |
| closed_pnl_total | 7872.750907000001 |
| rebuilt_realized_known | 7872.710577000007 |
| closed_pnl_known | 7872.750907 |
| realized_diff | -0.040329999992536614 |
| realized_diff_rel | 5.122732888281463e-06 |
| fills_unknown_entry | 0 |
| fills_pnl_mismatch | 1 |
| realized_mismatch_first_src_row | 867131 |
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
| outage_exact | 1 | traders.csv | 125732 |
| outage_spanned | 1 | traders.csv | 125732 |
| pnl_identity_mismatch | 1 | traders.csv | 125644 |
| snapshot_gap | 1 | traders.csv | 125732 |
| stale_equity | 129 | traders.csv | 125598, 125600, 125602, 125603, 125606, 125607, 125609, 125610, 125612, 125613 |
