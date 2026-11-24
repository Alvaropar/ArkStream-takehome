"""Cost uncertainty surface (ADR-0050): base scenario, development test windows, all-gate passers.

One-at-a-time points around the placeholder costs (square-root impact Y, participation, address gross cap), then
the most and least favourable combinations, each chosen per parameter from the one-at-a-time results. The archived
comparison (`research/replay_sizing/`) evaluated both sizing variants of ADR-A0116; from ADR-0052 on only the frozen
one is run (`policies=("frozen",)`). Reads the shared inputs in the output folder (universe, drift cells, bands,
spreads) and writes `cost_surface.csv` there. The holdout is never computed.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from arkstream import drift, hlprices
from arkstream.config import assert_no_live_trading, load_yaml
from arkstream.refprices import load_map
from arkstream.replay import UNIVERSE, model_inputs_by_origin, replay_settings
from arkstream.replay_book import summaries, value_book
from arkstream.replay_cap import MinuteMarks, cap_legs, impact_bars, reference_equity
from arkstream.replay_market import bounded_inputs, midnight, trade_queries
from arkstream.replay_orders import Parameters, batches, execute, order_inputs, quotes

C = pl.col
CENTRE: dict[str, float | None] = {"y": 1.0, "participation": 0.005, "cap_x": 1.5}
GRID: dict[str, tuple[float | None, ...]] = {"y": (0.5, 2.0), "participation": (0.0025, 0.01, None),
                                             "cap_x": (1.0, 2.0)}
POLICIES = ("dynamic", "frozen")


def one_at_a_time() -> list[tuple[str, dict]]:
    points = [("centre", dict(CENTRE))]
    for key, values in GRID.items():
        points += [(f"{key}={'none' if v is None else v}", {**CENTRE, key: v}) for v in values]
    return points


def corners(pooled: pl.DataFrame, policies: tuple[str, ...] = POLICIES) -> dict[str, list[tuple[str, dict]]]:
    """ADR-0050: per policy, each parameter at its best (worst) one-at-a-time value; ties go to the centre."""
    out: dict[str, list[tuple[str, dict]]] = {}
    for policy in policies:
        p = pooled.filter((C("policy") == policy) & (C("origin") == "all_tests"))
        centre = p.filter(C("point") == "centre")["mean_return"].item()
        best, worst = dict(CENTRE), dict(CENTRE)
        for key, values in GRID.items():
            options: list[tuple[float | None, float]] = [(CENTRE[key], centre)]
            for v in values:
                name = f"{key}={'none' if v is None else v}"
                options.append((v, p.filter(C("point") == name)["mean_return"].item()))
            top = max(r for _, r in options)
            low = min(r for _, r in options)
            best[key] = CENTRE[key] if centre == top else next(v for v, r in options if r == top)
            worst[key] = CENTRE[key] if centre == low else next(v for v, r in options if r == low)
        out[policy] = [("most_favourable", best), ("least_favourable", worst)]
    return out


def _pool(rows: pl.DataFrame, allocation: float) -> pl.DataFrame:
    stats = [
        pl.len().alias("address_windows"),
        C("copy_return").count().alias("measured"),
        (C("copy_return") > 0).sum().alias("positive"),
        C("copy_return").mean().alias("mean_return"),
        (C("final_equity") - allocation).filter(C("copy_return").is_not_null()).sum().alias("profit_usdc"),
        C("total_turnover").filter(C("copy_return").is_not_null()).sum().alias("turnover_usdc"),
    ]
    keys = ["policy", "point", "y", "participation", "cap_x"]
    by = rows.group_by(*keys, "origin").agg(stats)
    total = rows.group_by(*keys).agg(stats).with_columns(origin=pl.lit("all_tests"))
    return (
        pl.concat([by.with_columns(C("origin").cast(pl.String)), total.select(by.columns)])
        .with_columns(absorb_bps=pl.when(C("turnover_usdc") > 0).then(C("profit_usdc") / C("turnover_usdc") * 1e4))
        .sort("policy", "point", "origin")
    )


def _universe(out: Path, origin) -> Path:
    folder = out / f"origin={origin.date()}" / "window=test"
    return folder / UNIVERSE if (folder / UNIVERSE).is_file() else folder / "scenario=base" / "address_summary.parquet"


def run(ctx, out: Path | None = None, policies: tuple[str, ...] = ("frozen",)) -> pl.DataFrame:
    assert_no_live_trading(ctx.root / "config")
    out = Path(out) if out else ctx.root / "research/replay_frozen"
    if not (out / "drift_cells.parquet").is_file():
        raise FileNotFoundError(f"{out}: run `python -m arkstream replay --frozen` first")
    if set(policies) - set(POLICIES):
        raise ValueError(f"unknown sizing policy in {policies}")
    scenarios, rules = replay_settings(load_yaml("execution.yaml", ctx.root / "config"))
    base = scenarios["base"]  # ADR-0058: the base delay is the measured median, 1.2 s (in ms)
    allocation = float(rules["allocation_usdc"])
    dr = drift.DriftRules.from_config(ctx.raw)
    stop = midnight(dr.holdout_start)
    origins = [midnight(o) for o in dr.origin_dates]
    tests = [(o, origins[i + 1]) for i, o in enumerate(origins[:-1])]  # development tests; never the holdout
    universes = {
        o: pl.read_parquet(_universe(out, o),
                           columns=["trader", "return_source", "all_gates_pass", "hold_band", "leader_return",
                                    "leader_days"]).filter("all_gates_pass").sort("trader")
        for o, _ in tests
    }
    candidate = pl.concat(list(universes.values())).select("trader").unique()
    inputs = bounded_inputs(ctx, stop)
    eligible = inputs.fills.filter(C("eligible") & (C("event_kind") == "trade")).join(candidate, on="trader",
                                                                                       how="semi")
    tape = trade_queries(ctx, eligible, dr, stop, basket=True)
    checker = hlprices.PointInTimeCheck.load(ctx)
    checks_by = {o: checker.checks(o) for o, _ in tests}
    union = sorted(set().union(*(checker.passing(o) for o, _ in tests)))
    per_origin = model_inputs_by_origin(ctx, inputs, stop, candidate, checks_by)
    events = per_origin[tests[0][0]][0].join(inputs.fills.select("src_row", "size"), on="src_row", how="left")
    marks = per_origin[tests[0][0]][3]
    mapping = load_map(ctx.path("binance_map")).select("valid_from", "valid_to", "price_factor_hl_per_binance",
                                                       coin="hl")
    candles, _ = hlprices.load_candles(ctx.path("hyperliquid_dir"), stop)
    bars = impact_bars(candles, stop, rules["square_root"]["volatility_bars"])
    minute_marks = MinuteMarks.load(ctx.path("reference_prices_dir"), tests[0][0], stop, union)
    bands = pl.read_parquet(out / "drift_hold_bands.parquet")
    spreads = pl.read_parquet(out / "spread_estimates.parquet")
    params = Parameters.from_rules(pl.read_parquet(out / "drift_cells.parquet"), rules)
    del inputs, eligible

    def evaluate(points_by_policy: dict[str, list[tuple[str, dict]]]) -> pl.DataFrame:
        rows = []
        for policy, points in points_by_policy.items():
            for origin, end in tests:
                u = universes[origin]
                _, snaps, _, _, funding = per_origin[origin][:5]
                checks = checks_by[origin]
                passing = set(checks.filter(C("outcome") == "pass")["coin"])
                signals = events.join(u.select("trader"), on="trader", how="semi")
                batch = batches(signals, rules["receive_ms"], rules["debounce_ms"], origin, end)
                sizing = (reference_equity(snaps, u["trader"].to_list(), origin, end, rules["review_days"])
                          if policy == "frozen" else snaps)
                for cap_x in sorted({p["cap_x"] for _, p in points}):
                    limit = allocation * cap_x
                    plan = cap_legs(batch, signals, sizing, minute_marks, passing, allocation, limit,
                                    rules["receive_ms"], origin, end, no_scale_up=True)
                    frame = order_inputs(plan, sizing, bars, checks, mapping, tape, bands, dr.origin_dates, spreads,
                                         rules, origin, end, base["delay_ms"])
                    priced = quotes(frame, "base", base, params, sweep=True)
                    for name, p in points:
                        if p["cap_x"] != cap_x:
                            continue
                        settings = dict(base, sqrt_y=p["y"], participation=p["participation"], no_scale_up=True)
                        orders = execute(priced, settings, dict(rules, cap_usdc=limit), cap_marks=minute_marks)
                        daily, _, _ = value_book(orders, u, marks, funding, origin, end, allocation)
                        s = summaries(daily, orders, u, allocation)
                        rows.append(s.select("trader", "copy_return", "final_equity", "total_turnover").with_columns(
                            policy=pl.lit(policy), point=pl.lit(name), y=pl.lit(p["y"]),
                            participation=pl.lit(p["participation"], pl.Float64), cap_x=pl.lit(cap_x),
                            origin=pl.lit(origin.date())))
                print(f"{policy} {origin.date()} surface points done", flush=True)
        return pl.concat(rows)

    first = evaluate({policy: one_at_a_time() for policy in policies})
    pooled = _pool(first, allocation).with_columns(kind=pl.when(C("point") == "centre").then(pl.lit("centre"))
                                                   .otherwise(pl.lit("one_at_a_time")))
    combos = corners(pooled, policies)
    second = _pool(evaluate(combos), allocation).with_columns(kind=C("point"))
    surface = pl.concat([pooled, second.select(pooled.columns)]).sort("policy", "kind", "point", "origin")
    lows = (surface.filter(C("origin") == "all_tests").sort("mean_return").group_by("policy", maintain_order=True)
            .first().select("policy", lower_bound_point="point", lower_bound_return="mean_return"))
    surface = surface.join(lows, on="policy", how="left").sort("policy", "kind", "point", "origin")
    surface.write_csv(out / "cost_surface.csv")
    return surface
