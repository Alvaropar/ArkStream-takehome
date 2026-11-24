# Pre-Phase 4 fixes: results

> **Superseded delays (2026-11-21).** The replay numbers below use the assumed delays (base 10 s, stress 60 s /
> 300 s). The replay was rerun with the measured copy delay (ADR-0058: base 1.2 s, stress 5 s, severe 60 s / 300 s):
> [`measured-latency-results.md`](measured-latency-results.md) has the before/after tables and is the current state.

Brief: [`briefs/pre-phase-4-fixes.md`](briefs/pre-phase-4-fixes.md). Decisions: ADRs
[0044](adr/0044-point-in-time-price-check.md)-[0055](adr/0055-stress-coverage-pricing-failures.md). Items 8-10 (cost
surface, clean-copy reproducibility, final reruns) are below. The user chose frozen `E_ref` (ADR-0052) and asked
for three changes before item 10 (first review at the first usable snapshot, a stress fallback, the manifest
cutoff); they are in the section "Changes before item 10" and item 8 is reported for both variants, as it was before
the choice. After item 10 the user narrowed the stress coverage measure to pricing failures (ADR-0055, decided after
seeing the results) and made frozen the only policy: section 11 is the current state, from `research/replay_frozen/`;
`research/replay_sizing/` and the dynamic figures are the archived record behind ADR-A0116/0052. The holdout test window
(2025-12-03..2026-01-04) was not computed and selection has not started. "Before" numbers come from
`provenance/pre_phase4_before/`, saved before any rerun.

## 1. Price check as of each origin (ADR-0044)

The ADR-0010 rule applied to the compared bars closing by each origin. At the CUTOFF the same bars reproduce the
ADR-0011 list exactly (163 pass, 22 fail, 10 no Binance), which the funding step checks on every run.

| Origin | Pass | Fail | Insufficient | No Binance | Not passing as of origin but passing at CUTOFF | Passing as of origin but not at CUTOFF | Next-window notional moved out / in |
| --- | ---: | ---: | ---: | ---: | --- | --- | ---: |
| 8 Oct | 154 | 24 | 7 | 10 | 14: ZEC, ZORA, 0G, FXS, ENS, CHILLGUY, BIO, BIGTIME, HEMI, BLUR, NIL, SKY (fail); AERO, ICP (insufficient) | 5: ZEREBRO, NOT, TST, DYDX, BOME | 0.98% / 0.08% |
| 22 Oct | 155 | 25 | 5 | 10 | 14: ZORA, 0G, MINA, BIO, ENS, SKY, CHILLGUY, BIGTIME, NIL, BLUR, FXS, MAV; AERO, ICP | 6: ZEREBRO, MERL, BOME, DYDX, NOT, TST | 0.14% / 0.07% |
| 5 Nov | 158 | 22 | 5 | 10 | 10: MINA, ZORA, DOOD, BIGTIME, ENS, NIL, FXS, CHILLGUY; ICP, AERO | 5: MERL, ZEREBRO, BOME, NOT, TST | 0.54% / 0.08% |
| 19 Nov | 159 | 24 | 2 | 10 | 9: ZORA, MINA, NIL, DOOD, STBL, CHILLGUY, BIGTIME, ENS, FXS | 5: MERL, ZEREBRO, TST, BOME, NOT | 0.10% / 0.24% |
| 3 Dec | 164 | 19 | 2 | 10 | 2: CHILLGUY, DOOD | 3: BOME, TST, ZEREBRO | holdout, not counted |

