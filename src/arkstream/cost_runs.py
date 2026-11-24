"""Runs B and C (ADR-0098; pinned in ADR-0099): the frozen strategy charged rebuilt real costs, with the frozen cost
model in the risk rules (B) or C's daily point-in-time refit there (C). Development data only here; the holdout
entry point (`holdout.py`) calls the same functions on its own window.

Steps (`phase5 cost-runs`):
* `drift`: C's daily drift table over the development days (`cost_updated.daily_cells`), checked against the
  origins' frozen cells;
* `runs`: the frozen O2 bounds, then B (S*, U*, G*) and C (S*, G*) on the four development test windows, base tree
  inputs, the P5-5 configurations;
* `report`: A against B, B against C, per-part accuracy, D3 and C1 on B, the shadow counts and the fallback rates.

Every table carries the label "rebuilt real conditions, development: not real fills" (ADR-0098 item 7).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import polars as pl

from arkstream import cost_rebuild as CR
from arkstream import cost_updated as CU
from arkstream import phase5_pair as P
from arkstream import portfolio_engine as PE
from arkstream import portfolio_replay as PR

C = pl.col
DEFAULT_OUT = "research/cost_runs"
BOOKS = {"B": ("S", "U", "G"), "C": ("S", "G")}
LABEL = "rebuilt real conditions, development: not real fills"
PARTS = ("delay_ms", "drift_bps", "half_bps", "impact_bps", "fee_bps", "shortfall_bps")


def window_days(win) -> list[date]:
    return [win.start.date() + timedelta(days=k) for k in range((win.end - win.start).days)]


@dataclass
class Setup:
    """Everything one window's B and C runs need beside `PR.WindowData`."""

    rebuild: CR.RebuildInputs
    params: object
    bands: pl.DataFrame
    spreads14: dict
    taker: pl.DataFrame
    tables: dict[str, pl.DataFrame]


def taker_obs(ctx, fills, bars, coins, days, stop, frozen_half, sp_rules, base_half) -> tuple[pl.DataFrame,
                                                                                                pl.DataFrame]:
    """Taker-order observations (x, z) per day on the tape coins, with the same-day spreads their z uses."""
    sym = CR.tape_symbols(ctx)
    same = CR.daily_spreads(fills, sorted(sym), days, sp_rules, base_half)
    half = CR.spread_lookup(same)
    staleness = int(float(ctx.raw["drift"]["max_staleness_s"]) * 1000)
    tape = CR.Tape(ctx.path("aggtrades_dir"), sym, [days[0] - timedelta(days=1), *days], stop, staleness)
    obs = CR.impact_observations(fills, tape, bars, half, frozen_half, sorted(sym), CR.midnight(days[0]),
                                 CR.midnight(days[-1] + timedelta(days=1)))
    return obs, same


def prepare(ctx, win, data: PR.WindowData, fills: pl.DataFrame, bars: pl.DataFrame, costs, ex: dict,
            o2: dict[str, float], cells: pl.DataFrame, bands: pl.DataFrame, stop: datetime) -> Setup:
    from arkstream.replay_orders import Parameters

    base = costs["base"]
    base_half = {"majors": base.half_majors, "other": base.half_other}
    sp_rules = ex["spreads"]
    days = window_days(win)
    sym = CR.tape_symbols(ctx)
    coins = sorted(set(data.coins) | set(sym))
    lo = win.start - timedelta(days=CU.TRAILING_DAYS + 1)
    f = fills.filter((C("ts") >= lo) & (C("ts") < win.end) & C("symbol").is_in(coins))

    def frozen_half(coin: str, t: int) -> float:
        return data.market.half_spread(coin, t, "base")

    # C's trailing impact sample before the window (its tape is freed after use)
    pre = [win.start.date() - timedelta(days=k) for k in range(CU.TRAILING_DAYS, 0, -1)]
    obs_pre, _ = taker_obs(ctx, f, bars, coins, pre, stop, frozen_half, sp_rules, base_half)
    # the window: same-day spreads, the tape kept for pricing, same-day impact
    staleness = int(float(ctx.raw["drift"]["max_staleness_s"]) * 1000)
    tape = CR.Tape(ctx.path("aggtrades_dir"), sym, [days[0] - timedelta(days=1), *days], stop, staleness)
    same = CR.daily_spreads(f, coins, days, sp_rules, base_half)
    half_day = CR.spread_lookup(same)
    obs = CR.impact_observations(f, tape, bars, half_day, frozen_half, sorted(sym), win.start, win.end)
    trailing = CR.daily_spreads(f, coins, days, sp_rules, base_half, lookback_days=CU.TRAILING_DAYS)
    q = CR.delay_quantiles(ctx.root / "research/latency/total_delay.csv")
    rb = CR.RebuildInputs(tape=tape, spread_day=half_day, y_day=CR.fit_y(obs), o2=o2, quantiles=q,
                          receive_ms=base.receive_ms, debounce_ms=base.debounce_ms, fee_bps=base.fee_bps,
                          frozen_y=base.sqrt_y)
    y = pl.DataFrame([(c, d, v, n) for (c, d), (v, n) in sorted(rb.y_day.items())],
                     schema={"coin": pl.String, "day": pl.Date, "y": pl.Float64, "orders": pl.Int64}, orient="row")
    return Setup(rebuild=rb, params=Parameters.from_rules(cells, ex), bands=bands,
                 spreads14=CU.trailing_spreads(trailing), taker=pl.concat([obs_pre, obs]),
                 tables={"spread_same_day": same, "spread_trailing14": trailing, "impact_y_day": y,
                         "tape_missing": pl.DataFrame(tape.missing, schema={"coin": pl.String, "day": pl.Date},
                                                      orient="row")})


