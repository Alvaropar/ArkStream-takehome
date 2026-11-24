# Leader evidence as of 2025-10-08 00:00 UTC

Core-perp books and round trips include Hyperliquid funding. Gate thresholds are placeholders.

- Universe: 302 addresses graded A or B at this origin (A 200, B 102).
- Primary return source: 0 funded core-perp books and 302 cross-margin snapshot series. Snapshot TWR is retained as a check for each book-sourced address.
- Median account-return coverage: 0.97; median completed round trips: 12.0; open trades with a Hyperliquid closing mark: 942.
- Book vs account: 172 addresses agree (`xc_flag = ok`); median correlation 1.00. Fit uses active, checkable snapshot intervals.
- Median unpriced exposure share: 0.0000 (coins not passing the price check at this origin have no eligible intraday source, ADR-0044); median notional share in coins that cannot be copied (not passing or HIP-3, ADR-0047): 0.0000.
- Stress shock: largest 24 h move per coin at hour marks before this origin. **The 10-11 Oct 2025 crash is not yet known at this origin and is not used.**

## Gate counts (placeholders; counts only)

| gate | pass | fail | unmeasured |
| --- | --- | --- | --- |
| gate_rebuild_fit | 135 | 51 | 116 |
| gate_book_account | 172 | 12 | 118 |
| gate_unpriced | 254 | 43 | 5 |
| gate_evidence | 114 | 188 | 0 |
| gate_active | 271 | 31 | 0 |
| gate_history | 122 | 180 | 0 |
| gate_hold | 270 | 3 | 29 |
| gate_order_rate | 301 | 1 | 0 |
| gate_maker | 241 | 61 | 0 |
| gate_intraday_dd | 227 | 64 | 11 |
| gate_worst_day | 224 | 74 | 4 |
| gate_worst_3d | 239 | 55 | 8 |
| gate_max_dd | 246 | 52 | 4 |
| gate_liquidations | 302 | 0 | 0 |
| gate_top_dependence | 162 | 96 | 44 |
| gate_leverage_p95 | 259 | 30 | 13 |
| gate_liq_distance | 255 | 34 | 13 |
| gate_worstcase_dd | 211 | 89 | 2 |
| gate_stress_peak | 184 | 105 | 13 |
| cat_data_integrity | 129 | 84 | 89 |
| cat_evidence | 67 | 235 | 0 |
| cat_style_diagnostic | 218 | 65 | 19 |
| cat_risk_historical | 115 | 156 | 31 |
| cat_risk_position | 251 | 38 | 13 |
| cat_risk_stress | 161 | 128 | 13 |
| cat_risk | 92 | 185 | 25 |
| all_gates_pass | 22 | 280 | 0 |
