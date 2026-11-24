# Full selection criteria: from 1,500 addresses to the 3 Dec basket

Written 2026-11-22. This document describes the selection lifecycle as it is **implemented and frozen**
(freeze `cbb44708…`, rule `rule_b_coin_filter`), with every criterion's definition, its threshold and the address
counts it produces. Sources: `config/decision_context.yaml` (all thresholds), `config/execution.yaml` (replay), the ADRs
cited in each section, and the outputs under `research/`. Thresholds marked PLACEHOLDER in the config were fixed on
development data before the outcome they affect was computed. Open issues found in the pre-holdout review are listed in
section 7 and in [pre-holdout-checks.md](pre-holdout-checks.md).

## 0. The funnel at a glance

Selection runs **point in time at each origin** (decision date): 8 Oct, 22 Oct, 5 Nov, 19 Nov and 3 Dec 2025 (the
holdout origin). At an origin only data with timestamp before it is used; grades, gates and keys are recomputed
independently each time.

| Stage | What it removes | 8 Oct | 22 Oct | 5 Nov | 19 Nov | **3 Dec** |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Addresses known by the origin | | 1,072 | 1,118 | 1,166 | 1,214 | **1,313** |
| Milestone 1: grade A or B (section 1, ADR-0066) | untrustworthy data | 302 | 332 | 335 | 361 | **358** |
| &nbsp;&nbsp;of which A / B | | 200 / 102 | 223 / 109 | 211 / 124 | 250 / 111 | 182 / 176 |
| Phase 2: all binding gates pass (section 2, ADR-0067) | missing data, thin evidence, severe leader risk | 22 | 19 | 25 | 25 | **23** |
| Phase 3: no address removed (section 3) | produces the copy series every later test uses | 22 | 19 | 25 | 25 | **23** |
| Phase 4 v2 S3: copyability (section 4.0, ADRs 0073, 0076), with S1-S2 | coins outside the tradable set > 10% of the leader's book, direction change, equity band, break-even delay, weaker copier | 5 | 3 | 2 | 2 | **2** |
| &nbsp;&nbsp;tradable coins (pooled T1-T5) | | 20 | 25 | 26 | 29 | 27 |
| Phase 4 v2 S4-S5: measured, all A/B (ADRs 0070, 0080, 0082) | under 20 exposed days or 4 exposed weeks (E0) | 141 | 202 | 225 | 251 | **259** |
| &nbsp;&nbsp;categories E- / E1 / E2, all A/B (ADRs 0072, 0084: α excludes funding) | | 65 / 65 / 11 | 77 / 117 / 8 | 82 / 143 / 0 | 93 / 158 / 0 | **97 / 162 / 0** |
| &nbsp;&nbsp;of the E2, carry books (ADR-0083; before ADR-0084: 3 / 1 / 5 / 6 / 5) | | 0 | 0 | 0 | 0 | **0** |
| &nbsp;&nbsp;τ² (DerSimonian-Laird; robustly 0?) | | 7.3e-7 (no) | 7.8e-7 (no) | 2.6e-8 (no) | 4.0e-8 (no) | **0 (yes)** |
| Phase 4 v2 qualified: E1 or E2 and S1-S3 | no positive own α, or not copyable | 1 E2, 2 E1 | 2 E1 | 1 E1 | 1 E1 | **1 E1** |
| Phase 4 v2 S7: near-duplicates removed (ADR-0074) | the same bet twice | 0 | 0 | 0 | 0 | **0** |
| **Phase 4 v2 hand-off to Phase 5** (`eligible.parquet`) | | 3 | 2 | 1 | 1 | **1 (0x2cd9, E1)** |
| Phase 4 v2 S6: ordering used? (ADR-0075) | IC of m +0.098 / -0.029 / -0.038 / -0.150 | | | | | **no** |

**Phase 4 v2 is in force** (`decision/phase-4-v2-results.md`, 2026-11-23). It qualifies addresses and no longer forms a
basket.
- **One E2 reaches the hand-off:** 0x971f at 8 Oct. Every other hand-off row is E1 (shadow only).
- **ADR-0084 removes funding from α.** E2 then exists only at 8 Oct and 22 Oct, and at 3 Dec τ² is robustly 0: there
  is no measurable skill dispersion, so nobody can reach E2. The former 3 Dec E2s were all carry books (short BTC/ETH
  copies collecting funding), and all failed Phase 2. The v1 rows (eligible, selectable, selected) are retired; before
ADRs 0066-0068 their counts were:
- A/B: 300 / 327 / 330 / 358 / 354;
- Phase 2: 16 / 12 / 15 / 13 / 11;
- eligible: 3 / 2 / 3 / 5 / 4;
- selectable: 1 / 1 / 3 / 4 / 3;
- selected: 1 / 1 / 2 / 3 / 3.

