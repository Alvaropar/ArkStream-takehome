# Leader evidence as of 2025-11-19 00:00 UTC

Core-perp books and round trips include Hyperliquid funding. Gate thresholds are placeholders.

- Universe: 361 addresses graded A or B at this origin (A 250, B 111).
- Primary return source: 0 funded core-perp books and 361 cross-margin snapshot series. Snapshot TWR is retained as a check for each book-sourced address.
- Median account-return coverage: 0.97; median completed round trips: 20.0; open trades with a Hyperliquid closing mark: 852.
- Book vs account: 217 addresses agree (`xc_flag = ok`); median correlation 1.00. Fit uses active, checkable snapshot intervals.
- Median unpriced exposure share: 0.0000 (coins not passing the price check at this origin have no eligible intraday source, ADR-0044); median notional share in coins that cannot be copied (not passing or HIP-3, ADR-0047): 0.0000.
- Stress shock: largest 24 h move per coin at hour marks before this origin. 148 of 159 coins take their largest fall from 10-11 Oct 2025.

## Gate counts (placeholders; counts only)

| gate | pass | fail | unmeasured |
| --- | --- | --- | --- |
| gate_rebuild_fit | 184 | 56 | 121 |
| gate_book_account | 217 | 19 | 125 |
| gate_unpriced | 302 | 47 | 12 |
| gate_evidence | 183 | 178 | 0 |
| gate_active | 305 | 56 | 0 |
| gate_history | 250 | 111 | 0 |
| gate_hold | 323 | 13 | 25 |
| gate_order_rate | 358 | 3 | 0 |
| gate_maker | 293 | 68 | 0 |
| gate_intraday_dd | 243 | 104 | 14 |
| gate_worst_day | 252 | 109 | 0 |
| gate_worst_3d | 269 | 90 | 2 |
| gate_max_dd | 273 | 88 | 0 |
| gate_liquidations | 359 | 2 | 0 |
| gate_top_dependence | 205 | 124 | 32 |
| gate_leverage_p95 | 297 | 43 | 21 |
| gate_liq_distance | 281 | 59 | 21 |
| gate_worstcase_dd | 183 | 169 | 9 |
| gate_stress_peak | 160 | 180 | 21 |
| cat_data_integrity | 162 | 99 | 100 |
| cat_evidence | 143 | 218 | 0 |
| cat_style_diagnostic | 262 | 82 | 17 |
| cat_risk_historical | 131 | 211 | 19 |
| cat_risk_position | 278 | 62 | 21 |
| cat_risk_stress | 114 | 226 | 21 |
| cat_risk | 59 | 284 | 18 |
| all_gates_pass | 25 | 336 | 0 |
