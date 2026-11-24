"""The v2 holdout entry point (P5-8; ADRs 0092, 0093, 0098; pinned in ADR-0099 item 11).

Refused by `freeze.guard` at the window end unless `provenance/HOLDOUT_FREEZE.txt` holds; nothing runs before the
guard. The holdout window is 3 Dec 2025 00:00 -> 4 Jan 2026 00:00 UTC (32 calendar rows), from the 3 Dec origin.

Stage A (`--stage a`), in order:
1. **trees**: the 10k tradable tree and the 2,500 gray tree (both sleeves) for the window through the single-window
   path of `run_sensitivities` with the origin's tradable sets; their shared inputs (the origin's drift cells, bands,
   spreads) copied from the development trees;
2. **marks**: the Hyperliquid daily closes to the window end, as `replay.run` writes them;
3. **trigger series**: the Phase 2 tables at the window end (`leader.compute`), each value used from its own time;
4. **run A**: S*, U* and G* in the four scenarios with the P5-5 code, the origin's risk model; the G* rerun for each
   cutoff hand-off address other than the 3 Dec hand-off (ADR-0092 item 3);
5. **H5 outcomes**: `selection_v2.test_outcomes` on the window;
6. **report**: `holdout_report.report`, unchanged, and the decision entry `decision_A.json` (D1-D5).

Stage B and C (`--stage bc`) refuse to start until `decision_A.json` exists and record its sha256: C's daily drift
table on the window, the cost rebuild and the runs of `cost_runs`.

`--check` runs the same code on the last development window (19 Nov -> 3 Dec, series at 3 Dec) into
`research/holdout_check/` and compares it with the development outputs; it reads nothing at or after 3 Dec 00:00.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl
import polars.testing

from arkstream import phase5_pair as P
from arkstream import portfolio_engine as PE
from arkstream import portfolio_replay as PR

C = pl.col
OUT = "research/holdout"
CHECK_OUT = "research/holdout_check"
GRAY = 2500.0
SHARED = ("spread_estimates.parquet", "drift_cells.parquet", "drift_hold_bands.parquet")


@dataclass(frozen=True)
class Spec:
    origin: date
    start: datetime
    end: datetime
    check: bool

    @property
    def series_asof(self) -> datetime:
        return self.end


def midnight(d: date) -> datetime:
    return datetime.combine(d, datetime.min.time(), UTC)


def holdout_spec(ctx) -> Spec:
    """ADR-0092 item 1: 3 Dec 00:00 -> 4 Jan 00:00, `splits.holdout.end` read as an exclusive midnight."""
    sp = ctx.raw["splits"]["holdout"]
    o = date.fromisoformat(str(sp["start"]))
    return Spec(o, midnight(o), midnight(date.fromisoformat(str(sp["end"]))), False)


def check_spec(ctx) -> Spec:
    from arkstream import drift

    dr = drift.DriftRules.from_config(ctx.raw)
    dev = [o for o in dr.origin_dates if o < dr.holdout_start]
    return Spec(dev[-1], midnight(dev[-1]), midnight(dr.holdout_start), True)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------------------------- 1-3 inputs
def tradable_sets(ctx, origin: date, traders: list[str] | None = None) -> pl.DataFrame:
    """The published ADR-0076 sets of the 10k tree at the origin."""
    pairs = pl.read_parquet(ctx.root / ctx.raw["selection_v2"]["tradable_dir"] / "tradable_pairs.parquet")
    pairs = pairs.filter(C("origin") == origin)
    if traders is not None:
        pairs = pairs.filter(C("trader").is_in(traders))
    return pairs.select("trader", "coin")


def build_tree(ctx, spec: Spec, target: Path, sets: pl.DataFrame, allocation: float | None = None,
               traders: list[str] | None = None) -> Path:
    from arkstream.replay_frozen import MODEL
    from arkstream.replay_sensitivity import run_sensitivities

    allpriced = ctx.root / ctx.raw["selection_v2"]["allpriced_dir"]
    run_sensitivities(ctx, output=target, models=(MODEL,), original=allpriced, tradable={spec.origin: sets},
                      window=(spec.origin, spec.start.date(), spec.end.date()), allocation_usdc=allocation,
                      traders=traders)
    src = ctx.root / ctx.raw["selection_v2"]["tradable_dir"]
    for name in SHARED:
        shutil.copy2(src / name, target / name)
    return target


def window_marks(ctx, spec: Spec) -> pl.DataFrame:
    """The Hyperliquid daily closes to the window end, exactly as `replay.run` writes `valuation_marks`."""
    from arkstream import drift, hlprices
    from arkstream.replay import model_inputs_by_origin
    from arkstream.replay_market import bounded_inputs

    dr = drift.DriftRules.from_config(ctx.raw)
    origins = [midnight(o) for o in dr.origin_dates]
    inputs = bounded_inputs(ctx, spec.end)
    tables = [pl.read_parquet(ctx.root / "research/leader" / f"origin={o.date()}" / "evidence.parquet")
              .select("trader") for o in origins]
    candidates = pl.concat(tables).unique()
    checker = hlprices.PointInTimeCheck.load(ctx)
    checks_by = {o: checker.checks(o) for o in origins}
    per = model_inputs_by_origin(ctx, inputs, spec.end, candidates, checks_by)
    return per[origins[0]][3]


def trigger_tables(ctx, spec: Spec, target: Path) -> Path:
    """The Phase 2 tables at the window end (ADR-0099 item 11), as `leader.run` builds them: the panels shared over
    the configured origins and the window end, then `leader.compute` at the window end, written as `leader.write`
    does. The inputs are bounded at the window end, so nothing at or after it is loaded."""
    from arkstream import leader
    from arkstream.freeze import guard
    from arkstream.replay_market import bounded_inputs

    guard(ctx, spec.series_asof)  # the panels load data to the window end before `leader.compute` runs
    inputs = bounded_inputs(ctx, spec.series_asof)
    os_ = sorted({*leader.origins(ctx), spec.series_asof})
    tabs = leader.compute(ctx, inputs, spec.series_asof, **leader.shared_panels(ctx, inputs, os_),
                          beyond_last_origin=True)
    leader.write(ctx, tabs, spec.series_asof.date(), target)
    return target


# ---------------------------------------------------------------------------------------------- 4 run A
def bars_to(ctx, end: datetime, ex: dict) -> pl.DataFrame:
    from arkstream import hlprices
    from arkstream.replay_cap import impact_bars

    candles, _ = hlprices.load_candles(ctx.path("hyperliquid_dir"), end)
    return impact_bars(candles, end, ex["square_root"]["volatility_bars"])


def window_inputs(spec: Spec, series: Path | None) -> PR.WindowInputs:
    return PR.WindowInputs(spec.origin, "test", spec.start, spec.end, spec.series_asof.date(), series)


def alpha_from(ctx, origin: date, marks: pl.DataFrame):
    """`phase5_pair.alpha_market` with the window's marks (the origin's published factors and betas)."""
    from arkstream.selection_v2_market import coin_returns
    from arkstream.selection_v2_stats import Market

    sv = ctx.root / "research/selection_v2" / f"origin={origin}"
    members = pl.read_parquet(sv / "coins.parquet").filter("tradable")["coin"].to_list()
    return Market(origin, sorted(members), coin_returns(marks), pl.read_parquet(sv / "factors.parquet"),
                  pl.read_parquet(sv / "betas.parquet"), False)


def book_runs(ctx, spec: Spec, win: PR.WindowInputs, trees: dict[float, Path], bars: pl.DataFrame,
              marks: pl.DataFrame, out_tree: Path, plan: list[tuple[str, str, float, list[str], str]]) -> list[dict]:
    """`phase5_pair.Runner.window` on the given trees: each (config, scenario, size, traders, tag) run, written in
    the P5-5 layout so `holdout_report.report` reads it unchanged."""
    costs, ex = PR.costs_by_scenario(ctx)
    over, _, _ = P.variant_overrides(ctx)
    stress = costs["stress"]
    traders_all = sorted({t for _, _, _, tr, _ in plan for t in tr})
    data = PR.WindowData(ctx, win, traders_all, list(dict.fromkeys(trees.values())), bars, costs, ex)
    market = alpha_from(ctx, spec.origin, marks)
    rows = []
    for config, scenario, size, traders, tag in plan:
        alloc = {t: float(size) for t in traders}
        rules = PR.scheme_rules(ctx, config, alloc, stress, **over)
        eng = PE.Engine(rules, costs[scenario], data.market, PR.ms(win.start), PR.ms(win.end),
                        triggers=data.triggers, reviews=PR.review_times(win.start, win.end, rules.review_days))
        sigs = PR.signals_from_orders(PR.tree_orders(trees[size], win.origin, "test", scenario, traders))
        res = eng.run([s for tr in traders for s in sigs.get(tr, [])])
        fr = PR.frames(res)
        daily, fund, ledger = PR.daily_book(fr["fills"], rules.allocations, marks, data.funding, win.start, win.end)
        alpha = P.alpha_of(ledger, fund, marks, market, win.start.date(), win.end.date(), sorted(rules.allocations))
        folder = out_tree / f"origin={win.origin}" / f"config={tag}" / f"scenario={scenario}"
        PR.write_run(folder, {**fr, "daily": daily})
        (folder / "max_stress_book.json").write_text(json.dumps(
            {k: {"stress": v[0], "t": v[1], "book": v[2], "marks": v[3]} for k, v in eng.max_stress_book.items()},
            sort_keys=True) + "\n", encoding="utf-8")
        rows += P.summarize(win, tag, scenario, rules, fr, daily, alpha, eng)
        print(f"{win.origin} {tag} {scenario}: {len(res.fills)} fills", flush=True)
    return rows


def cutoff_reruns(ctx, spec: Spec, cutoff: list[str], handoff: list[str], out: Path
                  ) -> tuple[list[tuple[str, Path]], list[str]]:
    """ADR-0092 item 3: a 2,500 gray tree for each cutoff hand-off address other than the 3 Dec hand-off, from the
    origin's inputs. Returns the replayable (address, tree) pairs and the unmeasured addresses."""
    from arkstream import selection_v2_coins as SC

    allpriced = ctx.root / ctx.raw["selection_v2"]["allpriced_dir"]
    universe = set(pl.read_parquet(allpriced / f"origin={spec.origin}" / "window=training" / "universe.parquet")[
        "trader"].to_list())
    sets = SC.wallet_sets(ctx, spec.origin, allpriced)
    done, unmeasured = [], []
    for addr in sorted(set(cutoff) - set(handoff)):
        s = sets.filter(C("trader") == addr).select("trader", "coin")
        if addr not in universe or s.height == 0:
            unmeasured.append(addr)
            continue
        target = out / "replay_gray_cutoff" / f"trader={addr}"
        done.append((addr, build_tree(ctx, spec, target, s, allocation=GRAY, traders=[addr])))
    return done, unmeasured


