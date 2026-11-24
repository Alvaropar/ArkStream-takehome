# Leader evidence as of 2025-10-22 00:00 UTC

Core-perp books and round trips include Hyperliquid funding. Gate thresholds are placeholders.

- Universe: 332 addresses graded A or B at this origin (A 223, B 109).
- Primary return source: 0 funded core-perp books and 332 cross-margin snapshot series. Snapshot TWR is retained as a check for each book-sourced address.
- Median account-return coverage: 0.97; median completed round trips: 18.0; open trades with a Hyperliquid closing mark: 809.
- Book vs account: 191 addresses agree (`xc_flag = ok`); median correlation 1.00. Fit uses active, checkable snapshot intervals.
- Median unpriced exposure share: 0.0000 (coins not passing the price check at this origin have no eligible intraday source, ADR-0044); median notional share in coins that cannot be copied (not passing or HIP-3, ADR-0047): 0.0000.
- Stress shock: largest 24 h move per coin at hour marks before this origin. 146 of 155 coins take their largest fall from 10-11 Oct 2025.

## Gate counts (placeholders; counts only)

| gate | pass | fail | unmeasured |
| --- | --- | --- | --- |
| gate_rebuild_fit | 150 | 58 | 124 |
| gate_book_account | 191 | 14 | 127 |
| gate_unpriced | 273 | 48 | 11 |
| gate_evidence | 154 | 178 | 0 |
| gate_active | 314 | 18 | 0 |
| gate_history | 214 | 118 | 0 |
| gate_hold | 308 | 6 | 18 |
| gate_order_rate | 331 | 1 | 0 |
| gate_maker | 269 | 63 | 0 |
| gate_intraday_dd | 239 | 79 | 14 |
| gate_worst_day | 238 | 94 | 0 |
| gate_worst_3d | 255 | 76 | 1 |
| gate_max_dd | 267 | 65 | 0 |
| gate_liquidations | 330 | 2 | 0 |
| gate_top_dependence | 186 | 121 | 25 |
| gate_leverage_p95 | 274 | 35 | 23 |
| gate_liq_distance | 269 | 40 | 23 |
| gate_worstcase_dd | 165 | 160 | 7 |
| gate_stress_peak | 161 | 148 | 23 |
| cat_data_integrity | 133 | 100 | 99 |
| cat_evidence | 119 | 213 | 0 |
| cat_style_diagnostic | 250 | 68 | 14 |
| cat_risk_historical | 118 | 193 | 21 |
| cat_risk_position | 264 | 45 | 23 |
| cat_risk_stress | 107 | 203 | 22 |
| cat_risk | 56 | 256 | 20 |
| all_gates_pass | 19 | 313 | 0 |
