# Leader evidence as of 2025-12-03 00:00 UTC

Core-perp books and round trips include Hyperliquid funding. Gate thresholds are placeholders.

- Universe: 358 addresses graded A or B at this origin (A 182, B 176).
- Primary return source: 0 funded core-perp books and 358 cross-margin snapshot series. Snapshot TWR is retained as a check for each book-sourced address.
- Median account-return coverage: 0.97; median completed round trips: 19.0; open trades with a Hyperliquid closing mark: 825.
- Book vs account: 215 addresses agree (`xc_flag = ok`); median correlation 1.00. Fit uses active, checkable snapshot intervals.
- Median unpriced exposure share: 0.0000 (coins not passing the price check at this origin have no eligible intraday source, ADR-0044); median notional share in coins that cannot be copied (not passing or HIP-3, ADR-0047): 0.0000.
- Stress shock: largest 24 h move per coin at hour marks before this origin. 147 of 164 coins take their largest fall from 10-11 Oct 2025.

## Gate counts (placeholders; counts only)

| gate | pass | fail | unmeasured |
| --- | --- | --- | --- |
| gate_rebuild_fit | 179 | 51 | 128 |
| gate_book_account | 215 | 12 | 131 |
| gate_unpriced | 306 | 40 | 12 |
| gate_evidence | 178 | 180 | 0 |
| gate_active | 281 | 77 | 0 |
| gate_history | 250 | 108 | 0 |
| gate_hold | 330 | 7 | 21 |
| gate_order_rate | 355 | 3 | 0 |
| gate_maker | 292 | 66 | 0 |
| gate_intraday_dd | 228 | 115 | 15 |
| gate_worst_day | 247 | 111 | 0 |
| gate_worst_3d | 255 | 103 | 0 |
| gate_max_dd | 257 | 101 | 0 |
| gate_liquidations | 356 | 2 | 0 |
| gate_top_dependence | 210 | 123 | 25 |
| gate_leverage_p95 | 298 | 41 | 19 |
| gate_liq_distance | 278 | 61 | 19 |
| gate_worstcase_dd | 170 | 175 | 13 |
| gate_stress_peak | 151 | 188 | 19 |
| cat_data_integrity | 160 | 89 | 109 |
| cat_evidence | 138 | 220 | 0 |
| cat_style_diagnostic | 269 | 74 | 15 |
| cat_risk_historical | 129 | 214 | 15 |
| cat_risk_position | 275 | 64 | 19 |
| cat_risk_stress | 114 | 225 | 19 |
| cat_risk | 61 | 283 | 14 |
| all_gates_pass | 23 | 335 | 0 |