# ---------------------------------------------------------------------------------------------- 5-6 outcomes, report
def outcomes(ctx, spec: Spec, tree: Path, marks: pl.DataFrame) -> pl.DataFrame:
    """H5: next-window α per address on the window, as `selection_v2.run` computes `test_outcomes`."""
    from arkstream import selection_v2 as SV
    from arkstream import selection_v2_coins as SC
    from arkstream import selection_v2_stats as ST
    from arkstream.replay_market import bounded_inputs

    o = spec.origin
    allpriced, tradable, _ = SV.trees(ctx)
    crash = [date.fromisoformat(d) for d in ctx.raw["selection"]["crash_dates"]]
    inp = bounded_inputs(ctx, midnight(o))
    first = inp.fills["ts"].min().date()
    uni = SV.universe(tradable, o)
    coins, _ = SC.coin_table(ctx, o, allpriced)
    members = coins.filter("tradable")["coin"].to_list()
    nh = SC.leader_notional_hours(inp.fills, o, first).join(uni.select("trader"), on="trader", how="semi")
    market = ST.market_at(ctx, o, marks, members, extra_coins=nh["coin"].unique().to_list())
    return SV.test_outcomes(ctx, o, spec.end.date(), tree, market, uni["trader"].to_list(), crash)


def decision_entry(ctx, spec: Spec, out: Path, tables: dict, d5: bool | None, unmeasured: list[str],
                   freeze_hash: str | None) -> Path:
    from arkstream import holdout_report as HR

    dec = HR.decide(tables, d5, development=spec.check)
    if unmeasured:  # ADR-0092 item 3: a cutoff address that cannot be replayed has D2b unmeasured (fails)
        dec["D2b"] = False
        dec["decision"] = "NO-GO"
    dec.update(window=f"{spec.start.isoformat()} -> {spec.end.isoformat()}", origin=str(spec.origin),
               d2b_unmeasured_cutoff_addresses=unmeasured, freeze_hash=freeze_hash,
               d5_source="cutoff hand-off given as input (ADR-0099 item 11)" if d5 is not None else
               "not given: unmeasured (ADR-0068)", run="A (frozen cost model; decides, ADR-0098 item 7)",
               written=datetime.now(UTC).isoformat(timespec="seconds"),
               report_sha256={p.name: sha256(p) for p in sorted((out / "window_report").glob("*.csv"))})
    path = out / "decision_A.json"
    path.write_text(json.dumps(dec, indent=2, default=str) + "\n", encoding="utf-8")
    return path


