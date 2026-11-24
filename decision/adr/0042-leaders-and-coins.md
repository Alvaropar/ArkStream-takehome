# ADR-0042: Leader addresses and coins for the receive-delay runs

- Status: Accepted
- Date: 2026-11-20
- Phase: Phase 3 / Phase 6 (latency measurement, ADR-0038 item 1)

## Context
The brief asks for `userFills` on 5-10 active leaders taken from `data/raw/fills.csv` (most fills in the last 14 days of the
data) and `trades` on BTC, ETH, HYPE, SOL and 3-4 thinner coins. Hyperliquid allows at most 10 distinct users in
user subscriptions. The package ends on 2026-01-04, ten months before the runs. Probing the package's top 10
on 2026-11-20 found 4 whose latest fill was 2026-01-07 to 2026-09-19. In 3.7 and 4 minute smoke runs, `userFills`
delivered no live fill at all. `userFills` is the primary result, so the number of live fills matters.

## Decision
1. **Candidates:** the 30 addresses with the most fills in the last 14 days of `fills.csv` (stdlib count over
   every row; ties broken by address).
2. **Probe** (`--probe-leaders`): subscribe to each candidate's `userFills`, 10 per connection, and read the
   snapshot of its latest fills. Only subscribe messages are sent (ADR-0040).
3. **Active** = latest fill within 7 days of the probe. **Selected** = the 10 active candidates with the most
   snapshot fills in the last 24 h (the snapshot holds at most 30; ties broken by package order). The result is written to
   `data/reference/latency/hyperliquid/leaders.csv` with the probe time, and every run uses that file's selected rows
   (recorded in its `run.json`). Re-probe before a run on a later day.
4. **Coins:** BTC, ETH, HYPE, SOL and **ZEC, PENDLE, AIXBT, TRX**. These four are traded by the package leaders
   in the last 14 days ($0.3-2.8M notional in the package, against $6-112M for the majors) and are core perps.
   HIP-3 names stay out (ADR-0022).

## Consequences
Probe of 2026-11-20 09:20 UTC: 18 of 30 candidates active, and 10 selected, each with 30 fills in the last 24 h.
The measured leaders are therefore the package's still-active ones, not its top 10. The delay a copy engine sees
depends on the venue and the network, not on which address traded, so this changes the sample size, not what is
measured. The 10-user limit caps `userFills` volume; `trades` covers volume and coin dependence. Tested:
14-day ranking, the 10-user cap, the active and selection rules, and that the probe sends only subscribes and close.
