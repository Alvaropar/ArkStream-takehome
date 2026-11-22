# Brief: Phase 4, selection, the freeze and the single holdout evaluation

Written 2026-11-21. Project: `C:\Projects\quant-task-arkstream` (ArkStream Hyperliquid copy pilot, take-home).
ADR numbers reserved for this session: **0130-0149**. The main session will not edit the project while this runs.
The Hyperliquid latency session may still be recording: do not touch `src/arkstream_fetch/hl_ws_latency.py`,
`src/arkstream/latency.py`, `data/reference/latency/` or `research/latency/`.

## Why

The assignment asks for a capital decision at the cutoff: selected and rejected addresses with reasons, or a clear
no-go. Everything so far is an evaluation framework. Phase 4 turns it into a named selection rule, shows whether the
rule beats random picks on the four development windows, freezes it, and opens the holdout (3 Dec 2025 - 4 Jan 2026)
**once**. The plan's section **Selection and point-in-time validation** is the method; this brief fixes the inputs
and the order.

## Where things stand (read, do not recompute)

- **Sizing policy:** frozen `E_ref` only (ADR-0119): copy multiplier min(allocation / E_ref, 1), reviews at the
  window start (or first usable snapshot) and every 14 days; target-position mirroring with netting. No dynamic runs.
- **Copy series:** `research/replay_frozen/` (full stack: square-root impact Y = 1, 1.5x cap, 0.5% participation,
  no scale-up, leader-sweep anchor, conservative alt drift, point-in-time price check, stress fallback and the
  ADR-0122 coverage measure). Per origin: `window=training` (from 27 Jul to the origin; ranking input) and
  `window=test` (the next 14 days; the outcome). The 3 Dec origin has training only.
- **Leader evidence and gates:** `research/leader/origin=<date>/` (grades, the 18 gates including the worst-case
  gate of ADR-0045, profiles, market exposure, `share_not_copyable`).
- **Development result of all gate-passers** (56 test address-windows, frozen, base): +0.47% mean, positive in 3 of 4
  tests, 6.2 bps per side of headroom; least favourable cost point -0.06%; stress -1.40% over 55 measured, 9 fail the
  -10% check. **All A/B addresses do better than gate-passers in base (+0.95%)**: the gates screen risk, not copy
  return, so the random-pick comparisons below are essential.
- **One crash-week outlier:** at 8 Oct, address `0x14e2ad43...` copies +31% base / +33% stress (leader +132% in two
  weeks) on a mean gross of $777: a real result that moves a test's mean. Use robust statistics.

**Scoring scenario.** Run this brief only after `decision/briefs/measured-latency-rerun.md` is done. Rank and score
on the measured-delay scenarios: base 1.2 s, stress 5 s, optimistic 1 s, and the labelled `severe` case (60 s / 300 s),
from the frozen replay it produces. The development figures quoted above are from the earlier 10 s base and will move
slightly; use the new outputs.

## Scope, in this order

1. **Selection-level gates** (computed at each origin from data up to it; thresholds PLACEHOLDER, set on
   development data, each in an ADR before it is evaluated), on top of grade A/B and the 18 Phase 2 gates. From the
   plan: at least 90 snapshot days and 60 usable return days; median equity in the 20k-2M band (`equity_in_band`);
   at least 90% of traded notional copyable (`share_not_copyable` <= 10%); holding time inside the copyable band and
   break-even delay above the base delay (from the training-window copy, never the test window); not maker-heavy or
   high-frequency (already gated); not the weaker member of a confirmed copier or duplicate cluster (copier screen;
   co-movement clusters below).
2. **Ranking statistic** (pre-registered in an ADR before any test outcome of the rule is computed): the follower's
   training-window result, not the leader's. Default from the plan: mean net return per completed follower round
   trip after costs and funding (frozen policy, base scenario), with its lower bound from a block bootstrap that
   resamples calendar-week blocks (2,000 draws, seeded, trades overlapping in time kept together); key = the 20th
   percentile (PLACEHOLDER). Report the daily copy TWR, its drawdown and the training-window stress result next to
   it. An address needs a positive key to be selectable. Flag addresses whose training result depends on one event
   (for example removing their best week turns the key negative); flag, do not silently rank.
