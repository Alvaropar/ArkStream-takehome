# ADR-0027: Evidence minimum = 20 completed round trips (PLACEHOLDER)

- Status: Accepted (PLACEHOLDER; to be set on development data)
- Date: 2026-11-19
- Phase: Phase 2

## Context
The plan sets 20-30 completed round trips on development data. Median usable closed trips per A/B address is
9 at 8 Oct and grows with the history.

## Decision
`leader.gates.min_round_trips = 20`: completed, uncensored round trips by the origin. Open trades are valued
and reported but do not count toward the minimum.

## Consequences
Passing: 114 / 152 / 167 / 181 / 178 addresses at the five origins. Raising it to 30 is a Phase 4 decision.
