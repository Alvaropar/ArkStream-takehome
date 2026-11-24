"""Command line: python -m arkstream {ingest,build,audit,checksums,refprices,drift,leader}."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import polars as pl

from arkstream import audit
from arkstream.config import load_context
from arkstream.ingest import ingest_all
from arkstream.pipeline import build, load_inputs, processed_dir, write_outputs
from arkstream.prices import MANIFEST_NAME, manifest_files
from arkstream.provenance import sha256_file, write_checksums
from arkstream.timeparse import parse_one_utc


def _raw_paths(ctx) -> list[Path]:
    paths = [ctx.path("traders"), ctx.path("fills")]
    paths += [ctx.root / p for p in ctx.raw["inputs"].get("originals", []) if (ctx.root / p).exists()]
    paths += manifest_files(ctx.path("reference_prices_dir"))  # refuses files not in the manifest
    ref_dir = ctx.path("reference_prices_dir")
    if (ref_dir / MANIFEST_NAME).exists():
        paths.append(ref_dir / MANIFEST_NAME)
    for key in ("binance_map", "binance_window_overrides"):
        if ctx.path(key).exists():
            paths.append(ctx.path(key))
    return paths


def cmd_checksums(ctx) -> None:
    lines = write_checksums(_raw_paths(ctx), ctx.root, ctx.root / "provenance" / "CHECKSUMS.txt",
                            "raw inputs (read-only); regenerate with `python -m arkstream checksums`")
    print("\n".join(lines))


def cmd_ingest(ctx) -> None:
    cmd_checksums(ctx)
    w = ingest_all(ctx.path("traders"), ctx.path("fills"), processed_dir(ctx))
    print(f"wrote {sum(len(v) for v in w.values())} partitions under {processed_dir(ctx)}")


def cmd_build(ctx, asof: str | None, cards: bool) -> int:
    res = build(ctx, load_inputs(ctx), parse_one_utc(asof) if asof else None)
    written = write_outputs(ctx, res, cards=cards)
    outs = [p for p in written if "cards" not in p.parts]
    write_checksums(outs, ctx.root, ctx.root / "provenance" / "OUTPUT_CHECKSUMS.txt",
                    f"build outputs as of {res.asof.isoformat()} (cards excluded)")
    print(json.dumps(res.headline, indent=2, default=str))
    return 0


def cmd_refprices(ctx, checksums: bool, from_zips: str | None = None, zip_hashes: str | None = None,
                  lake_out: str | None = None, out_dir: str | None = None) -> int:
    """Validity windows -> mapping; Binance 1m klines -> data/reference/prices/ + MANIFEST.yaml (A13).

    `from_zips`: first rebuild the kline lake from Binance's monthly 1m zips (fetch_klines), each checked against
    its verified SHA-256 (`zip_hashes`: the fetcher's MANIFEST.csv or CHECKSUMS.txt), into `lake_out` (default:
    inputs.binance_lake, which must then be empty). `out_dir`: write the mapping, window evidence and prices there
    instead of the project's data/reference (used to check a rebuild against the published manifest)."""
    from arkstream import refprices as rf

    lake, cutoff = ctx.path("binance_lake"), ctx.cutoff
    if from_zips:
        src = Path(from_zips)
        fetched = src / "MANIFEST.csv"  # written by fetch_klines; else the hashes recorded with the lake's zips
        default_hashes = fetched if fetched.exists() else ctx.path("binance_map").parent / "CHECKSUMS.txt"
        zips = rf.verified_kline_zips(src, rf.load_zip_hashes(Path(zip_hashes) if zip_hashes else default_hashes))
        lake = Path(lake_out) if lake_out else lake
        written = rf.lake_from_zips(zips, lake)
        print(f"kline lake from {len(zips)} verified zips: {len(written)} files under {lake}")
    bdir = Path(out_dir) if out_dir else ctx.path("binance_map").parent
    bdir.mkdir(parents=True, exist_ok=True)
    map_out = bdir / "hl_binance_map.csv" if out_dir else ctx.path("binance_map")
    prices_out = bdir / "prices" if out_dir else ctx.path("reference_prices_dir")
    ev = rf.window_evidence(rf.scan_klines(lake), cutoff)
    mapping = rf.apply_windows(rf.load_map(ctx.path("binance_map")), ev,
                               rf.load_overrides(ctx.path("binance_window_overrides")), cutoff)
    rf.write_map(mapping, map_out)
    evo = (mapping.select("hl", "binance", "valid_from", "valid_to", "status", "window_rule", "hl_first_fill",
                          "hl_last_fill")
           .join(ev.rename({"symbol": "binance"}), on="binance", how="left"))
    rf.write_map(evo.with_columns([pl.col(c).dt.strftime("%Y-%m-%d %H:%M:%S")
                                   for c in ("first_bar", "last_bar", "first_live", "last_live")]),
                 bdir / "window_evidence.csv")
    rp = ctx.raw["reference_prices"]
    meta = {"dataset": "reference_prices", "source": rp["source"], "resolution": rp["resolution"],
            "retrieved_on": rp["retrieved_on"], "known_at": "bar close (Binance open_time + 60 s)",
            "cutoff": cutoff.isoformat(), "rules": [
                "only bars known at or before the cutoff",
                "only bars inside the coin's [valid_from, valid_to] (hl_binance_map.csv)",
                "only bars with volume > 0 (no carry-forward through zero-volume bars)",
                "price = close x price_factor_hl_per_binance"],
            "mapping_sha256": sha256_file(map_out)}
    files = rf.build_reference_files(lake, mapping, cutoff, prices_out, meta)
    if checksums and not from_zips:
        rf.write_raw_checksums(lake / "_raw", bdir / "CHECKSUMS.txt", lake / "_raw" / "_verified.sqlite")
    print(mapping.group_by("status").len().sort("status"))
    for f in files:
        shown = f.relative_to(ctx.root).as_posix() if f.is_relative_to(ctx.root) else f.as_posix()
        print(f"{shown}  {f.stat().st_size / 1e6:.1f} MB")
    return 0