def run_book(ctx, data: PR.WindowData, win, setup: Setup, run: str, config: str, size: float, traders: list[str],
             signals: list[PE.Signal], costs, over: dict) -> tuple[PE.Rules, PE.Engine, PE.Result]:
    alloc = {t: float(size) for t in traders}
    rules = PR.scheme_rules(ctx, config, alloc, costs["stress"], **over)
    pricer = CR.Rebuild(setup.rebuild, CR.DelaySampler(setup.rebuild.quantiles, CR.delay_seed(win.origin, config)),
                        costs["base"], costs["stress"])
    risk = None
    if run == "C":
        risk = CU.UpdatedMarket(data.market, setup.params, setup.bands, setup.spreads14, setup.taker, pricer,
                                costs["base"].sqrt_y)
        pricer.updated = risk
    eng = PE.Engine(rules, costs["base"], data.market, PR.ms(win.start), PR.ms(win.end), triggers=data.triggers,
                    reviews=PR.review_times(win.start, win.end, rules.review_days), risk_market=risk, pricer=pricer,
                    shadow_market=risk)
    return rules, eng, eng.run(signals)


def tree_signals(tree: Path, win, traders: list[str], scenario: str = "base") -> list[PE.Signal]:
    sigs = PR.signals_from_orders(PR.tree_orders(tree, win.origin, "test", scenario, traders))
    out: list[PE.Signal] = []
    for tr in traders:
        out += sigs.get(tr, [])
    return out


def window_runs(ctx, win, data: PR.WindowData, setup: Setup, trees: dict[float, Path], sleeves: list[str],
                handoff: list[str], gray: float, costs, over: dict, marks: pl.DataFrame, market, out: Path,
                runs=("B", "C"), extra: dict | None = None) -> list[dict]:
    rows = []
    for run in runs:
        for config in BOOKS[run]:
            size, traders = (gray, handoff) if config == "G" else (10000.0, sleeves)
            rules, eng, res = run_book(ctx, data, win, setup, run, config, size, traders,
                                       tree_signals(trees[size], win, traders), costs, over)
            fr = PR.frames(res)
            daily, fund, ledger = PR.daily_book(fr["fills"], rules.allocations, marks, data.funding, win.start,
                                                win.end)
            alpha = P.alpha_of(ledger, fund, marks, market, win.start.date(), win.end.date(),
                               sorted(rules.allocations))
            tag = config if config != "G" else f"G{int(gray)}"
            rec = pl.DataFrame(res.cost_records, infer_schema_length=None) if res.cost_records else pl.DataFrame()
            folder = out / f"origin={win.origin}" / f"run={run}" / f"config={tag}"
            PR.write_run(folder, {**fr, "daily": daily, "cost_records": rec})
            ev = fr["events"]
            for r in P.summarize(win, tag, "base", rules, fr, daily, alpha, eng):
                scope = r["scope"]
                names = sorted(rules.allocations) if scope == "combined" else [scope]
                e = ev.filter(C("trader").is_in([*names, "scheme"])) if ev.height else ev
                o = rec.filter(C("trader").is_in(names)) if rec.height else rec
                r.update(run=run, label=LABEL, **(extra or {}),
                         rebuilt_orders=o.height,
                         rejected_o2=int((o["rebuilt_status"] == "rejected_o2").sum()) if o.height else 0,
                         shadow_c1_on=int(((e["event"] == "shadow_trigger_on")).sum()) if e.height else 0,
                         shadow_o2_reject=int((e["event"] == "shadow_o2_reject").sum()) if e.height else 0,
                         c1_on=int(((e["event"] == "trigger_on") & (e["trigger"] == "C1")).sum()) if e.height else 0)
                rows.append(r)
            print(f"{win.origin} run {run} {tag}: {len(res.cost_records)} rebuilt orders", flush=True)
    return rows


