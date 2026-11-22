## 2025-12-03

| Window | Scenario | Positive / measured / gate-passers | Traded | Unpriced / intents | Drawdown over 10% |
| --- | --- | ---: | ---: | ---: | ---: |
| training | base | 9 / 11 / 11 | 11 | 1546 / 5341 | 6 |
| training | optimistic | 10 / 11 / 11 | 11 | 1508 / 5350 | 7 |
| training | stress | 3 / 3 / 11 | 11 | 1499 / 5355 | 2 |

Base training bands with positive mean funded net PnL per completed trip were 1-6h, 1-7d, 15m-1h, 6-24h, >7d.
Across the A/B universe the price-check rule as of the origin (ADR-0110) excluded 5,832 base intents in training. The omitted contribution at leader prices was 141,771.49 USDC across 340/354 measurable comparisons.

Mean shortfall on parameterised orders understates copy-series volatility and can distort Sharpe.
