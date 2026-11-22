# Leader evidence as of 2025-11-19 00:00 UTC

Core-perp books and round trips include Hyperliquid funding. Gate thresholds are placeholders.

- Universe: 358 addresses graded A or B at this origin (A 246, B 112).
- Primary return source: 2 funded core-perp books and 356 cross-margin snapshot series. Snapshot TWR is retained as a check for each book-sourced address.
- Median account-return coverage: 0.97; median completed round trips: 19.5; open trades with a Hyperliquid closing mark: 845.
- Book vs account: 223 addresses agree (`xc_flag = ok`); median correlation 1.00. Fit uses active, checkable snapshot intervals.
- Median unpriced exposure share: 0.0000 (coins not passing the price check at this origin have no eligible intraday source, ADR-0110); median notional share in coins that cannot be copied (not passing or HIP-3, ADR-0113): 0.0000.
- Stress shock: largest 24 h move per coin at hour marks before this origin. 148 of 159 coins take their largest fall from 10-11 Oct 2025.

## Gate counts (placeholders; counts only)

| gate | pass | fail | unmeasured |
| --- | --- | --- | --- |
| gate_evidence | 179 | 179 | 0 |
| gate_intraday_dd | 240 | 102 | 16 |
| gate_worst_day | 250 | 108 | 0 |
| gate_worst_3d | 267 | 89 | 2 |
| gate_max_dd | 271 | 87 | 0 |
| gate_stress_peak | 179 | 156 | 23 |
| gate_leverage_p95 | 292 | 43 | 23 |
| gate_liq_distance | 276 | 59 | 23 |
| gate_liquidations | 356 | 2 | 0 |
| gate_top_dependence | 134 | 142 | 82 |
| gate_unpriced | 298 | 48 | 12 |
| gate_book_account | 223 | 9 | 126 |
| gate_hold | 319 | 13 | 26 |
| gate_order_rate | 355 | 3 | 0 |
| gate_maker | 290 | 68 | 0 |
| gate_active | 302 | 56 | 0 |
| gate_rebuild_fit | 216 | 20 | 122 |
| gate_worstcase_dd | 183 | 166 | 9 |
| all_gates_pass | 13 | 345 | 0 |
