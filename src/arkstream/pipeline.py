"""Milestone 1 build: every output computed as of one timestamp, from processed Parquet."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import polars as pl

from arkstream import copiers, hlprices, prices, quality, reconcile
from arkstream.config import Context, assert_no_live_trading, load_instruments
from arkstream.ingest import ingest_all, load_processed
from arkstream.instruments import annotate_fills, instrument_master, key_report
from arkstream.positions import continuity, order_fills, pit, rebuild


@dataclass
class Inputs:
    traders: pl.DataFrame
    fills: pl.DataFrame  # annotated


@dataclass
class Result:
    asof: datetime
    tables: dict[str, pl.DataFrame] = field(default_factory=dict)
    headline: dict[str, object] = field(default_factory=dict)


def processed_dir(ctx: Context) -> Path:
    return ctx.root / "data" / "processed"


def ensure_ingested(ctx: Context) -> None:
    p = processed_dir(ctx)
    if not (p / "fills").exists() or not (p / "traders").exists():
        ingest_all(ctx.path("traders"), ctx.path("fills"), p)


def load_inputs(ctx: Context) -> Inputs:
    ensure_ingested(ctx)
    p = processed_dir(ctx)
    traders = load_processed(p / "traders")
    fills = annotate_fills(load_processed(p / "fills"), load_instruments(ctx.root / "config"))
    return Inputs(traders=traders, fills=fills)


def effective_asof(ctx: Context, asof: datetime | None) -> datetime:
    """asof defaults to CUTOFF and is capped at it: nothing after the cutoff is ever used."""
    return ctx.cutoff if asof is None else min(asof, ctx.cutoff)


def positions_asof(fills: pl.DataFrame, asof: datetime) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    perp = pit(fills, asof).filter(pl.col("is_perp") & (pl.col("event_kind") == "trade"))
    ledger, trips = rebuild(continuity(order_fills(perp)))
    trips = trips.with_columns(
        open_at_asof=pl.col("close_ts").is_null(),
        holding_s=pl.when(pl.col("close_ts").is_not_null())
        .then((pl.col("close_ts") - pl.col("open_ts")).dt.total_milliseconds() / 1000),
        age_at_asof_s=pl.when(pl.col("close_ts").is_null())
        .then((pl.lit(asof) - pl.col("open_ts")).dt.total_milliseconds() / 1000),
    ).sort("trader", "symbol", "trip_no")
    open_pos = (ledger.group_by("trader", "symbol").agg(
        position=pl.col("pos_after").last(), last_ts=pl.col("ts").last(), last_src_row=pl.col("src_row").last(),
        last_tid=pl.col("tid").last(), last_oid=pl.col("oid").last(),
        instrument_class=pl.col("instrument_class").last(),
    ).filter(pl.col("position").abs() > 1e-9)
        .join(trips.filter("open_at_asof").select("trader", "symbol", "trip_no", "open_ts", "left_censored"),
              on=["trader", "symbol"], how="left")
        .with_columns(asof=pl.lit(asof)).sort("trader", "symbol"))
    return ledger, trips, open_pos


def mark_open_positions(open_pos: pl.DataFrame, ref: pl.LazyFrame, fills: pl.DataFrame, asof: datetime,
                        rp: dict) -> pl.DataFrame:
    """Value each open position at asof: reference price, else the package's own print, else unpriced (A13)."""
    q = open_pos.with_columns(t=pl.col("asof").dt.cast_time_unit("ms"))
    m = prices.price_asof(q, ref, fills, asof, rp["max_age_s"], rp["fallback_print_window_s"],
                          coin_col="symbol", ts_col="t")
    return m.drop("t").rename({"price": "mark_price", "price_ts": "mark_ts", "price_source": "mark_source",
                               "price_ref_file": "mark_ref_file", "price_src_row": "mark_print_src_row"}
                              ).with_columns(mark_notional=pl.col("position") * pl.col("mark_price"))


