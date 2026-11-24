# ADR-0001: Record decisions as ADRs

- Status: Accepted; numbering amended by ADR-0085 (renumbered once in decision order on 2026-11-23; next free
  number from then on)
- Date: 2026-11-19
- Phase: all

## Context
Decisions were spread over `config/decision_context.yaml` comments, the plan's assumption register,
`provenance/trial_log.md` and session messages. Work is now split across parallel sessions, which need one
place to read what has been decided and why.

## Decision
From 2026-11-19 every project decision is recorded as an ADR in `decision/adr/` (format and rules in
`README.md`). The trial log keeps the trials and numbers; the assumption register keeps the assumptions; an
ADR links to both. Decisions taken earlier on 2026-11-19 are recorded retrospectively as ADRs 0002-0006.
Milestone 1 decisions before that remain in the plan (v2) and the trial log.

## Consequences
Each session writes its ADRs in the number block its brief reserves, and updates the index for its rows. Since
ADR-0085, a new ADR takes the next free number, and parallel sessions reserve consecutive numbers from it.
