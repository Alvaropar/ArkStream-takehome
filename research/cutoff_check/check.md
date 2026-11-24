# Cutoff selection entry point, check mode (ADR-0100 item 7)

Origin 2025-12-03 (the last development origin), real configuration; nothing at or after it is read.

| Output | Compared with | Files | Result |
| --- | --- | ---: | --- |
| drift tables (builder, to 1e-9) | `research/drift` | 3 | identical |
| Phase 2 tables (builder; engine tables exact, others to 1e-12) | `research/leader/origin=2025-12-03` | 22 | identical |
| all-priced shared inputs | `research/replay_allpriced` | 4 | identical |
| every window's universe and leader series | `research/replay_allpriced` | 18 | identical |
| all-priced training window at 2025-12-03 | `research/replay_allpriced` | 28 | identical |
| all-priced capture rows of that window | `research/replay_allpriced` | 3 | identical |
| tradable training window at 2025-12-03 | `research/replay_tradable` | 28 | identical |
| tradable capture rows of that window | `research/replay_tradable` | 3 | identical |
| tradable sets | `tradable_pairs.parquet (that origin)` | 1 | identical |
| selection at 2025-12-03 (eligible.parquet included) | `research/selection_v2/origin=2025-12-03` | 12 | identical |

**Result: PASS**