3. **Behaviour and co-movement clusters** (plan table): behaviour features without outcome measures (Ward on
   standardised features); co-movement from daily copy-return correlation and position overlap. Rank within behaviour
   clusters; walk down the ranking and add an address only while its correlation and position overlap with those
   already chosen stay below thresholds set on development data.
4. **Basket size and weights.** k comes from the evidence: every address with a positive key that passes the
   diversification check, up to a maximum K (PLACEHOLDER, for example 5). k = 0 is a valid outcome and is reported as
   such. Weights: equal across selected addresses, each a separate copy sleeve. (The shared 100k account with netting
   and common margin is Phase 5, not here.)
5. **Development walk-forward.** At each development origin (8 Oct, 22 Oct, 5 Nov, 19 Nov) apply the rule to data up
   to the origin, then score the selected basket on the following test window: mean of the selected sleeves' copy
   returns (frozen, base; also optimistic and stress with the ADR-0122 coverage rule and stress check). Baselines on
   the same window:
   - matched random-k from the same eligible pool (after all gates; 1,000 seeded draws): does the *ranking* add value?
   - random-k from all A/B addresses (1,000 draws): do the *gates* add value? (They did not in base so far.)
   - equal weight of all eligible addresses, and cash (0).
   Per window: the basket's percentile within the matched random-k distribution and a win when it is above that
   distribution's median. Report medians and trimmed means next to means, and each window with and without
   crash-driven (10-11 Oct) results. Clopper-Pearson on wins out of windows and MinTRL as in the plan's "Decision
   gates", standard library only.
   **Note:** the per-address capture and market-relative tables are produced by the frozen replay (Phase 3, added
   during the alt-floor rerun). Items 5a and 5b below aggregate them for the basket, sleeves and baselines; compute
   here only what is basket-level. Using capture as a ranking input is allowed only if fixed in the selection ADR
   before results, from training windows.
5a. **Market-relative performance.** All copy returns so far are absolute (over cash). For every copy series
   (selected basket, each selected sleeve, the baselines), over each test window and the holdout: the return of
   holding BTC and ETH over the same window; the copy's beta and alpha to BTC and ETH daily returns (Hyperliquid daily
   marks, as in Phase 2's market exposure, with confidence intervals and the number of days); and the basket's return
   over cash and over BTC side by side. A basket that only earns its market exposure has not shown copy skill.