The frozen 3 Dec basket (0xd2f0…e9e1, 0x2cd9…946e, 0x971f…77fa, `research/selection/shortlist_2025-12-03.csv`) is
superseded. **0x971f now fails Phase 2 gate 7.**

The full package has **1,500 addresses** at the data cutoff (4 Jan 2026): 350 A, 153 B and 997 C (ADR-0066). The
3 Dec origin sees 1,313 of them.

---

## 1. Milestone 1: data grades A / B / C (data trustworthiness)

Code: `src/arkstream/quality.py`; ADRs 0023, 0028, 0045. Grades answer one question: *can this address's records be
turned into a return series we trust?* They contain no performance measure.

### 1.1 Inputs per address, as of the origin

- **Snapshots** (`traders.csv`): equity `E_t`, `pnl`, `net_deposit`, one row per observation.
- **Fills** (`fills.csv`): every trade, with `start_position`, side, size, price, fee, `closed_pnl`, `tid`, `oid`.
  Only core perpetuals are "eligible" (spot and HIP-3 are out, ADR-0021/0022).

### 1.2 Measures

- **Calendar days:** `D = (origin date - first snapshot date) + 1`, inclusive (ADR-0023).
- **Presence share** = distinct UTC dates with a snapshot / `D`.
- **Usable days:** dates with a snapshot that is neither near-zero (|equity| < 10 USDC) nor *frozen*.
  **Frozen** = two consecutive snapshots with identical equity while the fully priced core-perp trading PnL rebuilt
  from fills moved by more than 0.000001 USDC between them. **Unusable share** = 1 - usable days / `D`.
- **PnL identity (ADR-0066):** for each snapshot, `ε_t = pnl - (equity - net_deposit)`. A snapshot *breaches
  materially* when |ε_t| > max(10 USDC, 0.5% of equity), ADR-0045's materiality. With S = max(median equity, 500):
  - **material match share** = share of snapshots without a material breach;
  - **stable offset** = at least 99% of snapshots within the same bound around the median residual, and the median
    does not shift by more than 0.5% of S between the earlier and later halves of the history;
  - **bounded** = |median residual| ≤ 10% of S.

  The previous rule (a 0.01 USDC match share and a CV of at most 0.25) is replaced; the counts in section 0 predate
  ADR-0066 until the rerun.
- *(Superseded detail kept for the record)* the old rule:
  - **Match share** = share of snapshots with |residual| ≤ 0.01 USDC.
  - **Offset CV** = std(residual) / |mean(residual)| ("stable offset" when ≤ 0.25: a constant scope difference
    such as funds held outside cross margin, which the rebuilt book can correct).
- **Continuity break:** in chain order per coin, a fill's `start_position` differs from the previous fill's ending
  position by more than a small absolute plus relative tolerance. It means fills are missing.
- **Zero equity while holding:** a snapshot with equity exactly 0 while the fill ledger shows an open position.

### 1.3 Rules (`config: grades`)

| Grade | Condition (first match wins: C, then B, else A) |
| --- | --- |
| **C, excluded** | any of: no snapshots; no fills; a continuity break; near-zero equity on more than 50% of snapshots; unusable share > 20%; material match share < 99% **and** the offset is not stable, or stable but larger than 10% of equity (ADR-0066) |
| **B, usable with a stated fix** | any of: presence share < 95% (fix: multi-day returns across gaps); material match share < 99% with a stable, bounded offset (fix: use the rebuilt book); zero equity while holding (fix: use the rebuilt book) |
| **A, as is** | none of the above |

At the cutoff the C reasons are: too many unusable days 663, unstable scope mismatch 366, no fills 300, equity near
zero 45 (an address can have several). B reasons: snapshot gaps 152, stable scope offset 6.

### 1.4 Return series attached to each A/B address (used by every later phase)

- **Snapshot TWR** (ADR-0014): for consecutive snapshots,
  `PnL_t = E_t - E_{t-1} - ΔND_t`, `r_t = PnL_t / (E_{t-1} + ΔND_t)` (start-flow convention; `PnL_t / E_{t-1}` is the
  end-flow sensitivity). Intervals are excluded when opening equity < 500 USDC, the denominator is ≤ 0, or the two
  conventions differ by more than 1 point. A gap gives one multi-day return; nothing is interpolated.
- **Rebuilt core-perp book** (ADRs 0015, 0024, 0028): positions rebuilt from fills, valued hourly at venue marks
  (Hyperliquid daily for the 32 coins that fail the Binance price check, Binance 1m otherwise), funded with actual
  hourly funding. The daily book return = book PnL of the UTC day / cross-margin equity at the opening midnight.