def stage_a(ctx, spec: Spec, out: Path, cutoff: list[str] | None, freeze_hash: str | None,
            resume: bool = False) -> Path:
    from arkstream import holdout_report as HR
    from arkstream import replay_gray

    costs, ex = PR.costs_by_scenario(ctx)
    sleeves = list(replay_gray.sleeves(ctx))
    handoff = sorted(pl.read_parquet(ctx.root / "research/selection_v2" / f"origin={spec.origin}" /
                                     "eligible.parquet")["trader"].to_list()) if not spec.check else sorted(
        pl.read_parquet(ctx.root / "research/selection_v2/origin=2025-12-03/eligible.parquet")["trader"].to_list())
    rel = Path(f"origin={spec.origin}") / "window=test"
    t10, tg = out / "replay_tradable", out / "replay_gray" / f"sleeve={int(GRAY)}"
    if not (resume and (t10 / rel).is_dir()):
        build_tree(ctx, spec, t10, tradable_sets(ctx, spec.origin))
    if not (resume and (tg / rel).is_dir()):
        build_tree(ctx, spec, tg, tradable_sets(ctx, spec.origin, sleeves), allocation=GRAY, traders=sleeves)
    if resume and (out / "valuation_marks.parquet").is_file():
        marks = pl.read_parquet(out / "valuation_marks.parquet")
    else:
        marks = window_marks(ctx, spec)
        marks.write_parquet(out / "valuation_marks.parquet", compression="zstd", statistics=True)
    # the tree's own marks reach its window end, as the development trees' do (`selection_v2` reads them)
    marks.write_parquet(t10 / "valuation_marks.parquet", compression="zstd", statistics=True)
    series = out / "leader"
    if not (resume and (series / f"origin={spec.series_asof.date()}" / "daily_twr.parquet").is_file()):
        trigger_tables(ctx, spec, series)
    reruns, unmeasured = cutoff_reruns(ctx, spec, cutoff or [], handoff, out)
    plan = [(c, sc, 10000.0, sleeves, c) for sc in PR.SCENARIOS for c in ("S", "U")]
    plan += [("G", sc, GRAY, handoff, f"G{int(GRAY)}") for sc in PR.SCENARIOS]
    trees = {10000.0: t10, GRAY: tg}
    tree_a = out / "portfolio" / "run=A"
    bars = bars_to(ctx, spec.end, ex)
    win = window_inputs(spec, series)
    rows = book_runs(ctx, spec, win, trees, bars, marks, tree_a, plan)
    for addr, tree in reruns:
        rows += book_runs(ctx, spec, win, {GRAY: tree}, bars, marks, tree_a,
                          [("G", sc, GRAY, [addr], f"G{int(GRAY)}_{addr[:6]}") for sc in PR.SCENARIOS])
    pl.DataFrame(rows, infer_schema_length=None).write_csv(tree_a / "pair_summary.csv")
    oc = outcomes(ctx, spec, t10, marks)
    oc.write_parquet(out / "test_outcomes.parquet", compression="zstd", statistics=True)
    from arkstream import drift

    dr = drift.DriftRules.from_config(ctx.raw)
    dev = pl.concat([pl.read_parquet(ctx.root / "research/portfolio_replay" / f"origin={o}" / "config=S" /
                                     "scenario=base" / "fills.parquet")
                     for o in dr.origin_dates if o < dr.holdout_start], how="diagonal_relaxed")
    d5 = None if cutoff is None else bool(cutoff)
    tables = HR.report(ctx, spec.origin, tree_a, oc, dev, out / "window_report", development=spec.check,
                       handoff_nonempty=d5)
    return decision_entry(ctx, spec, out, tables, d5, unmeasured, freeze_hash)