# ---------------------------------------------------------------------------------------------- steps
def step_drift(ctx, out: Path) -> Path:
    from arkstream import drift
    from arkstream.freeze import guard
    from arkstream.replay_market import bounded_inputs

    dr = drift.DriftRules.from_config(ctx.raw)
    stop = PR.midnight(dr.holdout_start)
    guard(ctx, stop)
    wins = PR.dev_windows(ctx)
    days = sorted({d for w in wins for d in window_days(w)})
    cells, bands = CU.daily_cells(ctx, bounded_inputs(ctx, stop), days, stop)
    out.mkdir(parents=True, exist_ok=True)
    cells.write_parquet(out / "drift_daily_cells.parquet", compression="zstd", statistics=True)
    bands.write_parquet(out / "drift_daily_bands.parquet", compression="zstd", statistics=True)
    tree = pl.read_parquet(ctx.root / ctx.raw["selection_v2"]["tradable_dir"] / "drift_cells.parquet")
    CU.origin_check(cells, tree, [w.origin for w in wins]).write_csv(out / "drift_daily_origin_check.csv")
    return out


def o2_table(ctx, origins: list[date]) -> pl.DataFrame:
    return CR.o2_bounds(ctx.root / ctx.raw["selection_v2"]["tradable_dir"], origins)


def step_runs(ctx, out: Path) -> Path:
    from arkstream import drift
    from arkstream.replay_market import bounded_inputs

    dr = drift.DriftRules.from_config(ctx.raw)
    stop = PR.midnight(dr.holdout_start)
    runner = P.Runner(ctx, out)  # freeze.guard at the holdout start; costs, bars, sleeves, hand-off, variants
    wins = PR.dev_windows(ctx)
    o2t = o2_table(ctx, [w.origin for w in wins])
    o2t.with_columns(label=pl.lit("frozen O2 bound (ADR-0099 item 5): development stress p99, trigger legs")
                     ).write_csv(out / "o2_bounds.csv")
    o2 = {b: float(v) for b, v in o2t.select("liq_bucket", "p99_bps").rows()}
    cells = pl.read_parquet(out / "drift_daily_cells.parquet")
    bands = pl.read_parquet(out / "drift_daily_bands.parquet")
    gray = int(json.loads((ctx.root / "research/portfolio_replay/gray_size.json").read_text(encoding="utf-8"))[
        "chosen"])
    inputs = bounded_inputs(ctx, stop)
    fills = inputs.fills
    del inputs
    rows: list[dict] = []
    aux: dict[str, list[pl.DataFrame]] = {}
    for win in wins:
        data = PR.WindowData(ctx, win, runner.sleeves, [runner.t10, runner.tree(gray)], runner.bars, runner.costs,
                             runner.ex)
        setup = prepare(ctx, win, data, fills, runner.bars, runner.costs, runner.ex, o2, cells, bands, stop)
        for k, t in setup.tables.items():
            aux.setdefault(k, []).append(t.with_columns(origin=pl.lit(win.origin)))
        market, marks = P.alpha_market(ctx, win.origin)
        rows += window_runs(ctx, win, data, setup, {10000.0: runner.t10, float(gray): runner.tree(gray)},
                            runner.sleeves, runner.handoff, float(gray), runner.costs, runner.over, marks, market,
                            out)
        del setup
    pl.DataFrame(rows, infer_schema_length=None).write_csv(out / "cost_summary.csv")
    for k, parts in aux.items():
        pl.concat(parts, how="diagonal_relaxed").write_csv(out / f"{k}.csv")
    return out


# ---------------------------------------------------------------------------------------------- report
def records(out: Path, origins: list[date]) -> pl.DataFrame:
    parts = []
    for p in sorted(out.glob("origin=*/run=*/config=*/cost_records.parquet")):
        o = date.fromisoformat(p.parent.parent.parent.name[7:])
        if o not in origins:
            continue
        d = pl.read_parquet(p)
        if d.height:
            parts.append(d.with_columns(origin=pl.lit(o), run=pl.lit(p.parent.parent.name[4:]),
                                        config=pl.lit(p.parent.name[7:])))
    return pl.concat(parts, how="diagonal_relaxed")


def accuracy(rec: pl.DataFrame, model: str) -> pl.DataFrame:
    """Per run, config and part: model minus rebuild over the filled orders (ADR-0099 item 10)."""
    f = rec.filter(C("rebuilt_status") == "filled")
    if model == "updated":
        f = f.filter(C("updated_drift_bps").is_not_null())
    f = f.with_columns(tape=C("drift_flag") == "tape")
    rows = []
    for (run, config, tape), g in f.group_by("run", "config", "tape", maintain_order=True):
        for part in PARTS:
            m, r = g[f"{model}_{part}"].cast(pl.Float64), g[f"rebuilt_{part}"].cast(pl.Float64)
            d = (m - r).drop_nulls()
            rows.append({"run": run, "config": config, "drift_from_tape": tape, "model": model, "part": part,
                         "orders": d.len(), "model_mean": P.num(m.mean()), "rebuilt_mean": P.num(r.mean()),
                         "mean_diff": P.num(d.mean()), "median_diff": P.num(d.median()),
                         "mae": P.num(d.abs().mean())})
    return pl.DataFrame(rows).sort("run", "config", "drift_from_tape", "part")


