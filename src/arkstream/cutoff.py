"""The cutoff selection (ADR-0094 item 3) and the cutoff deliverables (item 4); pinned in ADR-0100.

The frozen Phase 4 v2 pipeline at the cutoff origin, 2026-01-04 00:00 UTC (the last midnight at or before the cutoff,
the last origin the frozen replay admits), on inputs bounded at it, into `research/cutoff/`:

1. `drift/`: `drift.estimate` at the configured origins and the cutoff origin (the code of `make drift`);
2. `leader/origin=2026-01-04/`: the Phase 2 tables (`leader.compute`, panels shared over the six origins); the
   development origins' `evidence` and `daily_twr` copied from `research/leader` (the prepare step reads them);
3. `replay_allpriced/`: `replay.run` prepare only, then the cutoff training window (`run_sensitivities(training=)`)
   and its capture;
4. `replay_tradable/`: the cutoff tradable sets, the training window on them, the shared inputs, capture;
5. `selection_v2/origin=2026-01-04/`: `selection_v2.run(only=[cutoff origin])`; `eligible.parquet` is the cutoff
   hand-off, summarised in `cutoff_handoff.json` (D5; replayable from the 3 Dec inputs or not).

`deliverables` writes `trader_decisions.csv` and `target_allocations.csv` (P5-9) from run A's decision entry.

Refused by `freeze.guard` until the freeze holds, and until run A's outputs exist (the P5-8 order, ADR-0100 item 5).
`--check` runs the same code at the 3 Dec origin with the real configuration into `research/cutoff_check/` and
compares it with the development outputs; it reads nothing at or after 3 Dec 00:00.
"""

from __future__ import annotations

import copy
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl
import polars.testing

C = pl.col
OUT = "research/cutoff"
CHECK_OUT = "research/cutoff_check"
RUN_A = "research/holdout/run_A.json"
S3_ORDER = ("sel_equity_band", "sel_break_even", "sel_tradable_share", "sel_direction", "sel_copier")
CATEGORY_ORDER = {"E2": 0, "E1": 1}
LIVE_SLEEVE_USDC = 2500.0
LIVE_MAX_USDC = 5000.0


def midnight(d: date) -> datetime:
    return datetime.combine(d, datetime.min.time(), UTC)


@dataclass(frozen=True)
class Spec:
    origin: date
    check: bool


def cutoff_origin(ctx) -> date:
    """ADR-0100 item 1: the last UTC midnight at or before the cutoff."""
    return ctx.cutoff.astimezone(UTC).date()


def cutoff_context(ctx, origin: date, out: Path):
    """ADR-0100 item 2: the configured origins plus the cutoff origin, the estimation window to the day before it,
    the replay boundary at it; the freeze guard keeps the real holdout start; the Phase 2, drift and tree folders
    point to `out`."""
    raw = copy.deepcopy(ctx.raw)
    raw["drift"]["origins"] = [*[str(o) for o in raw["drift"]["origins"]], origin.isoformat()]
    raw["drift"]["estimate_window"] = {**raw["drift"]["estimate_window"],
                                       "end": (origin - timedelta(days=1)).isoformat()}
    raw["freeze_holdout_start"] = str(ctx.raw["splits"]["holdout"]["start"])
    raw["splits"] = {**raw["splits"], "holdout": {"start": origin.isoformat(), "end": origin.isoformat()}}
    rel = out.relative_to(ctx.root).as_posix()
    raw["research_dirs"] = {"leader": f"{rel}/leader", "drift": f"{rel}/drift"}
    raw["selection_v2"] = {**raw["selection_v2"], "allpriced_dir": f"{rel}/replay_allpriced",
                           "tradable_dir": f"{rel}/replay_tradable", "out_dir": f"{rel}/selection_v2"}
    return type(ctx)(raw=raw, root=ctx.root)


def check_context(ctx, out: Path):
    """Check mode: the real configuration; the trees and the selection go to `out`; the published drift and Phase 2
    tables are the inputs, as the development trees were built."""
    raw = copy.deepcopy(ctx.raw)
    rel = out.relative_to(ctx.root).as_posix()
    raw["selection_v2"] = {**raw["selection_v2"], "allpriced_dir": f"{rel}/replay_allpriced",
                           "tradable_dir": f"{rel}/replay_tradable", "out_dir": f"{rel}/selection_v2"}
    return type(ctx)(raw=raw, root=ctx.root)


