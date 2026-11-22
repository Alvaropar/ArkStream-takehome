## 2025-10-08

| Window | Scenario | Positive / measured / gate-passers | Traded | Unpriced / intents | Drawdown over 10% |
| --- | --- | ---: | ---: | ---: | ---: |
| test | base | 6 / 16 / 16 | 16 | 418 / 2090 | 8 |
| test | optimistic | 6 / 16 / 16 | 16 | 207 / 2111 | 6 |
| test | stress | 4 / 12 / 16 | 16 | 419 / 2095 | 6 |
| training | base | 7 / 16 / 16 | 16 | 3226 / 5288 | 8 |
| training | optimistic | 11 / 16 / 16 | 16 | 3019 / 5349 | 8 |
| training | stress | 0 / 1 / 16 | 16 | 3244 / 5319 | 1 |

Base test bands with positive mean funded net PnL per completed trip were 1-15m, 1-6h, 1-7d, 15m-1h, 6-24h, <1m, >7d.
Across the A/B universe the price-check rule as of the origin (ADR-0110) excluded 1,855 base intents in test. The omitted contribution at leader prices was 43,355.92 USDC across 300/300 measurable comparisons.

Base training bands with positive mean funded net PnL per completed trip were 1-6h, 15m-1h, 6-24h, >7d.
Across the A/B universe the price-check rule as of the origin (ADR-0110) excluded 3,638 base intents in training. The omitted contribution at leader prices was 34,214.63 USDC across 290/300 measurable comparisons.

Mean shortfall on parameterised orders understates copy-series volatility and can distort Sharpe.
