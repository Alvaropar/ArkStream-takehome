"""Cost sensitivities for the nine Phase 3 windows (ADRs 0033-0036)."""

from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory

import polars as pl
import pyarrow.parquet as pq

from arkstream import drift, hlprices
from arkstream.config import assert_no_live_trading, load_yaml
from arkstream.refprices import load_map
from arkstream.replay import (
    UNIVERSE,
    delay_results,
    grid_rows,
    model_inputs_by_origin,
    replay_settings,
    run,
    stress_floor,
    windows,
    write,
)
from arkstream.replay_book import completed_trips, summaries, value_book
from arkstream.replay_cap import MinuteMarks, cap_legs, impact_bars, reference_equity
from arkstream.replay_market import bounded_inputs, midnight, trade_queries
from arkstream.replay_orders import Parameters, batches, delay_plan, execute, grid_owner, order_inputs, quotes

C = pl.col
MODELS = ("original", "sqrt", "cap", "sqrt_cap", "part", "part_ns", "part_ns_sweep", "part_ns_sweep_frozen")
SUFFIX = {
    "original": "",
    "sqrt": "_sqrt",
    "cap": "_cap",
    "sqrt_cap": "_sqrt_cap",
    "part": "_sqrt_cap_part",
    "part_ns": "_sqrt_cap_part_ns",
    "part_ns_sweep": "_sqrt_cap_part_ns_sweep",
    "part_ns_sweep_frozen": "_sqrt_cap_part_ns_sweep_frozen",
}
# Which target plan each variant trades, and which execution rules it adds. Cumulative from sqrt_cap:
# part = + participation cap (ADR-0035); part_ns = + no scale-up (ADR-A0087); part_ns_sweep = + leader sweep anchor
# (ADR-0036); part_ns_sweep_frozen = the same stack sized on the frozen reference equity (ADR-A0116).
SPEC = {
    "sqrt": {"plan": "uncapped", "sqrt": True},
    "cap": {"plan": "capped", "sqrt": False},
    "sqrt_cap": {"plan": "capped", "sqrt": True},
    "part": {"plan": "capped", "sqrt": True, "part": True},
    "part_ns": {"plan": "capped_ns", "sqrt": True, "part": True, "ns": True},
    "part_ns_sweep": {"plan": "capped_ns", "sqrt": True, "part": True, "ns": True, "sweep": True},
    "part_ns_sweep_frozen": {"plan": "capped_frozen", "sqrt": True, "part": True, "ns": True, "sweep": True},
}
SIZING_MODELS = ("part_ns_sweep", "part_ns_sweep_frozen")  # dynamic vs frozen reference equity (ADR-A0116)


def canonical(scenario, model):
    if scenario == "optimistic":
        # Optimistic has zero impact, so the square-root variants share the linear ledgers.
        model = {"sqrt": "original", "sqrt_cap": "cap"}.get(model, model)
    return scenario + SUFFIX[model]


def settings_for(settings, model, rules):
    spec = SPEC[model]
    used = dict(settings)
    if spec["sqrt"]:
        used["sqrt_y"] = rules["square_root"]["y"]
    if spec.get("part"):
        used.update(participation=rules["max_participation"], no_scale_up=spec.get("ns", False))
    return used


BENCHMARK = "benchmark=unattainable_frozen"
BENCHMARK_SETTINGS = {"fee_bps": 0.0, "impact": "none", "half_spread_bps": {"majors": 0.0, "other": 0.0}}


def benchmark_orders(plan, sizing, bars, checks, mapping, tape, bands, origins, spreads, params, rules, start, end,
                     minute_marks):
    """ADR-0063 benchmark: the frozen plan's decisions (multiplier, cap, leader budget) acknowledged at the leader
    fill's own time and price, without spread, impact, fee, minimum size or participation budget, on every coin."""
    frame = order_inputs(plan, sizing, bars, checks, mapping, tape, bands, origins, spreads, rules, start, end, 0)
    priced = quotes(frame, "unattainable_all", BENCHMARK_SETTINGS, params)
    settings = {**settings_for(BENCHMARK_SETTINGS, "part_ns_sweep_frozen", rules), "participation": None}
    return execute(priced, settings, rules, ideal=True, cap_marks=minute_marks)


