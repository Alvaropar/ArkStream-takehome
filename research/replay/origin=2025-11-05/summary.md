## 2025-11-05

| Window | Scenario | Positive / gate-passers | Traded | Unpriced / intents | Drawdown over 10% |
| --- | --- | ---: | ---: | ---: | ---: |
| test | base | 10 / 18 | 17 | 31 / 1535 | 3 |
| test | optimistic | 11 / 18 | 17 | 39 / 1535 | 3 |
| test | stress | 9 / 18 | 17 | 364 / 1489 | 3 |
| training | base | 11 / 18 | 18 | 2736 / 8051 | 12 |
| training | optimistic | 13 / 18 | 18 | 2779 / 8036 | 11 |
| training | stress | 10 / 18 | 18 | 4387 / 7681 | 9 |

Base test bands with positive mean funded net PnL per completed trip were 1-6h, 6-24h, <1m.
Across the A/B universe the 32-coin rule excluded 536 base intents in test. The omitted contribution at leader prices was 11,888.73 USDC across 330/330 measurable comparisons.

Base training bands with positive mean funded net PnL per completed trip were 1-6h, 1-7d, 15m-1h, 6-24h, >7d.
Across the A/B universe the 32-coin rule excluded 4,961 base intents in training. The omitted contribution at leader prices was 121,293.22 USDC across 319/330 measurable comparisons.

Mean shortfall on parameterised orders understates copy-series volatility and can distort Sharpe.
