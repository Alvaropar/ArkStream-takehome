# 0x1846e2ee0cdf5bc0bfa710bcac0f39ddcc43eac1

as of 2026-01-04T23:59:42.020000+00:00 · grade **C** · too_many_unusable_days

## Flags

| field | value |
| --- | --- |
| n_snapshots | 139 |
| first_snapshot | 2025-07-11 22:34:08.117000+00:00 |
| last_snapshot | 2026-01-04 23:04:05.393000+00:00 |
| days_present | 139 |
| first_date | 2025-07-11 |
| last_date | 2026-01-04 |
| n_snapshot_gaps | 3 |
| max_gap_days | 28.91427428240741 |
| snapshot_gap_first_src_row | 12608 |
| outage_exact | False |
| outage_spanned | False |
| outage_first_src_row | None |
| stale_equity_rows | 8 |
| stale_equity_first_src_row | 12656 |
| zero_equity_rows | 0 |
| zero_equity_first_src_row | None |
| near_zero_equity_share | 0.0 |
| median_equity | 27888.723477 |
| frozen_rows | 0 |
| frozen_first_src_row | None |
| usable_days | 139 |
| dropped_out | False |
| joined_date | 2025-07-11 |
| calendar_days | 178 |
| days_present_share | 0.7808988764044944 |
| unusable_day_share | 0.2191011235955056 |
| days_to_asof | 178 |
| zero_equity_holding_rows | 0 |
| zero_equity_holding_first_src_row | None |
| n_fills | 366 |
| n_perp_fills | 366 |
| eligible_notional_share | 1.0 |
| maker_share | 0.0 |
| first_fill | 2025-07-28 10:17:40.649000+00:00 |
| last_fill | 2025-12-10 16:40:04.876000+00:00 |
| non_trade_events | 0 |
| continuity_breaks | 0 |
| continuity_break_first_src_row | None |
| unresolved_chains | 0 |
| mixed_ms_groups | 0 |
| pnl_match_share | 1.0 |
| pnl_rows_gt_tight | 0 |
| pnl_rows_gt_loose | 0 |
| pnl_diff_mean | 1.4296733261682361e-12 |
| pnl_offset_cv | 2.1500744194253856 |
| pnl_larger_when_loose | True |
| pnl_mismatch_first_src_row | None |
| closed_pnl_total | 26071.66777 |
| rebuilt_realized_known | 17903.001753999906 |
| closed_pnl_known | 17902.94195 |
| realized_diff | 0.059803999905852834 |
| realized_diff_rel | 3.3404565614341856e-06 |
| fills_unknown_entry | 59 |
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
| snapshot_gap | 3 | traders.csv | 12608, 12640, 12664 |
| stale_equity | 8 | traders.csv | 12656, 12657, 12658, 12659, 12660, 12661, 12662, 12663 |
