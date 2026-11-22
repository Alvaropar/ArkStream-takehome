# Leader evidence as of 2025-10-22 00:00 UTC

Core-perp books and round trips include Hyperliquid funding. Gate thresholds are placeholders.

- Universe: 327 addresses graded A or B at this origin (A 217, B 110).
- Primary return source: 1 funded core-perp books and 326 cross-margin snapshot series. Snapshot TWR is retained as a check for each book-sourced address.
- Median account-return coverage: 0.97; median completed round trips: 18.0; open trades with a Hyperliquid closing mark: 794.
- Book vs account: 192 addresses agree (`xc_flag = ok`); median correlation 1.00. Fit uses active, checkable snapshot intervals.
- Median unpriced exposure share: 0.0000 (coins not passing the price check at this origin have no eligible intraday source, ADR-0110); median notional share in coins that cannot be copied (not passing or HIP-3, ADR-0113): 0.0000.
- Stress shock: largest 24 h move per coin at hour marks before this origin. 146 of 155 coins take their largest fall from 10-11 Oct 2025.

## Gate counts (placeholders; counts only)

| gate | pass | fail | unmeasured |
| --- | --- | --- | --- |
| gate_evidence | 150 | 177 | 0 |
| gate_intraday_dd | 236 | 77 | 14 |
| gate_worst_day | 235 | 92 | 0 |
| gate_worst_3d | 252 | 74 | 1 |
| gate_max_dd | 264 | 63 | 0 |
| gate_stress_peak | 177 | 127 | 23 |
| gate_leverage_p95 | 269 | 35 | 23 |
| gate_liq_distance | 264 | 40 | 23 |
| gate_liquidations | 325 | 2 | 0 |
| gate_top_dependence | 131 | 126 | 70 |
| gate_unpriced | 271 | 45 | 11 |
| gate_book_account | 192 | 11 | 124 |
| gate_hold | 302 | 7 | 18 |
| gate_order_rate | 326 | 1 | 0 |
| gate_maker | 266 | 61 | 0 |
| gate_active | 309 | 18 | 0 |
| gate_rebuild_fit | 191 | 15 | 121 |
| gate_worstcase_dd | 163 | 157 | 7 |
| all_gates_pass | 12 | 315 | 0 |