def cost_totals(orders, universe):
    f = (
        orders.filter(C("status") == "filled")
        .join(universe.select("trader", "all_gates_pass"), on="trader")
        .with_columns(
            notional=C("quantity").abs() * C("fill_px"),
            anchor_bps=C("quantity").sign() * (C("mid_L") / C("anchor_px") - 1) * 10000,
        )
    )
    rows = []
    for scope, group in (("all_ab", f), ("gate_passers", f.filter("all_gates_pass"))):
        for group_name, subset in (
            ("all", group),
            ("BTC_ETH", group.filter(C("coin").is_in(["BTC", "ETH"]))),
            ("other", group.filter(~C("coin").is_in(["BTC", "ETH"]))),
        ):
            rows.append(
                subset.select(
                    fills=pl.len(),
                    notional=C("notional").sum(),
                    fee=(C("fee") * 10000).sum(),
                    spread=(C("notional") * C("half_bps")).sum(),
                    impact=(C("notional") * C("impact_bps")).sum(),
                    drift=(C("notional") * C("shortfall_bps")).sum(),
                    anchor=(C("notional") * C("anchor_bps")).sum(),
                ).with_columns(universe=pl.lit(scope), coins=pl.lit(group_name))
            )
    return pl.concat(rows)


def combine_bands(parts):
    all_rows = pl.concat(parts)
    values = ["gross_bps", "cost_bps", "funding_bps"]
    return (
        all_rows.group_by("hold_band", maintain_order=True)
        .agg(
            C("completed", "addresses").sum(),
            *[(C(k) * C("completed")).sum().truediv(C("completed").sum()).alias(k) for k in values],
        )
        .with_columns(net_bps=C("gross_bps") - C("cost_bps") + C("funding_bps"))
        .sort("hold_band")
    )


def chunks(universe, events):
    sizes = dict(events.group_by("trader").len().rows())
    block = []
    n = 0
    for trader in sorted(universe["trader"]):
        size = sizes.get(trader, 0)
        if block and n + size > 18000:
            yield block
            block, n = [], 0
        block.append(trader)
        n += size
    if block:
        yield block


def mark_tradable(plan, pairs):
    """ADR-0076: flag every leg outside the wallet's tradable set (`pairs`: trader, coin); `quotes` makes it
    `not_tradable`. The plan itself (cap scale, resize legs) is the all-priced one."""
    keep = pairs.select("trader", "coin").unique().with_columns(_tradable=pl.lit(True))
    return plan.join(keep, on=["trader", "coin"], how="left", maintain_order="left").with_columns(
        not_tradable=C("_tradable").is_null()).drop("_tradable")


