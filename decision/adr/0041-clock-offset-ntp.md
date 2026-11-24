# ADR-0041: Clock offset to NTP measured before and after each run; correction and usability rules

- Status: Accepted; items 3 and 4 amended by ADR-0057 (drift corrected, 20 ms limit on steps only)
- Date: 2026-11-20
- Phase: Phase 3 / Phase 6 (latency measurement, ADR-0038 item 1)

## Context
Delay = local receive time - event time, so any local clock error enters the result in full. The brief asks for
the offset to NTP before and after each run, a correction, and for a run whose offset moves by more than 20 ms to
be reported and not used. In the first smoke run (trial log, 2026-11-20):
- the local clock was about 63 ms behind NTP;
- the best NTP round trips were 61-66 ms (so up to ±33 ms of path asymmetry);
- `time.google.com` timed out on UDP 123;
- wall time minus `time.monotonic_ns()` jumped by up to 16 ms. That is the 15.6 ms tick of `time.monotonic` on
  Windows, not a clock step.

## Decision
1. **Measurement.** SNTP (RFC 4330) from Python, 8 samples to each of `time.windows.com`, `time.google.com`,
   `time.cloudflare.com`, `pool.ntp.org` and `time.apple.com`. Per server, keep the sample with the lowest round
   trip. The run's offset is the lowest-round-trip sample over all servers, and its **uncertainty is half that round
   trip**, the bound on asymmetric-path error. Each measurement also records:
   - the median over servers and their spread, as a check against a bad server;
   - Windows' own `w32tm /stripchart /computer:time.windows.com /samples:5 /dataonly`, as a cross-check.
2. **Correction.** corrected receive = `recv_ns` + offset. The offset is interpolated linearly in wall time between
   the before and after measurements, and held flat outside them (`arkstream.latency.ClockFit`).
3. **Monotonic stamp** = `time.perf_counter_ns()` (QueryPerformanceCounter, sub-microsecond), not
   `time.monotonic_ns()`.
4. **A run is usable only if** all of the following hold. Otherwise it is listed with its reason and left out of `ALL`:
   - both offsets exist;
   - |offset after - offset before| <= 20 ms;
   - the largest jump of (wall - monotonic) between consecutive messages is <= 20 ms. A step would show here;
     a slow slew shows in the offset change instead.
5. The uncertainty (`offset_uncertainty_ms`, the larger of before and after) is reported beside every per-run row.
   It is a bound, not a correction: when several servers agree closely, the real error is likely smaller.

## Consequences
Second smoke run: offset +60.2 / +64.9 ms (change +4.8 ms), uncertainty ±34 ms, step 1.2 ms, so usable. A
`--clock-only` check gave four servers within 7.5 ms of each other, and `w32tm` 2.5 ms from the chosen offset.
The ±33 ms bound is large next to a ~330 ms trades median. A wired connection or a nearer NTP server would
tighten it, and the network description in `run.json` should say which was used. Tests cover the SNTP
arithmetic, kiss-of-death replies, the best-sample choice, `w32tm` parsing, interpolation and the three
usability rules.