# ---------------------------------------------------------------------------------------------- 1-2 builders
def drift_tables(ctx_o, origin: date, target: Path) -> Path:
    """`make drift` (cli.cmd_drift) at the context's origins, on inputs bounded at `origin`."""
    from arkstream import drift
    from arkstream.prices import scan_reference
    from arkstream.replay_market import bounded_inputs

    rules = drift.DriftRules.from_config(ctx_o.raw)
    src = drift.AggTradesSource(ctx_o.path("aggtrades_dir"), rules)
    cov = drift.coverage_report(src, rules)
    complete = cov.filter(~C("available")).height == 0
    rp = ctx_o.raw["reference_prices"]
    res = drift.estimate(bounded_inputs(ctx_o, midnight(origin)).fills,
                         scan_reference(ctx_o.path("reference_prices_dir")), src, rules, rp["max_age_s"],
                         rp["fallback_print_window_s"])
    target.mkdir(parents=True, exist_ok=True)
    tag = pl.lit("complete" if complete else "PRELIMINARY: aggTrades days missing")
    for name in ("development", "stress"):
        res[name].with_columns(aggtrades_coverage=tag, aggtrades_source=pl.lit(src.label)).write_csv(
            target / f"drift_{name}.csv")
    cov.write_csv(target / "aggtrades_coverage.csv")
    res["bands"].write_csv(target / "drift_hold_bands.csv")
    return target


def phase2_tables(ctx_o, origin: date, target: Path) -> Path:
    """The Phase 2 tables at `origin` as `leader.run` builds them (panels shared over the context's origins)."""
    from arkstream import leader
    from arkstream.replay_market import bounded_inputs

    inputs = bounded_inputs(ctx_o, midnight(origin))
    tabs = leader.compute(ctx_o, inputs, midnight(origin), **leader.shared_panels(ctx_o, inputs,
                                                                                   leader.origins(ctx_o)))
    leader.write(ctx_o, tabs, origin, target)
    return target


def copy_phase2_inputs(ctx, target: Path, origins: list[date]) -> None:
    """The development origins' tables the prepare step reads (`evidence`, `daily_twr`), copied unchanged."""
    for o in origins:
        d = target / f"origin={o}"
        d.mkdir(parents=True, exist_ok=True)
        for name in ("evidence.parquet", "daily_twr.parquet"):
            shutil.copy2(ctx.root / "research/leader" / f"origin={o}" / name, d / name)


# ---------------------------------------------------------------------------------------------- 3-5 trees, selection
def prepare(ctx_o, tree: Path) -> Path:
    """`replay.run` prepare only: the shared inputs and every window's universe and leader series."""
    from arkstream.replay import run as replay_run

    replay_run(ctx_o, output=tree, simulate=False)
    return tree


def allpriced_tree(ctx_o, origin: date, tree: Path) -> Path:
    from arkstream import replay_capture
    from arkstream.replay_frozen import MODEL
    from arkstream.replay_sensitivity import run_sensitivities

    run_sensitivities(ctx_o, output=tree, models=(MODEL,), original=tree, training=origin)
    replay_capture.run(ctx_o, tree)  # capture for the simulated window only
    return tree


def tradable_tree(ctx_o, origin: date, allpriced: Path, tree: Path) -> Path:
    from arkstream import replay_capture
    from arkstream import selection_v2_coins as SC
    from arkstream.replay_frozen import MODEL
    from arkstream.replay_sensitivity import run_sensitivities
    from arkstream.replay_tradable import copy_shared, tradable_pairs

    tree.mkdir(parents=True, exist_ok=True)
    sets = {origin: SC.wallet_sets(ctx_o, origin, allpriced)}
    tradable_pairs(sets).write_parquet(tree / "tradable_pairs.parquet")
    run_sensitivities(ctx_o, output=tree, models=(MODEL,), original=allpriced, tradable=sets, training=origin)
    copy_shared(allpriced, tree, [Path(f"origin={origin}") / "window=training"])
    replay_capture.run(ctx_o, tree)
    return tree


def select(ctx_o, origin: date, out: Path) -> Path:
    from arkstream import selection_v2

    selection_v2.run(ctx_o, out=out, only=[origin])
    return out


