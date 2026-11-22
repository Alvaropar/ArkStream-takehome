## 2025-10-08

| Window | Scenario | Positive / gate-passers | Traded | Unpriced / intents | Drawdown over 10% |
| --- | --- | ---: | ---: | ---: | ---: |
| test | base | 6 / 17 | 17 | 101 / 2163 | 9 |
| test | optimistic | 7 / 17 | 17 | 115 / 2161 | 7 |
| test | stress | 8 / 17 | 16 | 1306 / 2000 | 5 |
| training | base | 9 / 17 | 17 | 2949 / 5461 | 10 |
| training | optimistic | 12 / 17 | 17 | 3077 / 5452 | 9 |
| training | stress | 12 / 17 | 15 | 3856 / 5353 | 5 |

Base test bands with positive mean funded net PnL per completed trip were 1-15m, 1-6h, 1-7d, 15m-1h, 6-24h, <1m, >7d.
Across the A/B universe the 32-coin rule excluded 1,352 base intents in test. The omitted contribution at leader prices was 35,326.74 USDC across 300/300 measurable comparisons.

Base training bands with positive mean funded net PnL per completed trip were 1-6h, 15m-1h, 6-24h.
Across the A/B universe the 32-coin rule excluded 3,180 base intents in training. The omitted contribution at leader prices was 34,198.60 USDC across 291/300 measurable comparisons.

Mean shortfall on parameterised orders understates copy-series volatility and can distort Sharpe.
