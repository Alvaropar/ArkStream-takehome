# Architecture decision records

One file per decision: `NNNN-short-title.md`. **Numbers follow the order in which the decisions were made.**
- They were renumbered once, on 2026-11-23 ([ADR-0085](0085-adr-renumbering-and-archive.md)). Every old number and its new one are in [RENUMBERING.md](RENUMBERING.md).
- A changed decision gets a new ADR, and the old one's status line says what amended it.
- An ADR that no longer carries any decision used by the study is deleted, after the parts still in force are copied into the ADR that replaces it. The 18 deleted on 2026-11-23 are listed, with the reason, in [RENUMBERING.md](RENUMBERING.md); older documents may still mention them as `ADR-A<old number>`.

**When to write one.** Any choice that changes a result, a data source, a rule, a threshold, the scope or
the layout of the project, and any choice another session or a reviewer would otherwise have to rediscover.
Exploratory trials and their numbers go in `provenance/trial_log.md`; the ADR records what was decided and
why, and points to the trials.

**Numbering.** A new ADR takes the next free number (0102 onward). Sessions working in parallel reserve consecutive numbers from the next free one in their brief, so the numbers stay in decision order.

## Template

```markdown
# ADR-NNNN: <decision in a few words>

- Status: Proposed | Accepted | Superseded by ADR-NNNN
- Date: YYYY-MM-DD
- Phase: <milestone or phase>

## Context
What forced the decision; the evidence (numbers, files, trial-log rows).

## Decision
What we do, precisely enough to implement or check.

## Consequences
What changes, what it costs, what stays open, how it is tested.
```

## Where to start: the rules in force, by phase

