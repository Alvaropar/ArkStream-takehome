## 2025-11-19

| Window | Scenario | Positive / gate-passers | Traded | Unpriced / intents | Drawdown over 10% |
| --- | --- | ---: | ---: | ---: | ---: |
| test | base | 11 / 17 | 15 | 32 / 1272 | 2 |
| test | optimistic | 11 / 17 | 15 | 34 / 1270 | 2 |
| test | stress | 6 / 17 | 15 | 43 / 1258 | 3 |
| training | base | 13 / 17 | 17 | 2738 / 9070 | 11 |
| training | optimistic | 13 / 17 | 17 | 2781 / 9055 | 11 |
| training | stress | 11 / 17 | 17 | 4591 / 8758 | 9 |

Base test bands with positive mean funded net PnL per completed trip were 15m-1h, 6-24h.
Across the A/B universe the 32-coin rule excluded 751 base intents in test. The omitted contribution at leader prices was 19,144.58 USDC across 357/358 measurable comparisons.

Base training bands with positive mean funded net PnL per completed trip were 1-6h, 1-7d, 15m-1h, 6-24h, >7d.
Across the A/B universe the 32-coin rule excluded 5,321 base intents in training. The omitted contribution at leader prices was 141,286.29 USDC across 346/358 measurable comparisons.

Mean shortfall on parameterised orders understates copy-series volatility and can distort Sharpe.