def window_variants(dest, original, universe, start, end, shared, scenarios, rules, horizons, test, models):
    (events, snaps, bars, checks, mapping, tape, bands, origins, spreads, params, marks, funding,
     minute_marks) = shared[:13]
    tradable = shared[13] if len(shared) > 13 else None
    ev = events.filter(
        C("event_ms").is_between(int(start.timestamp() * 1000), int(end.timestamp() * 1000), closed="left")
    )
    ev = ev.join(universe.select("trader"), on="trader", how="semi")
    passing = set(checks.filter(C("outcome") == "pass")["coin"])
    returns, delays, band_tables, cost_parts = {}, {}, {}, {}
    writers = {}
    with ExitStack() as files:
        for traders in chunks(universe, ev):
            u = universe.filter(C("trader").is_in(traders)).sort("trader")
            signals = ev.filter(C("trader").is_in(traders))
            batch = batches(signals, rules["receive_ms"], rules["debounce_ms"], start, end)
            plans = {"uncapped": (batch, False, snaps)}
            needed = {SPEC[m]["plan"] for m in models}
            for plan_name, no_scale_up in (("capped", False), ("capped_ns", True), ("capped_frozen", True)):
                if plan_name in needed:
                    # ADR-A0116: the frozen plan sizes on the reference equity fixed at each review.
                    sizing = (
                        reference_equity(snaps, traders, start, end, rules["review_days"])
                        if plan_name == "capped_frozen"
                        else snaps
                    )
                    legs = cap_legs(
                        batch,
                        signals,
                        sizing,
                        minute_marks,
                        passing,
                        rules["allocation_usdc"],
                        rules["cap_usdc"],
                        rules["receive_ms"],
                        start,
                        end,
                        no_scale_up=no_scale_up,
                    )
                    if tradable is not None:
                        legs = mark_tradable(legs, tradable)
                    plans[plan_name] = (legs, True, sizing)
            for plan_name, (plan, cap, sizing) in plans.items():
                variants = [m for m in models if SPEC[m]["plan"] == plan_name]
                if not variants:
                    continue
                if "part_ns_sweep_frozen" in variants:
                    # ADR-0063: the same frozen plan at zero delay, leader prices, zero cost, every coin.
                    bench = benchmark_orders(plan, sizing, bars, checks, mapping, tape, bands, origins, spreads,
                                             params, rules, start, end, minute_marks)
                    daily, fund, _ = value_book(bench, u, marks, funding, start, end, rules["allocation_usdc"])
                    bench = bench.drop("cs_half_bps", "known_at", "valid_from", "valid_to", "param_reason")
                    for table, data in (("follower_orders", bench), ("daily_copy_twr", daily),
                                        ("funding_payments", fund)):
                        path = dest / BENCHMARK / (table + ".parquet")
                        path.parent.mkdir(parents=True, exist_ok=True)
                        arrow = data.rechunk().to_arrow()
                        if path not in writers:
                            writer = pq.ParquetWriter(path, arrow.schema, compression="zstd")
                            writers[path] = files.enter_context(writer)
                        writers[path].write_table(arrow)
                # ADR-0058: every grid point (ms) for the scenarios that own a grid, then any main delay off the grid
                # (severe's 60 s / 300 s thin-coin rule). A grid point that is a scenario's own delay is its main run.
                for h, runs in delay_plan(scenarios, horizons):
                    frame = order_inputs(
                        plan, sizing, bars, checks, mapping, tape, bands, origins, spreads, rules, start, end, h
                    )
                    for name, on_grid, main in runs:
                        settings = scenarios[name]
                        priced_by_anchor = {}
                        for model in variants:
                            if name == "optimistic" and model in ("sqrt", "sqrt_cap"):
                                continue  # zero impact shares the optimistic and optimistic_cap ledgers
                            sweep = SPEC[model].get("sweep", False)
                            if sweep not in priced_by_anchor:
                                priced_by_anchor[sweep] = quotes(frame, name, settings, params, sweep=sweep)
                            priced = priced_by_anchor[sweep]
                            label = canonical(name, model)
                            settings_used = settings_for(settings, model, rules)
                            orders = execute(priced, settings_used, rules, cap_marks=minute_marks if cap else None)
                            daily, fund, fills = value_book(
                                orders, u, marks, funding, start, end, rules["allocation_usdc"]
                            )
                            summary = summaries(
                                daily, orders, u, rules["allocation_usdc"], stress_floor(name, rules, settings)
                            )
                            if on_grid:
                                delays.setdefault(label, []).append(grid_rows(summary, h))
                            if not main:
                                continue
                            returns.setdefault(label, []).append(summary)
                            band_tables.setdefault(label, []).append(completed_trips(fills, fund, u))
                            if test:
                                cost_parts.setdefault(label, []).append(cost_totals(orders, u))
                            folder = dest / f"scenario={label}"
                            folder.mkdir(parents=True, exist_ok=True)
                            orders = orders.drop("cs_half_bps", "known_at", "valid_from", "valid_to", "param_reason")
                            for table, data in (
                                ("follower_orders", orders),
                                ("daily_copy_twr", daily),
                                ("funding_payments", fund),
                            ):
                                path = folder / (table + ".parquet")
                                arrow = data.rechunk().to_arrow()
                                if path not in writers:
                                    writers[path] = files.enter_context(
                                        pq.ParquetWriter(path, arrow.schema, compression="zstd")
                                    )
                                writers[path].write_table(arrow)
    owners = {}
    for name, settings in scenarios.items():
        for model in models:
            owners[canonical(name, model)] = canonical(grid_owner(name, settings), model)
    for label in sorted(returns):
        folder = dest / f"scenario={label}"
        owner = owners[label]  # severe reports the stress grid (same costs at each fixed delay); no copy is written
        grid = pl.concat(delays[owner]).sort("trader", "delay_ms")
        summary = pl.concat(returns[label]).join(delay_results(grid), on="trader").sort("trader")
        write(summary, folder, "address_summary")
        if owner == label:
            write(grid, folder, "delay_grid")
        write(combine_bands(band_tables[label]), folder, "band_break_even")
    if not test:
        return [], [], [], []
    comparisons, costs, trips, breaks = [], [], [], []
    for name in scenarios:
        for model in MODELS:
            label = canonical(name, model)
            # Variants computed in this run are staged in dest; earlier ones are read from their published folder.
            # A variant present in neither (not part of this output tree) is left out of the comparison.
            folder = (dest if (dest / f"scenario={label}").is_dir() else original) / f"scenario={label}"
            if not (folder / "address_summary.parquet").is_file():
                continue
            g = pl.read_parquet(folder / "address_summary.parquet").filter("all_gates_pass")
            tag = {"scenario": pl.lit(name), "variant": pl.lit(model), "artifact": pl.lit(label)}
            unmeasured = (
                (C("measurement") == "unmeasured_low_coverage").sum() if "measurement" in g.columns else pl.lit(0)
            )
            comparisons.append(
                g.select(
                    gate_passers=pl.len(),
                    measured=C("copy_return").count(),
                    unmeasured_low_coverage=unmeasured,
                    positive=(C("copy_return") > 0).sum(),
                    mean_return=C("copy_return").mean(),
                    unpriced=C("unpriced").sum(),
                    intents=C("orders").sum(),
                ).with_columns(**tag)
            )
            if label not in cost_parts:
                cost_parts[label] = [cost_totals(pl.read_parquet(folder / "follower_orders.parquet"), universe)]
            sums = (
                pl.concat(cost_parts[label])
                .group_by("universe", "coins", maintain_order=True)
                .agg(C("fills", "notional", "fee", "spread", "impact", "drift", "anchor").sum())
            )
            costs.append(
                sums.select(
                    "universe",
                    "coins",
                    "fills",
                    "notional",
                    *[
                        pl.when(C("notional") > 0).then(C(k) / C("notional")).alias(k + "_bps")
                        for k in ("fee", "spread", "impact", "drift", "anchor")
                    ],
                ).with_columns(**tag)
            )
            trips.append(pl.read_parquet(folder / "band_break_even.parquet").with_columns(**tag))
            keys = ["nonpositive_at_shortest", "crossing_bracket", "positive_through_grid", "unmeasured"]
            breaks.append(
                g.select(*[(C("break_even_delay_status") == k).sum().alias(k) for k in keys]).with_columns(**tag)
            )
    return comparisons, costs, trips, breaks


