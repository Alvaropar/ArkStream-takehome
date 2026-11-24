"""Phase 2 point-in-time address evidence, funded books and suitability gate counts."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl

from arkstream import hlprices, leader_assets, leader_book, leader_marks
from arkstream import leader_returns as lr
from arkstream import leader_risk as lk
from arkstream import leader_trips as lt
from arkstream import leader_worstcase as lw
from arkstream.book_state import book_state
from arkstream.config import Context, assert_no_live_trading
from arkstream.pipeline import Inputs, build, effective_asof, positions_asof
from arkstream.positions import pit
from arkstream.prices import scan_reference

TABLES = [
    "account_returns",
    "account_coverage",
    "book_hourly",
    "book_daily",
    "book_vs_account",
    "round_trips",
    "trip_summary",
    "stress_shocks",
    "gates",
    "profiles",
    "evidence",
    "daily_marks",
    "funding_payments",
    "snapshot_marks",
    "daily_twr",
    "twr_summary",
    "gap_path",
    "market_exposure",
    "market_sample",
    "book_attribution",
    "worstcase_dd",
    "worstcase_check",
]


def origins(ctx: Context) -> list[datetime]:
    return [datetime.combine(date.fromisoformat(str(o)), datetime.min.time(), UTC) for o in ctx.raw["drift"]["origins"]]


def load_funding(ctx: Context, asof: datetime) -> pl.DataFrame:
    return pl.scan_parquet(ctx.root / ctx.raw["leader"]["funding"]).filter(pl.col("known_at") <= asof).collect()


def price_grid(ctx: Context, inputs: Inputs, coins: list[str], asof: datetime,
               query: list[str] | None = None) -> pl.DataFrame:
    """Binance reference at every hour for the `query` coins (default: those passing the price check as of asof,
    ADR-0044); other coins get null prices. Consumers mask by their own origin's list (`leader_marks.price_panels`),
    so a grid built for the union of several origins' lists serves each of them."""
    from arkstream.prices import price_asof

    start = datetime.fromisoformat(ctx.raw["leader"]["price_history_start"]).replace(tzinfo=UTC)
    hours = pl.datetime_range(start, asof, "1h", time_zone="UTC", time_unit="ms", eager=True)
    q = pl.DataFrame({"coin": coins}, schema={"coin": pl.String}).join(pl.DataFrame({"t": hours}), how="cross")
    if query is None:
        query = hlprices.PointInTimeCheck.load(ctx).passing(asof)
    check = pl.DataFrame({"coin": sorted(query)}, schema={"coin": pl.String})
    sources = price_asof(
        q.join(check, on="coin", how="semi"),
        scan_reference(ctx.path("reference_prices_dir")),
        inputs.fills.clear(),
        asof,
        60,
        0,
    )
    return q.join(
        sources.select("coin", "t", "price", "price_source", ref_ts="price_ts", ref_file="price_ref_file"),
        on=["coin", "t"],
        how="left",
    ).sort("coin", "t")


def not_copyable_exposure(fills: pl.DataFrame, passing: list[str]) -> pl.DataFrame:
    """ADR-0047: each address's perp notional to the origin and the shares the replay cannot copy: core perps not
    passing the price check at this origin, and HIP-3. Spot is in neither numerator nor denominator."""
    perp = fills.filter(pl.col("is_perp") & (pl.col("event_kind") == "trade"))
    n = pl.col("notional")
    out = perp.group_by("trader").agg(
        perp_notional_to_origin=n.sum(),
        notional_not_passing=n.filter(pl.col("eligible") & ~pl.col("symbol").is_in(sorted(passing))).sum(),
        notional_hip3=n.filter(pl.col("instrument_class") == "hip3").sum(),
    )
    share = pl.when(pl.col("perp_notional_to_origin") > 0)
    return out.with_columns(
        share_not_passing=share.then(pl.col("notional_not_passing") / pl.col("perp_notional_to_origin")),
        share_hip3=share.then(pl.col("notional_hip3") / pl.col("perp_notional_to_origin")),
    ).with_columns(share_not_copyable=pl.col("share_not_passing") + pl.col("share_hip3")).sort("trader")


