# ADR-0105: Steady clock drift is corrected; the 20 ms limit applies to clock steps

- Status: Accepted
- Date: 2026-11-21
- Phase: Phase 3 / Phase 6 (latency measurement, ADR-0044 item 1)
- Amends: ADR-0101 item 4 (usability rule) and item 3 (step check)

**Decided after seeing the three recorded runs** (ADR-0104). Under ADR-0101 none of them was usable. This ADR changes
the rule because of what those runs showed. It is not a threshold chosen in advance.

## Context
In all three 91-minute runs the NTP offset moved by more than ADR-0101's 20 ms: +33.4, +49.9 and +92.0 ms. The drift is
real. At every reading the NTP servers and Windows' `w32tm` agree within about 10 ms. Measured against the
machine's high-resolution counter (QueryPerformanceCounter), true time ran 8.0-12.1 ppm faster, a steady rate.
The wall clock also moved in small steps of about 15 ms, which is how Windows' time service adjusts it.
- Linear correction in wall time between the two NTP readings (ADR-0101 item 2) and an independent correction
  timed on the counter agree within 1.0 ms (run 1) and 4.4 ms (run 2) at p10/p50/p90/p99. In run 3 they
  differ by 6.0 ms: a steady +5 to +6 ms on every percentile of both channels. That points to an uneven
  overnight slew of the wall clock, not a step.
- Run 2's apparent 101 ms "step" was a single message whose two stamps were taken about 95 ms apart (the process
  was paused between them). The next message was back on the line.

## Decision
1. **Steady drift between NTP readings is not a reason to exclude a run.** It is corrected linearly in wall time
   between the readings: before, after, and the readings during the run (item 4). The offset change is still
   reported for every run.
2. **The 20 ms limit applies to clock steps only.** A step is the largest lasting jump of (wall time minus
   high-resolution counter) between consecutive messages, after removing the straight line from the first to the
   last message, taken on a 5-message rolling median so a one- or two-message pause is not a step. A run with a
   step over 20 ms, or without NTP readings before and after, is reported and not used. The three runs: 13.4, 15.6
   and 14.8 ms.
3. **Cross-check, reported for every run** (`qpc_check_ms`): the counter-based correction is a piecewise-linear
   map from counter to true time through the NTP readings. The cross-check is the largest difference from the
   wall-time correction at p10/p50/p90/p99 over both channels. Within 5 ms is the expected agreement. A run above
   5 ms is **kept and labelled** `counter check X ms (> 5)`. It is not excluded, because a uniform 6 ms shift
   is far smaller than both the NTP bound and the run-to-run spread (ADR-0104). Only run 3 is labelled
   (6.0 ms). The 2026-11-21 report had described all three runs as "within 5 ms", which was rounded too loosely.
4. **NTP uncertainty beside every number.** Each per-run row carries that run's bound: half the best NTP round trip,
   the larger of before and after. A pooled row carries the largest bound of the runs it pools. A run whose bound
   exceeds 50 ms is kept and labelled `wide NTP bound`. That is run 3, at +/-83 ms: its NTP replies were slow at
   03:44-05:15 UTC, and its before offset (-26.9 ms) followed a correction of the clock overnight.
5. **Future runs measure the drift** (implemented here, no new runs recorded). The recorder takes an NTP reading every
   5 minutes during the run on a background thread (`--ntp-every-min`, 4 samples per server, no `w32tm`; the
   thread only waits on UDP). Every reading records `perf_ns` beside `local_ns` (the counter at the same moment).
   The correction then follows the measured offset path between readings instead of assuming a straight line.
   Each run reports `ntp_mid_readings` and `drift_residual_ms`, the largest distance of a reading from the
   before-after line. Runs recorded before this change have no readings during the run, and their counter
   anchors are mapped through the first and last message.

## Consequences
All three runs are usable, and run 3 carries both labels. The step check no longer reacts to steady drift or
single-message pauses but still catches a lasting jump (tested). The clock rule is weaker than ADR-0101's for the
three existing runs: a curved drift between the two readings would go undetected. The counter cross-check limits
that to about 6 ms here, and periodic readings remove the assumption for future runs. Tests: drift, pause and step
cases of the step check, piecewise correction through readings during the run, the counter fit with and without
`perf_ns`, labels, the sampler including a failed reading, and `record()` storing `clock.mid`.
