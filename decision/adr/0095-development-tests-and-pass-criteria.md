# ADR-0095: Phase 5 development tests: trigger calibration and risk-rule variants on the population, the pair on the four test windows, stress tests, and the F1-F6 pass criteria

- Status: Accepted (the user approved ADRs 0086-0095 on 2026-11-24); criteria PLACEHOLDER, written before any Phase 5 run. The F6 shape test
  belongs to the user's decision 2 of 2026-11-23, written as decided. Population-run details pinned in ADR-0096.
  Results (`decision/phase-5-results.md`): F1-F6 pass on development data; item 2's variants were both rejected at
  P5-4; L1, which cannot fire on a training window, was measured out of sample on the test windows.
- Date: 2026-11-23
- Phase: Phase 5 (revision 4), steps P5-1 to P5-6
- Source: `decision/phase-5-methodology.md` sections 6, 7 and 13 (revision 4)

## Context
The scheme's rules (ADRs 0086-0089) are set on development data only (ADR-0065). Two things keep that honest:
- rules acting on sleeves are calibrated on the population, never on the chosen pair, which is in-sample on every
  development window (ADR-0086 item 3);
- the pass criteria are written before the runs.

## Decision
1. **Trigger calibration (P5-4), on the population.**
   - **Population:** every A/B single-sleeve copy over the training windows, each copy a basket of one, through the
     P5-3 engine.
   - **Reported per trigger:**
     - the firing rate per sleeve-month (30 days of a sleeve with a usable `E_ref`; a firing is a trigger's condition
       turning on, ADR-0089, pinned in ADR-0096 item 6);
     - the copy's 14-day return and drawdown after a firing against matched days without one (descriptive);
     - the false-alarm share: firings followed by a non-negative 14-day return.
   - **A threshold changes only** if it fires more than once per sleeve-month (operational noise), never to improve
     return. Every change is logged.
2. **Risk-rule variants (P5-4), on the population.**

   | Item | Current | Variant |
   | --- | --- | --- |
   | Cap denominator | 1.5 × fixed allocation (ADR-0034) | 1.5 × min(`A_i`, sleeve NAV) |
   | `E_ref` at reviews | reset to the latest equity (ADR-0052) | high-water reference `max(E_ref,prev, E_latest)` |

   - Each item is decided on all A/B single-sleeve copies over the four development test windows, never on the pair.
   - **Criterion:** keep the current rule unless the variant lowers the 95% expected shortfall of window returns by
     at least 20% at a mean cost of no more than 0.25 pp per window.
     - The ES is the mean of the worst 5% of address-window returns (base), pooled over the four windows.
     - The cost is the mean of (current − variant) return per address-window.
   - The two items are decided separately, each against the current rule.
   - **Result (P5-4):** both rejected. The cap denominator min(A, NAV) cut the ES95 by 1.3% and the high-water `E_ref`
     by 1.6%, against the 20% required, so the current rules stay.
3. **Sizing replays (P5-1):** the two sleeves at 2,500 and 5,000 USDC on the frozen tradable stack (10k exists).
   - **Reported:** the unscaled sub-minimum share and the expected live order rate per week. The share that sets the
     gray size is measured on G\* after `λ`, from the P5-3 engine on the four development test windows (P5-5;
     ADR-0090 items 4 and 6).
   - **Check:** a byte-identical rerun.
4. **Risk model (P5-2):** the stress shocks, betas and covariance per origin (ADR-0088 item 2), in
   `risk_model/origin=<date>/`.
   - **Leak test:** a planted post-origin move must not change any output.