def cmd_drift(ctx, aggtrades_dir: str | None, out_dir: str | None, preliminary: bool) -> int:
    """Drift parameters at each origin from data before it; 10-11 Oct separately (stress)."""
    from arkstream import drift
    from arkstream.prices import scan_reference

    rules = drift.DriftRules.from_config(ctx.raw)
    src_dir = Path(aggtrades_dir) if aggtrades_dir else ctx.path("aggtrades_dir")
    src = drift.AggTradesSource(src_dir, rules, require_manifest=not preliminary)
    cov = drift.coverage_report(src, rules)
    missing = cov.filter(~pl.col("available"))
    complete = missing.height == 0
    rp = ctx.raw["reference_prices"]
    res = drift.estimate(load_inputs(ctx).fills, scan_reference(ctx.path("reference_prices_dir")), src, rules,
                         rp["max_age_s"], rp["fallback_print_window_s"])
    out = Path(out_dir) if out_dir else ctx.root / "research" / "drift"
    out.mkdir(parents=True, exist_ok=True)
    tag = pl.lit("complete" if complete else "PRELIMINARY: aggTrades days missing")
    for name in ("development", "stress"):
        res[name].with_columns(aggtrades_coverage=tag, aggtrades_source=pl.lit(src.label)).write_csv(
            out / f"drift_{name}.csv")
    cov.write_csv(out / "aggtrades_coverage.csv")
    res["bands"].write_csv(out / "drift_hold_bands.csv")
    show = res["development"].filter((pl.col("band") == "all") & (pl.col("source") == "aggtrades"))
    print(show.select("origin", "coin", "horizon_ms", "measured", "leaders", "days", "mean_bps", "se_bps"))
    st = res["stress"].filter((pl.col("band") == "all") & (pl.col("source") == "aggtrades"))
    print(st.select("origin", "coin", "horizon_ms", "measured", "mean_bps", "se_bps"))
    print(f"aggTrades coverage: {cov['available'].sum()}/{cov.height} symbol-days"
          + ("" if complete else f"; missing e.g. {missing.head(3).rows()} -> outputs labelled PRELIMINARY"))
    print(f"wrote {out}")
    return 0


