# Key figures

Regenerate with `make figures` (or `uv run --group figures python scripts/make_figures.py`). Every figure is read
from saved outputs in `research/`; nothing is recomputed. All gate thresholds and cost parameters behind them are
placeholders, to be set on development data.

| Figure | What it shows | Source |
| --- | --- | --- |
| [p2_gate_funnel.png](p2_gate_funnel.png) | Addresses graded A/B, passing the suitability gates, and passing every gate, at each test date | `research/leader/origin=*/evidence.parquet` |
| [p2_rebuild_vs_snapshots.png](p2_rebuild_vs_snapshots.png) | One gate-passing address: cumulative PnL from snapshots vs the book rebuilt from fills (exact snapshot times, with funding) | `book_vs_account.parquet` (3 Dec) |
| [p2_worstcase_vs_hourly.png](p2_worstcase_vs_hourly.png) | Max drawdown at hourly closes vs worst case inside 4h bars (Hyperliquid OHLC), with the −50% gate (ADR-0039) | `evidence.parquet` (3 Dec) |
| [p3_cost_per_side.png](p3_cost_per_side.png) | Copy cost per filled side (fee, half-spread, impact) for each cost and sizing variant | `research/replay/sensitivity_costs.csv` |
| [p3_return_by_variant.png](p3_return_by_variant.png) | Mean funded copy return across gate-passers per variant, pooled and per test window, including the worst-case gate | `sensitivity_returns.csv`, `sensitivity_returns_worstcase_gate.csv` |
| [p3_holding_bands.png](p3_holding_bands.png) | Net result per completed round trip by the leader's holding time, full variant | `sensitivity_bands.csv` |
| [p4_frozen_vs_dynamic.png](p4_frozen_vs_dynamic.png) | Archived record behind ADR-0052: the chosen frozen `E_ref` sizing against the dynamic denominator, base mean funded return per test window and pooled, gate-passers (not rerun) | `research/replay_sizing/sizing_comparison_pooled.csv` |
| [p4_cost_surface_frozen.png](p4_cost_surface_frozen.png) | Pre-Phase 4: cost uncertainty surface under frozen sizing (Y, participation, cap one at a time, best and worst corners) and its lower bound | `research/replay_frozen/cost_surface.csv` |
| [p4_holding_bands_frozen.png](p4_holding_bands_frozen.png) | Pre-Phase 4: net result per completed follower round trip by the leader's holding band, frozen sizing, base | `research/replay_frozen/sensitivity_bands.csv` |
| [p4_stress_coverage.png](p4_stress_coverage.png) | Pre-Phase 4: frozen stress result under the ADR-0049 and ADR-0055 coverage measures, measured windows, the worst-measured sensitivity and the stress check | `research/replay_frozen/stress_coverage.csv` |

The p3 figures are the Phase 3 record (before the pre-Phase 4 fixes, from `research/replay`); the p4 figures are the
current state with the frozen policy (`research/replay_frozen`), except `p4_frozen_vs_dynamic`, the archived
comparison the policy was chosen on.
