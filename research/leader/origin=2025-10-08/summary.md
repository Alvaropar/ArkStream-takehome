# Leader evidence as of 2025-10-08 00:00 UTC

Core-perp books and round trips include Hyperliquid funding. Gate thresholds are placeholders.

- Universe: 300 addresses graded A or B at this origin (A 196, B 104).
- Primary return source: 3 funded core-perp books and 297 cross-margin snapshot series. Snapshot TWR is retained as a check for each book-sourced address.
- Median account-return coverage: 0.97; median completed round trips: 12.0; open trades with a Hyperliquid closing mark: 923.
- Book vs account: 173 addresses agree (`xc_flag = ok`); median correlation 1.00. Fit uses active, checkable snapshot intervals.
- Median unpriced exposure share: 0.0000 (coins not passing the price check at this origin have no eligible intraday source, ADR-0110); median notional share in coins that cannot be copied (not passing or HIP-3, ADR-0113): 0.0000.
- Stress shock: largest 24 h move per coin at hour marks before this origin. **The 10-11 Oct 2025 crash is not yet known at this origin and is not used.**

## Gate counts (placeholders; counts only)

| gate | pass | fail | unmeasured |
| --- | --- | --- | --- |
| gate_evidence | 113 | 187 | 0 |
| gate_intraday_dd | 226 | 63 | 11 |
| gate_worst_day | 225 | 72 | 3 |
| gate_worst_3d | 240 | 52 | 8 |
| gate_max_dd | 247 | 50 | 3 |
| gate_stress_peak | 200 | 87 | 13 |
| gate_leverage_p95 | 257 | 30 | 13 |
| gate_liq_distance | 253 | 34 | 13 |
| gate_liquidations | 300 | 0 | 0 |
| gate_top_dependence | 109 | 87 | 104 |
| gate_unpriced | 254 | 41 | 5 |
| gate_book_account | 173 | 10 | 117 |
| gate_hold | 267 | 3 | 30 |
| gate_order_rate | 299 | 1 | 0 |
| gate_maker | 240 | 60 | 0 |
| gate_active | 269 | 31 | 0 |
| gate_rebuild_fit | 166 | 19 | 115 |
| gate_worstcase_dd | 212 | 86 | 2 |
| all_gates_pass | 16 | 284 | 0 |
