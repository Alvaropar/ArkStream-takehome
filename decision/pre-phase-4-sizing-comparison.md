# Frozen reference equity versus the dynamic denominator (item 7, ADR-A0116)

> **Archived record (2026-11-21).** Frozen `E_ref` is the only sizing policy from here (ADR-0052, section 5): the
> dynamic denominator adds an implicit mean-reversion overlay (it enlarges the copy as the leader's equity falls and
> shrinks it as it rises), which is why it was rejected. No further dynamic runs or comparisons are made; this page
> and `research/replay_sizing/` stay as they were when the choice was made. Current results:
> [`pre-phase-4-results.md`](pre-phase-4-results.md#11-stress-coverage-counting-only-pricing-failures-adr-0122).

**Decision (2026-11-21): the user chose frozen `E_ref`** ([ADR-0052](adr/0052-frozen-reference-equity-sizing.md)),
with the first review moved to the first usable snapshot when the window-start review has none. The tables below are
the comparison the choice was made on (round 1). Base and optimistic results and the cost surface are unchanged in
the final runs; stress figures here predate the ADR-0053 fallback; the training-window gap fell from -0.84 to
-0.16 pp. Final numbers: [`pre-phase-4-results.md`](pre-phase-4-results.md#10-final-state-with-the-frozen-policy).

**Recommendation: adopt the frozen `E_ref` (the plan's policy).** On the 56 gate-passing development test
address-windows the two variants are close: frozen earns +0.47% mean funded base return against +0.55% for dynamic
(28 vs 29 positive; 6.2 vs 7.4 bps per filled side of headroom), with lower gross and a much lower worst leverage
(1.58x vs 2.72x of follower equity). The return gap is small and comes from a few leaders; the dynamic rule's
advantage there is that it enlarges the copy of a leader whose equity falls, which is the behaviour the plan rules
out. Both variants clear base costs after the look-ahead fixes; stress stays negative and is half unmeasured.

## What was compared

Same full stack, nine windows (five training from 27 Jul 2025, four 14-day tests; holdout never computed):
square-root impact (Y = 1), 1.5x cap, 0.5% participation, no scale-up with the leader-batch budget, sweep anchor,
and the item 1-6 fixes. Only the sizing equity differs: **dynamic** = latest usable snapshot at each decision;
**frozen** = latest usable snapshot at each review (window start, then every 14 days), fixed until the next one;
unusable at a review means reduce-only (no orders if no earlier reference in the window). Data:
`research/replay_sizing/sizing_comparison_pooled.csv`, `sizing_comparison_addresses.csv` (one row per address,
window and scenario, both variants, differences and the leader's equity path).

## Pooled, four test windows, gate-passers (56 address-windows)

| Scenario | Variant | Positive / measured | Mean return | PnL (USDC) | Turnover | Headroom bps/side | Mean gross | Max leverage | Mean multiplier |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| base | dynamic | 29 / 56 | +0.55% | 3,091 | 4.17M | 7.4 | 2,804 | 2.72 | 0.707 |
| base | frozen | 28 / 56 | +0.47% | 2,611 | 4.20M | 6.2 | 2,652 | 1.58 | 0.711 |
| optimistic | dynamic | 29 / 56 | +1.16% | 6,494 | 4.19M | 15.5 | 2,842 | 2.56 | 0.707 |
| optimistic | frozen | 29 / 56 | +1.09% | 6,105 | 4.23M | 14.4 | 2,691 | 1.57 | 0.711 |
| stress | dynamic | 13 / 31 (25 unmeasured) | -1.90% | -5,887 | 3.31M | -17.8 | 2,387 | 2.49 | 0.707 |
| stress | frozen | 13 / 31 (25 unmeasured) | -1.90% | -5,886 | 3.28M | -17.9 | 2,218 | 1.63 | 0.711 |

Base per test (dynamic / frozen): 8 Oct +1.07% / +1.05%; 22 Oct +0.90% / +0.91%; 5 Nov -0.25% / -0.42%;
19 Nov +0.52% / +0.36%. Mean max drawdown -4.2% / -4.1%; drawdowns beyond 10%: 6 / 7. All A/B (1,315
address-windows): base +0.97% / +0.95%, stress -0.64% / -0.71%, stress worst leverage 8.65 / 3.21.

Orders and skips (base, gate-passers): frozen sends more basket resize legs because a fixed multiplier lets the
1.5x cap bind more often: cap-headroom deferrals 3,029 vs 1,055 (counted in the broad "unpriced" figure), filled
resize legs 1,045 vs 1,363; triggering-leg fills 4,328 vs 4,310. No gate-passer had an unusable review in a test
window (one A/B address did, at 8 Oct); reduce-only never fired in a test window.

## Where they differ (base, test windows, all A/B)

| Leader equity in the window | Address-windows (passers) | Mean dynamic | Mean frozen | Frozen better / worse | Multiplier dyn / frz |
| --- | ---: | ---: | ---: | ---: | ---: |
| fell 25% or more | 42 (2) | -9.53% | -9.25% | 20 / 15 | 0.39 / 0.33 |
| rose 25% or more | 71 (3) | +9.65% | +9.95% | 31 / 31 | 0.25 / 0.32 |
| a single flow of 25%+ of equity | 124 (1) | +4.59% | +4.44% | 33 / 49 | 0.32 / 0.32 |
| small leader (`E_ref` < 10,000: copied 1:1) | 450 (32) | +0.75% | +0.72% | 11 / 26 | 0.99 / 1.00 |
| other | 398 (16) | +0.23% | +0.16% | 133 / 187 | 0.34 / 0.34 |
| inactive in the window | 230 (2) | 0 | 0 | 0 / 1 | - |

Largest single cases: a leader whose equity fell 58% (dynamic -48.9%, frozen -36.5%: dynamic raised the
multiplier from 0.56 to 0.91 as they lost); a leader whose equity rose 54% (dynamic +12.3%, frozen +40.8%: dynamic
cut the copy of a winner); a gate-passer whose equity fell 27% with no flows (dynamic +0.1%, frozen -3.6%: here the
larger copy into the drawdown happened to recover). In training windows frozen is 0.84 pp lower on average, mostly
because 304 addresses have no snapshot at the 27 Jul review and stay flat until 10 Aug.

## Cost surface for both variants (item 8, ADR-0050)

Frozen trails dynamic at every point of the surface, by 0.06-0.24 pp of mean return (0.8-3.2 bps of headroom per
filled side; the widest gap is at the 2.0x cap). Its lower bound
is -0.06% (-0.8 bps; Y 2, 0.25% participation, 2.0x cap) against +0.11% (+1.7 bps; Y 2, 0.25%, 1.0x) for
dynamic, so under the least favourable costs the frozen copy of the 56 gate-passer windows no longer clears costs.
The gap is small against the spread of 56 address-windows and comes from the same few leaders as above. Details in
[`pre-phase-4-results.md`](pre-phase-4-results.md#8-cost-uncertainty-surface-adr-0117).

## Before versus after the fixes (dynamic full stack, same 56 gate-passer windows)

Base +0.77% (30 positive, 9.9 bps headroom) -> +0.55% (29, 7.4 bps); optimistic +1.03% -> +1.16%; stress -1.31%
(all measured) -> -1.90% over 31 measured (25 unmeasured). The base case still clears costs with the look-ahead
removed and the conservative drift bound, with less headroom; it is negative in one of four tests (5 Nov).