def build(ctx: Context, inputs: Inputs, asof: datetime | None = None) -> Result:
    assert_no_live_trading(ctx.root / "config")
    t = effective_asof(ctx, asof)
    cfg = ctx.raw
    traders = pit(inputs.traders, t)
    fills = pit(inputs.fills, t)
    res = Result(asof=t)

    ledger, trips, open_pos = positions_asof(fills, t)
    rc = cfg["reconcile"]
    recon_snap = reconcile.snapshot_summary(traders, t, rc["pnl_tolerance_tight"], rc["pnl_tolerance_loose"])
    recon_fill = reconcile.fill_summary(ledger, t)

    rp = cfg["reference_prices"]
    ref = prices.scan_reference(ctx.path("reference_prices_dir"))  # manifest-verified, lazy
    coins = fills.filter("eligible")["symbol"].unique().to_list()
    price_cov = prices.coverage(ref, coins, t, ctx.cutoff)
    price_cmp = prices.compare_to_prints(ref, fills, t, rp["disagreement_tolerance_bps"], rp["print_match_window_s"])
    open_pos = mark_open_positions(open_pos, ref, fills, t, rp)
    unpriced = open_pos.filter(pl.col("mark_source") == "unpriced").select(
        "trader", "symbol", "position", "asof", "unpriced_reason", "last_src_row")

    cop = copiers.screen(fills, t, cfg["copiers"])

    snaps, ev_snap = quality.snapshot_flags(traders, t, cfg)
    passing = hlprices.PointInTimeCheck.load(ctx).passing(t)  # ADR-0110: the price check as of t
    snaps = quality.frozen_flags(snaps, ledger, fills, t, ref, passing)
    table, ev_addr = quality.address_table(traders, snaps, ledger, fills, recon_snap, recon_fill, cop["clusters"],
                                           t, cfg)
    report = quality.grade(table, cfg).with_columns(asof=pl.lit(t), config_version=pl.lit(cfg["version"]))
    ev_pnl = reconcile.snapshot_rows(traders, t).filter(
        pl.col("pnl_identity_diff").abs() > rc["pnl_tolerance_tight"])
    evidence = pl.concat([
        ev_snap, ev_addr, quality._evidence(snaps.filter("frozen"), "frozen_snapshot", "traders.csv",
                                            pl.format("previous snapshot row {}", pl.col("prev_src_row"))),
        quality._evidence(ev_pnl, "pnl_identity_mismatch", "traders.csv",
                          pl.col("pnl_identity_diff").round(6).cast(pl.String)),
        quality._evidence(fills.filter(pl.col("event_kind") == "non_trade"), "non_trade_event", "fills.csv",
                          pl.col("dir")),
    ]).sort("trader", "flag", "file", "src_row")

    res.tables = {
        "ledger": ledger.drop("raw_timestamp"), "round_trips": trips, "open_positions": open_pos,
        "recon_snapshots": recon_snap, "recon_fills": recon_fill,
        "price_coverage": price_cov, "price_compare": price_cmp, "price_unpriced": unpriced,
        "copier_pairs": cop["pairs"], "copier_flagged": cop["flagged"], "copier_clusters": cop["clusters"],
        "instrument_master": instrument_master(fills), "quality_report": report, "quality_evidence": evidence,
    }
    ic = fills["instrument_class"].value_counts()
    cls = dict(zip(ic["instrument_class"].to_list(), ic["count"].to_list(), strict=True))
    res.headline = {
        "asof": t.isoformat(),
        "traders_rows": traders.height, "traders_addresses": traders["trader"].n_unique(),
        "fills_rows": fills.height, "fills_addresses": fills["trader"].n_unique(),
        "fills_symbols": fills["symbol"].n_unique(),
        **key_report(fills),
        "spot_rows": cls.get("spot", 0), "hip3_rows": cls.get("hip3", 0), "core_perp_rows": cls.get("core_perp", 0),
        "perp_fills": ledger.height,
        "continuity_breaks": int(ledger["continuity_break"].sum()),
        "unresolved_chains": int((~ledger["chain_resolved"]).sum()),
        "mixed_ms_fills": int((ledger["group_kind"] == "mixed").sum()),
        "round_trips": trips.height, "round_trips_closed": int(trips["close_ts"].is_not_null().sum()),
        "round_trips_left_censored": int(trips["left_censored"].sum()),
        "open_positions": open_pos.height,
        **reconcile.headline(traders, t, rc["pnl_tolerance_tight"], rc["pnl_tolerance_loose"]),
        **quality.headline(snaps, table),
        "reference_price_rows": prices.reference_rows(ref, t),
        "coins_without_reference": int((price_cov["ref_flag"] != "ok").sum()),
        "prints_disagree_with_reference": int((price_cmp["cmp_flag"] == "disagree").sum()),
        "prints_without_reference": int((price_cmp["cmp_flag"] == "no_reference_in_window").sum()),
        "open_positions_marked_reference": int((open_pos["mark_source"] == "reference").sum()),
        "open_positions_marked_print": int((open_pos["mark_source"] == "package_print").sum()),
        "open_positions_unpriced": unpriced.height,
        "copier_pairs_with_match": cop["pairs"].height,
        "copier_confirmed_pairs": int(cop["flagged"]["confirmed"].sum()),
        "copier_clusters": int(cop["clusters"]["cluster_id"].n_unique()) if cop["clusters"].height else 0,
        "grade_A": int((report["grade"] == "A").sum()), "grade_B": int((report["grade"] == "B").sum()),
        "grade_C": int((report["grade"] == "C").sum()),
    }
    return res