def handoff_summary(ctx, origin: date, selection: Path, target: Path) -> dict:
    """ADR-0100 item 4: the cutoff hand-off, D5, and whether each new address can be replayed from 3 Dec."""
    hand = sorted(pl.read_parquet(selection / f"origin={origin}" / "eligible.parquet")["trader"].to_list())
    dev_origin = date.fromisoformat(str(ctx.raw["splits"]["holdout"]["start"]))
    old = set(pl.read_parquet(ctx.root / "research/selection_v2" / f"origin={dev_origin}" / "eligible.parquet")[
        "trader"].to_list())
    allp = ctx.root / ctx.raw["selection_v2"]["allpriced_dir"]
    universe = set(pl.read_parquet(allp / f"origin={dev_origin}" / "window=training" / "universe.parquet")[
        "trader"].to_list())
    pairs = pl.read_parquet(ctx.root / ctx.raw["selection_v2"]["tradable_dir"] / "tradable_pairs.parquet")
    with_set = set(pairs.filter(C("origin") == dev_origin)["trader"].to_list())
    out = {"origin": str(origin), "handoff": hand, "D5": bool(hand), "handoff_3_dec": sorted(old),
           "differs_from_3_dec": sorted(set(hand) - old),
           "replayable_from_3_dec": {a: a in universe and a in with_set for a in sorted(set(hand) - old)},
           "eligible_sha256": _sha(selection / f"origin={origin}" / "eligible.parquet")}
    target.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return out