- **Which is primary** (ADR-0045): a snapshot *breaches* when |residual| > max(10 USDC, 0.5% of equity). The rebuilt
  book is primary when ≥ 5% of snapshots known by the origin breach, or ≥ 3 consecutive ones do; otherwise the
  snapshot TWR is primary and breaching intervals are excluded from it. Recomputed at every origin.

### 1.5 Copier screen (also Milestone 1, used in Phase 4)

`src/arkstream/copiers.py`. For an ordered pair (L, F), a leader order is *matched* when F places an order in the same
coin and side within 30 s after it. `match_share` = matched / L's orders inside F's active span (at least 30 orders).
A pair is flagged at `match_share ≥ 0.25`, and **confirmed** when it exceeds 3x the 95th percentile of a placebo
built from 20 random constant time shifts of F (up to 1 day; seed 20260104). A confirmed cluster counts as one bet.

---

## 2. Phase 2: leader evidence and the suitability gates (four categories, ADR-0067)

Code: `src/arkstream/leader*.py`; ADRs 0013-0019, 0039, 0025-0028, 0045, 0066, 0067, 0068 and 0069. The gates are computed for
every A/B address at each origin, from data before it.
- **Each gate is pass / fail / unmeasured, and a missing measurement never passes** (ADR-0068).
- An address must pass every **binding** gate. The style gates are reported diagnostics: the simulated taker copy
  decides copyability in Phase 4.
- Funding is included.
- The one-sided 80% lower bounds use the same confidence level as the Phase 4 key.

3 Dec counts below are after ADRs 0066, 0067 and 0068 (358 A/B addresses).

### 2.1 Data integrity (binding)

| # | Gate | Metric | Pass if | 3 Dec pass / fail / unmeasured |
| ---: | --- | --- | --- | --- |
| 6 | `gate_rebuild_fit` | share of checkable, active intervals (opening equity ≥ 500) with \|account PnL - book PnL\| / opening equity ≤ 1%. Gated on the **one-sided 80% Clopper-Pearson lower bound** (a perfect fit needs ≥ 16 intervals; ≥ 10 to be measured). Reported: point share, longest run of misses, lag-1 autocorrelation of misses | lower bound ≥ 0.90 | 179 / 51 / 128 |
| 7 | `gate_book_account` | **gate 7 v2 (ADR-0069)** on usable intervals (≥ 10): 7a Spearman lower bound (Bonett-Wright, one-sided 80%) ≥ 0.5; 7b week-clustered lower bound of the steady-gap rate ≤ 5 bps/day; 7c Theil-Sen slope in [2/3, 3/2]; 7d std(account - book) ≤ 0.02. Reported: Pearson and its bound, OLS slope and intercept with CIs, nRMSE, residual autocorrelation, three largest residual intervals (`src_row`) | all four | 215 / 12 / 131 |
| 18 | `gate_unpriced` | share of **notional × hours** in coins without a usable price | ≤ 5% | 306 / 40 / 12 |
| | **category** | | | **160 / 89 / 109** (passers unchanged by ADR-0069: every new gate 7 failure was already failing or unmeasured on gate 6 or 18) |

### 2.2 Evidence sufficiency (binding)

| # | Gate | Metric | Pass if | 3 Dec |
| ---: | --- | --- | --- | --- |
| 1 | `gate_evidence` | completed, uncensored, usable round trips (observability). Reported: independent entry weeks and the week-clustered 95% half-width of the mean trip return. Skill is decided by the Phase 4 key on the copy | ≥ 20 | 178 / 180 / 0 |
| 5 | `gate_active` | days since the last eligible fill | ≤ 14 | 281 / 77 / 0 |
| - | `gate_history` | distinct snapshot dates and usable return days known by the origin (moved from Phase 4 `sel_history`, same test) | ≥ 90 and ≥ 60 | 250 / 108 / 0 |
| | **category** | | | **138 / 220 / 0** |

### 2.3 Trading-style copyability (diagnostic; judged by the simulated copy in Phase 4)

| # | Gate | Metric (reported) | Former threshold | 3 Dec pass / fail / unmeasured |
| ---: | --- | --- | --- | --- |
| 2 | `gate_hold` | median, p10 and p25 holding time; share of gross trip profit and net PnL from trips under 60 s and 5 min | median ≥ 60 s | 330 / 7 / 21 |
| 3 | `gate_order_rate` | orders per day; notional turnover / median equity / day; fee rate. Phase 4 adds follower fill rate and maximum copy leverage | ≤ 24 per day | 355 / 3 / 0 |
| 4 | `gate_maker` | maker share of fills (the copy always pays taker costs in the simulation) | ≤ 70% | 292 / 66 / 0 |

