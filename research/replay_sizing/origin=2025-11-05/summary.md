## 2025-11-05

| Window | Scenario | Positive / measured / gate-passers | Traded | Unpriced / intents | Drawdown over 10% |
| --- | --- | ---: | ---: | ---: | ---: |
| test | base | 8 / 15 / 15 | 14 | 54 / 1280 | 2 |
| test | optimistic | 8 / 15 / 15 | 14 | 59 / 1283 | 2 |
| test | stress | 7 / 15 / 15 | 14 | 55 / 1282 | 4 |
| training | base | 9 / 15 / 15 | 15 | 1894 / 5566 | 8 |
| training | optimistic | 12 / 15 / 15 | 15 | 1839 / 5625 | 8 |
| training | stress | 0 / 1 / 15 | 15 | 1877 / 5588 | 1 |

Base test bands with positive mean funded net PnL per completed trip were 1-6h, 6-24h.
Across the A/B universe the price-check rule as of the origin (ADR-0110) excluded 784 base intents in test. The omitted contribution at leader prices was 16,553.90 USDC across 330/330 measurable comparisons.

Base training bands with positive mean funded net PnL per completed trip were 1-6h, 1-7d, 15m-1h, 6-24h, >7d.
Across the A/B universe the price-check rule as of the origin (ADR-0110) excluded 5,236 base intents in training. The omitted contribution at leader prices was 122,040.67 USDC across 319/330 measurable comparisons.

Mean shortfall on parameterised orders understates copy-series volatility and can distort Sharpe.