def asof_tag(t: datetime) -> str:
    return t.strftime("%Y%m%dT%H%M%SZ")


def write_outputs(ctx: Context, res: Result, cards: bool = True) -> list[Path]:
    out_dir = processed_dir(ctx) / "derived" / f"asof={asof_tag(res.asof)}"
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, df in res.tables.items():
        p = out_dir / f"{name}.parquet"
        df.write_parquet(p, compression="zstd", statistics=True)
        written.append(p)
    research = ctx.root / "research"
    for name in ("quality_report", "quality_evidence"):
        p = research / f"{name}.parquet"
        res.tables[name].write_parquet(p, compression="zstd", statistics=True)
        written.append(p)
    if cards:
        written += write_cards(research / "cards", res)
    return sorted(written)


def write_cards(card_dir: Path, res: Result) -> list[Path]:
    card_dir.mkdir(parents=True, exist_ok=True)
    rep, ev = res.tables["quality_report"], res.tables["quality_evidence"]
    ev_counts = ev.group_by("trader", "flag").agg(n=pl.len(), rows=pl.col("src_row").head(10),
                                                  file=pl.col("file").first())
    by_trader: dict[str, list[tuple]] = {}
    for tr, flag, n, rows, file in ev_counts.sort("trader", "flag").iter_rows():
        by_trader.setdefault(tr, []).append((flag, n, rows, file))
    paths = []
    skip = {"trader"}
    for row in rep.iter_rows(named=True):
        tr = row["trader"]
        lines = [f"# {tr}", "", f"as of {res.asof.isoformat()} · grade **{row['grade']}**"
                 + (f" · {row['grade_reason']}" if row["grade_reason"] else ""), "", "## Flags", "",
                 "| field | value |", "| --- | --- |"]
        lines += [f"| {k} | {v} |" for k, v in row.items() if k not in skip]
        lines += ["", "## Evidence (raw rows; first 10 per flag)", "", "| flag | rows | file | src_row |",
                  "| --- | --- | --- | --- |"]
        for flag, n, rows, file in by_trader.get(tr, []):
            lines.append(f"| {flag} | {n} | {file} | {', '.join(map(str, rows))} |")
        p = card_dir / f"{tr}.md"
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        paths.append(p)
    return paths
