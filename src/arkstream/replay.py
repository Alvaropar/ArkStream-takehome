"""Offline Phase 3 walk-forward follower replay. The holdout has no test-window entry point."""

from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import polars as pl

from arkstream import drift, hlprices, leader, leader_assets, leader_book, leader_marks, leader_returns, quality
from arkstream.book_state import book_state
from arkstream.config import assert_no_live_trading, load_yaml
from arkstream.pipeline import Inputs, positions_asof
from arkstream.prices import scan_reference
from arkstream.refprices import load_map
from arkstream.replay_book import completed_trips, summaries, value_book
from arkstream.replay_market import DAY, bounded_inputs, midnight, trade_queries, vintages
from arkstream.replay_orders import (
    VOL_NOTE,
    Parameters,
    batches,
    delay_plan,
    execute,
    grid_owner,
    order_inputs,
    quotes,
    regime,
    resolve_scenarios,
)
from arkstream.replay_spreads import fit_spreads

C = pl.col
IDEALS = ("unattainable_passing", "unattainable_all")
ZERO = {"fee_bps": 0.0, "impact": "none", "half_spread_bps": {"majors": 0.0, "other": 0.0}}


def windows(origins, start, holdout):
    if sorted(set(origins)) != list(origins) or origins[-1] != holdout:
        raise ValueError("last origin must be holdout start")
    for i, origin in enumerate(origins):
        yield origin, "training", start, origin
        if origin < holdout:
            yield origin, "test", origin, origins[i + 1]


def delay_results(grid):
    """ADR-0032 break-even delay bracket per address from its delay grid (delays in ms, ADR-0058)."""
    by = {}
    for tr, h, ret, fills in grid.sort("trader", "delay_ms").select("trader", "delay_ms", "copy_return",
                                                                     "filled").rows():
        by.setdefault(tr, []).append((h, ret if fills else None))
    rows = []
    for tr, points in sorted(by.items()):
        prev = None
        lo = hi = None
        status = "positive_through_grid"
        for h, ret in points:
            if ret is None:
                status = "unmeasured"
                break
            if ret <= 0:
                status = "crossing_bracket" if prev else "nonpositive_at_shortest"
                lo, hi = prev, h
                break
            prev = h
        rows.append((tr, lo, hi, status))
    return pl.DataFrame(
        rows,
        orient="row",
        schema={
            "trader": pl.String,
            "break_even_delay_lo_ms": pl.Int64,
            "break_even_delay_hi_ms": pl.Int64,
            "break_even_delay_status": pl.String,
        },
    ).with_columns(
        break_even_delay_lo_s=C("break_even_delay_lo_ms") / 1000,
        break_even_delay_hi_s=C("break_even_delay_hi_ms") / 1000,
    )


def grid_rows(summary, delay_ms):
    """One delay-grid row per address: the result at a fixed delay (ms; `delay_s` is a readable copy)."""
    return summary.select(
        "trader", "copy_return", "before_funding", "filled", "unpriced_share",
        delay_ms=pl.lit(delay_ms, pl.Int64), delay_s=pl.lit(delay_ms / 1000, pl.Float64),
    )


def replay_settings(ex):
    """execution.yaml -> (scenarios with ms delays, replay rules). ADR-0058."""
    return resolve_scenarios(ex["scenarios"]), dict(ex["replay"])


def stress_floor(name, rules, settings=None):
    """ADR-0049/0055: the minimum priced share for a stress-regime result (stress, severe) to count as measured (None
    elsewhere)."""
    return rules["stress_min_priced_share"] if regime(name, settings) == "stress" else None


def write(df, directory, name):
    df.rechunk().write_parquet(directory / (name + ".parquet"), statistics=True)