def compute(
    ctx: Context,
    inputs: Inputs,
    asof: datetime,
    px: pl.DataFrame | None = None,
    volume: pl.DataFrame | None = None,
    funding: pl.DataFrame | None = None,
    candles: pl.DataFrame | None = None,
    ohlc: pl.DataFrame | None = None,
    extremes: pl.DataFrame | None = None,
    price_check: hlprices.PointInTimeCheck | None = None,
    beyond_last_origin: bool = False,
) -> dict[str, pl.DataFrame]:
    """Every leader-evidence table at asof for the addresses graded A/B at asof.

    `beyond_last_origin`: the holdout's trigger series at the window end (ADR-0099 item 11), after the last configured
    origin and only behind `freeze.guard`."""
    assert_no_live_trading(ctx.root / "config")
    t = effective_asof(ctx, asof)
    rules = ctx.raw["leader"]
    if t > max(origins(ctx)):
        if not beyond_last_origin:
            raise ValueError("Phase 2 ends at the final configured origin")
        from arkstream.freeze import guard

        guard(ctx, t)
    quality = build(ctx, inputs, t).tables
    report = quality["quality_report"]
    frozen = quality["quality_evidence"].filter(pl.col("flag") == "frozen_snapshot")["src_row"]
    del quality
    graded = report.filter(pl.col("grade").is_in(rules["grades"]))
    # ADR-0045: material and persistent identity breaches known by the origin choose the rebuilt book.
    snap_flags, breaches = leader_assets.identity_breaches(
        pit(inputs.traders, t).join(graded.select("trader"), on="trader", how="semi"), t, rules["return_source"])
    uni = graded.select(
        "trader", "grade", "grade_reason", "pnl_rows_gt_tight", "pnl_match_share",
        return_source_adr0065=leader_assets.primary_source(),
    ).join(breaches, on="trader", how="left").with_columns(
        return_source=leader_assets.material_source(rules["return_source"]))
    keep = pl.col("trader").is_in(uni["trader"].implode())
    fills, traders = pit(inputs.fills, t).filter(keep), pit(inputs.traders, t).filter(keep)

    ledger, trips, open_pos = positions_asof(fills, t)
    elig = fills.filter("eligible").select("symbol").unique()
    ledger = ledger.filter("eligible")
    trips = trips.join(elig, on="symbol", how="semi")
    open_pos = open_pos.join(elig, on="symbol", how="semi")
    # ADR-0044: the price-check outcome as of this origin, never the CUTOFF list.
    checker = hlprices.PointInTimeCheck.load(ctx) if price_check is None else price_check
    outcomes = checker.checks(t)
    passing = checker.passing(t)
    coins = outcomes["coin"].to_list()
    px = (
        price_grid(ctx, inputs, coins, t, passing) if px is None
        else px.filter((pl.col("t") <= t) & pl.col("coin").is_in(coins))
    )

    ref = scan_reference(ctx.path("reference_prices_dir"))
    if candles is None:
        candles, _ = hlprices.load_candles(ctx.path("hyperliquid_dir"), t)
    px, daily_marks, proxies = leader_marks.price_panels(px, candles, outcomes, t, ctx.raw["funding"]["price_check"])
    rates = load_funding(ctx, t) if funding is None else funding
    pay = leader_marks.payments(ledger, rates, proxies, t)
    acc = lr.account_returns(traders, t, rules)
    stale_endpoint = pl.col("src_row").is_in(frozen.implode()) | pl.col("prev_src_row").is_in(frozen.implode())
    acc = acc.with_columns(
        usable=pl.col("usable") & ~stale_endpoint,
        exclude_reason=pl.when(stale_endpoint).then(pl.lit("frozen_snapshot")).otherwise("exclude_reason"),
    )
    cov = lr.account_coverage(acc, traders, t)
    hourly, marks = lr.book_hourly(ledger, px, traders, t, pay)
    hourly = hourly.with_columns(
        price_source=pl.lit("binance_1m"),
        validation=pl.when("priced").then(pl.lit("validated")).otherwise(pl.lit("unvalidated")),
    )
    feed_start = datetime.fromisoformat(ctx.raw["funding"]["start"])
    daily, boundary = leader_book.daily_book(traders, ledger, daily_marks, pay, t, ref, fills, feed_start)
    state, snapshot_marks = book_state(traders, ledger, t, ref, passing, fills)
    state = leader_book.funded_state(state, pay, t)
    xc_rows, xc = leader_book.intervals(acc, state, fills, t, feed_start, rules)
    # ADR-0045: where the snapshot series is primary, intervals touching a breaching snapshot leave it (reason kept);
    # coverage, fit and the account risk view above keep every interval.
    snap_primary = uni.filter(pl.col("return_source") == leader_assets.SNAPSHOT)["trader"]
    acc_series = leader_assets.exclude_breaches(acc, snap_flags.filter("breach")["src_row"], snap_primary)
    snapshot = leader_assets.twr_series(acc_series, t).join(
        uni.select("trader", return_role=pl.when(pl.col("return_source") == leader_assets.BOOK)
                   .then(pl.lit("check_only")).otherwise(pl.lit("primary"))),
        on="trader", how="left",
    ).sort("trader", "ts", "src_row")
    twr = leader_assets.primary_series(snapshot.drop("return_role"), daily, uni, frozen, t,
                                      rules["returns"]["min_open_equity_usdc"])
    gaps = leader_assets.gap_path(
        twr.join(xc_rows.select("trader", "src_row", "scope"), on=["trader", "src_row"]), state, boundary, t
    )
    primary_cov = lr.account_coverage(twr, traders, t).rename({"account_coverage": "return_coverage"})
    assets, market, sample = leader_assets.asset_tables(twr, daily_marks, gaps, primary_cov, t)
    snap_check = snapshot.filter("usable").group_by("trader").agg(
        snapshot_twr_check=pl.col("index_start").last() - 1,
        snapshot_twr_end_check=pl.col("index_end").last() - 1,
    )
    book_twr = leader_assets.book_check(daily, frozen, t, rules["returns"]["min_open_equity_usdc"])
    assets = (assets.join(uni.select("trader", "return_source"), on="trader")
              .join(cov.select("trader", "account_coverage"), on="trader")
              .join(snap_check, on="trader", how="left")
              .join(book_twr, on="trader", how="left")
              .with_columns(pl.col("book_days_check").fill_null(0)))
    market = market.join(uni.select("trader", "return_source"), on="trader")
    at = t.replace(hour=0, minute=0, second=0, microsecond=0)
    open_marks = open_pos.select("trader", "symbol").join(
        daily_marks.filter(pl.col("t") == at).select(
            symbol="coin", mark_price="price", mark_source="price_source", validation="validation"
        ),
        on="symbol",
        how="left",
    )
    rt = lt.round_trips(trips, ledger, marks, open_marks, t, rules, pay)
    rt = rt.join(open_marks.select("trader", "symbol", "validation"), on=["trader", "symbol"], how="left").with_columns(
        price_source=pl.col("mark_source"),
        validation=pl.when(pl.col("status") == "open_at_asof").then("validation"),
        excursion_status=pl.when(pl.col("mae").is_null()).then(pl.lit("unavailable")).otherwise(pl.lit("binance_1m")),
    )
    ts = lt.trip_summary(rt, rules)
    lineage = fills.filter(pl.col("eligible") & (pl.col("event_kind") == "trade")).sort("trader", "ts", "src_row")
    lineage = lineage.group_by("trader").agg(
        last_fill_src_row=pl.col("src_row").last(),
        tid=pl.col("tid").last(),
        oid=pl.col("oid").last(),
        last_fill_ts=pl.col("ts").last(),
    )
    lineage = (
        traders.sort("trader", "ts", "src_row")
        .group_by("trader")
        .agg(snapshot_src_row=pl.col("src_row").last(), snapshot_ts=pl.col("ts").last())
        .join(lineage, on="trader", how="left")
    )
    validation = twr.filter("usable").group_by("trader").agg(
        validation=pl.when((pl.col("validation") == "flagged").any()).then(pl.lit("flagged"))
        .when((pl.col("validation") == "unvalidated").any()).then(pl.lit("unvalidated")).otherwise(pl.lit("validated")))
    assets = (assets.join(lineage, on="trader", how="left").join(validation, on="trader", how="left")
              .with_columns(validation=pl.col("validation").fill_null("unvalidated"),
                            price_source=pl.when(pl.col("return_source") == leader_assets.BOOK)
                            .then(pl.lit("hyperliquid_4h")).otherwise(pl.lit("hyperliquid_snapshot")))
              .sort("trader"))
    market = market.join(lineage, on="trader", how="left").with_columns(price_source=pl.lit("hyperliquid_4h"))
    factor_status = sample.group_by("trader").agg(
        any_flagged=pl.any_horizontal(pl.col("BTC_validation", "ETH_validation") == "flagged").any(),
        any_unvalidated=pl.any_horizontal(pl.col("BTC_validation", "ETH_validation") == "unvalidated").any(),
    )
    market = market.join(factor_status, on="trader", how="left").sort("trader").with_columns(
        validation=pl.when(pl.col("any_unvalidated").fill_null(True))
        .then(pl.lit("unvalidated"))
        .when("any_flagged")
        .then(pl.lit("flagged"))
        .otherwise(pl.lit("validated"))
    )

    sh = lk.shocks(px, t, int(rules["risk"]["stress_horizon_h"]))
    metrics = lk.risk_metrics(hourly, daily, acc, marks, sh, fills, t, rules)
    # ADR-0039: worst case inside each 4h bar (Hyperliquid OHLC; Binance 1m highs/lows as a recorded check).
    if ohlc is None:
        ohlc = hlprices.load_candles_ohlc(ctx.path("hyperliquid_dir"), t)
    if extremes is None:
        from arkstream import refprices as rf

        extremes = lw.binance_extremes(ctx.path("binance_lake"), rf.load_map(ctx.path("binance_map")), passing, t)
    wc, wc_check = lw.worstcase(
        ledger, ohlc.filter(pl.col("ts") <= t),
        extremes.filter((pl.col("bar_ms") <= int(t.timestamp() * 1000)) & pl.col("coin").is_in(passing)),
        traders, feed_start, t,
    )
    metrics = metrics.join(wc, on="trader", how="left")
    prof = lk.profiles(
        fills, rt, traders, volume.filter(pl.col("coin").is_in(passing)) if volume is not None else None, t, rules
    )

    ev = (
        uni.join(assets, on=["trader", "return_source"], how="left")
        .join(
            market.select(
                "trader",
                "alpha",
                "alpha_lo",
                "alpha_hi",
                "beta_btc",
                "beta_btc_lo",
                "beta_btc_hi",
                "beta_eth",
                "beta_eth_lo",
                "beta_eth_hi",
                "r_squared",
                "n_days",
                "market_coverage",
                pl.col("validation").alias("market_validation"),
            ),
            on="trader",
            how="left",
        )
        .join(xc, on="trader", how="left")
        .join(ts, on="trader", how="left")
        .join(metrics, on="trader", how="left")
        .join(
            prof.select(
                "trader",
                "days_since_fill",
                "median_hold_s",
                "hold_p10_s",
                "hold_p25_s",
                *[c for c in prof.columns if c.startswith("short_")],
                "turnover_equity_per_day",
                "hold_band",
                "orders_per_day",
                "maker_share",
                "maker_heavy",
                "fee_rate_bps",
                "median_equity",
                "equity_in_band",
                *[c for c in ("order_to_volume_bps_median", "order_to_volume_bps_p95") if c in prof.columns],
            ),
            on="trader",
            how="left",
        )
    )
    ev = ev.with_columns(pl.col("rt_closed", "rt_open_valued", "rt_censored").fill_null(0)).join(
        not_copyable_exposure(fills, passing), on="trader", how="left")
    # ADR-0067 gate_history (moved from Phase 4): distinct UTC snapshot dates known by the origin
    snap_days = traders.group_by("trader").agg(snapshot_days=pl.col("ts").dt.date().n_unique())
    ev = ev.join(snap_days, on="trader", how="left")
    gates = lk.apply_gates(ev, rules)
    stamp = {"asof": pl.lit(t).dt.cast_time_unit("ms"), "funding_status": pl.lit("included")}
    gate_view = gates.select(
        "trader", "grade", "snapshot_src_row", "snapshot_ts", "last_fill_src_row", "tid", "oid", "last_fill_ts",
        "return_source", "return_coverage", "account_coverage", "fit_coverage", *lk.GATE_COLS, *lk.CATEGORY_COLS,
        "gates_failed", "gates_unmeasured", "style_flags", "all_gates_pass", **stamp
    )
    tables = {
        "book_attribution": leader_book.attribution(xc_rows, t),
        "funding_payments": pay,
        "daily_marks": daily_marks,
        "snapshot_marks": snapshot_marks,
        "daily_twr": twr,
        "twr_summary": assets,
        "gap_path": gaps,
        "market_exposure": market,
        "market_sample": sample,
        "account_returns": snapshot,
        "account_coverage": cov.with_columns(asof=stamp["asof"]),
        "book_hourly": hourly.join(fills.select(first_src_row="src_row", tid="tid", oid="oid", fill_ts="ts"),
                                  on="first_src_row",how="left").sort("trader","hour_end"),
        "book_daily": daily,
        "book_vs_account": xc_rows,
        "round_trips": rt,
        "trip_summary": ts.with_columns(**stamp),
        "stress_shocks": sh,
        "gates": gate_view.sort("trader"),
        "profiles": prof,
        "evidence": gates.with_columns(**stamp).sort("trader"),
        "worstcase_dd": wc,
        "worstcase_check": wc_check,
    }
    return {name: table.with_columns(asof=stamp["asof"]) for name, table in tables.items()}


