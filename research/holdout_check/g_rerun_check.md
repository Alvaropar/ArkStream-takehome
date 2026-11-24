# G* rerun path for a differing cutoff hand-off, development check (ADR-0100 item 4)

Window 2025-11-19 -> 2025-12-03; synthetic cutoff hand-off ['0x2cd9f4645b14bf968212c7c108213eaeb193946e', '0x971fc0c9becffd708c52a195b8a87c27359e77fa'] (0x971f added; it is in the origin's all-priced universe with a published tradable set). Not a selection.

| Config | Scenario | Loss measure (USDC) | Limit | Within | Cap breaches |
| --- | --- | ---: | ---: | --- | ---: |
| G2500 | base | 92.4 | 750 | True | 0 |
| G2500 | optimistic | 94.0 | 750 | True | 0 |
| G2500 | severe | 89.0 | 750 | True | 0 |
| G2500 | stress | 92.4 | 750 | True | 0 |
| G2500_0x971f | base | 16.9 | 750 | True | 0 |
| G2500_0x971f | optimistic | 16.7 | 750 | True | 0 |
| G2500_0x971f | severe | 21.6 | 750 | True | 0 |
| G2500_0x971f | stress | 21.5 | 750 | True | 0 |

- D2b over both G\* books: **True**; unmeasured cutoff addresses: []
- the rerun's tree: `replay_gray_cutoff/trader=0x971fc0c9becffd708c52a195b8a87c27359e77fa` (30 files)
