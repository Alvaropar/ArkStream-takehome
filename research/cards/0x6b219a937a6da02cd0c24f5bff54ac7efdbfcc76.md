# 0x6b219a937a6da02cd0c24f5bff54ac7efdbfcc76

as of 2026-01-04T23:59:42.020000+00:00 · grade **C** · too_many_unusable_days;unstable_scope_mismatch

## Flags

| field | value |
| --- | --- |
| n_snapshots | 32 |
| first_snapshot | 2025-09-25 22:16:22.028000+00:00 |
| last_snapshot | 2025-11-21 14:29:35.995000+00:00 |
| days_present | 32 |
| first_date | 2025-09-25 |
| last_date | 2025-11-21 |
| n_snapshot_gaps | 1 |
| max_gap_days | 26.818583425925926 |
| snapshot_gap_first_src_row | 55056 |
| outage_exact | False |
| outage_spanned | False |
| outage_first_src_row | None |
| stale_equity_rows | 29 |
| stale_equity_first_src_row | 55027 |
| zero_equity_rows | 0 |
| zero_equity_first_src_row | None |
| near_zero_equity_share | 0.46875 |
| median_equity | 86931.3928095 |
| frozen_rows | 0 |
| frozen_first_src_row | None |
| usable_days | 17 |
| dropped_out | True |
| joined_date | 2025-09-25 |
| calendar_days | 102 |
| days_present_share | 0.3137254901960784 |
| unusable_day_share | 0.8333333333333334 |
| days_to_asof | 102 |
| zero_equity_holding_rows | 0 |
| zero_equity_holding_first_src_row | None |
| n_fills | 491 |
| n_perp_fills | 491 |
| eligible_notional_share | 1.0 |
| maker_share | 0.3910386965376782 |
| first_fill | 2025-09-25 11:46:20.327000+00:00 |
| last_fill | 2025-10-10 23:40:48.156000+00:00 |
| non_trade_events | 0 |
| continuity_breaks | 0 |
| continuity_break_first_src_row | None |
| unresolved_chains | 0 |
| mixed_ms_groups | 0 |
| pnl_match_share | 0.5 |
| pnl_rows_gt_tight | 16 |
| pnl_rows_gt_loose | 16 |
| pnl_diff_mean | 32511.734495593744 |
| pnl_offset_cv | 1.0846963138684984 |
| pnl_larger_when_loose | True |
| pnl_mismatch_first_src_row | 55026 |
| closed_pnl_total | 14259.927802999999 |
| rebuilt_realized_known | 14298.855907999836 |
| closed_pnl_known | 14259.927803 |
| realized_diff | 38.92810499983534 |
| realized_diff_rel | 0.0027298949572273187 |
| fills_unknown_entry | 0 |
| fills_pnl_mismatch | 142 |
| realized_mismatch_first_src_row | 389206 |
| copier_cluster | None |
| copier_cluster_size | None |
| copier_is_original | False |
| no_snapshots | False |
| copier_flag | False |
| no_fills | False |
| grade | C |
| grade_reason | too_many_unusable_days;unstable_scope_mismatch |
| asof | 2026-01-04 23:59:42.020000+00:00 |
| config_version | 0.1.0-m1 |

## Evidence (raw rows; first 10 per flag)

| flag | rows | file | src_row |
| --- | --- | --- | --- |
| pnl_identity_mismatch | 16 | traders.csv | 55026, 55027, 55028, 55029, 55030, 55031, 55032, 55033, 55034, 55035 |
| snapshot_gap | 1 | traders.csv | 55056 |
| stale_equity | 29 | traders.csv | 55027, 55028, 55029, 55030, 55031, 55032, 55033, 55034, 55035, 55036 |
