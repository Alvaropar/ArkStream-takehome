# ADR-0067: Phase 2 gates in four categories; uncertainty-aware data checks; style screens judged by the simulated copy

- Status: Accepted (placeholders); rules fixed before any outcome under them was computed
- Date: 2026-11-23
- Phase: Phase 2 (leader evidence), with knock-on changes in Phase 4 (selection gates and reporting)
- Amends: ADRs 0018, A0027, 0039 and 0027 (gate set and definitions) and ADR-A0130 (`sel_history` moves into Phase 2)
- **Decided after seeing results.** It follows a gate review (user, 2026-11-23) and the development pools of 2-5
  eligible addresses. Every rule below is applied at all five origins and logged in the trial log, whatever it does
  to the pools.

## Context
Phase 2 required all 18 gates to pass, each scored the same way. The review asked for:
- four categories (the user's structure);
- uncertainty on the data checks;
- copyability judged by the economics of a taker copy instead of fixed style thresholds;
- stress measured as residual margin rather than "loss ≤ 100% of equity";
- a stable denominator for PnL concentration;
- follower-level risk limits.

Numbering below is that of `decision/full_selection_criteria.md` section 2.

## Decision

### 1. Four categories; `all_gates_pass` = every *binding* gate passes
A gate is still pass / fail / unmeasured, and **unmeasured never passes** (ADR-0068). Each category gets a status
column (`cat_*`) and gate-count rows.

| Category | Gates | Binding |
| --- | --- | --- |
| **Data integrity** | 6 `gate_rebuild_fit`, 7 `gate_book_account`, 18 `gate_unpriced` | yes |
| **Evidence sufficiency** | 1 `gate_evidence`, 5 `gate_active`, new `gate_history` | yes |
| **Trading-style copyability** | 2 `gate_hold`, 3 `gate_order_rate`, 4 `gate_maker` | **no: diagnostic** (item 4) |
| **Risk and account safety** | historical: 8, 9, 10, 11, 16, 17 · position: 14, 15 · stress: 12, 13 | yes |

### 2. Data integrity
- **Gate 6, rebuild fit.** The point share of intervals within 1% (≥ 0.90, at least 10 intervals) is replaced by
  the **one-sided 80% Clopper-Pearson lower bound of that share ≥ 0.90**. The confidence level is the same one-sided
  80% the Phase 4 key uses (ADR-A0131). A perfect fit now needs at least 16 intervals. Reported beside it:
  - the point share and the interval count;
  - the longest run of consecutive misses;
  - the lag-1 autocorrelation of the miss indicator (persistence).
- **Gate 7, book vs account.** The correlation must hold at its **one-sided 80% Fisher-z lower bound ≥ 0.5**. The
  tracking std ≤ 0.02 and at least 10 intervals are unchanged. Reported beside it, from the regression of account
  return on book return:
  - the slope and intercept, with 95% CIs;
  - the normalised RMSE: RMSE(account - book) / std(account).
- **Gate 18, unpriced exposure: unchanged.** The review asked for notional weighting, but the share is already
  notional × hours (`pos × last fill price` summed over hours, `leader_returns.book_hourly`). A missing mark on a
  50k position already weighs 500 times one on a 100 USDC position.

### 3. Evidence sufficiency
- **Gate 1** keeps 20 completed trips as the minimum for **observability**. Skill is not decided here. It is decided
  by the Phase 4 key: a one-sided 80% block-bootstrap lower bound on the copy's own trips (ADR-A0131). Reported beside
  the gate:
  - the number of entry weeks with completed trips (independent blocks);
  - the 95% half-width of the mean trip return, with a standard error clustered by entry week.
- **Gate 5** is unchanged.
- **`gate_history`** (moved from Phase 4 `sel_history`, ADR-A0130, same test): at least 90 distinct snapshot dates and
  at least 60 usable return days known by the origin. `sel_history` leaves the Phase 4 gate list, so the outcome is
  unchanged.

### 4. Trading-style copyability: diagnostics, decided by the simulated copy
The follower is simulated as a taker on every order: half-spread, taker fee, square-root impact, delay drift, sweep
anchor. That simulation already decides copyability in Phase 4, through `sel_hold_band`, `sel_break_even` and the
key. Fixed thresholds on the leader's style therefore exclude addresses on a proxy. Gates 2-4 are computed and
reported, but **no longer exclude**:
- **Gate 2:** holding time p10, p25 and median; the share of gross trip profit and the net PnL from trips held under
  60 s and under 5 min. An address that mixes fast trades with copyable slower ones stays in. Phase 4 judges its
  copy. **Rejecting its fast trades is not implemented.** It needs a copy-policy rule, for example copying exposure
  only once it has persisted for τ seconds, because the follower cannot know at entry that a position will be short.
  It is recorded as a later design item, with its own ADR and test on development data.
- **Gate 3:** orders per day, plus notional turnover / median equity / day and the fee rate per notional. The
  follower fill rate (filled / submitted, training window) and the copy's maximum leverage are reported in the Phase 4
  candidate table.
- **Gate 4:** the maker share is reported. The copy pays taker costs in the simulation, so the leader's maker
  economics never enter the follower's result.

### 5. Risk and account safety
Three subgroups, each with its own status column. The thresholds are **unchanged**, and the gates stay a
**severe-risk screen on the leader**, not a risk limit:
- **Historical** (8 intraday drawdown, 9 worst day, 10 worst 3 days, 11 max drawdown, 16 liquidations, 17 profit
  concentration).
- **Position** (14 leverage p95, 15 liquidation distance). Leverage p99 and max are added as reported values.
- **Stress** (12 worst-case drawdown, labelled the *conservative bound*, every position at its bar extreme; 13 stress
  headroom).

Changes:
- **Gate 13:** "peak stressed loss ≤ 100% of equity" is replaced by **stressed residual margin headroom ≥ 0** at
  every hourly mark: `1 - stressed loss / equity - MMR × gross leverage ≥ 0`. In words, after the joint 24 h shock
  the account must still cover maintenance margin on its pre-shock gross. Using the pre-shock gross is conservative
  for longs; for shorts it is stated as an approximation.
- **Gate 17:** the denominator becomes **gross positive trip profit**: the share of positive trip PnL from the top 1%
  of trips ≤ 0.5. Net PnL as denominator is unstable, and it made every losing leader unmeasured. Reported beside it:
  - the largest entry week's share of positive weekly PnL;
  - net PnL without the best week (leave-one-event-out).
- **Gates 9-11: not tightened.** The review is right that a 25% day or a 50% drawdown is not an acceptable loss for a
  follower. But the copy is not the leader: the 1.5x gross cap de-levers it. For example, 0x077a's leader had
  +88% / -59% days while its copy moved +5% / -2% (`research/copy_daily_twr_training.csv`). Tightening leader
  thresholds would exclude leaders whose copies never approach the loss. **Follower-level stressed loss limits are a
  Phase 5 deliverable** (ADR-0065), set from the risk budget and evaluated on the copy series.
- **Gate 15: tiered maintenance margin agreed, not implemented.** `MM = N × MMR_tier - D_tier` needs Hyperliquid's
  margin tables, a new external input (`info` `meta`). The tables available today are not point-in-time for 2025, so
  they would be an assumption, labelled. The uniform 2.5% stays a stated assumption (ADR-0018) until that fetch is
  added. It understates maintenance margin for low-max-leverage alts.

### 6. Thresholds (config `leader.gates`, PLACEHOLDER)
- `fit_lower_conf: 0.80` and `book_corr_lower_conf: 0.80`;
- `min_snapshot_days: 90` and `min_usable_days: 60` (moved from `selection.gates`);
- `min_stress_headroom: 0.0` replaces `max_stress_peak_loss: 1.0`;
- `max_top_profit_share: 0.5` replaces `max_top_pnl_share: 0.5`;
- `short_hold_s: [60, 300]` (reporting).

## Result (Phase 2 rerun at five origins, `scripts/audit_gate_change.py`)
| | 8 Oct | 22 Oct | 5 Nov | 19 Nov | 3 Dec |
| --- | ---: | ---: | ---: | ---: | ---: |
| A/B universe (ADR-0066) | 302 | 332 | 335 | 361 | 358 |
| All binding gates pass, before → after | 16 → 22 | 12 → 19 | 15 → 25 | 13 → 25 | 11 → 23 |

**Gains** (70 address-origins):
- gate 17 on positive profit (31): failures, or unmeasured losers;
- the maker share is no longer binding (30);
- the rest were unmeasured under the old gates.

**Losses** (23):
- `gate_history` (12): these were already excluded in Phase 4, so pools are unaffected;
- gate 17 (9), gate 6 (5), gate 13 (4), gate 7 (3).

**0x971f, in the frozen 3 Dec basket, now fails gate 7** at 19 Nov and 3 Dec:
- the account/book correlation is 0.538 on 118 intervals, and its lower bound is 0.480;
- the normalised RMSE is 0.85, and the slope is 1.07 [0.76, 1.37].

Its account returns and rebuilt book disagree more than the old point test showed. The outcome is a knife-edge
(0.48 against 0.50), stated as such.

## Consequences
- Phase 2 pass counts change at every origin. The three style gates no longer exclude, while gates 6, 7 and 13 are
  stricter. Counts by category are reported per origin.
- The Phase 3/4 rerun on the new universes (already required by ADR-0066) uses these gates.
- The freeze is void until the Phase 5 freeze.
- Tests cover: the categories and binding set, the lower bounds, persistence, the regression stats, headroom,
  profit concentration and `gate_history`.