An address with fast trades stays in. Rejecting only its fast trades needs a copy-policy rule, for example a
persistence filter that copies exposure only once it has existed for τ seconds. That is a later design item.

### 2.4 Risk and account safety (binding; a severe-risk screen on the leader, not a follower risk limit)

| # | Subgroup | Gate | Metric | Pass if | 3 Dec |
| ---: | --- | --- | --- | --- | --- |
| 8 | historical | `gate_intraday_dd` | max drawdown of compounded hourly book returns (priced hours) | ≥ -50% | 228 / 115 / 15 |
| 9 | historical | `gate_worst_day` | worst daily book return | ≥ -25% | 247 / 111 / 0 |
| 10 | historical | `gate_worst_3d` | worst compounded 3-day book return | ≥ -35% | 255 / 103 / 0 |
| 11 | historical | `gate_max_dd` | max drawdown of the daily book index | ≥ -50% | 257 / 101 / 0 |
| 16 | historical | `gate_liquidations` | liquidation fills | = 0 | 356 / 2 / 0 |
| 17 | historical | `gate_top_dependence` | share of **positive** trip profit from the top 1% of trips. Reported: top-week share, net PnL without the best week | ≤ 50% | 210 / 123 / 25 |
| 14 | position | `gate_leverage_p95` | p95 of hourly gross / equity (p99 and max reported) | ≤ 10x | 298 / 41 / 19 |
| 15 | position | `gate_liq_distance` | 1 / max leverage - MMR, with a uniform 2.5% MMR (stated assumption; tiered MMR agreed but not implemented, ADR-0067) | ≥ 5% | 278 / 61 / 19 |
| 12 | stress | `gate_worstcase_dd` | **conservative bound**: positions at the adverse 4h bar extreme, chained (ADR-0039) | ≥ -50% | 170 / 175 / 13 |
| 13 | stress | `gate_stress_peak` | **stressed residual margin headroom**: min over hours of 1 - joint 24 h shock loss / equity - MMR × gross leverage | ≥ 0 | 151 / 188 / 19 |
| | | **category (historical / position / stress)** | | | **61 / 283 / 14** (129 / 275 / 114 pass) |

**All binding gates pass at 3 Dec: 23 addresses** (11 before ADR-0067). By origin: 22 / 19 / 25 / 25 / 23 (was
16 / 12 / 15 / 13 / 11). `research/audit/gate_change*.csv` lists every address that moves, with its reasons.

Notes:
- **No gate rewards high returns.** The gates screen data quality, evidence and severe risk. Copyability and skill
  are decided in Phase 4 on the simulated copy.
- **Follower risk limits come later.** Follower-level stressed loss limits are set from the risk budget in Phase 5
  (ADR-0065). The 1.5x gross cap de-levers the copy, so leader drawdown thresholds are not follower limits.

---

## 3. Phase 3: the follower replay (no address is removed here)

Code: `src/arkstream/replay*.py`; ADRs 0029-0036, 0044-0055, 0052, 0058-0063. Phase 3 answers *what would a copy
have earned after realistic costs?*
- It replays **every A/B address**, not only the gate-passers, at every origin.
- It covers the training window (27 Jul → origin) and the 14-day test window.
- Its outputs are the inputs of every Phase 4 test.
- It removes no address.

### 3.1 The copy model

- **Target-position mirroring with netting.** The follower targets `m × leader net position` in each coin, never
  individual fills, so a partial leader exit is never read as a full close.
  - Leader fills visible within a 250 ms debounce after the 392 ms receive delay form one decision.
  - The order is `target - (held + pending)`, so pending orders are never double counted.
  - Tested end to end through a fragmented leader lifecycle (`tests/test_fragmented_lifecycle.py`, pre-holdout
    Check 6).
- **Frozen sizing** (ADR-0052): `m = min(A / E_ref, 1)`. The allocation is A = 10,000 USDC per address, and `E_ref` is
  the leader's equity at the first usable snapshot, **reset to the latest usable equity at each 14-day review**. The
  copy is never larger than the leader (no scale-up, ADR-0037).
  - **What the reset does:** it keeps the copy's exposure equal to the leader's current leverage applied to A. After
    a leader loss the multiplier can rise, up to 1. In the 3 Dec training window, 483 of the 2,041 reviews that
    changed the multiplier raised it. The median address never rises above its first multiplier, the 90th percentile
    reaches 1.9x and the 99th 5.6x.
  - **The alternatives are overlays.** A fixed initial equity scales the copy up after leader gains. A high-water
    reference de-risks it after leader losses. Comparing them is a Phase 5 risk-policy item (ADR-0065).