def decision_frozen_flags(snaps, ledger, fills, asof, ref, passing):
    """ADR-0023 exact-interval freeze diagnosis using only series seen by the closing snapshot."""
    stale = snaps.filter("stale")
    endpoints = pl.concat(
        [stale.select("trader", "ts", "src_row"), stale.select("trader", ts="prev_ts", src_row="prev_src_row")]
    ).unique()
    state, _ = book_state(endpoints, ledger, asof, ref, passing, fills)
    # book_state counts every left-censored series before its first observation. An inherited
    # position first revealed AFTER the closing snapshot could not affect this earlier decision.
    inherited = (
        ledger.sort("trader", "symbol", "seq")
        .group_by("trader", "symbol")
        .first()
        .filter(C("pos_before").abs() > 1e-9)
        .select("trader", first_seen="ts")
    )
    future = stale.join(inherited, on="trader").filter(C("first_seen") > C("ts")).group_by("src_row").len(name="later")
    previous = state.select(
        "trader", prev_src_row="src_row", prev_value="value", prev_unknown="unpriced", prev_bad="bad_fees"
    )
    confirmed = (
        stale.join(state, on=["trader", "src_row", "ts"])
        .join(previous, on=["trader", "prev_src_row"])
        .join(future, on="src_row", how="left")
        .filter(
            (C("unpriced") + C("prev_unknown") == 2 * C("later").fill_null(0))
            & (C("bad_fees") == C("prev_bad"))
            & ((C("value") - C("prev_value")).abs() > 0.000001)
        )
    )
    return snaps.with_columns(frozen=C("src_row").is_in(confirmed["src_row"].implode()))


def model_inputs(ctx, inputs, stop, candidate, checks):
    """One origin's model inputs (see `model_inputs_by_origin`)."""
    return model_inputs_by_origin(ctx, inputs, stop, candidate, {None: checks})[None]


def model_inputs_by_origin(ctx, inputs, stop, candidate, checks_by):
    """Population-independent leader comparators, including addresses that later lose a grade, for each origin's
    price-check list (ADR-0044). The ledger, snapshots and price grid are shared; the frozen-snapshot diagnosis,
    the funding-price source and the leader's snapshot series depend on the origin's list."""
    fills = inputs.fills.join(candidate, on="trader", how="semi")
    traders = inputs.traders.join(candidate, on="trader", how="semi")
    ledger, _, _ = positions_asof(fills, stop)
    ledger = ledger.filter("eligible")
    ref = scan_reference(ctx.path("reference_prices_dir"))
    base_snaps, _ = quality.snapshot_flags(traders, stop, ctx.raw)
    candles, _ = hlprices.load_candles(ctx.path("hyperliquid_dir"), stop)
    union = sorted(set().union(*(set(c.filter(C("outcome") == "pass")["coin"]) for c in checks_by.values())))
    coins = sorted(set().union(*(set(c["coin"]) for c in checks_by.values())))
    grid = leader.price_grid(ctx, Inputs(traders, fills), coins, stop, union)
    rates = leader.load_funding(ctx, stop).with_columns(C("ts_hour").dt.cast_time_unit("ms"))
    acc_all = leader_returns.account_returns(traders, stop, ctx.raw["leader"])
    # ADR-0045: a breach flag belongs to its own snapshot, so it is known at that snapshot's time.
    snap_flags, _ = leader_assets.identity_breaches(traders, stop, ctx.raw["leader"]["return_source"])
    breach_rows = snap_flags.filter("breach")["src_row"]
    events = ledger.select(
        "trader",
        "seq",
        "price",
        "side",
        "tid",
        "oid",
        "src_row",
        "pos_after",
        "is_maker",
        "dir",
        coin="symbol",
        event_ms=C("ts").dt.epoch("ms"),
    )
    bars = candles.select(
        "coin", bar_ms=C("ts").dt.epoch("ms"), bar_volume_usdc=C("volume") * C("price"), volume_file="src_file"
    )
    out = {}
    for key, checks in checks_by.items():
        passing = checks.filter(C("outcome") == "pass")["coin"].to_list()
        flags = decision_frozen_flags(base_snaps, ledger, fills, stop, ref, passing)
        frozen = flags.filter("frozen")["src_row"].implode()
        snaps = flags.select("trader", "equity", "frozen", eq_ms=C("ts").dt.epoch("ms"), equity_row="src_row")
        _, daily_marks, proxy = leader_marks.price_panels(
            grid, candles, checks, stop, ctx.raw["funding"]["price_check"])
        marks, funding, snapshot = _origin_series(daily_marks, proxy, rates, acc_all, frozen, breach_rows, stop)
        out[key] = (
            events,
            snaps,
            bars,
            marks,
            funding,
            snapshot,
            (traders, ledger, daily_marks, proxy, rates, ref, fills, frozen),
        )
    return out