5b. **Copy capture: how much of the leader's result the copy keeps.** Computed from the built leader books (Phase 2)
   and the follower ledgers (frozen replay) over time, for each sleeve, the basket and every test window:
   - **Capture ratio** = follower PnL / benchmark PnL, where the benchmark is the same follower sizing (frozen
     multiplier, cap, no scale-up) filled at the leader's own prices with no delay and no cost (the replay's
     `unattainable` ledgers). This compares like with like: the raw leader return is on the leader's own equity and
     leverage, so it is reported beside the ratio, not divided into it.
   - **Where the gap goes**: decompose benchmark PnL minus follower PnL into delay drift, the leader-sweep anchor,
     half-spread, impact, fees, funding difference, and orders not executed (below minimum size, cap deferrals,
     uncopyable coins, pricing failures), in USDC and as a share of the benchmark.
   - **Over time**: daily cumulative follower PnL against the benchmark and against the leader's own TWR, so a reader
     sees where the copy keeps up and where it falls behind.
   - **Headline: per-address capture**, which answers "after fees, spreads, impact and delay, does the copy reproduce
     the leader's trading?". Show each address's copy PnL beside its benchmark PnL (a scatter and a table), and
     report the median and spread of per-address ratios **separately for windows where the benchmark won and where it
     lost** (on a losing benchmark a ratio near or above 1 means the copy lost as much or more, so the two must not be
     mixed into one median). Then explain the aggregate: total copy PnL / total benchmark PnL is much lower (35% in the
     development base, about 41% against a benchmark charged the leader's own fee rate of about 3.6 bps per side)
     because costs trim each winning window (the copy keeps roughly 80%) but enlarge each losing one, and the net of
     wins and losses is small. Also report capture against that leader-fee benchmark, since the leaders paid fees too.
   - Report medians and the spread across sleeves; a ratio with a benchmark near zero is shown as not meaningful,
     never as a huge number. Include it for the selected basket in the holdout (item 8) and in the cutoff evidence
     (item 9), and in the figures.
5c. **Pre-registered diagnostics** (on development windows; list them, with the features and statistics, in an ADR
   before computing any; they inform the rule but only items 1-4 select). All use data before each origin for the
   predictor and the following test window for the outcome, across all A/B addresses unless stated:
   - **Persistence:** at each origin, rank correlation between the training-window copy key and the next-window copy
     return, and hit rates (share of the top quintile ending above the median). If it is about zero, say plainly that
     ranking on past copy results does not predict, before choosing the rule.
   - **Feature screen:** the same test for a short fixed list (holding time, maker share, orders per day, leverage,
     worst-case drawdown, leader alpha and beta to BTC, copy capture ratio, sweep size, share of notional in
     parameterised coins, completed round trips). With four windows, signals are hypotheses; report all, including
     null results.
   - **Gate audit:** for each Phase 2 and selection gate, next-window copy return and drawdown of passing versus failing
     addresses (gate-passers did worse than all A/B in base: some gates may cut return without cutting risk).
   - **Attribution:** copy PnL by coin group (BTC/ETH/HYPE/SOL vs other), long vs short, holding band, leader order size
     and market regime (up weeks, down weeks, 10-11 Oct).
   - **Capture drivers:** which leader traits go with high copy capture (from the Phase 3 capture tables).
   - **Alpha vs beta:** share of each copy's return explained by BTC and ETH exposure.
   - **Crowding:** how often candidates hold the same coin and direction at the same time; the effective number of
     independent bets among the eligible pool and the selected basket.
   - **Tail dependence:** each candidate's copy result in the 10-11 Oct crash and its worst week, and the share of its
     total from its single best event.
   - **Decay:** for addresses ranked high at one origin, their copy results over the later windows.
5d. **One strategy refinement to test: a coin filter.** Copy a leader only in coins where copy capture is high (for
   example BTC/ETH/HYPE/SOL plus liquid coins above a stated 4h-volume level), treating the rest as uncopyable; define
   it from training-window capture only, fix it in an ADR before results, and count it as one of the item-6 variants.
   (Holding-band filters, a resizing dead band, leader pauses and non-equal weights are out of scope for Phase 4.)
6. **Researcher degrees of freedom.** At most three variants of the rule (for example the bootstrap percentile, K, or
   the holding-band gate) may be compared on the development windows; all are logged in `provenance/trial_log.md`,
   and the choice between them follows a criterion stated before they run (for example most windows above the random-k
   median, then the simpler rule). No variant may be chosen by its holdout result.
7. **Freeze.** Implement the plan's freeze: `provenance/HOLDOUT_FREEZE.txt` with SHA-256 of
   `config/decision_context.yaml`, the other config files, the selection, replay, drift, price and leader source
   files, and the 3 Dec shortlist (the rule applied at the 3 Dec origin); a timestamp; and `frozen: true` in the
   config. Any selection or replay call whose window ends after 2025-12-03 refuses to run unless the current hashes
   match the freeze (test it, including that a moved cutoff or an edited threshold is rejected). The repository has no
   git, so the user sends the freeze hash to the reviewers before the holdout run; say so in the report.

**STOP after item 7.** Report the development walk-forward, the chosen rule, the 3 Dec shortlist with reasons for
every selected and every rejected eligible address, and the freeze hash. Wait for the user to send the hash and say
"open the holdout".

8. **Holdout, once.** Add the holdout path to the replay (it currently refuses any window after 3 Dec by design):
   test window 3 Dec 2025 00:00 to the cutoff, inputs frozen at the 3 Dec vintage (drift cells, spreads, price check,
   bands, E_ref review at 3 Dec). Run the 3 Dec shortlist and the same baselines; report base, optimistic and stress,
   the economic-gate checks (positive base mean; stress drawdown within the -10% ladder step; cost-surface points on
   the selected basket) and Clopper-Pearson over all five windows. Whatever the result, do not retune and do not
   rerun with changed rules; a failure is reported as a failure.
9. **Selection at the cutoff.** Apply the frozen rule once more at the cutoff (2026-01-04 23:59:42.020Z), using all
   data, to name the addresses for the decision memo. This needs Phase 2 evidence and the copy series as of the cutoff
   (training only: there is no data after it). Write `decision/trader_decisions.csv` (every eligible address:
   selected or rejected, the reason, key metrics, evidence IDs: `src_row`, `tid`, `oid`) and
   `decision/target_allocations.csv` (equal sleeves, to be resized by Phase 5). State that a selection at the cutoff
   has no out-of-sample result of its own; its support is the walk-forward and the holdout of the same rule.

## Out of scope

The physical shared-account replay, portfolio limits and allocation sizes (Phase 5); the runbook (Phase 6); the
decision memo (after Phase 5). New cost or execution models. Any order-sending code ("No code path that sends real
orders, now or later, unless explicitly enabled").

## Rules (project spec, verbatim where quoted)

- "Inputs (read-only; never modify)".
- "Point in time: every function that produces values takes an `asof` timestamp and uses only rows with
  timestamp <= asof". Every gate, rank, cluster and weight at an origin uses data up to that origin; test windows
  are outcomes only. Add a seeded-leak test for the selection (a test-window return used in the ranking must change
  the shortlist and be caught).
- "Never invent missing inputs: no imputed prices, funding or quotes. Missing -> flag and exclude, with a reason".
- "Determinism: same inputs give byte-identical outputs" (seeded bootstrap and random-k; total sort orders; two reruns
  match at `POLARS_MAX_THREADS=8`).
- "Traceability: every derived row keeps the source keys (trader, tid, oid, timestamp)".
- The holdout is opened once, after the freeze and the user's go-ahead.
- Every threshold is fixed in an ADR before the outcome it affects is seen, marked PLACEHOLDER; every variant goes
  in the trial log, including the ones that look worse.
- Record decisions as ADRs in `decision/adr/` (numbers 0130-0149; update the index rows for yours).

## Done when

- Items 1-7 done and reported; the user's go-ahead given; items 8-9 done.
- Outputs: `research/selection/origin=<date>/` (candidates with every gate, the key and its bootstrap, clusters, the
  diversification walk, selected and rejected with reasons), `research/selection/baselines.csv`,
  `research/selection/walk_forward.csv`, `research/selection/holdout.csv`, `provenance/HOLDOUT_FREEZE.txt`,
  `decision/trader_decisions.csv`, `decision/target_allocations.csv`, and `decision/phase-4-results.md` with: the
  rule, the development walk-forward against both random-k baselines and equal weight, the holdout result, the
  economic-gate checks, Clopper-Pearson and MinTRL, the market-relative results (return over BTC, beta and alpha)
  and the copy capture table with its gap decomposition, and the cutoff selection with reasons. Outputs also include
  `research/selection/market_relative.csv` and `research/selection/capture.csv` (per sleeve, basket and window, plus
  the daily cumulative series), `research/selection/diagnostics/` (one table per item-5c diagnostic) and a diagnostics
  section in `phase-4-results.md`; tests cover the capture ratio, its decomposition summing to the gap, and the
  near-zero-benchmark rule.
- `uv run ruff check src tests scripts`, `uv run mypy src`, `uv run pytest -q` and `uv run python -m arkstream audit`
  pass; tests for the bootstrap, the clusters and diversification walk, the random-k baselines (seeded), the freeze
  guard and the selection seeded leak; two reruns byte-identical.

---

## Prompt to start the session

> Read `decision/briefs/phase-4-selection.md` in `C:\Projects\quant-task-arkstream` and carry it out: Phase 4 of the
> ArkStream copy pilot, the point-in-time selection rule (selection gates, a lower-bound ranking on the follower's
> training-window copy results, behaviour and co-movement clusters, a diversification walk), its development
> walk-forward against matched random-k, all-A/B random-k and equal-weight baselines, the freeze hash, and then the
> single holdout evaluation and the selection at the cutoff. Before writing code, read the plan's sections "Selection
> and point-in-time validation" and "Decision gates" in
> `ArkStream Hyperliquid Pilot — Revised Research & Deployment Plan (v2).md`, `decision/adr/README.md` with ADRs
> 0009, 0043, 0045, 0119 and 0122, `decision/pre-phase-4-results.md`, `config/decision_context.yaml`, and the outputs
> in `research/leader/` and `research/replay_frozen/`. Use the frozen sizing policy only. **Stop after item 7** (the
> freeze) and report the development results, the 3 Dec shortlist with reasons and the freeze hash; do not open the
> holdout until I say so. Record decisions as ADRs numbered 0130-0149, and do not touch the latency session's files.