def gate_counts(gates: pl.DataFrame, origin: date) -> pl.DataFrame:
    rows = []
    for c in [*lk.GATE_COLS, *lk.CATEGORY_COLS, "all_gates_pass"]:
        v = gates[c].cast(pl.String).replace({"true": "pass", "false": "fail"})
        vc = dict(zip(*v.value_counts().sort(c).to_dict(as_series=False).values(), strict=True))
        rows.append(
            {
                "origin": origin.isoformat(),
                "gate": c,
                "universe": gates.height,
                "pass": int(vc.get("pass", 0)),
                "fail": int(vc.get("fail", 0)),
                "unmeasured": int(vc.get("unmeasured", 0)),
            }
        )
    return pl.DataFrame(rows)


def summary_md(tables: dict[str, pl.DataFrame], counts: pl.DataFrame, origin: date) -> str:
    ev, sh = tables["evidence"], tables["stress_shocks"]
    crash = sh.filter(pl.col("shock_down_end").dt.date().is_in([date(2025, 10, 10), date(2025, 10, 11)]))
    marked_open = tables["round_trips"].filter((pl.col("status")=="open_at_asof") & pl.col("mark_price").is_not_null())
    q = ev.select(
        n=pl.len(),
        a=(pl.col("grade") == "A").sum(),
        b=(pl.col("grade") == "B").sum(),
        book=(pl.col("return_source") == leader_assets.BOOK).sum(),
        cov=pl.col("account_coverage").median(),
        rt=pl.col("rt_closed").median(),
        rt_open=pl.lit(marked_open.height),
        unp=pl.col("unpriced_exposure_share").median(),
        nc=pl.col("share_not_copyable").median(),
        xc_ok=(pl.col("xc_flag") == "ok").sum(),
        corr=pl.col("xc_corr").median(),
    ).row(0, named=True)
    lines = [
        f"# Leader evidence as of {origin.isoformat()} 00:00 UTC",
        "",
        "Core-perp books and round trips include Hyperliquid funding. Gate thresholds are placeholders.",
        "",
        f"- Universe: {q['n']} addresses graded A or B at this origin (A {q['a']}, B {q['b']}).",
        f"- Primary return source: {q['book']} funded core-perp books and {q['n'] - q['book']} cross-margin "
        "snapshot series. Snapshot TWR is retained as a check for each book-sourced address.",
        f"- Median account-return coverage: {q['cov']:.2f}; median completed round trips: {q['rt']}; "
        f"open trades with a Hyperliquid closing mark: {q['rt_open']}."
        if q["n"]
        else "- Empty universe.",
        f"- Book vs account: {q['xc_ok']} addresses agree (`xc_flag = ok`); median correlation "
        f"{(q['corr'] or float('nan')):.2f}. Fit uses active, checkable snapshot intervals.",
        f"- Median unpriced exposure share: {(q['unp'] or 0):.4f} (coins not passing the price check at this "
        "origin have no eligible intraday source, ADR-0044); median notional share in coins that cannot be copied "
        f"(not passing or HIP-3, ADR-0047): {(q['nc'] or 0):.4f}.",
        "- Stress shock: largest 24 h move per coin at hour marks before this origin. "
        + (
            f"{crash.height} of {sh.height} coins take their largest fall from 10-11 Oct 2025."
            if crash.height
            else "**The 10-11 Oct 2025 crash is not yet known at this origin and is not used.**"
        ),
        "",
        "## Gate counts (placeholders; counts only)",
        "",
        "| gate | pass | fail | unmeasured |",
        "| --- | --- | --- | --- |",
    ]
    lines += [f"| {r['gate']} | {r['pass']} | {r['fail']} | {r['unmeasured']} |" for r in counts.iter_rows(named=True)]
    lines.append("")
    return "\n".join(lines)


