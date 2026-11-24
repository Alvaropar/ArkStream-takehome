# Leader evidence as of 2026-01-04 00:00 UTC

Core-perp books and round trips include Hyperliquid funding. Gate thresholds are placeholders.

- Universe: 423 addresses graded A or B at this origin (A 237, B 186).
- Primary return source: 0 funded core-perp books and 423 cross-margin snapshot series. Snapshot TWR is retained as a check for each book-sourced address.
- Median account-return coverage: 0.98; median completed round trips: 16.0; open trades with a Hyperliquid closing mark: 851.
- Book vs account: 235 addresses agree (`xc_flag = ok`); median correlation 1.00. Fit uses active, checkable snapshot intervals.
- Median unpriced exposure share: 0.0000 (coins not passing the price check at this origin have no eligible intraday source, ADR-0044); median notional share in coins that cannot be copied (not passing or HIP-3, ADR-0047): 0.0000.
- Stress shock: largest 24 h move per coin at hour marks before this origin. 146 of 163 coins take their largest fall from 10-11 Oct 2025.

## Gate counts (placeholders; counts only)

| gate | pass | fail | unmeasured |
| --- | --- | --- | --- |
| gate_rebuild_fit | 200 | 45 | 178 |
| gate_book_account | 235 | 10 | 178 |
| gate_unpriced | 358 | 49 | 16 |
| gate_evidence | 188 | 235 | 0 |
| gate_active | 239 | 181 | 3 |
| gate_history | 263 | 160 | 0 |
| gate_hold | 378 | 11 | 34 |
| gate_order_rate | 417 | 3 | 3 |
| gate_maker | 342 | 78 | 3 |
| gate_intraday_dd | 271 | 122 | 30 |
| gate_worst_day | 309 | 111 | 3 |
| gate_worst_3d | 315 | 101 | 7 |
| gate_max_dd | 315 | 105 | 3 |
| gate_liquidations | 421 | 2 | 0 |
| gate_top_dependence | 232 | 155 | 36 |
| gate_leverage_p95 | 333 | 50 | 40 |
| gate_liq_distance | 307 | 76 | 40 |
| gate_worstcase_dd | 231 | 171 | 21 |
| gate_stress_peak | 179 | 204 | 40 |
| cat_data_integrity | 181 | 90 | 152 |
| cat_evidence | 119 | 304 | 0 |
| cat_style_diagnostic | 307 | 90 | 26 |
| cat_risk_historical | 139 | 255 | 29 |
| cat_risk_position | 304 | 79 | 40 |
| cat_risk_stress | 141 | 242 | 40 |
| cat_risk | 67 | 326 | 30 |
| all_gates_pass | 22 | 401 | 0 |
