# Leader evidence as of 2025-11-05 00:00 UTC

Core-perp books and round trips include Hyperliquid funding. Gate thresholds are placeholders.

- Universe: 330 addresses graded A or B at this origin (A 205, B 125).
- Primary return source: 1 funded core-perp books and 329 cross-margin snapshot series. Snapshot TWR is retained as a check for each book-sourced address.
- Median account-return coverage: 0.97; median completed round trips: 19.5; open trades with a Hyperliquid closing mark: 931.
- Book vs account: 202 addresses agree (`xc_flag = ok`); median correlation 1.00. Fit uses active, checkable snapshot intervals.
- Median unpriced exposure share: 0.0000 (coins not passing the price check at this origin have no eligible intraday source, ADR-0110); median notional share in coins that cannot be copied (not passing or HIP-3, ADR-0113): 0.0000.
- Stress shock: largest 24 h move per coin at hour marks before this origin. 147 of 158 coins take their largest fall from 10-11 Oct 2025.

## Gate counts (placeholders; counts only)

| gate | pass | fail | unmeasured |
| --- | --- | --- | --- |
| gate_evidence | 165 | 165 | 0 |
| gate_intraday_dd | 231 | 90 | 9 |
| gate_worst_day | 230 | 99 | 1 |
| gate_worst_3d | 249 | 78 | 3 |
| gate_max_dd | 257 | 72 | 1 |
| gate_stress_peak | 176 | 140 | 14 |
| gate_leverage_p95 | 273 | 43 | 14 |
| gate_liq_distance | 261 | 55 | 14 |
| gate_liquidations | 328 | 2 | 0 |
| gate_top_dependence | 124 | 122 | 84 |
| gate_unpriced | 278 | 44 | 8 |
| gate_book_account | 202 | 10 | 118 |
| gate_hold | 295 | 8 | 27 |
| gate_order_rate | 328 | 2 | 0 |
| gate_maker | 265 | 65 | 0 |
| gate_active | 296 | 34 | 0 |
| gate_rebuild_fit | 194 | 20 | 116 |
| gate_worstcase_dd | 166 | 162 | 2 |
| all_gates_pass | 15 | 315 | 0 |