def filter_checks(checks: pl.DataFrame, kept: list[str]) -> pl.DataFrame:
    """ADR-A0140: every coin outside the rule's coin set gets outcome `coin_filter`, its price-check outcome kept in
    `price_check_outcome`. The follower never trades it (a passing coin is `coin_filter_excluded`, a failing one keeps
    its price-check status), the benchmark never trades it, and the cap book and resize legs (built on the passing
    coins) leave it out."""
    return checks.with_columns(
        price_check_outcome=C("outcome"),
        outcome=pl.when(~C("coin").is_in(sorted(kept))).then(pl.lit("coin_filter")).otherwise(C("outcome")))


def run_sensitivities(ctx, output=None, models=None, original=None, coin_sets=None, window=None, tradable=None,
                      allocation_usdc=None, traders=None, training=None):
    """Variants next to the original-model replay in `original` (default research/replay), written to `output`
    (default: the same folder). The original replay supplies the universe, drift cells, bands and spreads.

    `coin_sets` (ADR-A0140): {origin date: kept coins}; every window at that origin copies only those coins.
    `tradable` (ADR-0076): {origin date: (trader, coin) tradable pairs}; the cap plan stays the all-priced one and
    every other leg is `not_tradable`. The two options exclude each other.
    `window` = (origin, start, end) dates: replay that one test-shaped window only, with every input bounded at its
    end. It is the holdout path (origin 3 Dec, 3 Dec - 4 Jan, behind `freeze.guard`) and, for a development window,
    its check (it must reproduce the full run's window byte for byte).
    `allocation_usdc` (ADR-0095 item 3, P5-1): the sleeve size in place of execution.yaml's, with the gross cap at the
    same multiple; `traders`: replay only these addresses (every per-address input is unchanged).
    `training` = an origin date: replay that origin's training window only, with every input bounded at the origin
    (the cutoff selection, ADR-0100; at a development origin it must reproduce the full run's window byte for
    byte)."""
    assert_no_live_trading(ctx.root / "config")
    if coin_sets is not None and tradable is not None:
        raise ValueError("coin_sets (ADR-A0140) and tradable (ADR-0076) exclude each other")
    scenarios, rules = replay_settings(load_yaml("execution.yaml", ctx.root / "config"))
    if allocation_usdc is not None:
        rules["allocation_usdc"] = allocation_usdc
    rules["cap_usdc"] = rules["allocation_usdc"] * load_yaml("risk.yaml", ctx.root / "config")["gross_exposure_max_x"]
    dr = drift.DriftRules.from_config(ctx.raw)
    delay_plan(scenarios, dr.horizons_ms)  # every scenario delay is a grid point (checked before any work)
    stop = midnight(dr.holdout_start)
    origins = [midnight(o) for o in dr.origin_dates]
    if stop != origins[-1] or stop > ctx.cutoff:
        raise ValueError("invalid replay boundary")
    holdout = False
    if window is not None:
        w_origin, w_start, w_end = (midnight(d) for d in window)
        if w_origin not in origins or w_start != w_origin or w_end <= w_start or w_end > ctx.cutoff:
            raise ValueError(f"invalid single window {window}")
        holdout = w_end > stop
        if holdout:
            from arkstream.freeze import guard

            guard(ctx, w_end)  # the holdout runs only on the frozen rules
        stop = w_end  # every input is bounded at the window's end
    if training is not None:
        t_origin = midnight(training)
        if window is not None or t_origin not in origins:
            raise ValueError(f"invalid single training window {training}")
        stop = t_origin  # the training window ends at its origin
    original = Path(original) if original else ctx.root / "research/replay"
    if not (original / "drift_cells.parquet").is_file():
        run(ctx, output=original)
    origin_tables = {}
    last = midnight(dr.holdout_start)
    for origin in origins:
        for win in ["training"] if origin == last else ["training", "test"]:
            folder = original / f"origin={origin.date()}" / f"window={win}"
            # A prepare-only tree (ADR-0052) has the universe itself; a full replay has it in its base summary.
            path = folder / UNIVERSE
            if not path.is_file():
                path = folder / "scenario=base" / "address_summary.parquet"
            table = pl.read_parquet(
                path, columns=["trader", "return_source", "all_gates_pass", "hold_band", "leader_return", "leader_days"]
            )
            origin_tables[origin, win] = table if traders is None else table.filter(C("trader").is_in(list(traders)))
    candidate = pl.concat(list(origin_tables.values())).select("trader").unique()
    inputs = bounded_inputs(ctx, stop)
    first = midnight(inputs.fills["ts"].min().date())
    eligible = inputs.fills.filter(C("eligible") & (C("event_kind") == "trade")).join(
        candidate, on="trader", how="semi"
    )
    tape = trade_queries(ctx, eligible, dr, stop, basket=True, holdout=holdout)
    print("Prepared causal trade endpoints for basket resizes", flush=True)
    # ADR-0044: every window uses the price-check list as of its origin.
    checker = hlprices.PointInTimeCheck.load(ctx)
    checks_by = {origin: checker.checks(origin) for origin in origins}
    union = sorted(set().union(*(checker.passing(origin) for origin in origins)))
    mapping = load_map(ctx.path("binance_map")).select(
        "valid_from", "valid_to", "price_factor_hl_per_binance", coin="hl"
    )
    per_origin = {
        origin: parts[:5] for origin, parts in model_inputs_by_origin(ctx, inputs, stop, candidate, checks_by).items()
    }
    # Leader fill sizes give each batch its own notional, VWAP and deepest fill (ADR-0036).
    events = per_origin[origins[0]][0].join(inputs.fills.select("src_row", "size"), on="src_row", how="left")
    marks = per_origin[origins[0]][3]  # Hyperliquid daily closes: the same at every origin
    del inputs, eligible
    models = tuple(models or [m for m in MODELS if m != "original"])
    candles, _ = hlprices.load_candles(ctx.path("hyperliquid_dir"), stop)
    bars = impact_bars(candles, stop, rules["square_root"]["volatility_bars"])
    minute_marks = MinuteMarks.load(ctx.path("reference_prices_dir"), first, stop, union)
    bands = pl.read_parquet(original / "drift_hold_bands.parquet")
    spreads = pl.read_parquet(original / "spread_estimates.parquet")
    params = Parameters.from_rules(pl.read_parquet(original / "drift_cells.parquet"), rules)

    def shared_for(origin):
        _, snaps, _, _, funding = per_origin[origin]
        checks = checks_by[origin]
        if coin_sets is not None:  # ADR-A0140: the leader-side inputs above keep the unfiltered list
            checks = filter_checks(checks, coin_sets[origin.date()])
        shared = (events, snaps, bars, checks, mapping, tape, bands, dr.origin_dates, spreads, params,
                  marks, funding, minute_marks)
        if tradable is not None:  # ADR-0076: the origin's per-wallet sets; checks stay unfiltered
            return (*shared, tradable[origin.date()])
        return shared

    if training is not None:
        plan = [(t_origin, "training", first, t_origin)]
    elif window is None:
        plan = list(windows(origins, first, last))
    else:
        plan = [(w_origin, "test", w_start, w_end)]
        if (w_origin, "test") not in origin_tables:  # the holdout: the universe graded at its origin
            origin_tables[w_origin, "test"] = origin_tables[w_origin, "training"]
    target = Path(output) if output else original
    target.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=target.parent, prefix=".sensitivity-") as stage:
        dest = Path(stage)
        write(bars, dest, "impact_inputs")
        reports = [[], [], [], []]
        for origin, win, start, end in plan:
            rel = Path(f"origin={origin.date()}") / f"window={win}"
            tables = window_variants(
                dest / rel,
                original / rel,
                origin_tables[origin, win],
                start,
                end,
                shared_for(origin),
                scenarios,
                rules,
                dr.horizons_ms,
                win == "test",
                models,
            )
            for output_rows, parts in zip(reports, tables, strict=True):
                if parts:
                    output_rows.append(pl.concat(parts).with_columns(origin=pl.lit(origin.date())))
            print(f"{origin.date()} {win} sensitivities finished", flush=True)
        for name, parts, extra in zip(
            ("returns", "costs", "bands", "delays"),
            reports,
            ([], ["universe", "coins"], ["hold_band"], []),
            strict=True,
        ):
            if not parts:  # a single training window has no delay-grid rows (test windows only)
                continue
            pl.concat(parts).sort("origin", "scenario", "variant", *extra).write_csv(dest / f"sensitivity_{name}.csv")
        for path in sorted(dest.rglob("*")):
            if path.is_file():
                final = target / path.relative_to(dest)
                final.parent.mkdir(parents=True, exist_ok=True)
                path.replace(final)