Shares are of all eligible leader notional in the following 14-day window. Coins that only move between `fail` and
`insufficient` (CC, LIT, MET, MON, STABLE) change no copy decision. Leader orders on the coins now excluded in the
next window: 1,282 / 208 / 426 / 147. Per coin: `research/hyperliquid/price_check_by_origin.csv` and
`research/hyperliquid/price_check_changes.csv`. ZEC is the largest single case: it fails the rule as of 8 Oct
(787 leader orders, 0.77% of the next window's notional) and passes only with the later bars.

Consumers now read the list as of their own time: the replay windows, the drift vintages, Phase 2 marks, validation,
funding proxies, snapshot-time book values and the worst-case Binance check, and the M1 frozen-snapshot diagnosis.
In Phase 2 nothing moved: grades, the A/B universe (300 / 327 / 330 / 358 / 354) and the all-gate passer sets
(16 / 12 / 15 / 13 / 11) are identical at all five origins. Follower intents on coins the replay cannot copy
(A/B universe, base, original model, test windows): 1,352 -> 1,855 (8 Oct), 902 -> 944, 536 -> 784, 751 -> 753.

## 2. Return-source materiality (ADR-0045)

| Origin | Book-primary, ADR-0028 (one cent) | Book-primary, ADR-0045 | Back to the snapshot series | Breaching intervals excluded | Gate-passers affected |
| --- | ---: | ---: | ---: | ---: | ---: |
| 8 Oct | 3 | 3 | 0 | 0 | 0 |
| 22 Oct | 16 | 1 | 15 | 28 | 0 |
| 5 Nov | 19 | 1 | 18 | 34 | 0 |
| 19 Nov | 21 | 2 | 19 | 36 | 0 |
| 3 Dec | 19 | 1 | 18 | 32 | 0 |

No gate-passer is book-primary under either rule and none has a breaching interval, so no gate-passer's return
moved. Every address now reports both series (`snapshot_twr_check`, `book_twr_check`, `book_days_check`) and the
breach counts behind the choice (`pnl_breaches`, `pnl_breach_share`, `pnl_breach_max_run`, `return_source_adr0065`).

## 3. Forced fills out of drift, the sweep anchor and the size study (ADR-0046)

Excluded from the drift sample (8 Sep-2 Dec, eligible core perps): 697 of 136,074 leader orders.

| Kind | Four aggTrades coins, 10-11 Oct | Four coins, other days | Other coins, 10-11 Oct | Other coins, other days | Notional |
| --- | ---: | ---: | ---: | ---: | ---: |
| Auto-deleveraging | 156 | 0 | 485 | 7 | $70.5M |
| Settlement | 0 | 0 | 0 | 25 | $0.5M |
| Liquidation | 4 | 1 | 15 | 4 | $0.4M |

Development cells barely move (aggTrades cells by at most 0.03 bps; 127-138 of about 350 approximate `all`-band
cells by a mean of 0.2-0.7 bps). The 10-11 Oct stress cells move a lot, because the crash sample was dominated by
ADL: BTC +35.1 -> +7.3 bps at 300 s and +10.0 -> +2.0 at 10 s; HYPE -44.5 -> -20.1 at 60 s; SOL -36.8 -> -21.4 at
60 s; 66 stress cells fall below the 30-order minimum and lose their estimate.

The leader-size study and the sweep-anchor counts are in sections 5-7 (they come from the replay rerun).

## 4. Notional the replay cannot copy (ADR-0047)

Per address and origin, over its perp fills to the origin: the share in core perps not passing as of the origin
and in HIP-3 (`share_not_copyable`, in `evidence`; no gate).

| Origin | Gate-passers | Median | 90th pct | Max | Passers above 5% | A/B above 5% / above 25% (of the A/B universe) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 8 Oct | 16 | 0.6% | 6.1% | 34.2% | 2 | 68 / 20 (of 300) |
| 22 Oct | 12 | 0.0% | 3.8% | 4.2% | 0 | 69 / 24 (of 327) |
| 5 Nov | 15 | 0.0% | 2.4% | 2.9% | 0 | 60 / 18 (of 330) |
| 19 Nov | 13 | 0.0% | 1.3% | 2.4% | 0 | 70 / 20 (of 358) |
| 3 Dec | 11 | 0.0% | 1.5% | 1.9% | 0 | 60 / 20 (of 354) |

One 8 Oct gate-passer traded 34% of its notional in coins that do not pass as of 8 Oct; its copy series represents
two thirds of its activity. HIP-3 appears only from November (at most 0.7% for one passer at 3 Dec).

## Reruns of `drift` and `leader`: counts against the previous outputs

| Origin | A/B before / after | Grade changes | All-gate passers before / after | Same set | Book-primary before / after |
| --- | ---: | ---: | ---: | --- | ---: |
| 8 Oct | 300 / 300 | 0 | 16 / 16 | yes | 3 / 3 |
| 22 Oct | 327 / 327 | 0 | 12 / 12 | yes | 16 / 1 |
| 5 Nov | 330 / 330 | 0 | 15 / 15 | yes | 19 / 1 |
| 19 Nov | 358 / 358 | 0 | 13 / 13 | yes | 21 / 2 |
| 3 Dec | 354 / 354 | 0 | 11 / 11 | yes | 19 / 1 |

"Before" is the published Phase 2 output with the ADR-0039 worst-case gate. Runtimes: `drift` 2 min 22 s (344/344
aggTrades symbol-days), `leader` 3 min 46 s.

## 3 (replay part). Forced batches off the sweep anchor

Forced batches among triggering legs (base, dynamic full stack, all A/B): test windows 340 / 2 / 2 / 0 (8 Oct
includes the 10-11 Oct crash; 334 are taker batches that ADR-0036 used to re-anchor), training 5 / 319 / 307 /
313 / 289. They are still mirrored as position changes, now at the first-fill anchor. The leader-size study, rerun
without forced fills, still finds no qualifying size term at any origin or horizon
(`research/replay_sizing/leader_size/leader_size_terms.csv`; identical in `research/replay_frozen/leader_size/`).

## 5. Base alt-drift bound (ADR-0048)

Gate-passers, base, test windows: drift on parameterised fills -0.36 / -0.25 / -0.02 / -0.12 bps per side before,
+3.91 / +4.28 / +5.18 / +0.13 after. Parameterised coins carry 42% / 36% / 33% / 28% of filled notional; per address
the median share is 24% / 32% / 16% / 30% and 6 / 3 / 5 / 2 passers exceed 50% (`parameterised_notional_share` in
`research/replay_sizing/sizing_comparison_addresses.csv`). Orders lacking the coin's own 300 s cell are now unpriced
in base (all A/B: 2,360 / 258 / 462 / 299).

## 6. Unmeasured stress (ADR-0049)

Gate-passers, test windows, stress results below 80% priced intents: 14 / 4 / 5 / 2 of 16 / 12 / 15 / 13 (dynamic
full stack). 8 Oct lacks the crash sample; at later origins the cause is mostly `no_drift_cell`: without the forced
fills many thin coins' 10-11 Oct cells fall below 30 voluntary orders. Training-window stress is almost entirely
unmeasured (pre-8 Sep signals have no aggTrades or drift cells).

## 7. Sizing

See [`pre-phase-4-sizing-comparison.md`](pre-phase-4-sizing-comparison.md) (the comparison the choice was made
on). Policy chosen: frozen `E_ref`, plain, target-position mirroring with netting ([ADR-0052](adr/0052-frozen-reference-equity-sizing.md)).

## 8. Cost uncertainty surface (ADR-0050)

Base scenario at 10 s, the four test windows, the 56 gate-passing address-windows; computed for both sizing
variants (the policy is not chosen yet). The centre reproduces the sizing run exactly. `research/replay_sizing/cost_surface.csv`.

| Point (Y, participation, cap) | Dynamic: mean / positive / profit / headroom | Frozen: mean / positive / profit / headroom |
| --- | ---: | ---: |
| centre (1, 0.5%, 1.5x) | +0.55% / 29 / 3,091 / 7.4 bps | +0.47% / 28 / 2,611 / 6.2 bps |
| Y 0.5 | +0.65% / 29 / 3,617 / 8.7 | +0.56% / 28 / 3,141 / 7.5 |
| Y 2 | +0.38% / 29 / 2,105 / 5.0 | +0.32% / 28 / 1,773 / 4.2 |
| participation 0.25% | +0.43% / 29 / 2,388 / 5.8 | +0.34% / 27 / 1,898 / 4.6 |
| participation 1% | +0.57% / 29 / 3,211 / 7.7 | +0.49% / 28 / 2,762 / 6.5 |
| participation none | +0.68% / 29 / 3,820 / 9.1 | +0.60% / 28 / 3,382 / 8.0 |
| cap 1.0x | +0.31% / 27 / 1,714 / 4.5 | +0.17% / 27 / 965 / 2.5 |
| cap 2.0x | +0.39% / 28 / 2,172 / 5.0 | +0.14% / 27 / 806 / 1.8 |
| most favourable (0.5, none, 1.5x) | +0.78% / 29 / 4,391 / 10.4 | +0.71% / 28 / 3,960 / 9.3 |
| **least favourable (lower bound)** | **(2, 0.25%, 1.0x): +0.11% / 27 / 624 / 1.7** | **(2, 0.25%, 2.0x): -0.06% / 27 / -334 / -0.8** |

Profit in USDC on 10,000 per address-window; headroom = profit / filled turnover, the extra cost per filled side
that would absorb it. The 1.5x cap is the best of the three caps under both variants. At the lower bound dynamic is
negative in one test (5 Nov, -0.31%) and frozen in two (8 Oct -0.65%, 5 Nov -0.25%).

## 9. Reproducibility from a clean copy (ADR-0051)

- `src/arkstream_fetch/fetch_klines.py`: monthly 1m kline zips, published checksums, resumable, seeds, manifest;
  tested offline (no download was made in this batch).
- `python -m arkstream refprices --from-zips`: rebuilt the lake from the 1,270 local verified zips and reproduced all
  seven reference price files, the mapping and the window evidence **byte for byte**. `MANIFEST.yaml` differs in one
  line: `cutoff` is `2026-01-04T23:59:59` in the shipped file and `23:59:42.020` in the config since ADR-0021. No bar
  is known between the two instants, so no price row differs; the read-only input was left as it is.
- `scripts/package_submission.py` -> `dist/arkstream_submission.zip` (3,490 files) with `MANIFEST.sha256`;
  two builds give the same bytes. Latency recordings ship only once finished (the latency session was recording
  while this ran).
- `VERIFY.md`: install, tests and audit, public-data fetch, every rebuild, checksum comparison
  (`provenance/PRE_PHASE4_OUTPUT_CHECKSUMS.txt`, 726 files at item 9; 312 after section 11).
- Clean-copy test: the zip extracted into an empty folder passes its own `MANIFEST.sha256` check, installs
  offline from `uv.lock`, ingests, and runs the full test suite with no failure; the seven tests that need
  regenerated data (the kline lake, replay ledgers) skip with the command that rebuilds it.

## Verification

Full `pytest` (185 tests, unit and data), `ruff`, `mypy` and the audit (31/31) pass on the final code. Two
independent runs of every changed command are byte-identical at `POLARS_MAX_THREADS=8`: drift (4 files), the
per-origin price check, Phase 2 (121 files), the size study and, after the user's changes, the sizing replay with its
comparison tables and the cost surface (596 files). `provenance/PRE_PHASE4_OUTPUT_CHECKSUMS.txt` listed all 726. At the
default thread count some Phase 2 float sums differ in the last bits (equal to 1e-9). After section 11 the list holds
the drift, price check and Phase 2 outputs and the frozen replay (`research/replay_frozen/`, 185 files, two runs
byte-identical): 312 files; the 599 archived `research/replay_sizing/` files are in
`provenance/SIZING_ARCHIVE_CHECKSUMS.txt`, verified unchanged.

## Changes before item 10 (the user's choice, 2026-11-21)

**1. First review at the first usable snapshot (ADR-0052).** An address with no usable equity at the window-start
review is now reviewed at its first usable snapshot in the window, then on the 14-day schedule. Base, all A/B,
frozen minus dynamic mean funded return:

| Window | Round 1 (start-of-window review only) | Final | Unsized intents, frozen: round 1 -> final (dynamic) |
| --- | ---: | ---: | ---: |
| training at 8 Oct | -0.38 pp | -0.16 pp | 1,563 -> 365 |
| training at 22 Oct | -0.71 pp | -0.11 pp | 2,441 -> 574 |
| training at 5 Nov | -0.94 pp | -0.18 pp | 3,298 -> 956 |
| training at 19 Nov | -1.01 pp | -0.21 pp | 3,744 -> 1,098 |
| training at 3 Dec | -1.09 pp | -0.16 pp | 4,295 -> 1,147 |
| all training windows | **-0.84 pp** | **-0.16 pp** | 15,341 -> 4,140 (4,165) |

The gap that came from the 27 Jul window start is closed: frozen now leaves fewer intents unsized than dynamic. Test
windows are unchanged (no gate-passer had an unusable window-start review; base stays +0.47%).

**2. Stress fallback (ADR-0053).** Parameterised stress orders without their own crash-sample cell use
max(liquidity-bucket stress estimate, 3 x max(own 300 s base drift, 0), 0); before 10 Oct the four-coin stress proxy
is 3 x max(development proxy, 0). The zero floor was added after seeing the bucket inputs (crash-sample bucket means
of -160 to +27 bps) and before any replay result. Frozen policy, gate-passing test windows:

| Test origin | Below 80% priced, before -> after (ADR-0049 measure) | Measured stress results, after | Mean stress return, after | Below 80% counting only pricing failures |
| --- | ---: | ---: | ---: | ---: |
| 8 Oct | 14 -> 6 of 16 | 10 | -0.58% | 1 (75%, 8 intents) |
| 22 Oct | 4 -> 1 of 12 | 11 | -1.09% | 0 |
| 5 Nov | 5 -> 0 of 15 | 15 | -2.91% | 0 |
| 19 Nov | 2 -> 0 of 13 | 13 | -1.45% | 0 |
| all four | 25 -> 7 of 56 | 49 | -1.64% | 1 |

**The 80% target is not fully met.** The seven windows still below it under ADR-0049's measure fall short mainly for
reasons that are not stress pricing: cap-headroom deferrals of basket resize legs (2,783 of one address's 11,283
intents) and coins the price check excludes at 8 Oct (counted as unpriced by ADR-0049's broad measure). The residual
stress-pricing failures at 8 Oct are 496 intents: 471 on coins that also lack a development 300 s estimate before
8 Oct, and 25 direct-coin orders without an eligible aggTrade; counting only pricing failures, one window
(8 intents) stays below 80%. Neither the coverage measure nor the fallback was changed
after these results. Dynamic for reference: 6 below 80%, 50 measured, mean -0.82%.

**3. Reference price manifest (ADR-0054).** `data/reference/prices/MANIFEST.yaml` regenerated with the current cutoff
(`2026-01-04T23:59:42.020Z`); the seven price files, the mapping and the window evidence were checked byte-identical
before only the manifest was replaced; `provenance/CHECKSUMS.txt` updated (the manifest's line only).

## 10. Final state with the frozen policy

Full stack, frozen `E_ref`, the 56 gate-passing development test address-windows (holdout not computed):

| Test origin | Base | Optimistic | Stress (measured / positive) |
| --- | ---: | ---: | ---: |
| 8 Oct (16) | +1.05% | +2.52% | -0.58% (10 / 5) |
| 22 Oct (12) | +0.91% | +1.15% | -1.09% (11 / 5) |
| 5 Nov (15) | -0.42% | -0.03% | -2.91% (15 / 5) |
| 19 Nov (13) | +0.36% | +0.57% | -1.45% (13 / 5) |
| all four | **+0.47%**, 28 positive, 2,611 USDC, 6.2 bps/side | +1.09%, 29 positive | -1.64% (49 / 20) |

Before the pre-Phase 4 fixes (dynamic, same 56 windows): base +0.77% (30 positive, 9.9 bps), optimistic +1.03%,
stress -1.31% (all 56 counted, 65% of 8 Oct unpriced). Cost surface (frozen, unchanged by the three changes): centre
+0.47%, best corner +0.71%, **lower bound -0.06% (-0.8 bps)** at Y 2, 0.25% participation, 2.0x cap. Training windows
(gate-passers, base, frozen): -1.06%, +6.32%, +5.47%, +7.00%, +7.23% at the five origins. Figures:
`decision/figures/p4_*.png` (`make figures`). Stress under the narrowed coverage measure: section 11.

## 11. Stress coverage counting only pricing failures (ADR-0055)

**Decided after seeing the item 10 results** (amends ADR-0049): only intents the replay could not price or cost
count as unpriced (`no_drift_cell`, `stress_sample_unavailable`, `no_eligible_aggtrade`, `outside_mapping_window`,
`missing_sqrt_inputs`, `missing_impact_volume`, `missing_participation_volume`, `missing_order_budget`,
`missing_cap_mark`, `invalid_scenario_price`); cap-headroom deferrals, price-check exclusions, reduce-only blocks,
minimum-size skips and unusable equity are the strategy's behaviour and count as measured. Any other status stops
the run. Frozen `E_ref` is the only policy (ADR-0052, section 5): `python -m arkstream replay --frozen` reran the
replay into `research/replay_frozen/` without simulating any dynamically sized model. Its orders, daily ledgers,
funding, bands, cost tables, cost surface and size study are byte-identical to the frozen variant of the archived run
(116 files); the address summaries differ only in the coverage fields and in stress results that became measured
(253 test and 272 training stress address-windows of all A/B; none the other way).

**Safeguard 1: both measures side by side.** Frozen, stress, gate-passing test address-windows
(`research/replay_frozen/stress_coverage.csv`):

| Test origin | Gate-passers | ADR-0049: measured / positive / mean | ADR-0055: measured / positive / mean | Unpriced intents, ADR-0049 -> ADR-0055 |
| --- | ---: | ---: | ---: | ---: |
| 8 Oct | 16 | 10 / 5 / -0.58% | 15 / 6 / -0.06% | 3,509 -> 496 of 13,071 |
| 22 Oct | 12 | 11 / 5 / -1.09% | 12 / 5 / -1.15% | 75 -> 10 of 1,142 |
| 5 Nov | 15 | 15 / 5 / -2.91% | 15 / 5 / -2.91% | 104 -> 23 of 1,547 |
| 19 Nov | 13 | 13 / 5 / -1.45% | 13 / 5 / -1.45% | 29 -> 5 of 1,069 |
| all four | 56 | 49 / 20 / **-1.64%** | 55 / 21 / **-1.40%** | 3,717 -> 534 of 16,829 |

Six windows become measured, five at 8 Oct and one at 22 Oct. Their stress returns are +33.3% (the address with
2,783 cap-headroom deferrals), -11.5%, -3.9%, -3.5%, -9.5% and -1.7%, close to the same windows' base returns
(+30.5%, -10.2%, -4.2%, -3.6%, -11.1%, -0.9%). The 8 Oct mean rises mostly because of the one +33% window. The
remaining pricing failures are 471 `stress_sample_unavailable` and 25 `no_eligible_aggtrade` at 8 Oct, and only
`no_eligible_aggtrade` later (10, 23, 5). **ADR-0053's target is still missed by one window:** at 8 Oct one
gate-passer has 2 of its 8 intents without a stress price (75%; base return -0.46%); seven windows were below 80%
under ADR-0049's measure.

**Safeguard 2: the stress check of the economic gate.** A window passes only if its stress result is measured, the
account is not exhausted and the stress maximum drawdown stays within the -10% `reduce_only` step of the drawdown
ladder; an unmeasured window fails and stays in the count:

| Test origin | ADR-0049: pass / fail on loss / fail unmeasured | ADR-0055: pass / fail on loss / fail unmeasured |
| --- | ---: | ---: |
| 8 Oct | 8 / 2 / 6 | 10 / 5 / 1 |
| 22 Oct | 10 / 1 / 1 | 11 / 1 / 0 |
| 5 Nov | 12 / 3 / 0 | 12 / 3 / 0 |
| 19 Nov | 13 / 0 / 0 | 13 / 0 / 0 |
| all four | 43 / 6 / 7 | **46 / 9 / 1** |

The narrower measure does not make the stress check pass: of the six newly measured windows three pass and three
fail on loss (drawdowns of -20.7%, -12.4% and -10.6%). Ten of the 56 gate-passing windows fail it (13 under
ADR-0049). The gate itself is judged on the selected basket in a later phase; no selection was made here.

**Safeguard 3: worst-measured sensitivity.** Each unmeasured stress window takes the worst measured stress return of
its test (the check stays failed):

| Test origin | ADR-0049: worst measured / mean with it / positive | ADR-0055: worst measured / mean with it / positive |
| --- | ---: | ---: |
| 8 Oct | -39.35% / -15.12% / 5 (6 imputed) | -39.35% / -2.51% / 6 (1 imputed) |
| 22 Oct | -9.23% / -1.77% / 5 (1 imputed) | none imputed: -1.15% / 5 |
| 5 Nov, 19 Nov | none imputed | none imputed |
| all four | **-5.82%** / 20 | **-2.08%** / 21 |

The 8 Oct worst measured window (-39.4% stress, -44.2% base) is one leader's own loss copied at full size, so the
imputation is deliberately harsh. Figure: `decision/figures/p4_stress_coverage.png`. Base (+0.47%), optimistic
(+1.09%) and the cost surface (lower bound -0.06%) are unchanged by the measure.

## Does the base case still clear costs once look-ahead is removed?

Yes at the placeholder costs, narrowly, and not across the whole surface. With the point-in-time price check, forced
fills removed, the conservative alt drift and the chosen frozen sizing, the full stack earns +0.47% mean funded base
return over the 56 gate-passing test address-windows, 6.2 bps per filled side of headroom (9.9 before the fixes),
positive in three of four tests (5 Nov -0.42%). At the least favourable cost point the headroom is -0.8 bps: under
frozen sizing the worst corner no longer clears costs. Stress is negative: -1.40% over 55 of 56 results counting
only pricing failures as unpriced (ADR-0055; -1.64% over 49 under ADR-0049's measure, -2.08% with the unmeasured
window at its test's worst), and 10 of the 56 windows fail the -10% stress check.
