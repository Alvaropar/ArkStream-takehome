# Leader evidence as of 2025-12-03 00:00 UTC

Core-perp books and round trips include Hyperliquid funding. Gate thresholds are placeholders.

- Universe: 354 addresses graded A or B at this origin (A 178, B 176).
- Primary return source: 1 funded core-perp books and 353 cross-margin snapshot series. Snapshot TWR is retained as a check for each book-sourced address.
- Median account-return coverage: 0.97; median completed round trips: 19.0; open trades with a Hyperliquid closing mark: 792.
- Book vs account: 219 addresses agree (`xc_flag = ok`); median correlation 1.00. Fit uses active, checkable snapshot intervals.
- Median unpriced exposure share: 0.0000 (coins not passing the price check at this origin have no eligible intraday source, ADR-0110); median notional share in coins that cannot be copied (not passing or HIP-3, ADR-0113): 0.0000.
- Stress shock: largest 24 h move per coin at hour marks before this origin. 147 of 164 coins take their largest fall from 10-11 Oct 2025.

## Gate counts (placeholders; counts only)

| gate | pass | fail | unmeasured |
| --- | --- | --- | --- |
| gate_evidence | 174 | 180 | 0 |
| gate_intraday_dd | 225 | 113 | 16 |
| gate_worst_day | 245 | 109 | 0 |
| gate_worst_3d | 253 | 101 | 0 |
| gate_max_dd | 255 | 99 | 0 |
| gate_stress_peak | 169 | 165 | 20 |
| gate_leverage_p95 | 293 | 41 | 20 |
| gate_liq_distance | 273 | 61 | 20 |
| gate_liquidations | 352 | 2 | 0 |
| gate_top_dependence | 134 | 149 | 71 |
| gate_unpriced | 302 | 40 | 12 |
| gate_book_account | 219 | 6 | 129 |
| gate_hold | 326 | 7 | 21 |
| gate_order_rate | 351 | 3 | 0 |
| gate_maker | 289 | 65 | 0 |
| gate_active | 277 | 77 | 0 |
| gate_rebuild_fit | 207 | 21 | 126 |
| gate_worstcase_dd | 170 | 171 | 13 |
| all_gates_pass | 11 | 343 | 0 |
