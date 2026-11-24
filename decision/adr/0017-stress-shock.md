# ADR-0017: Stress shock = largest 24 h fall (longs) and rise (shorts) before the origin

- Status: Accepted (horizon PLACEHOLDER)
- Date: 2026-11-19
- Phase: Phase 2

## Context
The plan applies "the largest observed move in each coin" to typical and peak exposure. The brief requires
moves before the origin only: at 8 Oct the 10 Oct crash is not yet known. A first version used the largest
absolute move: HYPER's largest move before 22 Oct is +433% (2025-07-11, after listing), which it then applied
to long exposure too.

## Decision
- Per coin, over hour marks from `leader.price_history_start` (2025-07-01) to asof, both ends priced: the
  largest fall and the largest rise of P(t) / P(t - 24 h) (`leader.risk.stress_horizon_h`).
- At each hourly mark the fall is applied to long and the rise to short exposure, all coins adverse at once;
  implied loss / equity; typical = median over marks, peak = max. Exposure in coins without a shock is
  reported (`unshocked_exposure_share`).
- The 8 Oct summary states that the 10-11 Oct crash is not known and not used; later origins state how many
  coins take their largest fall from 10-11 Oct.

## Consequences
Gate `max_stress_peak_loss` = 1.0 (PLACEHOLDER): failures rise from 96 (8 Oct) to 137-174 once the crash is
in the history. The shock table is `stress_shocks.parquet` per origin.
