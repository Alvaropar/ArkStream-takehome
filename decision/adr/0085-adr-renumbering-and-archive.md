# ADR-0085: Renumber the ADRs once in decision order and remove the ones no longer in force

- Status: Accepted (the user's request, 2026-11-23)
- Date: 2026-11-23
- Phase: project process
- Amends: ADR-0001 (numbering blocks per session; "never renumbered")

## Context
Parallel sessions took ADR numbers from reserved blocks (0010-0019, 0020-0039, 0060-0079, 0080-0099, 0100-0109,
0110-0129, 0130-0149, 0150-0159, 0160-0169, 0170-0179). The numbers stopped following the order of decisions:
- the 22-23 Nov decisions sat at 0046-0053, between ADRs of 19 Nov;
- the Phase 2 rework sat at 0060-0065;
- Phase 4 v2 sat at 0142-0147 and 0170-0177.

18 of the 102 ADRs no longer carried any decision used by the current study:
- Phase 4 v1 and its two void freezes;
- variants promoted into later ADRs;
- an ADR superseded by the recruiter's answers;
- a one-off action.

The user asked for:
- the latest Phase 2, 3 and 4 ADRs to be the only ones for those phases;
- the outdated ones removed;
- a chronological order, so the review is faster.

## Decision
1. **Renumbering.** The 84 ADRs in force are numbered 0001-0084 in decision order: by date, then by the order of
   work on that date. This ADR is 0085.
2. **Removed.** The other 18 get the ID `ADR-A<old number>`. They were first moved to `decision/adr/archive/`, then
   deleted the same day at the user's request. `RENUMBERING.md` lists them with the reason. 17 are in git commit
   `173f5a8` under their old names; A0051 was never committed. Older documents that mention them keep the
   `ADR-A<old number>` ID as plain text, with no link.
3. **Live parts copied forward first.** Before the move, every part of an archived ADR still in force was copied into
   the ADR that replaces it:

   | ADR in force | Copied from | What |
   | --- | --- | --- |
   | ADR-0037 (no scale-up) | ADR-A0087 | how the multiplier and the leader-batch order budget are applied |
   | ADR-0052 (frozen `E_ref`) | ADR-A0116 | the review rule, reduce-only, the order columns |
   | ADR-0065 (Phase 5) | ADRs A0139, A0141 | the freeze mechanism (`freeze.py`); the recorded hashes are void |
   | ADR-0072 (evidence) | ADR-A0132 | the behaviour clusters used as prior groups |
   | ADR-0073 (tradable universe) | ADR-A0130 | `sel_equity_band` [5k, 2M], `sel_break_even`, `sel_copier` |
   | ADR-0075 (IC rule, evaluation) | ADRs A0133, A0135 | the baseline seed and draws; the gate audit |
   | ADR-0078 (P4-4/P4-5 details) | ADRs A0051, A0131 | the former NAV and trip keys, reported beside the IC |

4. **References.** `scripts/adr_renumber.py` rewrote every reference in every file:
   - single IDs, ranges, lists and markdown links;
   - in a range, archived members are dropped when the range still has members in force;
   - generated outputs, checksum-record headers and the latency session's files were done last, with the user's
     approval. The six sizing-archive summaries changed, so their hash lines in
     `provenance/SIZING_ARCHIVE_CHECKSUMS.txt` were updated, and the record says so;
   - file and folder names that carried an old number were renamed (`research/audit/`, the two before-snapshots in
     `provenance/`), with their references.

   `decision/adr/RENUMBERING.md` maps every old number to its new one. The only old numbers left are four column and
   value names baked into outputs, listed there.
5. **From now on:**
   - a new ADR takes the next free number;
   - parallel sessions reserve consecutive numbers from the next free one;
   - an ADR whose decisions are all replaced is deleted once its live parts are copied forward, and listed in
     `RENUMBERING.md`.

   No further renumbering.

## Consequences
- No rule, threshold, input or result changes. Code changed only in comments and docstrings.
- **Old numbers still in use:** they appear in the conversation history and in four output column names, and are
  looked up in `RENUMBERING.md`. Old numbers 0001-0084 now name different ADRs, so an old number read
  anywhere outside the rewritten materials must be looked up, never assumed.
- **The trial log and the briefs** were rewritten by the same map and say so at the top. The reserved number blocks
  quoted in the briefs are left as they were reserved.
- **Tests:** ruff, mypy, the test suites and the audit run unchanged after the rewrite. No ADR link is broken, and no
  old number is left in the rewritten materials.