def _origin_series(daily_marks, proxy, rates, acc_all, frozen, breach_rows, stop):
    funding = (
        proxy.filter(C("ts_hour") < stop)
        .join(rates, on=["coin", "ts_hour"], how="left")
        .select(
            "coin",
            "price_ts",
            "price_file",
            "price_source",
            "funding_rate",
            "src_file",
            proxy="price",
            hour=C("ts_hour").dt.epoch("ms") // 3600000,
            known_ms=C("known_at").dt.epoch("ms"),
        )
    )
    marks = daily_marks.select("coin", "src_file", boundary=C("t").dt.epoch("ms") // DAY, mark="price")
    # The snapshot series is used only for snapshot-primary addresses, so ADR-0045's interval exclusion applies to
    # every address here: an interval touching a breaching snapshot is not part of the leader's return.
    rows = breach_rows.implode()
    acc = acc_all.filter(
        C("usable") & ~C("src_row").is_in(frozen) & ~C("prev_src_row").is_in(frozen)
        & ~C("src_row").is_in(rows) & ~C("prev_src_row").is_in(rows)
    )
    snapshot = acc.select(
        "trader", "prev_ts", "ts", "period_days", r="r_start", return_source=pl.lit(leader_assets.SNAPSHOT)
    )
    return marks, funding, snapshot


def leader_reference(ctx, origin, window, start, end, universe, snapshot, sources, with_series=False):
    if window == "training":
        from arkstream.config import research_dir

        series = pl.read_parquet(research_dir(ctx, "leader") / f"origin={origin.date()}" / "daily_twr.parquet")
        series = series.filter("usable").select("trader", "prev_ts", "ts", "period_days", "return_source", r="r_start")
    else:
        traders, ledger, marks, proxy, rates, ref, fills, frozen = sources
        book_ids = universe.filter(C("return_source") == leader_assets.BOOK).select("trader")
        led = ledger.join(book_ids, on="trader", how="semi").filter(C("ts") < end)
        pay = leader_marks.payments(led, rates.filter(C("ts_hour") < end), proxy, end)
        tr = traders.join(book_ids, on="trader", how="semi").filter(C("ts") <= end)
        daily, _ = leader_book.daily_book(
            tr, led, marks, pay, end, ref, fills, datetime.fromisoformat(ctx.raw["funding"]["start"])
        )
        daily = daily.filter(
            (C("missing_terms") == 0)
            & ~C("equity_src_row").is_in(frozen)
            & (C("equity_base") >= ctx.raw["leader"]["returns"]["min_open_equity_usdc"])
        )
        book = daily.select(
            "trader",
            C("day_start").alias("prev_ts"),
            "ts",
            period_days=pl.lit(1, pl.Int64),
            r="book_ret",
            return_source=pl.lit(leader_assets.BOOK),
        )
        series = pl.concat([book.select(snapshot.columns), snapshot], how="vertical_relaxed")
    ref = (
        series.filter((C("prev_ts") >= start) & (C("ts") <= end))
        .sort("trader", "ts")
        .group_by("trader", "return_source", maintain_order=True)
        .agg(leader_return=(1 + C("r")).product() - 1, leader_days=C("period_days").sum())
    )
    out = universe.join(ref, on=["trader", "return_source"], how="left").sort("trader")
    if not with_series:
        return out
    # ADR-0063: the same series, per period, for the capture's daily leader TWR
    inside = (
        series.filter((C("prev_ts") >= start) & (C("ts") <= end))
        .join(universe.select("trader", "return_source"), on=["trader", "return_source"], how="semi")
        .select("trader", "return_source", "prev_ts", "ts", "period_days", "r")
        .sort("trader", "ts", "prev_ts")
    )
    return out, inside


def simulate_window(directory, universe, start, end, market, scenarios, rules, horizons):
    """The original model on one window. `horizons`: the delay grid in ms; each scenario's main run is its own delay
    (a grid point, or its thin-coin rule); a scenario borrowing its costs shares its regime's grid (ADR-0058)."""
    events, snaps, bars, checks, mapping, tape, bands, origins, spread, params, marks, funding = market
    wk = events.join(universe.select("trader"), on="trader", how="semi")
    regular = batches(wk, rules["receive_ms"], rules["debounce_ms"], start, end)
    instant = batches(wk, 0, 0, start, end, ideal=True)
    results, grids, band_tables = {}, {}, {}
    plan = [(0, [(name, False, True) for name in IDEALS]), *delay_plan(scenarios, horizons)]
    for delay, runs in plan:
        settings_by_name = dict.fromkeys(IDEALS, ZERO) if delay == 0 else scenarios
        frame = order_inputs(
            instant if delay == 0 else regular,
            snaps,
            bars,
            checks,
            mapping,
            tape,
            bands,
            origins,
            spread,
            rules,
            start,
            end,
            delay,
        )
        for name, on_grid, main in runs:
            settings = settings_by_name[name]
            orders = execute(quotes(frame, name, settings, params), settings, rules, ideal=delay == 0)
            daily, fund, f = value_book(orders, universe, marks, funding, start, end, rules["allocation_usdc"])
            summary = summaries(daily, orders, universe, rules["allocation_usdc"], stress_floor(name, rules, settings))
            if on_grid:
                grids.setdefault(name, []).append(grid_rows(summary, delay))
            if main:
                dest = directory / f"scenario={name}"
                dest.mkdir(parents=True, exist_ok=True)
                write(
                    orders.drop("cs_half_bps", "known_at", "valid_from", "valid_to", "param_reason"),
                    dest,
                    "follower_orders",
                )
                write(daily, dest, "daily_copy_twr")
                write(fund, dest, "funding_payments")
                results[name] = summary
                band_tables[name] = completed_trips(f, fund, universe)
                write(band_tables[name], dest, "band_break_even")
    benchmark = results[IDEALS[0]].select(
        "trader",
        unattainable_passing_return=C("copy_return"),
        passing_pnl=C("final_equity") - rules["allocation_usdc"],
        passing_pre_funding_pnl=C("pre_final_equity") - rules["allocation_usdc"],
        passing_funding="funding_paid",
    )
    benchmark = benchmark.join(
        results[IDEALS[1]].select(
            "trader",
            all_coins_upper=C("copy_return"),
            all_coin_pnl=C("final_equity") - rules["allocation_usdc"],
            all_coin_pre_funding_pnl=C("pre_final_equity") - rules["allocation_usdc"],
            all_coin_funding="funding_paid",
        ),
        on="trader",
    ).with_columns(
        excluded_pnl_at_leader_prices=C("all_coin_pnl") - C("passing_pnl"),
        excluded_trading_pnl=C("all_coin_pre_funding_pnl") - C("passing_pre_funding_pnl"),
        excluded_funding=C("all_coin_funding") - C("passing_funding"),
    )
    for name, summary in results.items():
        dest = directory / f"scenario={name}"
        owner = grid_owner(name, scenarios.get(name, {}))
        if owner in grids:
            grid = pl.concat(grids[owner]).sort("trader", "delay_ms")
            if owner == name:  # a scenario that borrows its costs reports its regime's grid, not a copy of it
                write(grid, dest, "delay_grid")
            summary = summary.join(delay_results(grid), on="trader")
        results[name] = summary.join(benchmark, on="trader").sort("trader")
        write(results[name], dest, "address_summary")
    return results, band_tables


UNIVERSE = "universe.parquet"  # per window: the copy universe and leader reference return (prepare-only runs)


def run(ctx, output=None, simulate=True):
    """The original-model replay into `output` (default research/replay). With `simulate=False` only the shared
    inputs are written (spreads, drift cells and bands, valuation marks and each window's `universe.parquet`); no
    scenario is simulated, so nothing is sized on the dynamic denominator (ADR-0052: frozen only)."""
    assert_no_live_trading(ctx.root / "config")
    scenarios, rules = replay_settings(load_yaml("execution.yaml", ctx.root / "config"))
    dr = drift.DriftRules.from_config(ctx.raw)
    delay_plan(scenarios, dr.horizons_ms)  # every scenario delay is a grid point (checked before any work)
    origins = [midnight(o) for o in dr.origin_dates]
    stop = midnight(dr.holdout_start)
    if stop != origins[-1] or stop > ctx.cutoff:
        raise ValueError("invalid replay boundary")
    from arkstream.freeze import guard

    guard(ctx, stop)  # ADR-A0139: a window ending after the holdout start needs the freeze
    inputs = bounded_inputs(ctx, stop)
    from arkstream.config import research_dir

    origin_path = research_dir(ctx, "leader")
    origin_tables = {}
    for origin in origins:
        ev = pl.read_parquet(origin_path / f"origin={origin.date()}" / "evidence.parquet")
        origin_tables[origin] = ev.select("trader", "return_source", "all_gates_pass", "hold_band").with_columns(
            C("hold_band").fill_null("no_closed_trip")
        )
    candidates = pl.concat(list(origin_tables.values())).select("trader").unique()
    # ADR-0044: the training window at origin o and the test window [o, next origin) use the origin-o list.
    checker = hlprices.PointInTimeCheck.load(ctx)
    checks_by = {origin: checker.checks(origin) for origin in origins}
    mapping = load_map(ctx.path("binance_map")).select(
        "valid_from", "valid_to", "price_factor_hl_per_binance", coin="hl"
    )
    tape = trade_queries(ctx, inputs.fills, dr, stop)
    cells, bands = vintages(ctx, inputs, dr, tape, stop)
    first = midnight(inputs.fills["ts"].min().date())
    spread = fit_spreads(
        inputs.fills,
        checker.coins,
        origins[0],
        origins[1],
        rules["spreads"],
        scenarios["base"]["half_spread_bps"],
    )
    print("Prepared drift and spread inputs", flush=True)
    for name, settings in scenarios.items():
        w = settings["half_spread_bps"]
        configured = pl.when(C("coin").is_in(["BTC", "ETH"])).then(w["majors"]).otherwise(w["other"])
        spread = spread.with_columns(
            pl.max_horizontal(configured, "cs_half_bps").alias(name + "_half_bps"),
            (C("cs_half_bps") > configured).fill_null(False).alias(name + "_raised"),
        )
    per_origin = model_inputs_by_origin(ctx, inputs, stop, candidates, checks_by)
    params = Parameters.from_rules(cells, rules)

    def market_for(origin):
        events, snaps, bars, marks, funding, _, _ = per_origin[origin]
        return (events, snaps, bars, checks_by[origin], mapping, tape, bands, dr.origin_dates, spread, params, marks,
                funding)

    target = Path(output) if output else ctx.root / "research/replay"
    target.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=target.parent, prefix=".replay-") as stage:
        dest = Path(stage)
        write(spread, dest, "spread_estimates")
        write(cells, dest, "drift_cells")
        write(bands, dest, "drift_hold_bands")
        write(per_origin[origins[0]][3], dest, "valuation_marks")  # Hyperliquid closes: the same at every origin
        report_rows, band_rows = [], []
        for origin, window, start, end in windows(origins, first, stop):
            folder = dest / f"origin={origin.date()}" / f"window={window}"
            _, _, _, _, _, snapshot, sources = per_origin[origin]
            universe, series = leader_reference(ctx, origin, window, start, end, origin_tables[origin], snapshot,
                                                sources, with_series=True)
            if not simulate:
                folder.mkdir(parents=True, exist_ok=True)
                write(universe, folder, UNIVERSE.removesuffix(".parquet"))
                write(series, folder, "leader_series")
                print(f"{origin.date()} {window} universe prepared", flush=True)
                continue
            results, bt = simulate_window(
                folder, universe, start, end, market_for(origin), scenarios, rules, dr.horizons_ms)
            for name in scenarios:
                g = results[name].filter("all_gates_pass")
                report_rows.append(
                    dict(
                        origin=origin.date(),
                        window=window,
                        scenario=name,
                        gate_passers=len(g),
                        positive=g.filter(C("copy_return") > 0).height,
                        measured=g["copy_return"].count(),
                        unmeasured_low_coverage=(g["measurement"] == "unmeasured_low_coverage").sum(),
                        traded=g.filter(C("filled") > 0).height,
                        under_minus_10pct=g.filter(
                            (C("measurement") == "measured") & ((C("copy_return") < -0.10) | C("exhausted"))
                        ).height,
                        drawdown_over_10pct=g.filter(C("max_drawdown") < -0.10).height,
                        base_positive_pre_and_post=g.filter((C("copy_return") > 0) & (C("before_funding") > 0)).height,
                        mean_copy_return=g["copy_return"].mean(),
                        excluded_intents=results[name]["excluded"].sum(),
                        excluded_intended_usdc=results[name]["excluded_notional"].sum(),
                        excluded_benchmark_pnl_usdc=results[name]["excluded_pnl_at_leader_prices"].sum(),
                        excluded_benchmark_measured=results[name]["excluded_pnl_at_leader_prices"].count(),
                        total_addresses=len(results[name]),
                        skipped_unpriced=g["unpriced"].sum(),
                        intents=g["orders"].sum(),
                        priced_share=1 - g["unpriced"].sum() / g["orders"].sum() if g["orders"].sum() else None,
                    )
                )
                band_rows.append(
                    bt[name].with_columns(origin=pl.lit(origin.date()), window=pl.lit(window), scenario=pl.lit(name))
                )
            print(f"{origin.date()} {window} finished", flush=True)
        if simulate:
            counts = pl.DataFrame(report_rows).sort("origin", "window", "scenario")
            band_summary = pl.concat(band_rows).sort("origin", "window", "scenario", "hold_band")
            counts.write_csv(dest / "economic_screen.csv")
            band_summary.write_csv(dest / "band_break_even.csv")
            reporting(dest, counts, band_summary)
        # Prepare the complete run before publishing. Replacing each existing file is atomic.
        for path in sorted(dest.rglob("*")):
            if path.is_file():
                final = target / path.relative_to(dest)
                final.parent.mkdir(parents=True, exist_ok=True)
                path.replace(final)