| Phase | Latest decisions (start here) | Definitions they build on |
| --- | --- | --- |
| Process and scope | ADR-0064 (scope: the gray-launch go/no-go), ADR-0065 (Phase 5 designed before the holdout; the freeze mechanism), ADR-0021 (the recruiter's answers), ADR-0022 (HIP-3 out) | ADR-0001 (ADRs), ADR-0007 (addresses as assets), [ADR-0085](0085-adr-renumbering-and-archive.md) (this numbering) |
| Milestone 1: data and prices | ADR-0044 (point-in-time price check), ADR-0051 and ADR-0054 (clean, reproducible copy) | ADRs 0002-0005, 0006, 0008-0012, 0020 |
| Phase 2: leader evidence | ADR-0066 (grades A/B/C), ADR-0067 (gates in four categories), ADR-0068 (missing measurements never pass), ADR-0069 (gate 7 v2) | ADRs 0013-0019 and 0023-0028 (returns, book valuation, trips, stress, leverage), ADR-0045 (return-source switch), ADR-0039 (worst-case drawdown), ADR-0047 (excluded-coin exposure, reported) |
| Phase 3: follower replay | ADR-0052 (frozen `E_ref` sizing), ADR-0037 (no scale-up), ADR-0058 and ADR-0062 (measured delays), ADR-0061 (alt drift), ADR-0055 (stress coverage), ADR-0063 (capture) | ADRs 0029-0035 and 0036 (the copy model and costs), ADRs 0046, 0048, 0049, 0050, 0053, ADR-0038 and ADRs 0040-0043, 0056, 0057 (how the delay was measured), ADRs 0059 and 0060 |
| Phase 4: qualification (v2) | ADR-0070 (structure), ADR-0071 (holdings α), ADR-0084 (funding out of α), ADR-0072 (evidence and categories), ADR-0073 (tradable universe, S3 gates), ADR-0074 (duplicates), ADR-0075 (the IC rule and the evaluation) | ADRs 0076-0083 (details pinned before computing) |
| Phase 5: portfolio design (accepted 2026-11-24; development results in [phase-5-results.md](../phase-5-results.md)) | ADR-0086 (two-sleeve paper scheme S\*, twin U\*, capital book G\*), ADR-0088 (limits, whole-sleeve `λ_i`), ADR-0090 (gray as an execution measurement), ADR-0093 (decision rule), ADR-0098 (holdout cost runs B and C), ADR-0101 (the second live sleeve at the cutoff) | ADR-0065 (scope and order), ADR-0087 (execution), ADR-0089 (states, triggers), ADR-0091 (joint freeze), ADR-0092 (holdout), ADR-0094 (protocols), ADR-0095 (development tests, F1-F6), ADR-0096 (engine details), ADR-0097 (freeze mechanism), ADR-0099 (cost runs and the holdout entry point pinned), ADR-0100 (cutoff selection and deliverables pinned) |

## Index (in decision order)

### 2026-11-19: Set-up, data and Phase 2 leader evidence (0001–0028)

| ADR | Decision | Status |
| --- | --- | --- |
| [0001](0001-record-decisions-as-adrs.md) | Record decisions as ADRs | Accepted |
| [0002](0002-reference-prices-binance-klines.md) | Reference prices from Binance 1m klines, with validity windows | Amended by 0020, 0051 |
| [0003](0003-aggtrades-from-binance-zips.md) | Trade-level drift from verified Binance aggTrades zips, from 2025-09-08 | Accepted |
| [0004](0004-drift-per-test-date.md) | Drift estimated per test date from earlier data only | Amended by 0046 |
| [0005](0005-approximate-drift-venue-basis.md) | Approximate drift corrected by the venue basis, capped at 100 bps | Accepted |
| [0006](0006-deterministic-drift-outputs.md) | Sorted drift outputs; retrying renames on Windows | Accepted |
| [0007](0007-addresses-as-assets.md) | Addresses as assets: suitability gates, daily TWR, copy series as the investable price | Amended by 0021 |
| [0008](0008-hyperliquid-public-data-feasibility.md) | Hyperliquid info endpoint: funding history go, 4h candles for the price check, 1h no-go | Accepted |
| [0009](0009-hyperliquid-funding-rates.md) | Hyperliquid hourly funding rates: fetcher, table, Phase 3 payment convention | Accepted |
| [0010](0010-price-check-rule-preregistered.md) | Price check rule (Binance vs Hyperliquid 4h closes), pre-registered | Accepted |
| [0011](0011-price-check-result-hyperliquid-4h-source.md) | Price check: 163 coins keep Binance; 32 use Hyperliquid 4h closes (daily marks, no hourly) | Amended by 0044 |
| [0012](0012-user-funding-check.md) | userFunding (daily rollups) reproduces rate x position x proxy price to ~5 bps; check only | Accepted |
| [0013](0013-leader-evidence-scope.md) | Leader evidence per origin for grade A/B addresses, ex-funding | Amended by 0023–0027 |
| [0014](0014-account-returns.md) | Account returns: start convention base, end sensitivity, gaps as one return | Amended by 0026 and 0028 (placeholders) |
| [0015](0015-hourly-book-valuation.md) | Book valued hourly by exact mark-to-market; unpriced hours null | Amended by 0024, 0025 (placeholders) |
| [0016](0016-round-trip-metrics.md) | Round-trip return on peak notional; hourly excursions; open trades valued at asof | Amended by 0024 |
| [0017](0017-stress-shock.md) | Stress shock: largest 24 h fall (longs) / rise (shorts) before the origin | Accepted (placeholder) |
| [0018](0018-leverage-liquidation-gates.md) | Leverage, liquidation distance at a stated 2.5% MMR; gates pass/fail/unmeasured | Amended by 0027 (placeholders) |
| [0019](0019-profiles-and-impact.md) | Profiles; order size against Binance daily quote volume | Accepted |
| [0020](0020-hyperliquid-primary-daily-prices.md) | Hyperliquid prices for daily metrics, Binance validates; 22 failing and 10 unmapped coins on Hyperliquid prices | Amended by 0044 |
| [0021](0021-recruiter-answers.md) | Recruiter answers: cutoff = end of data; equity = cross-margin equity; public data incl. L2; perps, HIP-3 permitted, spot out | Accepted |
| [0022](0022-hip3-excluded-for-now.md) | HIP-3 perps stay out of scope for now (permitted, not included) | Accepted |
| [0023](0023-origin-coverage.md) | Grade coverage through each origin | Amended by 0044 |
| [0024](0024-funded-valuation.md) | Fund core-perp books and use venue-specific marks | Accepted |
| [0025](0025-snapshot-fit.md) | Reconcile at exact snapshot times and disclose uncheckable intervals | Accepted |
| [0026](0026-asset-returns-and-exposure.md) | Measure address TWR and joint BTC/ETH exposure | Amended by 0028 |
| [0027](0027-suitability-gates.md) | Count address suitability gates at each origin | Accepted |
| [0028](0028-cross-margin-return-source.md) | Choose the primary return using the cross-margin PnL identity | Amended by 0045 |

### 2026-11-20: Phase 3 follower replay, no scale-up, the latency method and the point-in-time fixes (0029–0049)

| ADR | Decision | Status |
| --- | --- | --- |
| [0029](0029-follower-execution-price.md) | Price follower orders at acknowledgement using aggTrades or point-in-time drift and skip the 32 coins without intraday prices | Amended by 0044, 0048, 0053 |
| [0030](0030-follower-decision-and-sizing.md) | Debounce visible fills, size against cross-margin equity and reserve pending quantity | Amended by 0052, 0062 |
| [0031](0031-spread-and-impact.md) | Freeze minute-print spreads and assume impact against completed 4h volume | Accepted |
| [0032](0032-follower-returns-and-break-even.md) | Value follower daily TWR, completed trips and the delay and cost break-even | Amended by 0049, 0055 |
| [0033](0033-square-root-impact.md) | Test square-root impact using trailing Hyperliquid volatility and volume | Accepted for research |
| [0034](0034-address-gross-exposure-cap.md) | Scale all address targets to 1.5 times fixed allocation | Accepted for research |
| [0035](0035-participation.md) | Limit each follower order to 0.5% of the latest completed 4h volume (sensitivity) | Accepted (placeholder) |
| [0036](0036-leader-sweeps.md) | Anchor copies at the leader sweep (base VWAP, stress deepest); size drift term tested, none qualified | Amended by 0046 |
| [0037](0037-no-scale-up-frozen.md) | No scale-up frozen as the copy sizing rule (promotes ADR-A0087) | Accepted (frozen); amended by 0052 |
| [0038](0038-measured-latency.md) | Measured latency replaces the assumed copy delay (Hyperliquid receive delay measured; decide and acknowledge from the Binance repo) | Accepted; scenarios amended by 0058 |
| [0039](0039-worst-case-intrabar-drawdown.md) | Worst-case drawdown inside each 4h bar (Hyperliquid OHLC, Binance 1m check) with a −50% gate | Accepted (placeholder) |
| [0040](0040-read-only-ws-recorder.md) | Read-only Hyperliquid stream recorder: stdlib client, one host, subscribe-only guard, raw + manifest | Accepted |
| [0041](0041-clock-offset-ntp.md) | NTP offset before/after each run (best of 5 servers, ±RTT/2), linear correction; unusable if it moves > 20 ms | Amended by 0057 |
| [0042](0042-leaders-and-coins.md) | Leaders: package top 30 probed, 10 active with most fills in 24 h; coins BTC/ETH/HYPE/SOL + ZEC/PENDLE/AIXBT/TRX | Accepted |
| [0043](0043-receive-delay-analysis.md) | Receive delay per event; snapshots and the initial trades backlog excluded; batching, size bins, outputs | Accepted |
| [0044](0044-point-in-time-price-check.md) | Price check applied as of each origin (bars closing by it); `insufficient` not copied; every consumer uses its own origin's list | Accepted |
| [0045](0045-material-return-source-switch.md) | Rebuilt book primary only on material (> max(10 USDC, 0.5% equity)) and persistent (>= 5% or 3 in a row) breaches; else breaching intervals excluded | Accepted (placeholders) |
| [0046](0046-forced-fills-not-signals.md) | ADL, liquidation and settlement fills left out of drift, the sweep anchor and the size study; still mirrored as reductions | Accepted |
| [0047](0047-excluded-coin-exposure.md) | Per-address notional share in coins not passing at the origin and in HIP-3 (reported, no gate) | Accepted |
| [0048](0048-conservative-alt-drift.md) | Base drift below 300 s on parameterised coins = max(four-coin proxy, own 300 s, 0) | Accepted; amended by 0061 (split-order estimate first, this floor as fallback) |
| [0049](0049-stress-coverage.md) | Stress results with < 80% priced intents are unmeasured | Amended by 0055 |

### 2026-11-21: Pre-Phase 4 fixes: frozen sizing, stress rules, measured latency (0050–0063)

| ADR | Decision | Status |
| --- | --- | --- |
| [0050](0050-cost-uncertainty-surface.md) | Cost surface: Y, participation and cap one at a time plus best/worst corners; lower bound = least favourable point | Accepted |
| [0051](0051-reproducible-clean-copy.md) | Kline fetcher, lake rebuilt from verified zips (prices byte-identical), deterministic package, VERIFY.md, 8-thread byte checks | Amended by 0054 |
| [0052](0052-frozen-reference-equity-sizing.md) | Sizing policy: frozen `E_ref` (user's choice), first review at the first usable snapshot, plain, target mirroring with netting; frozen only from 2026-11-21 (dynamic = mean-reversion overlay, archived) | Accepted |
| [0053](0053-stress-fallback.md) | Stress fallback for parameterised coins without a crash-sample cell: max(liquidity-bucket estimate, 3x own base drift, 0) | Accepted (placeholders) |
| [0054](0054-reference-manifest-cutoff.md) | Regenerate the reference price manifest with the current cutoff; price files unchanged | Accepted |
| [0055](0055-stress-coverage-pricing-failures.md) | Stress coverage counts only pricing failures as unpriced (decided after seeing results); unmeasured fails the stress check; worst-measured sensitivity | Accepted (placeholder) |
| [0056](0056-hyperliquid-receive-delay-result.md) | Receive delay measured: userFills p50 392 / p99 1,218 ms (run p50 339-738); total ~1.1 s median, ~4.4 s p99, partly from Binance; scenarios unchanged | Accepted; scenarios amended by 0058; receive used by the replay, 0062 |
| [0057](0057-clock-drift-corrected-steps-limited.md) | Steady clock drift corrected (counter cross-check), 20 ms limit on steps only; NTP bound beside every number; NTP every 5 min in future runs | Accepted |
| [0058](0058-measured-copy-delay-scenarios.md) | Delay scenarios from the measured copy delay (user's choice before Phase 4): optimistic 1 s, base 1.2 s, stress 5 s all coins, severe 60 s / 300 s thin (labelled sensitivity); costs unchanged | Accepted |
| [0059](0059-millisecond-delays-and-horizons.md) | Delays and drift horizons in whole ms end to end; horizons and delay grid 1, 1.2, 5, 10, 60, 300 s; size study keeps 1/10/60/300 s | Accepted |
| [0060](0060-severe-scenario.md) | `severe` = stress costs and rules (drift pool, fallback, sweep anchor, coverage, stress check) at the old delays; shares the stress delay grid | Accepted |
| [0061](0061-short-delay-alt-floor.md) | Base alt drift below 300 s = max(four-coin proxy, point-in-time Hyperliquid split-order estimate of the delay's bin, 0); ADR-0048 floor where the bin has no estimate (decided after seeing results, fixed before running) | Accepted |
| [0062](0062-measured-receive-delay.md) | Replay receive delay 250 -> 392 ms (measured userFills median); batch grouping unchanged, decision time moves (decided after seeing results, fixed before running) | Accepted |
| [0063](0063-copy-capture-and-market-relative.md) | Copy capture against a same-sizing benchmark, and market-relative copy returns | Accepted |

### 2026-11-22: Scope, the new Phase 5 and grading (0064–0066)

| ADR | Decision | Status |
| --- | --- | --- |
| [0064](0064-scope-go-no-go.md) | Scope is the gray-launch go/no-go: Phase 5 shared-account replay and Phase 6 engine/runbook not built; the written test's operating questions answered in the memo from existing evidence, untested parts labelled | Amended by 0065 |
| [0065](0065-new-phase-5-portfolio-design.md) | New Phase 5 after basket selection: design capital distribution, unallocated capital, risk limits, pause and exit rules on development data; frozen with selection and tested together on the holdout, which stays closed until then | Accepted |
| [0066](0066-material-scope-offset-grading.md) | Grades judge the PnL-identity residual by ADR-0045 materiality: A = 99% of snapshots without a material breach; B = stable (99% within materiality around the median, no half-to-half shift) and bounded (median offset <= 10% of equity); else C. Replaces the 0.01 USDC match share and offset CV; amended the same day (MAD stability let episodic breaches through); A/B +2 to +5 per origin | Accepted (placeholders) |

### 2026-11-23: Phase 2 gate review, Phase 4 v2 and the renumbering (0067–0085)

| ADR | Decision | Status |
| --- | --- | --- |
| [0067](0067-phase2-gate-categories.md) | Phase 2 gates in four categories (data integrity 6/7/18; evidence 1/5 + history moved from Phase 4; style 2/3/4 as diagnostics judged by the simulated taker copy; risk 8-17 in historical/position/stress subgroups); gate 6/7 on one-sided 80% lower bounds; gate 13 as stressed margin headroom; gate 17 on positive profit; gates 9-11 not tightened (follower limits in Phase 5); tiered MMR deferred | Accepted (placeholders) |
| [0068](0068-missing-measurement-policy.md) | One missing-measurement policy: unmeasured data/evidence/risk never pass; an unmeasured co-movement pair blocks a walk candidate (amends ADR-A0132); unmeasured key not selectable | Accepted |
| [0069](0069-gate7-v2-book-account.md) | Gate 7 v2: Spearman lower bound >= 0.5 (Bonett-Wright), steady-gap rate lower bound <= 5 bps/day (week-clustered), Theil-Sen slope in [2/3, 3/2], tracking std <= 0.02; Pearson reported | Accepted (placeholders) |
| [0070](0070-phase4-v2-structure-series.md) | Phase 4 v2: qualification only (basket to Phase 5); copy ledger at a provisional 10k sleeve; common 12-week window; measurable at 20 exposed days / 4 weeks; one-pass recompute if Phase 5 changes sleeve sizes | Accepted (placeholders) |
| [0071](0071-holdings-alpha-per-gross.md) | Holdings-based market adjustment (BTC/ETH/ALT, coin betas fit once per origin on 90 days); primary statistic alpha per unit of gross exposure-time; mandatory static-replica decomposition | Accepted (placeholders) |
| [0072](0072-evidence-shrinkage-categories.md) | Week-clustered SE; DerSimonian-Laird tau2 first ("robustly 0" = 0 and Q p >= 0.20 -> no E2); EB posterior with mu0 <= 0; own-data robustness (alpha ex best week > 0); categories E0/E-/E1/E2/E3 | Accepted (placeholders) |
| [0073](0073-tradable-universe-copyability.md) | Ex-ante tradable universe T1-T5 (priced, valued, liquid at 10k, cost <= 25 bps/side leave-one-wallet-out, >= 5 effective wallets); leader excluded above 10% non-tradable; cap on the full book; |dbeta| <= 0.25; hold band diagnostic; supersedes A0136/A0140 | Accepted (placeholders) |
| [0074](0074-duplicates-only.md) | Phase 4 removes only near-duplicates (overlap >= 0.7, ex-crash both-exposed corr lower95 >= 0.5, >= 20 days); co-movement incl. exposure-based risk correlation handed to Phase 5; walk and K retired (supersedes A0132 items 2-5) | Accepted (placeholders) |
| [0075](0075-ranking-validation-evaluation.md) | Ordering used only if mean IC >= 0.05 and positive at >= 3 of 4 origins (flat-start test windows); conditional placebo; Phase 4 evaluated as qualification (E sets vs random, category calibration); supersedes the A0137 criterion | Accepted |
| [0076](0076-p4-2-tradable-measurement.md) | P4-2 details: all-priced and tradable replays rerun on the ADR-0066 universes (`replay_allpriced`, `replay_tradable`); how T1-T5 are read off the all-priced training replay; per-wallet sets with leave-one-wallet-out T4; cap plan on the whole priced book, other legs `not_tradable`; leader notional-hours for `sel_tradable_share` and per-factor `sel_direction` | Accepted (placeholders) |
| [0077](0077-p4-3-statistic-details.md) | P4-3 details: day indexing, valid days, flat-day consequence, ALT on the pooled set, beta fit (n >= 10, identity BTC/ETH), CR1 week-clustered SE with t-to-normal scaling at 0.80, static replica (costs in timing), reported statistic set | Accepted (placeholders) |
| [0078](0078-p4-4-p4-5-evidence-ranking-details.md) | P4-4/P4-5 details: DL pool = all measured A/B, cluster priors only if tau2 > 0 and every cluster >= 30, point-mass posterior P = 0, robustness variants, synchronized 7-day block draw and seed, outcome alpha with no day minimum, undefined IC = 0 in the mean | Accepted (placeholders) |
| [0079](0079-p4-6-to-p4-8-comovement-evaluation-handoff.md) | P4-6 to P4-8 details: S1-S3 in v2 (copier weaker by category then m), pairs among qualified E1/E2, co-movement measures and the Ledoit-Wolf Sigma (60 of 90 days, complete cases), greedy duplicate resolution, qualification tests vs random subsets, hand-off columns | Accepted (placeholders) |
| [0080](0080-exposure-materiality-dust.md) | (kept by the user; G amended by 0082) An exposed day needs start-of-day gross >= 10 USDC (the replay's minimum order); dust residuals of clipped closes are not exposure (decided after seeing the first P4-3/P4-4 run: tau2 7e-4 from a 0.002 USDC LINK residual with s ~ 0) | Accepted |
| [0081](0081-time-shift-placebo.md) | Time-shift placebo for every E2 address (not only hand-off rows): the copy's exposure path shifted circularly 1-7 days inside the window, same coins, sizes and costs; 20 seeded shifts; reported, not binding | Accepted |
| [0082](0082-gross-max-start-end.md) | Gross exposure-time G = max(start-of-day, end-of-day gross); exposed when G >= 10 USDC, so entry days from flat count with their costs (the user's flat-day fix, decided before rerunning P4-3 to P4-5; residual still on start-of-day positions) | Accepted |
| [0083](0083-alpha-ex-funding-carry-books.md) | Report alpha excluding funding (and the funding part) beside alpha; carry book = positive alpha at least half funding; no carry factor, nothing binding changes | Accepted |
| [0084](0084-funding-out-of-alpha.md) | Funding is a separate source of return, not skill: the Phase 4 v2 residual and alpha exclude the copy funding PnL (alpha incl. funding and the carry label reported); NAV, stress and Phase 5 inputs keep funding; amends ADRs 0071, 0083 | Accepted (decided after seeing results) |
| [0085](0085-adr-renumbering-and-archive.md) | One-time renumbering in decision order; the 18 ADRs no longer in force archived after their live parts were copied forward | Accepted |

### 2026-11-23: Phase 5 design, the two-sleeve paper scheme (0086–0095)

| ADR | Decision | Status |
| --- | --- | --- |
| [0086](0086-two-sleeve-paper-scheme.md) | Phase 5 decides CONDITIONAL GO vs NO-GO (GO rejected); S\* = paper copy of the hand-off 0x2cd9 and the zero-capital observation sleeve 0x971f at 10k each; U\* (unconstrained twin) and G\* (the hand-off alone at the gray size) run beside it; P4-9 not triggered; weighting deferred | Accepted (U\*, G\*: the user's decisions) |
| [0087](0087-phase5-execution-model.md) | Execution: sleeve targets × `λ_i`, netting as an internal cross at the decision mark, participation per coin per 4h bar over sleeves (amends ADR-0035 for this engine), 30 s stale signals, flatten sweep, determinism | Accepted (placeholders) |
| [0088](0088-risk-limits-whole-sleeve-scaling.md) | Limits O1-P6 on `D` = 20,000; whole-sleeve `λ_i` solver repeated to a fixed point; stress shock expanding from 1 Jul 2025, covariance and betas on 90 days (covariance reporting only); P5 as a 1,200 USDC per-coin stress budget; G\* under option C (`L_gray` replaces S2, P2-P5) | Accepted (placeholders) |
| [0089](0089-risk-states-and-triggers.md) | Per-sleeve and scheme states (HALVED, REDUCE_ONLY in shape, FLATTEN, PAUSED, EXITED); triggers L1-L7, C1-C3 defined point in time; exit and resume at reviews (resume modelled in replays) | Accepted (placeholders) |
| [0090](0090-gray-as-execution-measurement.md) | Gray money is an execution measurement paid as a research cost: `L_gray` 750 USDC, at most 5,000 live, 2,500 per sleeve (5,000 under the sub-minimum rule; set at 2,500 at P5-5), ends at both 4 weeks and 200 orders, the loss cap or 12 weeks; fallback recorded; amends ADR-0072's E1 consequence; stress cap on the remaining budget; sub-minimum share measured on G\* after `λ` | Accepted (the user's decision) |
| [0091](0091-joint-freeze.md) | One hash over the Phase 4 v2 specification (ADRs 0066-0084; diagnostics not adopted, gate 7b unchanged), the Phase 5 rules, config, sources, data manifests, environment and the window-report module; run at P5-7 on the user's go; mechanism details in ADR-0097 | Accepted |
| [0092](0092-holdout-run-once.md) | Holdout 3 Dec 00:00 → 4 Jan 00:00 (32 rows, 4 Jan excluded), S\*/U\*/G\* in four scenarios, G\* rerun for a different cutoff hand-off, outputs H1-H6 (H3 model against model) | Accepted |
| [0093](0093-decision-rule.md) | CONDITIONAL GO only if D1-D5 all hold (D2b on G\*, D3 model against model), else NO-GO; D4 on `m` (> -0.20), or on own α (> -0.14) when `m` is constant, as at 3 Dec | Accepted (placeholders) |
| [0094](0094-deployment-protocols.md) | Paper protocol (reviews, revisit at a pooled IC ≥ 0.068 over 6 windows, 0.047 on own α when `m` is constant; 6-month stop rule) and gray protocol (ADR-0090); cutoff selection and deliverables | Accepted (placeholders) |
| [0095](0095-development-tests-and-pass-criteria.md) | Trigger calibration and risk-rule variants on all A/B single-sleeve copies; the pair on four test windows with 200 random pairs as context; stress tests; pass criteria F1-F6 (F6 shape) | Accepted (placeholders) |
| [0096](0096-phase5-engine-details-pinned.md) | Engine details pinned at P5-3/P5-4 before any result: leg pricing (tree trigger price, else decision mark x tape factor or parameterised drift), `λ` re-solved only at leader-driven updates, C1 against each order's own anchor, L6 after 7 in-run days, L7 without look-ahead, 14-day reviews with modelled resume, C3 by fault injection, no leader-notional budget, population copies with S1/S3/states/triggers, the `E_ref,prev` of the variant, exposure-weighted `λ` | Accepted |
| [0097](0097-freeze-mechanism-v2.md) | Freeze mechanism for the joint freeze: v2 hand-off as the shortlist; sources = v1 globs, Phase 5 modules and their static import closure, plus the CLI entry point; ADRs 0065-0084 and 0086-0097 and the Phase 4 v2 / Phase 5 texts hashed; committed output manifest of the trees the holdout path reads; environment block in the hash (OS recorded, not compared); text hashed with LF line endings, as git stores it; refusals (OPEN in `risk.yaml`, no `POLARS_MAX_THREADS`, stale output manifest); stale lake aggTrades entries and the pre-Phase 4 leader tables superseded by the P4-1 rerun annotated; the v2 holdout entry point not yet written | Accepted |
| [0098](0098-holdout-cost-runs.md) | Holdout cost runs with the strategy frozen: A frozen cost model (decides D1-D5, runs first); B rebuilt real costs with the frozen model in the risk rules; C rebuilt real costs with a daily point-in-time refit feeding the stress limits and the gray loss cap (ADR-0099 item 9). The cost rebuild (delay draw, Binance tape, same-day Hyperliquid prints and leader taker fills, O2 fill completeness) is not a run. C1 and O2 keep frozen benchmarks (shadow logs in C); B and C reported, D3 and C1 also on B; run on the development windows before the freeze; Hyperliquid L2 archive not used | Accepted |
| [0099](0099-cost-runs-and-holdout-entry-pinned.md) | Cost runs B and C and the v2 holdout entry point pinned before computing: delay draw (per-draw quantiles, seed [20251203, origin, config]); tape drift on seven coins as a ratio (basis cancels); same-day spread, raw Corwin-Schultz, no floor; same-day impact `y` from the package's taker orders; frozen O2 bound per liquidity bucket (development stress p99), binary; C's daily refit (14-day spread and impact, drift table at daily vintages); the stress limits (S2, P4, P5, `L_gray`) and the gray loss cap read C's model, C1 and O2 stay frozen with shadow logs; the guarded entry point (trees, marks, series, A, decision entry, then B and C; G\* rerun; D5 as an input); minimum counts | Accepted |
| [0100](0100-cutoff-selection-and-deliverables-pinned.md) | The cutoff selection and deliverables pinned before computing: cutoff origin 4 Jan 00:00 (the last origin the frozen replay admits; the 4 Jan partial day unused); the cutoff context (six origins, the freeze guard keeps the real holdout start); drift and Phase 2 tables, the all-priced prepare step, the cutoff training window of both trees and the selection at that origin, by the frozen functions; `cutoff_handoff.json` (D5, replayable from 3 Dec); the P5-8 order (run A, cutoff selection, decision entry, B and C) enforced; `trader_decisions.csv` (first failed gate in S1, S2, S3, category, duplicate order) and `target_allocations.csv` (paper or gray, at most two live sleeves at 2,500); check mode at 3 Dec byte for byte | Accepted |
| [0101](0101-second-live-sleeve-at-cutoff.md) | The second live sleeve at the 4 Jan cutoff: 0x971f (with 0x2cd9, 2,500 each; 0x3a12 and 0xe65c in paper), the frozen deliverable as computed, chosen for the measurement (about five times the orders of 0x3a12, less exposure, smaller worst loss), not for own α. Departs from ADR-0090 item 4's address order at this cutoff; ADR-0100 item 6's ordering reached it through the τ² artifact. ADRs 0090 and 0100 are frozen, so their status lines are not edited. Open: the ordering at later origins, a standard-error floor in τ², O2 | Accepted |