- **Limits:**
  - gross exposure ≤ 1.5 × A = **15,000 USDC, fixed** (ADR-0034), with all coins scaled together. The cap and the
    sizing use the fixed allocation, not the sleeve's current NAV, so after copy losses the copy's leverage on its own
    capital rises (a Phase 5 risk-policy item);
  - each order ≤ 0.5% of the latest completed Hyperliquid 4h volume (ADR-0035, per order);
  - each order ≤ the leader batch's own notional;
  - minimum 10 USDC. A clipped or sub-minimum close can leave a small remainder until the leader's next order in
    the coin (Check 5: 1.4-2.4% of exposure-time).
- **Execution price at acknowledgement** = leader anchor (base: the leader sweep's VWAP) + drift over the delay +
  half-spread + impact. Fee 4.5 bps (taker: the copy never earns the leader's maker economics).

  | Input | Source |
  | --- | --- |
  | Drift, BTC / ETH / HYPE / SOL | Binance aggTrades, trade level (Hyperliquid has no public trade archive) |
  | Drift, other coins | parameterised: the short-delay estimate from leaders' own Hyperliquid split orders (ADR-0061), else a conservative floor (ADR-0048) |
  | Half-spread | max(configured 1 / 5 bps, estimate from Hyperliquid prints in the package, ADR-0031) |
  | Impact | square root, `Y · σ_daily · sqrt(Q / V_daily)`, Y = 1, with Hyperliquid 4h volume and volatility (ADR-0033). **Y is an assumption, not calibrated** |
  | Marks | Hyperliquid daily (ADR-0020) |

  There is no historical order book, so depth at the moment an order arrives cannot be verified.
- **Delay** (ADR-0058): optimistic 1 s; **base 1.2 s** (the measured median total delay); stress 5 s with crash-period
  drift, 3x half-spreads and 3x impact; severe 60 s / 300 s (sensitivity).
  - The acknowledgement is the leader fill time plus the total delay. The receive delay and the debounce only place
    the decision inside it, so nothing is counted twice.
  - The delay is one value per scenario, not a sampled distribution. Delay drift is -1.2% of the cost gap on the
    development tests (all A/B), so the simplification is immaterial here.
- **Where the cost goes** (copy vs the zero-cost benchmark, development tests, all A/B, base; shares of the gap):
  fees 59%, half-spread 34%, impact 20%, delay drift -1.2%, sub-minimum skips -0.1%, participation clips 1.5%. Some
  parts are negative, so the shares do not sum to 100%.

### 3.2 Outputs that Phase 4 uses

| Output | Definition | Used by |
| --- | --- | --- |
| Daily copy NAV / TWR | equity / previous equity - 1, open positions marked at the Hyperliquid daily mark, with funding | **the key (4.2, ADR-A0051)**, co-movement (4.3), outcomes |
| Completed follower round trips | net return = (gross at the anchor - execution cost - fees + funding) / peak notional | holding-band gate (4.1); trip diagnostics beside the key |
| Delay grid | the same window replayed at 1, 1.2, 5, 10, 60 and 300 s | break-even gate (4.1) |
| Zero-cost benchmark (ADR-0063) | the same sizing and cap with no fees, spread, impact or drift | coin filter (4.4), capture |
| Stress results and coverage | stress return; unmeasured when < 80% of intents are priced (ADRs 0049, 0055) | reported, and the basket stress check |
| Fill rate, maximum copy leverage | filled / submitted orders; maximum gross / NAV of the copy | reported in the candidate table (ADR-0067) |

---

## 4. Phase 4: selection

### 4.0 Phase 4 v2: qualification (in force; ADRs 0070-0075 and 0084; details in ADRs 0076-0083)

Code: `src/arkstream/selection_v2*.py`, `replay_tradable.py`; `python -m arkstream replay --allpriced`, `replay
--tradable`, `select-v2`. Results: [phase-4-v2-results.md](phase-4-v2-results.md). Every input is point in time at the
origin; the holdout is never computed. Phase 4 answers "who is individually qualified, and how strong is the
evidence?"; the basket and its weights are Phase 5's.

| Stage | Rule | 8 Oct | 22 Oct | 5 Nov | 19 Nov | 3 Dec |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Tradable coins (ADRs 0073, 0076) | T1 priced and a drift source; T2 ≥ 95% of notional-hours valued; T3 ≥ 95% of orders within 0.5% of the 4h bar; T4 notional-weighted median shortfall ≤ 25 bps/side (leave-one-wallet-out per wallet); T5 ≥ 5 effective wallets; no PnL condition | 20 | 25 | 26 | 29 | 27 |
| A/B universe (S1) | ADR-0066 | 302 | 332 | 335 | 361 | 358 |
| S2: all binding Phase 2 gates, gate 7 v2 (ADR-0069) | | 22 | 19 | 25 | 25 | 23 |
| `sel_tradable_share` ≤ 10% of the leader's notional-hours outside its set | ADR-0076 item 6 | 149 | 173 | 182 | 205 | 203 |
| `sel_direction` max per-factor \|Δβ\| ≤ 0.25 | ADR-0076 item 7 | 235 | 258 | 268 | 294 | 283 |
| `sel_equity_band` [5k, 2M], `sel_break_even`, `sel_copier` | unchanged (ADR-A0130); copier weaker = lower category, then m | 207 / 139 / 301 | 239 / 190 / 332 | 235 / 194 / 335 | 251 / 203 / 361 | 254 / 208 / 356 |
| S1-S3 all pass | | 5 | 3 | 2 | 2 | 2 |
| Measured (S4): ≥ 20 exposed days (gross = max(start, end of day) ≥ 10 USDC, ADRs 0080, 0082) in ≥ 4 weeks | ADR-0070 | 141 | 202 | 225 | 251 | 259 |
| τ² / Q p-value (DerSimonian-Laird over measured A/B; α excludes funding, ADR-0084) | robustly 0 = τ² 0 and p ≥ 0.20 | 7.3e-7 / 1e-25 | 7.8e-7 / 7e-5 | 2.6e-8 / 0.24 | 4.0e-8 / 0.012 | **0 / 0.69 (robustly 0)** |
| E0 / E- / E1 / E2 (all A/B, S5) | E2: posterior P(α > 0) ≥ 0.8, τ² not robustly 0, α without the best week > 0 | 161 / 65 / 65 / 11 | 130 / 77 / 117 / 8 | 110 / 82 / 143 / 0 | 110 / 93 / 158 / 0 | 99 / 97 / 162 / 0 |
| Carry books among E2 (reported, ADR-0083; measured on α incl. funding) | before ADR-0084: 3 / 1 / 5 / 6 / 5 | 0 | 0 | 0 | 0 | 0 |
| Qualified (E1/E2 and S1-S3) | | 1 E2, 2 E1 | 2 E1 | 1 E1 | 1 E1 | 1 E1 |
| Near-duplicates removed (S7) | overlap ≥ 0.7, ex-crash both-exposed corr lower95 ≥ 0.5, ≥ 20 days | 0 | 0 | 0 | 0 | 0 |
| **Hand-off** (`research/selection_v2/origin=*/eligible.parquet`) | | 0x971f (E2), 0xa536, 0xaeb9 | 0x971f, 0xa536 | 0xa536 | 0x2cd9 | **0x2cd9** |

- **Statistic (ADR-0071):** α = Σ residual PnL / Σ gross exposure-time, with the day's gross the larger of its
  start and end gross (ADR-0082). The residual is holdings-based against BTC, ETH and ALT, with coin betas fitted once
  per origin on the 90 days before it. **The residual excludes the copy's funding (ADR-0084):** carry is a premium,
  not skill. α including funding and the funding part are reported (ADR-0083). α comes with a week-clustered standard
  error (ADR-0077) and a static-replica split.
- **S6 ranking:** ordering is **not used**. The mean IC of the posterior mean is -0.030, positive at 1 of 4 origins
  (rule: mean ≥ 0.05 and ≥ 3 positive).
- **Development evaluation:** the E1 ∪ E2 hand-off beats same-size random draws in 2 of 4 windows on α and 1 of 4 on
  raw return. The categories are not ordered by next-window α at any origin.
- **Placebo:** 10 of 19 E2 address-origins beat their time-shifted copies (it runs only at 8 Oct and 22 Oct, where E2
  exists). Before ADR-0084 it was 12 of 46.

Sections 4.1-4.5 below are the **v1 record** (ADRs A0130-A0141, `research/selection`, `research/replay_coinfilter`),
kept unchanged.

### v1 (superseded): ADRs A0130-A0141

Code: `src/arkstream/selection*.py`. Everything is computed from the **training window ending at the origin**, never
from a test window. The v1 rule was `rule_b_coin_filter`: every copy series below comes from the replay with the
coin filter executed inside it (`research/replay_coinfilter`, ADR-A0140).

### 4.1 Selection gates → *eligible* (ADR-A0130)

On top of grade A/B and all 18 Phase 2 gates:

| Gate | Pass if | Why |
| --- | --- | --- |
| ~~`sel_history`~~ | moved to Phase 2 `gate_history` (ADR-0067), same test | enough record to judge |
| `sel_equity_band` | median equity in [5,000, 2,000,000] USDC | under no scale-up, a leader smaller than the sleeve cannot absorb it; the user's choice from the capital (plan: 20k) |
| `sel_copyable_notional` | share of notional in coins failing the point-in-time price check, or HIP-3, ≤ 10% | the copy can trade what the leader trades |
| `sel_hold_band` | the leader's holding band (<1m, 1-15m, 15m-1h, 1-6h, 6-24h, 1-7d, >7d) is copyable: across **all A/B** follower trips in that band in the training window, mean net return per trip > 0 over ≥ 100 trips | the style survives costs on average |
| `sel_break_even` | on the training delay grid, the copy return is positive through the whole grid, or the last positive delay is ≥ 1,200 ms | the edge survives the measured delay |
| `sel_copier` | not the weaker member of a confirmed copier cluster (weaker = lower key) | one bet counted once |

At 3 Dec, 11 addresses pass Phase 2. The equity band fails 5 (median equity 0.8k-4.5k) and break-even fails 4 (two of
them also outside the band; the other two, 0x6e99 and 0xba93, lose money already at the shortest delay). That leaves
**4 eligible**: 0x2cd9, 0x4c6e, 0x971f, 0xd2f0.

### 4.2 Ranking key → *selectable* (ADR-A0131, statistic amended by ADR-A0051)

**Statistic:** the copy's **mark-to-market daily NAV return**. It covers the base scenario, in the coin-filter replay
(kept coins only), from the first day the copy holds exposure to the day before the origin.
- Open positions are marked every day, so nothing is censored.
- Flat days after the first exposure count as 0, so idle capital lowers the key.
- Days without a valid NAV are dropped and counted.

**Uncertainty: a calendar-week block bootstrap.**
1. Group days by calendar week (Monday, UTC).
2. For b = 1 … 2,000: draw as many weeks as observed, **with replacement**, and compute the mean daily return
   `μ*_b`. The seed is `[20251008, address prefix, origin]`, so the result does not depend on which other addresses
   exist.
3. **Key = the 20th percentile of {μ*_b}**: a one-sided 80% lower confidence bound on the mean daily return.

**Rules:**
- Unmeasured (not selectable) with fewer than 20 valid days or fewer than 4 weeks (ADR-0068).
- **Selectable only if key > 0.**
- `single_event` flag (shown, not dropped): the key is positive but the same bound without the best week is not.
- The former trip key (mean net return per completed trip, entry-week blocks, min 10 trips / 4 weeks) stays in the
  candidate table as a diagnostic (`trip_key`).

**Why it changed** (ADR-A0051, development comparison):
- the trip key ignored open positions and idle capital;
- it was measurable for only 33-148 addresses per origin, against 173-298;
- the two keys rank addresses differently (Spearman 0.39);
- **neither predicts** the next window's copy return. Spearman across all A/B: trip -0.16 / -0.07 / +0.07 / +0.17,
  NAV -0.01 / +0.27 / +0.31 / -0.19.

The 3 Dec values under the new key come with the rerun. With the stored pools, the NAV key would have made 0x4c6e
selectable at 3 Dec (+6.4 bps/day, where its trip key was unmeasured on 8 trips).

### 4.3 Behaviour clusters and the diversification walk → *selected* (ADR-A0132)

**Behaviour clusters:**
- Ward hierarchical clustering on z-scored features of every A/B address, cut at 6 clusters. The features are:
  - log hold (median and IQR);
  - log orders per day;
  - log order size / equity;
  - median and p95 leverage;
  - net-long share of held hours;
  - coin HHI and BTC+ETH share;
  - beta to BTC;
  - maker share and fills per order;
  - log turnover / equity.
- No outcome feature is used. An address with a missing feature is its own group.

**Walk order:** selectable addresses sorted by rank within their behaviour cluster, then key (descending), then
address. Each style's best address comes before any style's second.

**Co-movement per pair**, training window:
- `corr` = Pearson correlation of the two daily copy-TWR series over the days both have a return, unmeasured under
  20 days;
- `overlap` = cosine similarity of signed exposures by (day, coin): `Σ e_a·e_b / (‖e_a‖·‖e_b‖)`.

**Walk rules:**
- A candidate joins only if, against **every** chosen address, corr < 0.5 **and** overlap < 0.5.
- An unmeasured pair **blocks** the candidate (ADR-0068; ADR-A0132 originally let it pass).
- The walk stops at K = 5; k = 0 is a valid outcome.
- Weights are equal: one 10,000 USDC sleeve per address.

At 3 Dec: 0xd2f0 (step 1) → 0x2cd9 (corr -0.19, overlap 0.37 with 0xd2f0) → 0x971f (max corr 0.31, max overlap 0.00).
All three are selected.

### 4.4 The coin filter (ADRs A0136, A0140)

At each origin, from the **unfiltered** training replay, all A/B addresses pooled:
- per (address, coin): `PnL = cash flows + closing position × window-end mark + funding`, for the follower and for
  the zero-cost benchmark;
- per coin, summed over addresses: `capture = follower PnL / benchmark PnL`.

**A coin is kept** if it is BTC, ETH, HYPE or SOL, or if `benchmark PnL ≥ 500 USDC` and `capture ≥ 0.5`. The filter
is executed inside the replay: excluded coins are never traded, and the 1.5x cap is solved on kept coins only. Coins
kept: 11 / 33 / 32 / 35 / **37** at the five origins.

### 4.5 How the rule itself was chosen (ADRs A0133, A0137, A0138, A0140)

- **Three variants, pre-declared:**
  - `rule_a` (sections 4.1-4.3);
  - `rule_b_coin_filter` (+ 4.4);
  - `rule_c_p10` (key at the 10th percentile).
- **Criterion, fixed before results:** the most development windows in which the basket beats the **matched
  random-k** median. Matched random-k = 1,000 seeded draws of k addresses from the same eligible pool. Ties go to the
  simpler rule.
- **Result:** rule_b won 3 of 4 under attribution scoring. Executed in the replay, it wins 2 of 4 against matched
  random-k and 2 of 4 against all-A/B random-k, and beats equal weight in 3 of 4. The mean basket return is +0.71%
  base per 14-day window (median -0.02%). Under ADR-A0140 the rule stays in force whatever the rerun showed.
- **Statistical strength (reported, not used to select):**
  - Clopper-Pearson two-sided 95% on 3 of 4 wins: 0.19-0.99.
  - Eligible pools of 3 / 2 / 3 / 5 leave 2-10 possible matched picks per window.
  - The key does not persist across origins: Spearman -0.16 to +0.18.
  - MinTRL is about 1,560 days.

---

## 5. What each layer is, statistically

| Layer | Nature | Uses returns? | Error it guards against |
| --- | --- | --- | --- |
| Grades | deterministic data-quality rules | no | building on records that do not reconcile |
| Phase 2 gates | deterministic thresholds on risk and behaviour metrics | the leader's own risk only, never its level | copying an account that can blow up, cannot be reconciled or cannot be followed |
| Phase 3 | simulation | produces them | mistaking a leader's return for a follower's |
| Phase 4 gates | thresholds on copyability (size, coins, style, delay) | sign of copy outcomes, pooled or by delay | copying what cannot be traded profitably at our size and speed |
| Key | bootstrap lower bound (p20, week-block-resampled) | the copy's own mark-to-market daily NAV returns (ADR-A0051) | luck in a short record |
| Walk | correlation and overlap thresholds | daily copy returns | holding the same bet twice |

## 6. Point-in-time and reproducibility guarantees

- Every measure uses data with timestamp before the origin; the holdout window is computed by nothing above.
- Missing inputs are never filled: a missing measurement is "unmeasured", and never passes a gate.
- Seeds are fixed (bootstrap, random-k, copier placebo). The replay is byte-identical on reruns with
  POLARS_MAX_THREADS=8.
- Every selected or rejected address carries its evidence keys (`snapshot_src_row`, `last_fill_src_row`, `tid`,
  `oid`) in `research/selection/origin=…/variant=rule_b_coin_filter/decisions.csv` and `candidates.parquet`.

## 7. Known weaknesses (open before the holdout)

1. **The walk's correlation counts flat days.** The 3 Dec copies hold exposure on only 31, 79 and 68 of 129 days. On
   the days both copies of a pair hold positions, two pairs reach 0.50-0.51, the 0.5 limit. All three sleeves are
   long-only, and two are concentrated in HYPE. The diversification benefit is unverified (pre-holdout Check 2).
2. **The coin filter has no coverage condition.** Unvalued observations are counted but not required to be few. It
   is immaterial at every origin so far (Check 1), but it is unguarded for the cutoff selection.
3. **The gates screen risk, not return.** On the unfiltered copy, eligible address-windows averaged -4.3% base against
   +1.1% for the rest (`diagnostics/gate_audit.csv`).
4. **Capture is low.** The basket keeps 0.157 of the zero-cost benchmark's PnL. That gap is mostly spread (49%) and
   fees (27%). Separately, the 1.5x cap de-levers high-leverage leaders.
5. **The sample is small.** There are four 14-day development windows, eligible pools of 2-5 and a 32-day holdout.
   The evidence for the ranking is weak by construction, and the result is reported as such.