# ---------------------------------------------------------------------------------------------- B and C
def stage_bc(ctx, spec: Spec, out: Path) -> Path:
    """Runs B and C on the window (ADR-0098 item 7: only after A's decision entry is written)."""
    from arkstream import cost_runs as CRN
    from arkstream import cost_updated as CU
    from arkstream import replay_gray
    from arkstream.replay_market import bounded_inputs

    entry = out / "decision_A.json"
    if not entry.is_file():
        raise RuntimeError(f"{entry} missing: run A and its decision entry come before B and C (ADR-0098 item 7)")
    h = sha256(entry)
    costs, ex = PR.costs_by_scenario(ctx)
    sleeves = list(replay_gray.sleeves(ctx))
    handoff = sorted(pl.read_parquet(ctx.root / "research/selection_v2/origin=2025-12-03/eligible.parquet")[
        "trader"].to_list())
    o2t = pl.read_csv(ctx.root / CRN.DEFAULT_OUT / "o2_bounds.csv")  # frozen with the development outputs
    o2 = {b: float(v) for b, v in o2t.select("liq_bucket", "p99_bps").rows()}
    days = [spec.start.date() + timedelta(days=k) for k in range((spec.end - spec.start).days)]
    inputs = bounded_inputs(ctx, spec.end)
    fills = inputs.fills
    cells, bands = CU.daily_cells(ctx, inputs, days, spec.end)
    del inputs
    target = out / "cost_runs"
    target.mkdir(parents=True, exist_ok=True)
    cells.write_parquet(target / "drift_daily_cells.parquet", compression="zstd", statistics=True)
    bands.write_parquet(target / "drift_daily_bands.parquet", compression="zstd", statistics=True)
    trees = {10000.0: out / "replay_tradable", GRAY: out / "replay_gray" / f"sleeve={int(GRAY)}"}
    bars = bars_to(ctx, spec.end, ex)
    win = window_inputs(spec, out / "leader")
    data = PR.WindowData(ctx, win, sleeves, list(trees.values()), bars, costs, ex)
    setup = CRN.prepare(ctx, win, data, fills, bars, costs, ex, o2, cells, bands, spec.end)
    marks = pl.read_parquet(out / "valuation_marks.parquet")
    over, _, _ = P.variant_overrides(ctx)
    rows = CRN.window_runs(ctx, win, data, setup, trees, sleeves, handoff, GRAY, costs, over, marks,
                           alpha_from(ctx, spec.origin, marks), target, extra={"decision_A_sha256": h})
    pl.DataFrame(rows, infer_schema_length=None).write_csv(target / "cost_summary.csv")
    for k, t in setup.tables.items():
        t.write_csv(target / f"{k}.csv")
    rec = CRN.records(target, [spec.origin])
    pl.concat([CRN.accuracy(rec.filter(C("run") == "B"), "frozen"),
               CRN.accuracy(rec.filter(C("run") == "C"), "frozen"),
               CRN.accuracy(rec.filter(C("run") == "C"), "updated")]).write_csv(target / "accuracy.csv")
    CRN.fallback_rates(rec).write_csv(target / "fallback_rates.csv")
    return target


