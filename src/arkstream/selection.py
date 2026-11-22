"""Phase 4: the point-in-time selection rule (ADRs 0130-0132, 0136-0137).

At an origin o every input comes from data up to o (Phase 2 evidence at o, and the frozen replay's training window
ending at o, `research/replay_frozen/origin=o/window=training`); no test window is read here.

1. **Gates** (ADR-0130): grade A/B and the 18 Phase 2 gates (`all_gates_pass`), then the selection gates: history
   (snapshot days, usable return days), median equity in the band, copyable notional share, the leader's holding
   band inside the copyable bands of the training-window break-even study, break-even delay above the base delay
   (training-window delay grid), and not the weaker member of a confirmed copier cluster (copier screen as of o).
2. **Key** (ADR-0131): the follower's net return per completed training-window round trip (base, frozen sizing,
   after costs and funding, on peak notional), its lower bound from a calendar-week block bootstrap.
3. **Clusters and the walk** (ADR-0132): Ward behaviour clusters over all A/B addresses (features without outcome
   measures); co-movement between eligible addresses (daily copy-return correlation, position overlap); a walk down
   the within-cluster ranking that adds an address only while both stay below the thresholds, up to K.

`select_origin` returns every table for one origin and one variant; `run` writes them under research/selection/.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from arkstream import selection_stats as st
from arkstream.replay_book import ledger
from arkstream.replay_market import DAY, midnight, ms

C = pl.col
SUFFIX = "_sqrt_cap_part_ns_sweep_frozen"
KEY = ["trader", "coin"]
FOUR = ("BTC", "ETH", "HYPE", "SOL")
PHASE2_GATES = (
    "gate_evidence", "gate_intraday_dd", "gate_worst_day", "gate_worst_3d", "gate_max_dd", "gate_stress_peak",
    "gate_leverage_p95", "gate_liq_distance", "gate_liquidations", "gate_top_dependence", "gate_unpriced",
    "gate_book_account", "gate_hold", "gate_order_rate", "gate_maker", "gate_active", "gate_rebuild_fit",
    "gate_worstcase_dd",
)
SELECTION_GATES = ("sel_history", "sel_equity_band", "sel_copyable_notional", "sel_hold_band", "sel_break_even",
                   "sel_copier")
FEATURES = ("log_hold", "hold_spread", "log_orders_per_day", "log_order_to_equity", "leverage_median",
            "leverage_p95", "net_long_share", "coin_hhi", "btc_eth_share", "beta_btc", "maker_share",
            "fills_per_order", "log_turnover")


@dataclass(frozen=True)
class Rules:
    """Every threshold of the rule (config `selection`, all PLACEHOLDER; ADRs 0130-0132, 0136-0137)."""

    variant: str
    scenario: str
    min_snapshot_days: int
    min_usable_days: int
    equity_band: tuple[float, float]
    max_share_not_copyable: float
    band_min_completed: int
    base_delay_ms: int
    key_percentile: float
    draws: int
    seed: int
    min_trips: int
    min_blocks: int
    behaviour_k: int
    min_common_days: int
    max_corr: float
    max_overlap: float
    max_k: int
    coin_filter: bool
    filter_always: tuple[str, ...]
    filter_min_capture: float
    filter_min_benchmark_usdc: float
    replay_dir: str = "research/replay_frozen"

    @classmethod
    def from_config(cls, raw: dict[str, Any], variant: str | None = None) -> Rules:
        s = raw["selection"]
        g, k, cl, cf = s["gates"], s["key"], s["clusters"], s["coin_filter"]
        name = variant or s["rule"]
        base = cls(
            variant=name, scenario=s["scenario"],
            min_snapshot_days=int(g["min_snapshot_days"]), min_usable_days=int(g["min_usable_days"]),
            equity_band=(float(g["equity_band_usdc"][0]), float(g["equity_band_usdc"][1])),
            max_share_not_copyable=float(g["max_share_not_copyable"]),
            band_min_completed=int(g["band_min_completed"]), base_delay_ms=int(g["base_delay_ms"]),
            key_percentile=float(k["percentile"]), draws=int(k["draws"]), seed=int(k["seed"]),
            min_trips=int(k["min_trips"]), min_blocks=int(k["min_blocks"]),
            behaviour_k=int(cl["behaviour_k"]), min_common_days=int(cl["min_common_days"]),
            max_corr=float(cl["max_corr"]), max_overlap=float(cl["max_overlap"]),
            max_k=int(s["basket"]["max_k"]), coin_filter=False,
            filter_always=tuple(cf["always"]), filter_min_capture=float(cf["min_capture"]),
            filter_min_benchmark_usdc=float(cf["min_benchmark_pnl_usdc"]), replay_dir=s["replay_dir"],
        )
        overrides = s["variants"][name] or {}
        allowed = {"key_percentile", "max_k", "coin_filter", "replay_dir"}
        if set(overrides) - allowed:
            raise ValueError(f"variant {name}: only {sorted(allowed)} may differ")
        return replace(base, **overrides)


def replay_dir(ctx) -> Path:
    return ctx.root / ctx.raw["selection"]["replay_dir"]


def window_dir(ctx, origin: date, window: str) -> Path:
    return replay_dir(ctx) / f"origin={origin}" / f"window={window}"


def scenario_dir(ctx, origin: date, window: str, scenario: str) -> Path:
    return window_dir(ctx, origin, window) / f"scenario={scenario}{SUFFIX}"


ORDER_COLS = ["trader", "coin", "status", "quantity", "fill_px", "fee", "anchor_px", "ack_ms", "decision_ms",
              "batch", "oid", "source_rows", "source_tids", "leader_notional"]


def load_ledger(ctx, origin: date, window: str, scenario: str, end_ms: int) -> tuple[pl.DataFrame, pl.DataFrame]:
    """The filled follower ledger and funding accruals of one window and scenario, as the replay valued them."""
    d = scenario_dir(ctx, origin, window, scenario)
    orders = pl.read_parquet(d / "follower_orders.parquet", columns=ORDER_COLS)
    from datetime import UTC, datetime

    end = datetime.fromtimestamp(end_ms / 1000, tz=UTC)
    f = ledger(orders, end)
    fund = pl.read_parquet(d / "funding_payments.parquet", columns=["trader", "coin", "batch", "payment"])
    return f, fund


def follower_trips(f: pl.DataFrame, fund: pl.DataFrame) -> pl.DataFrame:
    """Completed follower round trips, one row each, exactly as `replay_book.completed_trips` forms them (reversals
    split at zero, fees apportioned, each funding accrual attached to its holding lot's trip, trips with an unknown
    accrual dropped), keeping open/close times and the leader source keys of the opening and closing orders."""
    before = C("pos") - C("quantity")
    f = f.with_columns(before=pl.when(before.abs() < 1e-10).then(0.0).otherwise(before))
    flip = C("before") * C("pos") < 0
    main = f.with_columns(
        q=pl.when(flip).then(-C("before")).otherwise("quantity"),
        after=pl.when(flip).then(0.0).otherwise("pos"),
        part=pl.lit(0),
    )
    tail = f.filter(flip).with_columns(q=C("pos"), after=C("pos"), before=pl.lit(0.0), part=pl.lit(1))
    parts = (
        pl.concat([main, tail])
        .sort(*KEY, "ack_ms", "decision_ms", "batch", "oid", "part")
        .with_columns(trip=(C("before") == 0).cast(pl.Int64).cum_sum().over(KEY))
    )
    holding = parts.group_by(*KEY, "batch", maintain_order=True).agg(C("trip").last())
    funding = (
        fund.join(holding, on=[*KEY, "batch"])
        .group_by(*KEY, "trip", maintain_order=True)
        .agg(funding=C("payment").sum(), unknown=C("payment").null_count())
    )
    trips = (
        parts.group_by(*KEY, "trip", maintain_order=True)
        .agg(
            closed=C("after").last() == 0,
            side=pl.when(C("after").first() > 0).then(pl.lit("long")).otherwise(pl.lit("short")),
            open_ms=C("ack_ms").first(),
            close_ms=C("ack_ms").last(),
            gross=(-C("q") * C("anchor_px")).sum(),
            cost=(C("q") * (C("fill_px") - C("anchor_px")) + C("fee") * (C("q") / C("quantity")).abs()).sum(),
            peak=(pl.max_horizontal(C("after").abs(), C("before").abs()) * C("anchor_px")).max(),
            entry_oid=C("oid").first(),
            exit_oid=C("oid").last(),
            entry_src_row=C("source_rows").first().list.first(),
            exit_src_row=C("source_rows").last().list.first(),
            entry_tid=C("source_tids").first().list.first(),
            exit_tid=C("source_tids").last().list.first(),
            entry_leader_notional=C("leader_notional").first(),
            fills=pl.len(),
        )
        .filter(C("closed") & (C("peak") > 0))
        .join(funding, on=[*KEY, "trip"], how="left")
        .with_columns(C("funding", "unknown").fill_null(0))
        .filter(C("unknown") == 0)
        .drop("closed", "unknown")
    )
    return trips.with_columns(
        pnl=C("gross") - C("cost") + C("funding"),
        net=(C("gross") - C("cost") + C("funding")) / C("peak"),
    ).sort("trader", "coin", "trip")


def trader_rng(seed: int, trader: str, origin: date, salt: int = 0) -> np.random.Generator:
    return np.random.default_rng([seed, int(trader[2:10], 16), origin.toordinal(), salt])


def address_keys(trips: pl.DataFrame, rules: Rules, origin: date) -> pl.DataFrame:
    """Per address: completed trips, blocks, mean net return per trip, the bootstrap lower bound (the key), the same
    bound without the best block, and the flag `single_event` when that bound is not positive but the key is."""
    rows = []
    q = rules.key_percentile
    for (trader,), g in trips.sort("trader", "open_ms", "coin", "trip").group_by("trader", maintain_order=True):
        net = g["net"].to_numpy()
        blocks = st.entry_week_blocks(g["open_ms"].to_numpy())
        nb = int(blocks.max()) + 1 if len(blocks) else 0
        row: dict[str, Any] = {"trader": trader, "trips": len(net), "blocks": nb, "mean_net": float(net.mean()),
                               "median_net": float(np.median(net)), "key": None, "key_p50": None,
                               "key_ex_best": None, "best_block_share": None, "single_event": False,
                               "key_status": "ok"}
        if len(net) < rules.min_trips or nb < rules.min_blocks:
            row["key_status"] = "too_few_trips" if len(net) < rules.min_trips else "too_few_blocks"
            rows.append(row)
            continue
        means = st.block_bootstrap(net, blocks, rules.draws, trader_rng(rules.seed, trader, origin))
        row["key"] = st.quantile(means, q)
        row["key_p50"] = st.quantile(means, 0.5)
        sums = np.bincount(blocks, weights=g["pnl"].to_numpy(), minlength=nb)
        best = int(np.argmax(sums))
        total = float(g["pnl"].sum())
        row["best_block_share"] = float(sums[best] / total) if total > 0 else None
        keep = blocks != best
        if keep.sum() >= 1 and nb - 1 >= 1:
            rest = np.unique(blocks[keep], return_inverse=True)[1]
            ex = st.block_bootstrap(net[keep], rest, rules.draws, trader_rng(rules.seed, trader, origin, 1))
            row["key_ex_best"] = st.quantile(ex, q)
        row["single_event"] = bool(row["key"] > 0 and (row["key_ex_best"] is None or row["key_ex_best"] <= 0))
        rows.append(row)
    schema = {"trader": pl.String, "trips": pl.Int64, "blocks": pl.Int64, "mean_net": pl.Float64,
              "median_net": pl.Float64, "key": pl.Float64, "key_p50": pl.Float64, "key_ex_best": pl.Float64,
              "best_block_share": pl.Float64, "single_event": pl.Boolean, "key_status": pl.String}
    return pl.DataFrame(rows, schema=schema, orient="row").sort("trader")


def snapshot_days(traders: pl.DataFrame, origin: date) -> pl.DataFrame:
    """Distinct UTC dates with a snapshot known by the origin (ts <= origin 00:00), per address."""
    t = midnight(origin)
    return traders.filter(C("ts") <= t).group_by("trader").agg(snapshot_days=C("ts").dt.date().n_unique())


def copyable_bands(ctx, origin: date, rules: Rules) -> pl.DataFrame:
    """ADR-0130: holding bands whose training-window completed follower trips (all A/B, base) net a positive return
    per trip over at least `band_min_completed` trips."""
    b = pl.read_parquet(scenario_dir(ctx, origin, "training", rules.scenario) / "band_break_even.parquet")
    return b.with_columns(copyable=(C("net_bps") > 0) & (C("completed") >= rules.band_min_completed)).sort("hold_band")


def gate(ok: pl.Expr, measured: pl.Expr) -> pl.Expr:
    return pl.when(~measured).then(pl.lit("unmeasured")).when(ok).then(pl.lit("pass")).otherwise(pl.lit("fail"))


def behaviour_features(ctx, origin: date, ev: pl.DataFrame) -> pl.DataFrame:
    """Plan table "Behavior": timing, sizing, market, execution and turnover features from Phase 2 at the origin.
    No outcome measure (returns, win rates, drawdowns) is used."""
    leader = ctx.root / "research/leader" / f"origin={origin}"
    prof = pl.read_parquet(leader / "profiles.parquet",
                           columns=["trader", "n_fills", "n_orders", "notional", "active_days",
                                    "median_order_notional"])
    rt = pl.read_parquet(leader / "round_trips.parquet", columns=["trader", "symbol", "status", "hold_s",
                                                                  "peak_notional"])
    hours = pl.read_parquet(leader / "book_hourly.parquet", columns=["trader", "gross_exposure", "net_exposure",
                                                                     "leverage"])
    # sorted inputs and order-preserving groups: float sums are then byte-identical on rerun
    rt = rt.sort("trader", "symbol", "hold_s", "peak_notional")
    hours = hours.sort("trader", "gross_exposure", "net_exposure", "leverage")
    spread = rt.filter((C("status") == "closed") & (C("hold_s") > 0)).group_by("trader", maintain_order=True).agg(
        hold_spread=C("hold_s").log10().quantile(0.75) - C("hold_s").log10().quantile(0.25))
    by_coin = rt.group_by("trader", "symbol", maintain_order=True).agg(n=C("peak_notional").abs().sum())
    conc = by_coin.with_columns(w=C("n") / C("n").sum().over("trader")).sort("trader", "symbol").group_by(
        "trader", maintain_order=True).agg(coin_hhi=(C("w") ** 2).sum(),
                                           btc_eth_share=C("w").filter(C("symbol").is_in(["BTC", "ETH"])).sum())
    held = hours.filter(C("gross_exposure") > 0).group_by("trader", maintain_order=True).agg(
        net_long_share=(C("net_exposure") > 0).mean(), leverage_median=C("leverage").median())
    out = (ev.select("trader", "median_hold_s", "orders_per_day", "median_equity", "leverage_p95", "beta_btc",
                     "maker_share")
           .join(prof, on="trader", how="left").join(spread, on="trader", how="left")
           .join(conc, on="trader", how="left").join(held, on="trader", how="left"))
    pos = lambda e: pl.when(e > 0).then(e.log10())  # noqa: E731
    return out.select(
        "trader",
        log_hold=pos(C("median_hold_s")),
        hold_spread="hold_spread",
        log_orders_per_day=pos(C("orders_per_day")),
        log_order_to_equity=pos(C("median_order_notional") / C("median_equity")),
        leverage_median="leverage_median",
        leverage_p95="leverage_p95",
        net_long_share="net_long_share",
        coin_hhi="coin_hhi",
        btc_eth_share="btc_eth_share",
        beta_btc="beta_btc",
        maker_share="maker_share",
        fills_per_order=C("n_fills") / C("n_orders"),
        log_turnover=pos(C("notional") / C("active_days") / C("median_equity")),
    ).sort("trader")


def behaviour_clusters(features: pl.DataFrame, k: int) -> pl.DataFrame:
    """Ward clusters on standardised features (addresses with any missing or non-finite feature: `unclustered`)."""
    x = features.select(FEATURES).to_numpy().astype(float)
    ok = np.isfinite(x).all(axis=1)
    labels = np.full(len(ok), -1, dtype=np.int64)
    if ok.sum() > 0:
        labels[ok] = st.ward(st.standardise(x[ok]), min(k, int(ok.sum())))
    return features.with_columns(
        behaviour_cluster=pl.Series([f"b{i}" if i >= 0 else "unclustered" for i in labels], dtype=pl.String))


def daily_positions(f: pl.DataFrame, marks: pl.DataFrame) -> pl.DataFrame:
    """Signed notional per (trader, day, coin) at each midnight the follower held a position (the replay's own
    valuation: position before the boundary at the Hyperliquid daily mark)."""
    held = (
        f.filter(C("pos") != 0)
        .select(*KEY, "pos", boundary=pl.int_ranges(C("ack_ms") // DAY + 1, C("next_ms") // DAY + 1))
        .explode("boundary", empty_as_null=False)
        .drop_nulls("boundary")
        .join(marks.select("coin", "boundary", "mark"), on=["coin", "boundary"], how="left")
    )
    return held.select("trader", "coin", "boundary", exposure=C("pos") * C("mark")).drop_nulls("exposure")


def comovement(traders: list[str], daily: pl.DataFrame, positions: pl.DataFrame, min_days: int) -> pl.DataFrame:
    """Pairwise daily copy-return correlation (common days with both returns, null under `min_days`) and position
    overlap (cosine similarity of signed exposures by (day, coin); null when either never held a position)."""
    d = daily.filter(C("trader").is_in(traders)).select("trader", "day", "daily_twr").drop_nulls("daily_twr")
    series = {t: g for (t,), g in d.sort("trader", "day").group_by("trader", maintain_order=True)}
    vec = {t: g for (t,), g in positions.filter(C("trader").is_in(traders)).group_by("trader", maintain_order=True)}
    rows = []
    for i, a in enumerate(traders):
        for b in traders[i + 1:]:
            corr, n = None, 0
            if a in series and b in series:
                j = series[a].join(series[b], on="day", suffix="_b")
                n = j.height
                x, y = j["daily_twr"].to_numpy(), j["daily_twr_b"].to_numpy()
                if n >= min_days and x.std() > 0 and y.std() > 0:
                    corr = float(np.corrcoef(x, y)[0, 1])
            overlap = None
            if a in vec and b in vec:
                va = vec[a].select("coin", "boundary", "exposure")
                vb = vec[b].select("coin", "boundary", "exposure")
                dot = va.join(vb, on=["coin", "boundary"]).select((C("exposure") * C("exposure_right")).sum()).item()
                na = math.sqrt(float((va["exposure"] ** 2).sum()))
                nb = math.sqrt(float((vb["exposure"] ** 2).sum()))
                overlap = float(dot) / (na * nb) if na > 0 and nb > 0 else None
            rows.append((a, b, n, corr, overlap))
    schema = {"trader_a": pl.String, "trader_b": pl.String, "common_days": pl.Int64, "corr": pl.Float64,
              "overlap": pl.Float64}
    return pl.DataFrame(rows, schema=schema, orient="row")


def comovement_clusters(traders: list[str], pairs: pl.DataFrame, max_corr: float) -> pl.DataFrame:
    """Average-linkage clusters on correlation distance 1 - corr (unmeasured pairs at distance 1), merged below
    1 - max_corr: addresses that move together closer than the walk allows."""
    n = len(traders)
    idx = {t: i for i, t in enumerate(traders)}
    dist = np.ones((n, n))
    np.fill_diagonal(dist, 0.0)
    for a, b, corr in pairs.select("trader_a", "trader_b", "corr").rows():
        if corr is not None:
            dist[idx[a], idx[b]] = dist[idx[b], idx[a]] = 1 - corr
    labels = st.average_linkage(dist, 1 - max_corr) if n else np.zeros(0, dtype=np.int64)
    return pl.DataFrame({"trader": traders, "comovement_cluster": [f"m{i}" for i in labels]}, schema={
        "trader": pl.String, "comovement_cluster": pl.String})


def walk(cands: pl.DataFrame, pairs: pl.DataFrame, rules: Rules) -> pl.DataFrame:
    """ADR-0132 diversification walk over the selectable addresses (eligible with a positive key), in order of
    within-behaviour-cluster rank, then key (descending), then address. An address joins while its correlation and
    its position overlap with every chosen address stay below the thresholds (an unmeasured pair does not block),
    up to K."""
    sel = cands.filter("selectable").with_columns(
        cluster_rank=C("key").rank("ordinal", descending=True).over("behaviour_cluster"))
    sel = sel.sort("cluster_rank", "key", "trader", descending=[False, True, False])
    lookup: dict[tuple[str, str], tuple[float | None, float | None]] = {}
    for a, b, corr, ov in pairs.select("trader_a", "trader_b", "corr", "overlap").rows():
        lookup[(a, b)] = lookup[(b, a)] = (corr, ov)
    chosen: list[str] = []
    rows = []
    for step, (trader, cluster, crank, key) in enumerate(
            sel.select("trader", "behaviour_cluster", "cluster_rank", "key").rows(), start=1):
        worst_c = worst_o = None
        with_c = with_o = None
        for c in chosen:
            corr, ov = lookup.get((trader, c), (None, None))
            if corr is not None and (worst_c is None or corr > worst_c):
                worst_c, with_c = corr, c
            if ov is not None and (worst_o is None or ov > worst_o):
                worst_o, with_o = ov, c
        if len(chosen) >= rules.max_k:
            decision, reason = "rejected", f"basket full (K = {rules.max_k})"
        elif worst_c is not None and worst_c >= rules.max_corr:
            decision = "rejected"
            reason = f"daily copy-return correlation {worst_c:.2f} with {with_c} >= {rules.max_corr}"
        elif worst_o is not None and worst_o >= rules.max_overlap:
            decision, reason = "rejected", f"position overlap {worst_o:.2f} with {with_o} >= {rules.max_overlap}"
        else:
            decision, reason = "selected", "positive key; diversification check passed"
            chosen.append(trader)
        rows.append((step, trader, cluster, int(crank), key, worst_c, with_c, worst_o, with_o, decision, reason))
    schema = {"step": pl.Int64, "trader": pl.String, "behaviour_cluster": pl.String, "cluster_rank": pl.Int64,
              "key": pl.Float64, "max_corr_chosen": pl.Float64, "max_corr_with": pl.String,
              "max_overlap_chosen": pl.Float64, "max_overlap_with": pl.String, "decision": pl.String,
              "reason": pl.String}
    return pl.DataFrame(rows, schema=schema, orient="row")


def copier_weaker(clusters: pl.DataFrame, keys: pl.DataFrame) -> pl.DataFrame:
    """Per address in a confirmed copier cluster: whether it is a weaker member (not the one with the highest key;
    an unmeasured key ranks below every measured one; ties by address)."""
    if clusters.height == 0:
        return pl.DataFrame(schema={"trader": pl.String, "copier_cluster": pl.String, "copier_weaker": pl.Boolean})
    c = clusters.join(keys.select("trader", "key"), on="trader", how="left").with_columns(
        has=C("key").is_not_null().cast(pl.Int8), k=C("key").fill_null(-1e18))
    c = c.sort("cluster_id", "has", "k", "trader", descending=[False, True, True, False]).with_columns(
        copier_weaker=pl.int_range(pl.len()).over("cluster_id") > 0)
    return c.select("trader", copier_cluster="cluster_id", copier_weaker="copier_weaker")


@dataclass
class OriginData:
    """Inputs at one origin that do not depend on the variant (point in time)."""

    origin: date
    evidence: pl.DataFrame
    summary: dict[str, pl.DataFrame]  # training address summaries per scenario name
    trips: pl.DataFrame
    daily: pl.DataFrame
    positions: pl.DataFrame
    bands: pl.DataFrame
    copiers: pl.DataFrame
    features: pl.DataFrame
    coin_set: pl.DataFrame | None = None


def training_end(origin: date) -> int:
    return ms(midnight(origin))


def load_origin(ctx, origin: date, traders: pl.DataFrame, copier_clusters: pl.DataFrame, rules: Rules) -> OriginData:
    from arkstream.freeze import guard

    guard(ctx, midnight(origin))  # a window ending after the holdout start needs the freeze
    leader = ctx.root / "research/leader" / f"origin={origin}"
    ev = pl.read_parquet(leader / "evidence.parquet")
    end = training_end(origin)
    summary = {sc: pl.read_parquet(scenario_dir(ctx, origin, "training", sc) / "address_summary.parquet")
               for sc in ("base", "optimistic", "stress")}
    f, fund = load_ledger(ctx, origin, "training", rules.scenario, end)
    trips = follower_trips(f, fund)
    daily = pl.read_parquet(scenario_dir(ctx, origin, "training", rules.scenario) / "daily_copy_twr.parquet",
                            columns=["trader", "day", "daily_twr", "equity"])
    marks = pl.read_parquet(replay_dir(ctx) / "valuation_marks.parquet")
    positions = daily_positions(f, marks)
    ev = ev.join(snapshot_days(traders, origin), on="trader", how="left").with_columns(
        C("snapshot_days").fill_null(0))
    feats = behaviour_clusters(behaviour_features(ctx, origin, ev), rules.behaviour_k)
    return OriginData(origin=origin, evidence=ev, summary=summary, trips=trips, daily=daily, positions=positions,
                      bands=copyable_bands(ctx, origin, rules), copiers=copier_clusters, features=feats)


def candidate_table(data: OriginData, rules: Rules) -> pl.DataFrame:
    """Every A/B address at the origin with every Phase 2 and selection gate, the key and its bootstrap, the
    training-window copy results beside it, the behaviour cluster and `eligible` / `selectable`."""
    trips = data.trips
    if rules.coin_filter and data.coin_set is not None:
        trips = trips.join(data.coin_set.filter("kept").select("coin"), on="coin", how="semi")
    keys = address_keys(trips, rules, data.origin)
    ok_bands = data.bands.filter("copyable")["hold_band"].to_list()
    base = data.summary["base"].select(
        "trader", train_copy_return="copy_return", train_max_drawdown="max_drawdown",
        train_daily_sharpe="daily_sharpe", train_measurement="measurement", break_even_delay_status=C(
            "break_even_delay_status"), break_even_delay_lo_ms="break_even_delay_lo_ms",
        train_parameterised_share="parameterised_notional_share")
    stress = data.summary["stress"].select("trader", train_stress_return="copy_return",
                                           train_stress_measurement="measurement",
                                           train_stress_max_drawdown="max_drawdown")
    opt = data.summary["optimistic"].select("trader", train_optimistic_return="copy_return")
    weak = copier_weaker(data.copiers, keys)
    lo, hi = rules.equity_band
    be_ok = (C("break_even_delay_status") == "positive_through_grid") | (
        (C("break_even_delay_status") == "crossing_bracket") & (C("break_even_delay_lo_ms") >= rules.base_delay_ms))
    t = (data.evidence.select(
            "trader", "grade", *PHASE2_GATES, "all_gates_pass", "gates_failed", "snapshot_days", "usable_days",
            "median_equity", "share_not_copyable", "hold_band", "median_hold_s", "maker_share", "orders_per_day",
            "leverage_p95", "wc_max_dd", "alpha", "beta_btc", "beta_eth", "rt_closed", "fee_rate_bps",
            "snapshot_src_row", "snapshot_ts", "last_fill_src_row", "tid", "oid", "last_fill_ts")
         .join(base, on="trader", how="left").join(stress, on="trader", how="left").join(opt, on="trader", how="left")
         .join(keys, on="trader", how="left").join(weak, on="trader", how="left")
         .join(data.features.select("trader", "behaviour_cluster"), on="trader", how="left")
         .with_columns(C("trips", "blocks").fill_null(0), C("key_status").fill_null("no_completed_trips"),
                       C("single_event").fill_null(False), C("copier_weaker").fill_null(False))
         .with_columns(
            sel_history=gate((C("snapshot_days") >= rules.min_snapshot_days)
                             & (C("usable_days") >= rules.min_usable_days), C("usable_days").is_not_null()),
            sel_equity_band=gate(C("median_equity").is_between(lo, hi), C("median_equity").is_not_null()),
            sel_copyable_notional=gate(C("share_not_copyable") <= rules.max_share_not_copyable,
                                       C("share_not_copyable").is_not_null()),
            sel_hold_band=gate(C("hold_band").is_in(ok_bands), C("hold_band").is_not_null()),
            sel_break_even=gate(be_ok, C("break_even_delay_status").is_not_null()
                                & (C("break_even_delay_status") != "unmeasured")),
            sel_copier=gate(~C("copier_weaker"), pl.lit(True)),
         ))
    passed = pl.all_horizontal([C(g) == "pass" for g in SELECTION_GATES])
    failed = pl.concat_str([pl.when(C(g) != "pass").then(pl.lit(g + ":") + C(g)) for g in SELECTION_GATES],
                           separator=",", ignore_nulls=True)
    return t.with_columns(
        selection_gates_failed=failed,
        eligible=C("all_gates_pass") & passed,
    ).with_columns(
        selectable=C("eligible") & C("key").is_not_null() & (C("key") > 0),
        origin=pl.lit(data.origin), variant=pl.lit(rules.variant),
    ).sort("trader")


def reason(row: dict[str, Any], walk_rows: dict[str, dict[str, Any]], rules: Rules) -> tuple[str, str]:
    t = row["trader"]
    if not row["all_gates_pass"]:
        return "not_eligible", f"Phase 2 gates failed: {row['gates_failed']}"
    if not row["eligible"]:
        return "not_eligible", f"selection gates: {row['selection_gates_failed']}"
    flag = " (flag: single_event, key not positive without the best week)" if row["single_event"] else ""
    if row["key"] is None:
        return "rejected", f"key unmeasured: {row['key_status']} ({row['trips']} trips, {row['blocks']} blocks)"
    if row["key"] <= 0:
        return "rejected", (f"key not positive: p{round(rules.key_percentile * 100)} of mean net per trip "
                            f"{row['key'] * 1e4:.1f} bps ({row['trips']} trips, {row['blocks']} blocks)")
    w = walk_rows[t]
    return w["decision"], w["reason"] + flag


class LeakError(ValueError):
    """A selection input dated after its origin."""


def check_point_in_time(data: OriginData) -> None:
    """Every ranking and co-movement input must be known by the origin: trips acknowledged before it, daily returns
    and positions for days before it (the training window ends at the origin)."""
    end = training_end(data.origin)
    late = data.trips.filter((C("open_ms") >= end) | (C("close_ms") >= end))
    if late.height:
        raise LeakError(f"{late.height} follower trips at or after the origin {data.origin}")
    if data.daily.filter(C("day") >= data.origin).height:
        raise LeakError(f"daily copy returns at or after the origin {data.origin}")
    if data.positions.filter(C("boundary") > end // DAY).height:
        raise LeakError(f"positions after the origin {data.origin}")


def select_origin(data: OriginData, rules: Rules, check: bool = True) -> dict[str, pl.DataFrame]:
    if check:
        check_point_in_time(data)
    cands = candidate_table(data, rules)
    eligible = cands.filter("eligible")["trader"].to_list()
    pairs = comovement(eligible, data.daily, data.positions, rules.min_common_days)
    comove = comovement_clusters(eligible, pairs, rules.max_corr)
    steps = walk(cands, pairs, rules)
    by = {r["trader"]: r for r in steps.iter_rows(named=True)}
    decisions = []
    for row in cands.iter_rows(named=True):
        d, why = reason(row, by, rules)
        decisions.append((row["trader"], d, why))
    dec = pl.DataFrame(decisions, schema={"trader": pl.String, "decision": pl.String, "reason": pl.String},
                       orient="row")
    cands = (cands.join(dec, on="trader").join(comove, on="trader", how="left")
             .join(steps.select("trader", "step", "cluster_rank"), on="trader", how="left").sort("trader"))
    tag = {"origin": pl.lit(data.origin), "variant": pl.lit(rules.variant)}
    trips = data.trips.join(cands.filter("eligible").select("trader"), on="trader", how="semi")
    if rules.coin_filter and data.coin_set is not None:
        trips = trips.join(data.coin_set.filter("kept").select("coin"), on="coin", how="semi")
    return {
        "candidates": cands,
        "decisions": cands.filter("eligible").select(
            "origin", "variant", "trader", "decision", "reason", "key", "key_p50", "mean_net", "trips", "blocks",
            "single_event", "key_ex_best", "best_block_share", "behaviour_cluster", "cluster_rank",
            "comovement_cluster", "step", "train_copy_return", "train_max_drawdown", "train_stress_return",
            "train_stress_measurement", "median_equity", "hold_band", "snapshot_src_row", "last_fill_src_row",
            "tid", "oid").sort("trader"),
        "walk": steps.with_columns(**tag),
        "comovement": pairs.with_columns(**tag),
        "behaviour": data.features.with_columns(**tag),
        "bands": data.bands.with_columns(**tag),
        "trips": trips.with_columns(**tag),
    }


def selected(tables: dict[str, pl.DataFrame]) -> list[str]:
    return sorted(tables["candidates"].filter(C("decision") == "selected")["trader"].to_list())
