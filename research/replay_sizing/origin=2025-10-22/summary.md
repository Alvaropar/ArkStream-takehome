## 2025-10-22

| Window | Scenario | Positive / measured / gate-passers | Traded | Unpriced / intents | Drawdown over 10% |
| --- | --- | ---: | ---: | ---: | ---: |
| test | base | 5 / 12 / 12 | 12 | 19 / 790 | 1 |
| test | optimistic | 8 / 12 / 12 | 12 | 9 / 795 | 1 |
| test | stress | 4 / 12 / 12 | 12 | 10 / 795 | 3 |
| training | base | 8 / 12 / 12 | 12 | 1842 / 4483 | 7 |
| training | optimistic | 10 / 12 / 12 | 12 | 1781 / 4535 | 5 |
| training | stress | 0 / 1 / 12 | 12 | 1834 / 4498 | 1 |

Base test bands with positive mean funded net PnL per completed trip were 1-6h, 6-24h.
Across the A/B universe the price-check rule as of the origin (ADR-0110) excluded 944 base intents in test. The omitted contribution at leader prices was 41,947.50 USDC across 326/327 measurable comparisons.

Base training bands with positive mean funded net PnL per completed trip were 1-15m, 1-6h, 1-7d, 15m-1h, 6-24h, >7d.
Across the A/B universe the price-check rule as of the origin (ADR-0110) excluded 4,980 base intents in training. The omitted contribution at leader prices was 79,503.60 USDC across 317/327 measurable comparisons.

Mean shortfall on parameterised orders understates copy-series volatility and can distort Sharpe.
