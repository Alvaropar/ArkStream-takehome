# 0xbc96c07aabafbd813a21eb88cd4ce4a5b458c9ac

as of 2026-01-04T23:59:42.020000+00:00 · grade **B** · snapshot_gaps:use_multi_day_returns

## Flags

| field | value |
| --- | --- |
| n_snapshots | 164 |
| first_snapshot | 2025-07-10 22:17:31.644000+00:00 |
| last_snapshot | 2026-01-04 19:26:04.708000+00:00 |
| days_present | 164 |
| first_date | 2025-07-10 |
| last_date | 2026-01-04 |
| n_snapshot_gaps | 1 |
| max_gap_days | 16.41781883101852 |
| snapshot_gap_first_src_row | 95773 |
| outage_exact | False |
| outage_spanned | False |
| outage_first_src_row | None |
| stale_equity_rows | 68 |
| stale_equity_first_src_row | 95767 |
| zero_equity_rows | 0 |
| zero_equity_first_src_row | None |
| near_zero_equity_share | 0.0 |
| median_equity | 2274.251188 |
| frozen_rows | 0 |
| frozen_first_src_row | None |
| usable_days | 164 |
| dropped_out | False |
| joined_date | 2025-07-10 |
| calendar_days | 179 |
| days_present_share | 0.9162011173184358 |
| unusable_day_share | 0.08379888268156421 |
| days_to_asof | 179 |
| zero_equity_holding_rows | 0 |
| zero_equity_holding_first_src_row | None |
| n_fills | 111 |
| n_perp_fills | 111 |
| eligible_notional_share | 1.0 |
| maker_share | 0.44144144144144143 |
| first_fill | 2025-08-01 13:20:13.489000+00:00 |
| last_fill | 2026-01-03 22:13:28.341000+00:00 |
| non_trade_events | 0 |
| continuity_breaks | 0 |
| continuity_break_first_src_row | None |
| unresolved_chains | 0 |
| mixed_ms_groups | 0 |
| pnl_match_share | 1.0 |
| pnl_rows_gt_tight | 0 |
| pnl_rows_gt_loose | 0 |
| pnl_diff_mean | -2.4955647304744982e-14 |
| pnl_offset_cv | 6.32382476637606 |
| pnl_larger_when_loose | True |
| pnl_mismatch_first_src_row | None |
| closed_pnl_total | 395.77723399999996 |
| rebuilt_realized_known | 395.76784299999815 |
| closed_pnl_known | 395.777234 |
| realized_diff | -0.009391000001869543 |
| realized_diff_rel | 2.3727994424938406e-05 |
| fills_unknown_entry | 0 |
| fills_pnl_mismatch | 0 |
| realized_mismatch_first_src_row | None |
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
| snapshot_gap | 1 | traders.csv | 95773 |
| stale_equity | 68 | traders.csv | 95767, 95768, 95769, 95770, 95771, 95772, 95791, 95793, 95794, 95795 |