5. **The pair on the four test windows (P5-5).**
   - **Run:** S\*, U\* and G\* with the P5-3 engine in the four scenarios.
   - **Reported for each configuration:**
     - raw return, α (excluding funding) and funding;
     - max drawdown, worst day, 95% ES;
     - time in each state and every firing;
     - each sleeve's `λ_i` over time, its time-weighted and exposure-weighted means (ADR-0096 item 11) and the
       limit that set it;
     - P5 binding;
     - netting between sleeves (shared BTC);
     - participation clips and flatten-sweep closures;
     - utilisation, and the cost split (half-spread, fee, impact, drift).
   - **S\* against U\*:** the return, drawdown and tracking error that the limits cost or save, per sleeve.
   - **G\*:** the stress loss before each trade against the cap, the gray `λ`, and the loss path against `L_gray`.
   - **Context, not a test:** 200 random pairs of A/B copies per window through the same engine (S\* rules), seed
     `[20251203, origin ordinal]`. Each pair is two distinct addresses with a usable copy in the window.
   - **Label in every table:** "selection in-sample on these windows; machinery test, not skill".
6. **Stress tests (P5-5).**
   - **Historical:** the 10-11 Oct path inside the 8 Oct window, in base and severe, for S\*, U\* and G\*. Reported:
     state changes, the loss against the ladder (S\*) and against `L_gray` (G\*), and the exit costs.
   - **At the limits (pinned here):**
     - each sleeve's book shape at the hour of its largest stress usage in the four test windows is scaled up until
       the first limit binds: S\* with both sleeves at the scheme's maximum permitted exposure, and G\* at the
       largest exposure its stress cap allows;
     - then the section 4 joint shock (every coin adverse at once) and a flatten at severe delays and stress costs.
7. **Pass criteria before the freeze (PLACEHOLDER):**

   | # | Criterion | Pass |
   | ---: | --- | --- |
   | F1 | Fault tests: every ladder and state transition both ways; reduce-only never increases \|position\|; flatten completes within O1 with its cost booked; resume refused outside a review; participation shared within a bar; stale signal dropped and resynced; flatten sweep closes a residual; the `E_ref` invariant; every limit restored by whole-sleeve scaling; solver non-convergence goes to `λ = 0`; C3 by fault injection | all pass |
   | F2a | Stress at the limits, S\* | loss ≤ 16.5% of `D` (the flatten step plus overshoot) |
   | F2b | Stress at the limits, G\* | loss including exit ≤ `L_gray` = 750 USDC |
   | F3 | Historical stress | the ladder and the G\* cap act as designed; no limit is breached without its action |
   | F4 | Trigger noise | each leader trigger fires at most once per sleeve-month on the population |
   | F5 | Determinism | two runs byte-identical |
   | F6 | Shape **[decision 2]** | in S\* and G\*, at every target update, each sleeve's targets equal one scalar × its U\* targets on every leg (relative tolerance 1e-9), apart from the logged REDUCE_ONLY legs; holdings' deviations are reported as tracking error with their logged causes |

   If a criterion fails, the rules are fixed on development data, logged and retested. The criteria are not relaxed.
8. **Window-report module (P5-6):** `holdout_report.py` takes any (origin, window). It is run on all four development
   windows, H5 included, with its schema fixed (pre-holdout Check 4).
9. **Order:** P5-1 and P5-2 → P5-3 → P5-4 → P5-5 → P5-6. Then, each on the user's explicit go: P5-7 (freeze),
   P5-8 (holdout) and P5-9 (cutoff deliverables). ruff, mypy, `uv run pytest` and `uv run python -m arkstream audit`
   stay green after each step.

## Consequences
- **Outputs:**
  - `research/replay_gray/` (P5-1);
  - `risk_model/origin=<date>/` (P5-2);
  - `portfolio_replay.py` and its tests (P5-3);
  - `triggers_calibration.csv` and the variant table (P5-4);
  - `decision/phase-5-results.md` (P5-5);
  - `holdout_report.py` (P5-6).
- **Development findings feed the memo** (ADR-0086 Consequences): `λ` for 0x2cd9, P5 behaviour, S\* against U\*,
  the cost of the risk actions and whether the costs match the model.
- **Every run and variant goes in the trial log,** with its trial count.