def _sha(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------------------------- deliverables
def first_failed_gate(row: dict) -> str:
    """ADR-0100 item 6: S1, S2 (Phase 2's first failed gate), S3 in order, the category, the duplicate screen."""
    if row.get("grade") not in ("A", "B"):
        return f"S1_grade_{row.get('grade') or 'none'}"
    if not row.get("s2"):
        failed = row.get("gates_failed") or []
        first = failed[0] if isinstance(failed, list) and failed else (str(failed) if failed else "unmeasured")
        return f"S2_{first}"
    for g in S3_ORDER:
        if row.get(g) != "pass":
            return f"S3_{g}_{row.get(g) or 'unmeasured'}"
    if row.get("category") not in CATEGORY_ORDER:
        return f"category_{row.get('category') or 'unmeasured'}"
    if row.get("duplicate_decision") not in (None, "kept"):
        return str(row["duplicate_decision"])
    return "none"


def trader_decisions(ctx, origin: date, selection: Path, observation: list[str]) -> pl.DataFrame:
    from arkstream.pipeline import build
    from arkstream.replay_market import bounded_inputs

    inputs = bounded_inputs(ctx, midnight(origin))
    grades = build(ctx, inputs, midnight(origin)).tables["quality_report"].select("trader", "grade")
    every = inputs.traders.select("trader").unique().join(grades, on="trader", how="left")
    cand = pl.read_parquet(selection / f"origin={origin}" / "candidates.parquet")
    hand = set(pl.read_parquet(selection / f"origin={origin}" / "eligible.parquet")["trader"].to_list())
    cols = ["trader", "s2", "gates_failed", *S3_ORDER, "category", "duplicate_decision"]
    rows = []
    by = {r["trader"]: r for r in cand.select(cols).iter_rows(named=True)}
    for tr, grade in every.sort("trader").rows():
        r = {"trader": tr, "grade": grade, **{k: v for k, v in by.get(tr, {}).items() if k != "trader"}}
        role = "hand-off" if tr in hand else ("observation" if tr in observation else "none")
        rows.append({"origin": origin, "trader": tr, "grade": grade, "category": r.get("category"),
                     "first_failed_gate": first_failed_gate(r), "role": role})
    return pl.DataFrame(rows, schema={"origin": pl.Date, "trader": pl.String, "grade": pl.String,
                                      "category": pl.String, "first_failed_gate": pl.String, "role": pl.String},
                        orient="row")


def target_allocations(ctx, origin: date, selection: Path, decision: str) -> pl.DataFrame:
    """ADR-0100 item 6: paper (NO-GO) or gray (CONDITIONAL GO) rows, the observation sleeve, the reserve."""
    from arkstream.config import load_yaml
    from arkstream.holdout_report import statistic_choice

    risk = load_yaml("risk.yaml", ctx.root / "config")
    capital = float(risk["capital_usdc"])
    sleeve = float(risk["scheme"]["sleeve_notional_usdc"])
    observation = [str(a) for a in risk["scheme"]["observation_sleeves"]]
    hand = pl.read_parquet(selection / f"origin={origin}" / "eligible.parquet")
    ev = hand.select("trader", "category", "m", "alpha")
    stat, _ = statistic_choice(_evidence(selection, origin))  # D4's statistic at the origin (ADR-0093 item 4)
    ev = ev.with_columns(key=C(stat), rank=C("category").replace_strict(CATEGORY_ORDER, default=9))
    order = ev.sort(["rank", "key", "trader"], descending=[False, True, False], nulls_last=True)["trader"].to_list()
    gray = decision == "CONDITIONAL GO"
    live = order[: int(LIVE_MAX_USDC // LIVE_SLEEVE_USDC)] if gray else []
    rows = []
    for tr in order:
        rows.append({"trader": tr, "role": "hand-off", "protocol": "gray" if tr in live else "paper",
                     "deployed_usdc": LIVE_SLEEVE_USDC if tr in live else 0.0,
                     "paper_notional_usdc": 0.0 if tr in live else sleeve})
    for tr in observation:
        if tr not in order:
            rows.append({"trader": tr, "role": "observation", "protocol": "paper", "deployed_usdc": 0.0,
                         "paper_notional_usdc": sleeve})
    deployed = sum(r["deployed_usdc"] for r in rows)
    rows.append({"trader": "reserve", "role": "reserve", "protocol": "off-exchange USDC",
                 "deployed_usdc": capital - deployed, "paper_notional_usdc": 0.0})
    return pl.DataFrame(rows).with_columns(origin=pl.lit(origin), decision=pl.lit(decision),
                                           ordering_statistic=pl.lit(stat))


def _evidence(selection: Path, origin: date) -> pl.DataFrame:
    return pl.read_parquet(selection / f"origin={origin}" / "evidence.parquet")


# ---------------------------------------------------------------------------------------------- entry
def run(ctx, out: Path | None = None, check: bool = False, resume: bool = False) -> Path:
    from arkstream.freeze import guard

    if resume and not check:
        raise ValueError("resume is for check mode only: the cutoff selection runs once, from the start")
    if check:
        from arkstream import drift

        origin = drift.DriftRules.from_config(ctx.raw).holdout_start
        guard(ctx, midnight(origin))  # the last development origin: nothing at or after it is read
    else:
        origin = cutoff_origin(ctx)
        guard(ctx, midnight(origin))  # holdout dates: refused unless the freeze holds
        if not (ctx.root / RUN_A).is_file():
            raise RuntimeError(f"{RUN_A} missing: run A on the holdout comes before the cutoff selection "
                               "(ADR-0100 item 5)")
    out = Path(out) if out else ctx.root / (CHECK_OUT if check else OUT)
    out.mkdir(parents=True, exist_ok=True)
    ctx_o = check_context(ctx, out) if check else cutoff_context(ctx, origin, out)

    def done(path: Path) -> bool:
        return resume and path.exists()

    if not done(out / "drift" / "drift_development.csv"):
        drift_tables(ctx if check else ctx_o, origin, out / "drift")
    if not done(out / "leader" / f"origin={origin}" / "evidence.parquet"):
        phase2_tables(ctx if check else ctx_o, origin, out / "leader")
    if not check:
        from arkstream import drift

        copy_phase2_inputs(ctx, out / "leader", list(drift.DriftRules.from_config(ctx.raw).origin_dates))
    allp, trad = out / "replay_allpriced", out / "replay_tradable"
    rel = Path(f"origin={origin}") / "window=training"
    if not done(allp / rel / "universe.parquet"):
        prepare(ctx_o, allp)
    if not done(allp / rel / "scenario=base_sqrt_cap_part_ns_sweep_frozen"):
        allpriced_tree(ctx_o, origin, allp)
    if not done(trad / rel / "scenario=base_sqrt_cap_part_ns_sweep_frozen"):
        tradable_tree(ctx_o, origin, allp, trad)
    select(ctx_o, origin, out / "selection_v2")
    handoff_summary(ctx, origin, out / "selection_v2", out / "cutoff_handoff.json")
    if check:
        compare(ctx, origin, out)
    return out


def deliverables(ctx, out: Path | None = None, check: bool = False, decision_entry: Path | None = None) -> Path:
    """P5-9 (ADR-0094 item 4): refused until the freeze holds and run A's decision entry exists."""
    from arkstream.config import load_yaml
    from arkstream.freeze import guard

    if check:
        from arkstream import drift

        origin = drift.DriftRules.from_config(ctx.raw).holdout_start
        guard(ctx, midnight(origin))
    else:
        origin = cutoff_origin(ctx)
        guard(ctx, midnight(origin))
    out = Path(out) if out else ctx.root / (CHECK_OUT if check else OUT)
    sel = out / "selection_v2"
    entry = decision_entry or ctx.root / "research/holdout/decision_A.json"
    if not check and not entry.is_file():
        raise RuntimeError(f"{entry} missing: the deliverables follow run A's decision entry (ADR-0100 item 5)")
    risk = load_yaml("risk.yaml", ctx.root / "config")
    observation = [str(a) for a in risk["scheme"]["observation_sleeves"]]
    target = out / "deliverables"
    target.mkdir(parents=True, exist_ok=True)
    trader_decisions(ctx, origin, sel, observation).write_csv(target / "trader_decisions.csv")
    if check:  # both protocols, so both branches run
        for verdict, name in (("NO-GO", "nogo"), ("CONDITIONAL GO", "go")):
            target_allocations(ctx, origin, sel, verdict).write_csv(target / f"target_allocations_{name}.csv")
        problems = check_deliverables(ctx, out)
        td = pl.read_csv(target / "trader_decisions.csv")
        lines = ["# Cutoff deliverables, check mode (ADR-0100 item 7)", "",
                 f"Origin {origin}: {td.height} addresses; roles {dict(td.group_by('role').len().rows())}; "
                 f"first failed gate `none` for {int((td['first_failed_gate'] == 'none').sum())}.", "",
                 *(f"- {x}" for x in problems), "", f"**Result: {'PASS' if not problems else 'FAIL'}**"]
        text = "\n".join(lines) + "\n"
        (target / "check.md").write_text(text, encoding="utf-8", newline="\n")
        print(text)
    else:
        verdict = json.loads(entry.read_text(encoding="utf-8"))["decision"]
        target_allocations(ctx, origin, sel, verdict).write_csv(target / "target_allocations.csv")
    return target


# ---------------------------------------------------------------------------------------------- check mode
def _same(a: Path, b: Path) -> bool:
    return a.is_file() and b.is_file() and a.read_bytes() == b.read_bytes()


def _close(a: pl.DataFrame, b: pl.DataFrame, tol: float) -> bool:
    key = [c for c in ("origin", "trader", "coin", "symbol", "period", "source", "band", "horizon_ms", "t", "ts",
                       "hour_end", "day") if c in a.columns]
    try:
        pl.testing.assert_frame_equal(a.sort(key) if key else a, b.sort(key) if key else b, check_exact=False,
                                      rel_tol=tol, abs_tol=tol)
        return True
    except AssertionError:
        return False


def compare(ctx, origin: date, out: Path) -> Path:
    """ADR-0100 item 7: the builders to tolerance, everything downstream byte for byte."""
    lines = ["# Cutoff selection entry point, check mode (ADR-0100 item 7)", "",
             f"Origin {origin} (the last development origin), real configuration; nothing at or after it is read.",
             "", "| Output | Compared with | Files | Result |", "| --- | --- | ---: | --- |"]
    bad = 0

    def row(name: str, ref: str, n: int, diff: list[str]) -> None:
        nonlocal bad
        bad += len(diff) + (n == 0)
        lines.append(f"| {name} | `{ref}` | {n} | {'; '.join(diff[:4]) or 'identical'} |")

    # builders
    d = ["drift_development.csv", "drift_stress.csv", "drift_hold_bands.csv"]
    diff = [f for f in d if not _close(pl.read_csv(out / "drift" / f, try_parse_dates=True),
                                       pl.read_csv(ctx.root / "research/drift" / f, try_parse_dates=True), 1e-9)]
    row("drift tables (builder, to 1e-9)", "research/drift", len(d), diff)
    a, b = out / "leader" / f"origin={origin}", ctx.root / "research/leader" / f"origin={origin}"
    files = sorted(p.name for p in a.glob("*.parquet"))
    exact = [f for f in ("daily_twr.parquet", "book_hourly.parquet") if not _same(a / f, b / f)]
    loose = [f for f in files if not _same(a / f, b / f)
             and not _close(pl.read_parquet(a / f), pl.read_parquet(b / f), 1e-12)]
    row("Phase 2 tables (builder; engine tables exact, others to 1e-12)", f"research/leader/origin={origin}",
        len(files), sorted(set(exact) | set(loose)))
    # downstream, byte for byte
    allp_dev = ctx.root / ctx.raw["selection_v2"]["allpriced_dir"]
    trad_dev = ctx.root / ctx.raw["selection_v2"]["tradable_dir"]
    shared = ["spread_estimates.parquet", "drift_cells.parquet", "drift_hold_bands.parquet",
              "valuation_marks.parquet"]
    row("all-priced shared inputs", allp_dev.relative_to(ctx.root).as_posix(), len(shared),
        [f for f in shared if not _same(out / "replay_allpriced" / f, allp_dev / f)])
    prep = sorted(p.relative_to(out / "replay_allpriced") for p in (out / "replay_allpriced").glob(
        "origin=*/window=*/*.parquet"))
    row("every window's universe and leader series", allp_dev.relative_to(ctx.root).as_posix(), len(prep),
        [str(p) for p in prep if not _same(out / "replay_allpriced" / p, allp_dev / p)])
    for name, tree, dev in (("all-priced", out / "replay_allpriced", allp_dev),
                            ("tradable", out / "replay_tradable", trad_dev)):
        w = tree / f"origin={origin}" / "window=training"
        fs = sorted(p.relative_to(tree) for p in w.rglob("*.parquet"))
        row(f"{name} training window at {origin}", dev.relative_to(ctx.root).as_posix(), len(fs),
            [str(p) for p in fs if not _same(tree / p, dev / p)])
        cap = []
        for f in ("capture_summary.parquet", "capture_daily.parquet", "market_relative.parquet"):
            x = pl.read_parquet(tree / f)
            y = pl.read_parquet(dev / f)
            if "origin" in y.columns:
                keys = x.select([c for c in ("origin", "window") if c in x.columns]).unique()
                y = y.join(keys, on=keys.columns, how="semi")
            if not x.equals(y.select(x.columns) if set(x.columns) == set(y.columns) else y):
                cap.append(f)
        row(f"{name} capture rows of that window", dev.relative_to(ctx.root).as_posix(), 3, cap)
    tp = pl.read_parquet(out / "replay_tradable" / "tradable_pairs.parquet")
    tp_dev = pl.read_parquet(trad_dev / "tradable_pairs.parquet").filter(C("origin") == origin)
    row("tradable sets", "tradable_pairs.parquet (that origin)", 1, [] if tp.equals(tp_dev) else ["differ"])
    sel = out / "selection_v2" / f"origin={origin}"
    sel_dev = ctx.root / "research/selection_v2" / f"origin={origin}"
    sel_files = sorted(p.name for p in sel_dev.glob("*.parquet"))
    row(f"selection at {origin} (eligible.parquet included)", f"research/selection_v2/origin={origin}",
        len(sel_files), [f for f in sel_files if not _same(sel / f, sel_dev / f)])
    lines += ["", f"**Result: {'PASS' if bad == 0 else 'FAIL'}**"]
    path = out / "check.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(lines))
    return path


def check_deliverables(ctx, out: Path) -> list[str]:
    """ADR-0100 item 7: every A/B address once; roles match the hand-off and risk.yaml; counts match the funnel."""
    from arkstream.config import load_yaml

    origin = date.fromisoformat(str(ctx.raw["splits"]["holdout"]["start"]))
    td = pl.read_csv(out / "deliverables" / "trader_decisions.csv", try_parse_dates=True)
    sel = ctx.root / "research/selection_v2" / f"origin={origin}"
    cand = pl.read_parquet(sel / "candidates.parquet")
    hand = set(pl.read_parquet(sel / "eligible.parquet")["trader"].to_list())
    funnel = pl.read_csv(ctx.root / "research/selection_v2/funnel_v2.csv", try_parse_dates=True).filter(
        C("origin") == origin)
    obs = {str(a) for a in load_yaml("risk.yaml", ctx.root / "config")["scheme"]["observation_sleeves"]}
    problems = []
    if td["trader"].n_unique() != td.height:
        problems.append("an address appears twice")
    if not set(cand["trader"].to_list()) <= set(td["trader"].to_list()):
        problems.append("an A/B address is missing")
    if set(td.filter(C("role") == "hand-off")["trader"].to_list()) != hand:
        problems.append("hand-off roles differ from eligible.parquet")
    if set(td.filter(C("role") == "observation")["trader"].to_list()) != obs - hand:
        problems.append("observation roles differ from risk.yaml")
    ab = td.filter(C("grade").is_in(["A", "B"]))
    if funnel.height and ab.height != int(funnel["ab_universe"][0]):
        problems.append(f"A/B count {ab.height} differs from the funnel {funnel['ab_universe'][0]}")
    if funnel.height and int((td["first_failed_gate"] == "none").sum()) != int(funnel["eligible"][0]):
        problems.append("addresses failing no gate differ from the funnel's eligible count")
    return problems
