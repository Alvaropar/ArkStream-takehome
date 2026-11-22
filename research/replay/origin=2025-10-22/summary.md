## 2025-10-22

| Window | Scenario | Positive / gate-passers | Traded | Unpriced / intents | Drawdown over 10% |
| --- | --- | ---: | ---: | ---: | ---: |
| test | base | 7 / 16 | 16 | 28 / 1632 | 3 |
| test | optimistic | 10 / 16 | 16 | 25 / 1632 | 2 |
| test | stress | 7 / 16 | 16 | 203 / 1614 | 4 |
| training | base | 11 / 16 | 16 | 3462 / 9123 | 10 |
| training | optimistic | 13 / 16 | 16 | 3528 / 9107 | 8 |
| training | stress | 8 / 16 | 16 | 6553 / 8774 | 5 |

Base test bands with positive mean funded net PnL per completed trip were 1-6h, 6-24h.
Across the A/B universe the 32-coin rule excluded 902 base intents in test. The omitted contribution at leader prices was 35,981.41 USDC across 326/327 measurable comparisons.

Base training bands with positive mean funded net PnL per completed trip were 1-15m, 1-6h, 1-7d, 15m-1h, 6-24h, <1m, >7d.
Across the A/B universe the 32-coin rule excluded 4,528 base intents in training. The omitted contribution at leader prices was 84,864.62 USDC across 317/327 measurable comparisons.

Mean shortfall on parameterised orders understates copy-series volatility and can distort Sharpe.