def write(ctx: Context, tables: dict[str, pl.DataFrame], origin: date, out: Path) -> list[Path]:
    d = out / f"origin={origin.isoformat()}"
    d.mkdir(parents=True, exist_ok=True)
    paths = []
    for name in TABLES:
        p = d / f"{name}.parquet"
        tables[name].write_parquet(p, compression="zstd", statistics=True)
        paths.append(p)
    counts = gate_counts(tables["gates"], origin)
    counts.write_csv(d / "gate_counts.csv")
    (d / "summary.md").write_text(summary_md(tables, counts, origin), encoding="utf-8")
    return [*paths, d / "gate_counts.csv", d / "summary.md"]


def shared_panels(ctx: Context, inputs: Inputs, os_: list[datetime]) -> dict:
    """The panels `run` shares across the origins `os_` (ADR-0044: each origin uses its own price-check list; the
    panels cover the union of those lists and every consumer masks them by its origin's list)."""
    from arkstream import refprices as rf

    checker = hlprices.PointInTimeCheck.load(ctx)
    coins = checker.coins
    union = sorted(set().union(*(checker.passing(o) for o in os_)))
    px_all = price_grid(ctx, inputs, coins, max(os_), union)  # each mark uses only data <= the mark (point in time)
    volume = lk.binance_daily_volume(ctx.path("binance_lake"), rf.load_map(ctx.path("binance_map")), max(os_))
    candles, _ = hlprices.load_candles(ctx.path("hyperliquid_dir"), max(os_))
    ohlc = hlprices.load_candles_ohlc(ctx.path("hyperliquid_dir"), max(os_))
    extremes = lw.binance_extremes(ctx.path("binance_lake"), rf.load_map(ctx.path("binance_map")), union, max(os_))
    funding = load_funding(ctx, max(os_))
    return {"px": px_all, "volume": volume, "funding": funding, "candles": candles, "ohlc": ohlc,
            "extremes": extremes, "price_check": checker}


def run(ctx: Context, inputs: Inputs, out: Path, only: list[date] | None = None) -> list[Path]:
    os_ = [o for o in origins(ctx) if only is None or o.date() in only]
    panels = shared_panels(ctx, inputs, os_)
    written, all_counts = [], []
    for o in os_:
        tabs = compute(ctx, inputs, o, **panels)
        written += write(ctx, tabs, o.date(), out)
        all_counts.append(gate_counts(tabs["gates"], o.date()))
        print(
            json.dumps(
                {
                    "origin": o.date().isoformat(),
                    "universe": tabs["evidence"].height,
                    "all_gates_pass": int(tabs["gates"]["all_gates_pass"].sum()),
                }
            )
        )
    pl.concat(all_counts).write_csv(out / "gate_counts.csv")
    return [*written, out / "gate_counts.csv"]