# ---------------------------------------------------------------------------------------------- entry
def run(ctx, out: Path | None = None, check: bool = False, stage: str = "all",
        cutoff_handoff: list[str] | None = None, resume: bool = False) -> Path:
    """`resume` (check mode only) reuses the trees, marks and trigger series an earlier check run finished."""
    from arkstream.freeze import guard

    if resume and not check:
        raise ValueError("resume is for check mode only: the holdout runs once, from the start")
    spec = check_spec(ctx) if check else holdout_spec(ctx)
    freeze_hash = guard(ctx, spec.end)  # the holdout: refused unless the freeze holds (ADR-0099 item 11)
    if not check and freeze_hash is None:
        raise RuntimeError("the holdout window must end after the holdout start")
    out = Path(out) if out else ctx.root / (CHECK_OUT if check else OUT)
    out.mkdir(parents=True, exist_ok=True)
    if stage in ("a", "all"):
        stage_a(ctx, spec, out, cutoff_handoff, freeze_hash, resume)
    if stage in ("bc", "all"):
        stage_bc(ctx, spec, out)
    if check:
        compare(ctx, spec, out)
    return out


# ---------------------------------------------------------------------------------------------- check mode
def same_files(a: Path, b: Path, pattern: str = "*.parquet") -> tuple[int, list[str]]:
    files = sorted(p for p in a.rglob(pattern) if p.is_file())
    diff = [str(p.relative_to(a)) for p in files if not (b / p.relative_to(a)).is_file()
            or (b / p.relative_to(a)).read_bytes() != p.read_bytes()]
    return len(files), diff