def reporting(dest, counts, bands):
    report = [
        "# Phase 3 development replay",
        "",
        "Counts show gate-passing addresses with positive funded copy return on a 10,000 USDC allocation.",
        "",
    ]
    for (origin,), g in counts.group_by("origin", maintain_order=True):
        lines = [
            f"## {origin}",
            "",
            "| Window | Scenario | Positive / measured / gate-passers | Traded | Unpriced / intents "
            "| Drawdown over 10% |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
        for r in g.iter_rows(named=True):
            lines.append(
                f"| {r['window']} | {r['scenario']} | {r['positive']} / {r['measured']} / {r['gate_passers']} | "
                f"{r['traded']} | {r['skipped_unpriced']} / {r['intents']} | {r['drawdown_over_10pct']} |"
            )
        for win in sorted(set(g["window"])):
            b = bands.filter(
                (C("origin") == origin)
                & (C("window") == win)
                & (C("scenario") == "base")
                & (C("hold_band") != "no_closed_trip")
                & (C("net_bps") > 0)
            )
            lines.extend(
                [
                    "",
                    f"Base {win} bands with positive mean funded net PnL per completed trip were "
                    + (", ".join(b["hold_band"]) or "none")
                    + ".",
                ]
            )
            row = g.filter((C("window") == win) & (C("scenario") == "base")).row(0, named=True)
            lines.append(
                "Across the A/B universe the price-check rule as of the origin (ADR-0044) excluded "
                f"{row['excluded_intents']:,} base "
                f"intents in {win}. The omitted contribution at leader prices was "
                f"{row['excluded_benchmark_pnl_usdc']:,.2f} USDC across "
                f"{row['excluded_benchmark_measured']}/{row['total_addresses']} measurable comparisons."
            )
        lines.extend(["", VOL_NOTE, ""])
        (dest / f"origin={origin}" / "summary.md").write_text("\n".join(lines), encoding="utf8")
        report.extend(lines)
    test = (
        bands.filter(
            (C("window") == "test")
            & (C("scenario") == "base")
            & (C("hold_band") != "no_closed_trip")
            & (C("net_bps") > 0)
        )
        .group_by("hold_band")
        .len()
    )
    consistent = sorted(test.filter(C("len") == counts.filter(C("window") == "test")["origin"].n_unique())["hold_band"])
    base = counts.filter((C("window") == "test") & (C("scenario") == "base")).sort("origin")
    observed = ", ".join(f"{p}/{n}" for p, n in base.select("positive", "gate_passers").rows())
    report[4:4] = [
        f"The base scenario produced positive funded copies for {observed} gate-passers "
        "in successive development tests.",
        f"The holding bands clearing mean round-trip costs in every test were {', '.join(consistent) or 'none'}.",
        "The first delay break-even screen passes for further research. At least one holding band cleared "
        "realised costs and gate-passing addresses earned positive base returns in every development test."
        if consistent and base["positive"].min() > 0
        else "The development tests do not establish a persistent positive band and base-copy result.",
        "Individual address stress drawdowns and pricing coverage constrain that finding. The October 8 "
        "origin has no prior crash sample for parameterised stress orders; stress results with less than 80% "
        "priced intents are unmeasured (ADR-0049). Training includes the period before "
        "the September 8 archive start. Returns include the cash left idle after skipped signals.",
        "",
    ]
    (dest / "summary.md").write_text("\n".join(report), encoding="utf8")
