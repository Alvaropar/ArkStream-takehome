# Leader evidence as of 2025-11-05 00:00 UTC

Core-perp books and round trips include Hyperliquid funding. Gate thresholds are placeholders.

- Universe: 335 addresses graded A or B at this origin (A 211, B 124).
- Primary return source: 0 funded core-perp books and 335 cross-margin snapshot series. Snapshot TWR is retained as a check for each book-sourced address.
- Median account-return coverage: 0.97; median completed round trips: 20.0; open trades with a Hyperliquid closing mark: 954.
- Book vs account: 194 addresses agree (`xc_flag = ok`); median correlation 1.00. Fit uses active, checkable snapshot intervals.
- Median unpriced exposure share: 0.0000 (coins not passing the price check at this origin have no eligible intraday source, ADR-0044); median notional share in coins that cannot be copied (not passing or HIP-3, ADR-0047): 0.0000.
- Stress shock: largest 24 h move per coin at hour marks before this origin. 147 of 158 coins take their largest fall from 10-11 Oct 2025.

## Gate counts (placeholders; counts only)

| gate | pass | fail | unmeasured |
| --- | --- | --- | --- |
| gate_rebuild_fit | 157 | 60 | 118 |
| gate_book_account | 194 | 21 | 120 |
| gate_unpriced | 283 | 44 | 8 |
| gate_evidence | 170 | 165 | 0 |
| gate_active | 300 | 35 | 0 |
| gate_history | 237 | 98 | 0 |
| gate_hold | 301 | 8 | 26 |
| gate_order_rate | 333 | 2 | 0 |
| gate_maker | 270 | 65 | 0 |
| gate_intraday_dd | 235 | 92 | 8 |
| gate_worst_day | 233 | 100 | 2 |
| gate_worst_3d | 252 | 79 | 4 |
| gate_max_dd | 260 | 73 | 2 |
| gate_liquidations | 333 | 2 | 0 |
| gate_top_dependence | 187 | 117 | 31 |
| gate_leverage_p95 | 279 | 43 | 13 |
| gate_liq_distance | 267 | 55 | 13 |
| gate_worstcase_dd | 168 | 165 | 2 |
| gate_stress_peak | 158 | 164 | 13 |
| cat_data_integrity | 136 | 103 | 96 |
| cat_evidence | 134 | 201 | 0 |
| cat_style_diagnostic | 243 | 73 | 19 |
| cat_risk_historical | 120 | 191 | 24 |
| cat_risk_position | 264 | 58 | 13 |
| cat_risk_stress | 108 | 214 | 13 |
| cat_risk | 57 | 259 | 19 |
| all_gates_pass | 25 | 310 | 0 |