def compare(ctx, spec: Spec, out: Path) -> Path:
    """Check mode: the entry point's outputs on the last development window against the development outputs."""
    o = spec.origin
    rel = Path(f"origin={o}") / "window=test"
    lines = ["# v2 holdout entry point, check mode (ADR-0099 item 11)", "",
             f"Window {spec.start:%Y-%m-%d} -> {spec.end:%Y-%m-%d} (the last development window), trigger series at "
             f"{spec.series_asof:%Y-%m-%d}. Nothing at or after the holdout start is read.", "",
             "| Output | Compared with | Files | Differ |", "| --- | --- | ---: | --- |"]
    bad = 0
    pairs = [
        ("10k tradable tree", out / "replay_tradable" / rel,
         ctx.root / ctx.raw["selection_v2"]["tradable_dir"] / rel),
        ("2,500 gray tree", out / "replay_gray" / "sleeve=2500" / rel,
         ctx.root / "research/replay_gray/sleeve=2500" / rel),
        ("run A books", out / "portfolio" / "run=A" / f"origin={o}",
         ctx.root / "research/portfolio_replay" / f"origin={o}"),
    ]
    if (out / "cost_runs" / f"origin={o}").is_dir():
        pairs.append(("runs B and C", out / "cost_runs" / f"origin={o}",
                      ctx.root / "research/cost_runs" / f"origin={o}"))
    pairs.append(("window report H1-H6", out / "window_report", ctx.root / "research/window_report" / f"origin={o}"))
    for name, a, b in pairs:
        n, diff = same_files(a, b, "*.csv" if name.startswith("window report") else "*.parquet")
        bad += len(diff) + (n == 0)
        lines.append(f"| {name} | `{b.relative_to(ctx.root).as_posix()}` | {n} | {'; '.join(diff[:4]) or 'none'} |")
    # the trigger series: the two tables the engine reads byte for byte, every other Phase 2 table to 1e-12
    # (the entry point's inputs are bounded at the window end, so float sums may differ in the last bits)
    sa = out / "leader" / f"origin={spec.series_asof.date()}"
    sb = ctx.root / "research/leader" / f"origin={spec.series_asof.date()}"
    n, diff = same_files(sa, sb)
    engine_tables = ("daily_twr.parquet", "book_hourly.parquet")
    exact = [d for d in diff if d in engine_tables]
    loose = []
    for d in diff:
        if d in engine_tables:
            continue
        x, y = pl.read_parquet(sa / d), pl.read_parquet(sb / d)
        key = [c for c in ("trader", "coin", "symbol", "t", "ts", "hour_end", "day") if c in x.columns]
        try:
            pl.testing.assert_frame_equal(x.sort(key) if key else x, y.sort(key) if key else y, check_exact=False,
                                          rel_tol=1e-12, abs_tol=1e-12)
        except AssertionError:
            loose.append(d)
    bad += len(exact) + len(loose) + (n == 0)
    lines.append(f"| trigger series (`daily_twr`, `book_hourly`, read by the engine) | "
                 f"`{sb.relative_to(ctx.root).as_posix()}` | 2 | {'; '.join(exact) or 'none'} |")
    lines.append(f"| other Phase 2 tables at the series date, to 1e-12 relative | same | {n - 2} | "
                 f"{'; '.join(loose) or 'none'} (byte-identical: {n - len(diff)} of {n}) |")
    checks = []
    m = pl.read_parquet(out / "valuation_marks.parquet")
    ref = pl.read_parquet(ctx.root / ctx.raw["selection_v2"]["tradable_dir"] / "valuation_marks.parquet")
    checks.append(("valuation marks", m.equals(ref)))
    oc = pl.read_parquet(out / "test_outcomes.parquet")
    st = pl.read_parquet(ctx.root / "research/selection_v2" / f"origin={o}" / "test_outcomes.parquet").drop("origin")
    checks.append(("H5 outcomes", oc.sort("trader").equals(st.sort("trader"))))
    for name, ok in checks:
        bad += 0 if ok else 1
        lines.append(f"| {name} | development output | 1 | {'none' if ok else 'differs'} |")
    lines += ["", f"**Result: {'PASS' if bad == 0 else 'FAIL'}**"]
    path = out / "check.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(lines))
    return path