def fallback_rates(rec: pl.DataFrame) -> pl.DataFrame:
    rows = []
    for (run, config), g in rec.group_by("run", "config", maintain_order=True):
        n = g.height
        rows.append({"run": run, "config": config, "orders": n,
                     "drift_fallback": P.num((g["drift_flag"] != "tape").mean()),
                     "drift_no_tape_coin": P.num((g["drift_flag"] == "frozen_no_tape").mean()),
                     "drift_no_print": P.num((g["drift_flag"] == "frozen_no_print").mean()),
                     "spread_fallback": P.num((g["half_flag"] != "day").mean()),
                     "impact_fallback": P.num((g["impact_flag"] != "day").mean()),
                     "rejected_o2": P.num((g["rebuilt_status"] == "rejected_o2").mean())})
    return pl.DataFrame(rows).sort("run", "config")


def d3_on_b(ctx, out: Path, origins: list[date]) -> pl.DataFrame:
    """D3 (H3) on B's S*: median cost per side by coin against the development p90 of A (ADR-0098 item 7)."""
    from arkstream import holdout_report as HR

    ref = ctx.root / "research/portfolio_replay"
    dev = pl.concat([pl.read_parquet(ref / f"origin={o}" / "config=S" / "scenario=base" / "fills.parquet")
                     for o in origins], how="diagonal_relaxed")
    rows = []
    for o in origins:
        for run, path in (("A", ref / f"origin={o}" / "config=S" / "scenario=base" / "fills.parquet"),
                          ("B", out / f"origin={o}" / "run=B" / "config=S" / "fills.parquet")):
            h3 = HR.h3_costs(pl.read_parquet(path), dev)
            m = h3.filter("measured")
            rows.append({"origin": o, "run": run, "coins_measured": m.height,
                         "coins_within_p90": int(m["within_p90"].sum()) if m.height else 0,
                         "D3": bool(m.height > 0 and m["within_p90"].all()),
                         "failing": ",".join(m.filter(~C("within_p90"))["coin"].to_list())})
    return pl.DataFrame(rows)


def books_table(ctx, out: Path) -> pl.DataFrame:
    """A (the P5-5 base runs) beside B and C, per window and book (combined scope)."""
    a = pl.read_csv(ctx.root / "research/portfolio_replay/pair_summary.csv", try_parse_dates=True).filter(
        (C("scenario") == "base") & (C("scope") == "combined") & C("config").is_in(["S", "U", "G2500"])
    ).with_columns(run=pl.lit("A"))
    bc = pl.read_csv(out / "cost_summary.csv", try_parse_dates=True).filter(C("scope") == "combined")
    cols = ["origin", "run", "config", "allocation", "final_nav", "raw_return", "max_drawdown_usdc",
            "max_loss_incl_exit_usdc", "firings", "trigger_on", "traded_usdc", "cost_half_spread_bps",
            "cost_impact_bps", "cost_drift_bps", "physical_fills", "lambda_exposure_weighted"]
    t = pl.concat([a.select(cols), bc.select(cols)], how="diagonal_relaxed")
    return t.with_columns(pnl_usdc=C("final_nav") - C("allocation")).sort("config", "origin", "run")


def step_report(ctx, out: Path) -> Path:
    from arkstream import drift

    dr = drift.DriftRules.from_config(ctx.raw)
    origins = [o for o in dr.origin_dates if o < dr.holdout_start]
    rec = records(out, origins)
    books_table(ctx, out).write_csv(out / "books_a_b_c.csv")
    pl.concat([accuracy(rec.filter(C("run") == "B"), "frozen"), accuracy(rec.filter(C("run") == "C"), "frozen"),
               accuracy(rec.filter(C("run") == "C"), "updated")]).write_csv(out / "accuracy.csv")
    fallback_rates(rec).write_csv(out / "fallback_rates.csv")
    d3_on_b(ctx, out, origins).write_csv(out / "d3_on_b.csv")
    return out


def run(ctx, out: Path | None = None, step: str = "all") -> Path:
    out = Path(out) if out else ctx.root / DEFAULT_OUT
    out.mkdir(parents=True, exist_ok=True)
    if step in ("drift", "all"):
        step_drift(ctx, out)
    if step in ("runs", "all"):
        step_runs(ctx, out)
    if step in ("report", "all", "runs"):
        step_report(ctx, out)
    return out