def cmd_leader(ctx, origins: list[str] | None, out_dir: str | None) -> int:
    """Phase 2 leader evidence per origin (grade A/B at each origin, funding included)."""
    from datetime import date

    from arkstream import leader

    out = Path(out_dir) if out_dir else ctx.root / "research" / "leader"
    out.mkdir(parents=True, exist_ok=True)
    only = [date.fromisoformat(o) for o in origins] if origins else None
    written = leader.run(ctx, load_inputs(ctx), out, only)
    print(f"wrote {len(written)} files under {out}")
    return 0


def cmd_audit(ctx, asof: str | None) -> int:
    res = build(ctx, load_inputs(ctx), parse_one_utc(asof) if asof else None)
    rows = audit.check(res, audit.load_expected(ctx.root / "provenance" / "expected_counts.yaml"))
    print(audit.format_rows(rows))
    bad = [r for r in rows if not r[3]]
    print(f"\n{len(rows) - len(bad)}/{len(rows)} checks passed")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="arkstream")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("checksums")
    sub.add_parser("ingest")
    replay = sub.add_parser("replay", help="Phase 3 follower replay through the last development window")
    replay.add_argument("--sensitivities", action="store_true", help="Run square-root impact and address cap variants")
    replay.add_argument("--size-study", action="store_true",
                        help="leader-size drift study on BTC/ETH/HYPE/SOL (ADR-0036), research/replay/leader_size")
    replay.add_argument("--models", default=None,
                        help="comma-separated sensitivity variants (default: all); e.g. part,part_ns,part_ns_sweep")
    replay.add_argument("--frozen", action="store_true",
                        help="ADR-0052: the current replay, frozen reference equity only: shared inputs, frozen "
                             "full stack, stress coverage (ADR-0055), cost surface, size study "
                             "(default research/replay_frozen)")
    replay.add_argument("--sizing", action="store_true",
                        help="archived (ADR-A0116/0052, not rerun): the dynamic vs frozen comparison in "
                             "research/replay_sizing")
    replay.add_argument("--cost-surface", action="store_true",
                        help="ADR-0050: frozen base cost surface on the test windows "
                             "(reads/writes research/replay_frozen)")
    replay.add_argument("--capture", action="store_true",
                        help="ADR-0063: capture and market-relative tables from an existing frozen tree "
                             "(default research/replay_frozen; also run at the end of --frozen)")
    replay.add_argument("--coin-filter", action="store_true",
                        help="ADR-A0140: the frozen replay with the selection rule's coin filter executed inside it "
                             "(default research/replay_coinfilter)")
    replay.add_argument("--allpriced", action="store_true",
                        help="ADR-0076: the frozen stack on every priced coin, current A/B universes "
                             "(default research/replay_allpriced)")
    replay.add_argument("--tradable", action="store_true",
                        help="ADR-0076: the frozen stack on each wallet's tradable set "
                             "(default research/replay_tradable; reads research/replay_allpriced)")
    replay.add_argument("--gray", action="store_true",
                        help="P5-1 (ADR-0095 item 3): the two Phase 5 sleeves at 2,500 and 5,000 USDC on the frozen "
                             "tradable stack (default research/replay_gray)")
    replay.add_argument("--holdout", action="store_true",
                        help="with --coin-filter: the holdout window only (refused unless the freeze holds)")
    replay.add_argument("--out", default=None, help="output folder (default depends on the mode)")
    b = sub.add_parser("build")
    b.add_argument("--asof", default=None, help="UTC timestamp; defaults to and is capped at CUTOFF")
    b.add_argument("--no-cards", action="store_true")
    r = sub.add_parser("refprices", help="build data/reference/prices from the Binance kline lake")
    r.add_argument("--no-checksums", action="store_true", help="skip hashing the raw Binance zips")
    r.add_argument("--from-zips", default=None, help="rebuild the kline lake from verified monthly 1m zips first")
    r.add_argument("--zip-hashes", default=None, help="verified hashes: fetcher MANIFEST.csv or CHECKSUMS.txt")
    r.add_argument("--lake-out", default=None, help="where to build the lake (default: inputs.binance_lake)")
    r.add_argument("--out-dir", default=None, help="write mapping, evidence and prices here (reproduction check)")
    d = sub.add_parser("drift", help="drift parameters from Binance aggTrades (development windows only)")
    d.add_argument("--aggtrades-dir", default=None, help="default: inputs.aggtrades_dir (needs MANIFEST.csv)")
    d.add_argument("--out", default=None, help="default: research/drift")
    d.add_argument("--preliminary", action="store_true",
                   help="read a folder without MANIFEST.csv (e.g. the lake's raw zips); outputs are labelled")
    le = sub.add_parser("leader", help="Phase 2 leader evidence per origin (drift.origins), point in time")
    le.add_argument("--origin", action="append", default=None, help="YYYY-MM-DD; repeatable; default: all origins")
    le.add_argument("--out", default=None, help="default: research/leader")
    hl = sub.add_parser("funding", help="Hyperliquid funding table, price check, userFunding check (ADRs 0009..0011)")
    hl.add_argument("--step", action="append",
                    choices=["coins", "table", "price-check", "price-check-origins", "user-check"], default=None,
                    help="repeatable; default: table, price-check, price-check-origins, user-check")
    hl.add_argument("--out", default=None, help="default: research/hyperliquid")
    lat = sub.add_parser("latency", help="Hyperliquid receive delay from recorded stream runs (ADRs 0040..0043, 0056)")
    lat.add_argument("--runs", default=None, help="default: data/reference/latency/hyperliquid")
    lat.add_argument("--out", default=None, help="default: research/latency")
    se = sub.add_parser("select", help="Phase 4 selection at every origin (ADRs A0130-A0139)")
    se.add_argument("--evaluate", action="store_true",
                    help="read the development test windows (ADRs A0133-A0137 first)")
    se.add_argument("--freeze", action="store_true",
                    help="ADRs 0091, 0097: write provenance/HOLDOUT_FREEZE.txt (needs frozen: true, no OPEN value in "
                         "risk.yaml, POLARS_MAX_THREADS and a matching output manifest)")
    se.add_argument("--output-manifest", action="store_true",
                    help="ADR-0097 item 4: write provenance/HOLDOUT_OUTPUT_MANIFEST.txt over the holdout path's trees")
    sv = sub.add_parser("select-v2", help="Phase 4 v2 qualification at every origin (ADRs 0070-0075, 0076-0079)")
    sv.add_argument("--out", default=None, help="default: research/selection_v2")
    p5 = sub.add_parser("phase5", help="Phase 5 development steps on development data only (ADR-0095)")
    p5.add_argument("step", choices=["risk-model", "population", "calibrate", "variants", "l1-oos", "pair", "report"],
                    help="risk-model: P5-2; population: P5-4 calibration and variants (or one of them); "
                         "l1-oos: L1 on the test windows (descriptive); "
                         "pair: P5-5 S*/U*/G*, random pairs, stress at the limits; report: P5-6 window report")
    p5.add_argument("--no-pairs", action="store_true", help="pair: skip the 200 random pairs per window")
    p5.add_argument("--out", default=None, help="output folder (default depends on the step)")
    a = sub.add_parser("audit")
    a.add_argument("--asof", default=None)
    args = ap.parse_args(argv)
    if args.cmd == "latency":  # no network, no package data needed
        from arkstream import latency
        return latency.main(Path(args.runs) if args.runs else latency.RUNS_DIR,
                            Path(args.out) if args.out else latency.OUT_DIR)
    ctx = load_context()
    if args.cmd == "checksums":
        cmd_checksums(ctx)
        return 0
    if args.cmd == "phase5":
        out = Path(args.out) if args.out else None
        if args.step == "risk-model":
            from arkstream import risk_model

            print(f"wrote {risk_model.run(ctx, out)}")
        elif args.step in ("population", "calibrate", "variants", "l1-oos"):
            from arkstream import phase5_population

            steps = ("calibrate", "variants") if args.step == "population" else (args.step,)
            print(f"wrote {phase5_population.run(ctx, out, steps)}")
        elif args.step == "pair":
            from arkstream import phase5_pair

            print(f"wrote {phase5_pair.run(ctx, out, pairs=not args.no_pairs)}")
        elif args.step == "report":
            from arkstream import holdout_report

            print(f"wrote {holdout_report.run_development(ctx, out=out)}")
        return 0
    if args.cmd == "replay":
        out = Path(args.out) if args.out else None
        if args.size_study:
            from arkstream.replay_size import study

            study(ctx, out or ctx.root / "research/replay/leader_size")
            return 0
        if args.cost_surface:
            from arkstream import replay_surface

            surface = replay_surface.run(ctx, out)
            with pl.Config(tbl_rows=60, tbl_cols=-1, tbl_width_chars=200):
                print(surface.filter(pl.col("origin") == "all_tests").select(
                    "policy", "kind", "point", "measured", "positive", "mean_return", "profit_usdc", "absorb_bps"))
            return 0
        if args.capture:
            from arkstream import replay_capture

            for path in replay_capture.run(ctx, out or ctx.root / "research/replay_frozen"):
                print(f"wrote {path}")
            return 0
        if args.coin_filter:
            from arkstream import replay_coinfilter

            target = replay_coinfilter.run_holdout(ctx, out) if args.holdout else replay_coinfilter.run(ctx, out)
            print(f"wrote {target}")
            return 0
        if args.frozen:
            from arkstream import replay_frozen

            print(f"wrote {replay_frozen.run(ctx, out)}")
            return 0
        if args.allpriced or args.tradable:
            from arkstream import replay_tradable

            run_v2 = replay_tradable.run_allpriced if args.allpriced else replay_tradable.run_tradable
            print(f"wrote {run_v2(ctx, out)}")
            return 0
        if args.gray:
            from arkstream import replay_gray

            print(f"wrote {replay_gray.run(ctx, out)}")
            return 0
        if args.sizing:
            from arkstream import replay_sizing

            print(f"wrote {replay_sizing.run(ctx, out)}")
            return 0
        if args.sensitivities:
            from arkstream.replay_sensitivity import run_sensitivities
            run_sensitivities(ctx, output=out, models=args.models.split(",") if args.models else None, original=out)
            return 0
        from arkstream.replay import run
        run(ctx, output=out)
        return 0
    if args.cmd == "ingest":
        cmd_ingest(ctx)
        return 0
    if args.cmd == "build":
        return cmd_build(ctx, args.asof, cards=not args.no_cards)
    if args.cmd == "refprices":
        return cmd_refprices(ctx, checksums=not args.no_checksums, from_zips=args.from_zips,
                             zip_hashes=args.zip_hashes, lake_out=args.lake_out, out_dir=args.out_dir)
    if args.cmd == "drift":
        return cmd_drift(ctx, args.aggtrades_dir, args.out, args.preliminary)
    if args.cmd == "leader":
        return cmd_leader(ctx, args.origin, args.out)
    if args.cmd == "funding":
        from arkstream import hyperliquid
        return hyperliquid.run(ctx, args.step or ["table", "price-check", "price-check-origins", "user-check"],
                               args.out)
    if args.cmd == "audit":
        return cmd_audit(ctx, args.asof)
    if args.cmd == "select-v2":
        from arkstream import selection_v2

        res = selection_v2.run(ctx, Path(args.out) if args.out else None)
        print(res.get("stopped") or f"ordering used: {res['decision']['ordering_used']}")
        return 0
    if args.cmd == "select":
        from arkstream import selection_run

        if args.output_manifest:
            from arkstream import freeze

            path, n = freeze.write_output_manifest(ctx.root)
            print(f"wrote {path} ({n} files)")
            return 0
        if args.freeze:
            from arkstream import freeze

            path, h = freeze.write_freeze(ctx, freeze.RULE)
            print(f"wrote {path}")
            print(f"freeze_hash: {h}")
            return 0

        res = selection_run.run(ctx, evaluate_dev=args.evaluate)
        print(f"selection written to {ctx.root / selection_run.OUT}" + (f"; rule {res['chosen']}" if args.evaluate
                                                                       else ""))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
