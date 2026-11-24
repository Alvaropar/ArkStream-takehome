## 2025-11-19

| Window | Scenario | Positive / measured / gate-passers | Traded | Unpriced / intents | Drawdown over 10% |
| --- | --- | ---: | ---: | ---: | ---: |
| test | base | 9 / 13 / 13 | 11 | 20 / 1009 | 1 |
| test | optimistic | 9 / 13 / 13 | 11 | 17 / 1012 | 1 |
| test | stress | 5 / 13 / 13 | 11 | 13 / 1014 | 3 |
| training | base | 11 / 13 / 13 | 13 | 1876 / 6298 | 6 |
| training | optimistic | 11 / 13 / 13 | 13 | 1816 / 6332 | 7 |
| training | stress | 1 / 1 / 13 | 13 | 1827 / 6322 | 0 |

Base test bands with positive mean funded net PnL per completed trip were 15m-1h, 6-24h.
Across the A/B universe the price-check rule as of the origin (ADR-0044) excluded 753 base intents in test. The omitted contribution at leader prices was 18,688.05 USDC across 357/358 measurable comparisons.

Base training bands with positive mean funded net PnL per completed trip were 1-6h, 1-7d, 15m-1h, 6-24h, >7d.
Across the A/B universe the price-check rule as of the origin (ADR-0044) excluded 5,946 base intents in training. The omitted contribution at leader prices was 139,205.95 USDC across 346/358 measurable comparisons.

Mean shortfall on parameterised orders understates copy-series volatility and can distort Sharpe.
