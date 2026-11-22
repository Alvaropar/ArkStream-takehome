"""Phase 4 driver: `python -m arkstream select` (ADRs 0130-0139).

Stage 1, `select_all` (no outcome is read): for every variant and every origin (the four development origins and
3 Dec), the copier screen as of the origin, the coin set (coin-filter variant) and every selection table, written to
research/selection/origin=<date>/variant=<v>/. Each variant reads its own replay tree (`selection.variants.*.
replay_dir`): the coin-filter rule the filtered tree (ADR-0140), the others the unfiltered one; the coin-filter rule's
ADR-0136 attribution scoring is kept beside it as `<variant>_attribution`.

Stage 2, `evaluate` (development outcomes): the walk-forward of every variant against its baselines, the choice
between variants by the pre-stated criterion (ADR-0137), and for the chosen rule the market-relative and capture
tables, Clopper-Pearson, MinTRL, the pre-registered diagnostics and the 3 Dec shortlist.

Nothing here computes a window after the holdout start without the freeze (`freeze.guard`).
"""

from __future__ import annotations

import math
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from arkstream import copiers, drift
from arkstream import selection as S
from arkstream import selection_coins as SC
from arkstream import selection_diagnostics as D
from arkstream import selection_eval as E
from arkstream.config import load_yaml
from arkstream.pipeline import load_inputs
from arkstream.replay_capture import market_relative
from arkstream.replay_market import midnight, ms

C = pl.col
OUT = "research/selection"
SHORTLIST_ORIGIN = date(2025, 12, 3)
# ADR-0137: ties on the criterion go to the simpler rule, in this order.
SIMPLICITY = ("rule_a", "rule_c_p10", "rule_b_coin_filter")


def origins(ctx) -> list[date]:
    return list(drift.DriftRules.from_config(ctx.raw).origin_dates)


def dev_origins(ctx) -> list[date]:
    hs = drift.DriftRules.from_config(ctx.raw).holdout_start
    return [o for o in origins(ctx) if o < hs]


def write(df: pl.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".csv":
        df.write_csv(path, float_precision=10)
    else:
        df.write_parquet(path, compression="zstd", statistics=False)


def variants(ctx) -> list[str]:
    return list(ctx.raw["selection"]["variants"])


FROZEN = "research/replay_frozen"
ATTRIBUTION = "_attribution"  # ADR-0136 record: rule_b scored by removing dropped coins from the unfiltered ledgers


def ctx_for(ctx, replay_dir: str):
    """The context with the selection reading `replay_dir` (unfiltered frozen tree, or the ADR-0140 filtered one)."""
    raw = {**ctx.raw, "selection": {**ctx.raw["selection"], "replay_dir": replay_dir}}
    return type(ctx)(raw=raw, root=ctx.root)


def origin_data(ctx, inp=None) -> dict[date, S.OriginData]:
    """Inputs at every origin from the context's replay tree; the coin set always from the unfiltered tree
    (ADR-0136 definition, ADR-0140 item 2)."""
    inp = inp or load_inputs(ctx)
    rules = S.Rules.from_config(ctx.raw)
    base = ctx_for(ctx, FROZEN)
    out = {}
    for o in origins(ctx):
        cop = copiers.screen(inp.fills, midnight(o), ctx.raw["copiers"])["clusters"]
        data = S.load_origin(ctx, o, inp.traders, cop, rules)
        data.coin_set = SC.coin_set(base, o, rules)
        out[o] = data
    return out


def plan(ctx) -> list[tuple[str, str, str]]:
    """(label, config variant, replay tree) for every rule evaluated: each config variant on its own tree, plus the
    ADR-0136 attribution record of every coin-filter variant on the unfiltered tree."""
    rows = []
    for v in variants(ctx):
        rules = S.Rules.from_config(ctx.raw, v)
        rows.append((v, v, rules.replay_dir))
        if rules.coin_filter and rules.replay_dir != FROZEN:
            rows.append((v + ATTRIBUTION, v, FROZEN))
    return rows


def select_all(ctx, data: dict[str, dict[date, S.OriginData]], out: Path
               ) -> dict[tuple[str, date], dict[str, pl.DataFrame]]:
    tables = {}
    for label, v, tree in plan(ctx):
        rules = S.Rules.from_config(ctx.raw, v)
        for o, d in data[tree].items():
            base = out / f"origin={o}"
            if tree == FROZEN:
                write(d.copiers.with_columns(origin=pl.lit(o)).sort("trader"), base / "copier_clusters.parquet")
                assert d.coin_set is not None
                write(d.coin_set, base / "coin_set.csv")
            t = S.select_origin(d, rules)
            for df_name in ("candidates", "decisions", "walk"):
                t[df_name] = t[df_name].with_columns(variant=pl.lit(label))
            tables[(label, o)] = t
            folder = base / f"variant={label}"
            for name, df in t.items():
                write(df, folder / f"{name}.parquet")
            write(t["decisions"], folder / "decisions.csv")
    return tables


def evaluate(ctx, data: dict[str, dict[date, S.OriginData]], tables: dict[tuple[str, date], dict[str, pl.DataFrame]],
             out: Path) -> dict[str, Any]:
    cfg = ctx.raw["selection"]
    ladder = float(load_yaml("risk.yaml", ctx.root / "config")["drawdown_ladder"]["reduce_only"])
    crash = [date.fromisoformat(x) for x in cfg["crash_dates"]]
    all_o = origins(ctx)
    devs = dev_origins(ctx)
    trees = sorted({tree for _, _, tree in plan(ctx)})
    outcomes = {tree: {o: E.sleeve_outcomes(ctx_for(ctx, tree), o, crash, ladder) for o in devs} for tree in trees}
    base = ctx_for(ctx, FROZEN)
    filtered = {}
    for o in devs:  # ADR-0136 attribution: dropped coins removed from the unfiltered ledgers
        cs = data[FROZEN][o].coin_set
        assert cs is not None
        filtered[o] = SC.filtered_outcomes(base, o, E.test_end(all_o, o), cs.filter("kept")["coin"].to_list(), crash,
                                           ladder, outcomes[FROZEN][o])
    wf, dist = [], []
    for label, v, tree in plan(ctx):
        rules = S.Rules.from_config(ctx.raw, v)
        c = ctx_for(ctx, tree)
        for o in devs:
            if rules.coin_filter and tree == FROZEN:
                row, d = E.evaluate_window(c, o, tables[(label, o)], filtered[o][0], cfg, label, filtered[o][1])
            else:
                row, d = E.evaluate_window(c, o, tables[(label, o)], outcomes[tree][o], cfg, label)
            row["replay_tree"] = tree
            wf.append(row)
            dist += d
    walk_forward = pl.DataFrame(wf, infer_schema_length=None).sort("variant", "origin")
    baselines = pl.DataFrame(dist, infer_schema_length=None).sort("variant", "origin", "baseline", "scenario")
    # ADR-0137 criterion, as it was applied: on the variants scored on the unfiltered tree (rule_b by attribution).
    # ADR-0140: the rule in force is the config's, whatever the executable rerun shows; no new choice is made.
    score = walk_forward.group_by("variant").agg(matched_wins=C("matched_win").sum(), ab_wins=C("ab_win").sum(),
                                                 mean_basket_base=C("basket_base").mean())
    basis = {label: (v if tree == FROZEN and label.endswith(ATTRIBUTION) else label)
             for label, v, tree in plan(ctx) if tree == FROZEN}
    order = {v: i for i, v in enumerate(SIMPLICITY)}
    ranked = sorted((r for r in score.rows(named=True) if r["variant"] in basis),
                    key=lambda r: (-r["matched_wins"], order.get(basis[r["variant"]], 99)))
    by_criterion = basis[ranked[0]["variant"]]
    chosen = cfg["rule"]
    if by_criterion != chosen:
        raise ValueError(f"ADR-0137 criterion gives {by_criterion}, the config names {chosen}")
    score = score.with_columns(
        adr0137_basis=C("variant").is_in(list(basis)),
        in_force=C("variant") == chosen,
        simplicity_order=C("variant").replace_strict({k: order.get(b, 99) for k, b in basis.items()}, default=99),
    ).sort("simplicity_order", "variant")
    write(walk_forward, out / "walk_forward.csv")
    write(baselines, out / "baselines.csv")
    write(score, out / "variant_choice.csv")
    tree = S.Rules.from_config(ctx.raw, chosen).replay_dir
    res = report_chosen(ctx_for(ctx, tree), data[tree], tables, outcomes[tree], chosen, out, crash, None)
    res.update(chosen=chosen, walk_forward=walk_forward, score=score)
    return res


def report_chosen(ctx, data, tables, outcomes, chosen: str, out: Path, crash: list[date],
                  filtered: dict | None = None) -> dict[str, Any]:
    """5a, 5b, intervals, MinTRL, diagnostics and the shortlist for the chosen rule. With the coin filter
    (`filtered` = per origin (outcomes, daily per scenario)) the basket, equal-weight and sleeve series are the
    filtered ones; capture adds filtered ratios (follower vs benchmark PnL in kept coins) beside the unfiltered
    ADR-0162 gap decomposition, which is not re-decomposed by coin."""
    allocation = E.ctx_allocation(ctx)
    all_o = origins(ctx)
    devs = dev_origins(ctx)
    wf = pl.read_csv(out / "walk_forward.csv", try_parse_dates=True).filter(C("variant") == chosen)
    n = wf.height
    iv = []
    for name, col in (("matched_random_k", "matched_win"), ("ab_random_k", "ab_win"),
                      ("equal_weight", "beats_equal_weight"),
                      ("matched_random_k_ex_crash", "matched_win_ex_crash")):
        iv.append({"comparison": name, **E.intervals(int(wf[col].sum()), n)})
    # 5a market-relative and 5b capture, per development window and scenario
    mr, caps, cdaily, med = [], [], [], []
    daily_basket: list[pl.DataFrame] = []
    daily_eq: list[pl.DataFrame] = []
    cap_all = pl.read_parquet(S.replay_dir(ctx) / "capture_summary.parquet")
    cap_daily_all = pl.read_parquet(S.replay_dir(ctx) / "capture_daily.parquet")
    m_all = pl.read_parquet(S.replay_dir(ctx) / "market_relative.parquet")
    for o in devs:
        end = E.test_end(all_o, o)
        t = tables[(chosen, o)]
        chosen_tr = S.selected(t)
        pool = sorted(t["candidates"].filter("eligible")["trader"].to_list())
        fee = data[o].evidence.select("trader", "fee_rate_bps")
        turnover = E.benchmark_turnover(ctx, o)
        fdaily = filtered[o][1] if filtered else None
        if fdaily is not None:
            kept = data[o].coin_set.filter("kept")["coin"].to_list()
            bench_f = SC.coin_daily(ctx, o, "test", None, o, end, kept)
        for sc in E.SCENARIOS:
            for name, members in (("basket", chosen_tr), ("equal_weight", pool)):
                if members:
                    mr.append({"origin": o, **E.series_market(ctx, o, end, sc, name, members,
                                                              None if fdaily is None else fdaily[sc])})
            if fdaily is not None:
                marks = pl.read_parquet(S.replay_dir(ctx) / "valuation_marks.parquet")
                fm = market_relative(fdaily[sc].filter(C("trader").is_in(chosen_tr)), marks,
                                     ms(midnight(o)), ms(midnight(end)))
                for r in fm.iter_rows(named=True):
                    mr.append({"origin": o, "series": "sleeve_filtered:" + r.pop("trader"), "scenario": sc,
                               "addresses": 1, **r,
                               "return_over_btc": None if r["copy_return"] is None or r["btc_buy_hold"] is None
                               else r["copy_return"] - r["btc_buy_hold"],
                               "return_over_eth": None if r["copy_return"] is None or r["eth_buy_hold"] is None
                               else r["copy_return"] - r["eth_buy_hold"]})
                fpnl = fdaily[sc].sort("trader", "day").group_by("trader", maintain_order=True).agg(
                    follower_pnl=C("equity").last() - allocation)
                bpnl = bench_f.sort("trader", "day").group_by("trader", maintain_order=True).agg(
                    benchmark_pnl=C("equity").last() - allocation)
                both = fpnl.join(bpnl, on="trader")
                for level, members in (("sleeve_filtered", chosen_tr), ("basket_filtered", chosen_tr),
                                       ("equal_weight_filtered", pool)):
                    units = [(t, [t]) for t in members] if level == "sleeve_filtered" else [(level, members)]
                    for label, mem in units:
                        u = both.filter(C("trader").is_in(mem))
                        if not u.height:
                            continue
                        fp, bp = u["follower_pnl"].sum(), u["benchmark_pnl"].sum()
                        ok = (u["follower_pnl"].null_count() == 0 and u["benchmark_pnl"].null_count() == 0
                              and abs(bp) >= 0.01 * allocation * u.height)
                        caps.append(pl.DataFrame([{
                            "level": level, "series": label, "addresses": u.height, "follower_pnl": fp,
                            "benchmark_pnl": bp, "capture_ratio": fp / bp if ok else None,
                            "status": "ok" if ok else "not_meaningful", "benchmark_won": bp > 0,
                            "origin": o, "scenario": sc}]))
                for name, members in (("basket_filtered", chosen_tr), ("equal_weight_filtered", pool)):
                    fd = fdaily[sc].filter(C("trader").is_in(members)).sort("day", "trader").group_by(
                        "day", maintain_order=True).agg(follower_pnl=(C("equity") - allocation).sum(),
                                                        addresses=pl.len())
                    bd = bench_f.filter(C("trader").is_in(members)).sort("day", "trader").group_by(
                        "day", maintain_order=True).agg(benchmark_pnl=(C("equity") - allocation).sum())
                    cdaily.append(fd.join(bd, on="day", how="left").with_columns(
                        leader_twr_mean=pl.lit(None, pl.Float64), origin=pl.lit(o), scenario=pl.lit(sc),
                        series=pl.lit(name)).sort("day"))
            sl = m_all.filter((C("origin") == o) & (C("window") == "test") & (C("scenario") == sc)
                              & C("trader").is_in(chosen_tr))
            for r in sl.iter_rows(named=True):
                mr.append({"origin": o, "series": "sleeve:" + r["trader"], "scenario": sc, "addresses": 1,
                           **{k: r[k] for k in ("copy_return", "copy_days", "n_days", "alpha", "alpha_lo", "alpha_hi",
                                                "beta_btc", "beta_btc_lo", "beta_btc_hi", "beta_eth", "beta_eth_lo",
                                                "beta_eth_hi", "r_squared", "btc_buy_hold", "eth_buy_hold",
                                                "buy_hold_from")},
                           "return_over_btc": None if r["copy_return"] is None or r["btc_buy_hold"] is None
                           else r["copy_return"] - r["btc_buy_hold"],
                           "return_over_eth": None if r["copy_return"] is None or r["eth_buy_hold"] is None
                           else r["copy_return"] - r["eth_buy_hold"]})
            cw = cap_all.filter((C("origin") == o) & (C("window") == "test") & (C("scenario") == sc))
            groups = {"sleeve": chosen_tr, "basket": chosen_tr, "equal_weight": pool}
            rows = E.capture_rows(cw, groups, fee, turnover, allocation)
            if rows.height:
                caps.append(rows.with_columns(origin=pl.lit(o), scenario=pl.lit(sc)))
                sleeves = rows.filter(C("level") == "sleeve")
                pool_rows = E.capture_rows(cw, {"sleeve": pool}, fee, turnover, allocation)
                med.append({"origin": o, "scenario": sc, "scope": "selected", **E.capture_medians(sleeves)})
                med.append({"origin": o, "scenario": sc, "scope": "eligible", **E.capture_medians(pool_rows)})
            cd = cap_daily_all.filter((C("origin") == o) & (C("window") == "test") & (C("scenario") == sc))
            for name, members in (("basket", chosen_tr), ("equal_weight", pool)):
                g = cd.filter(C("trader").is_in(members)).sort("day", "trader").group_by("day", maintain_order=True)
                cdaily.append(g.agg(follower_pnl=C("follower_pnl").sum(), benchmark_pnl=C("benchmark_pnl").sum(),
                                    leader_twr_mean=C("leader_twr").mean(), addresses=pl.len())
                              .with_columns(origin=pl.lit(o), scenario=pl.lit(sc), series=pl.lit(name)).sort("day"))
        for members, acc in ((chosen_tr, daily_basket), (pool, daily_eq)):
            if members:
                acc.append(E.basket_daily(ctx, o, "base", members, None if fdaily is None else fdaily["base"])
                           .with_columns(origin=pl.lit(o)))
        # random-k context for 5a: the median draw return beside BTC / ETH buy-and-hold
        bh = m_all.filter((C("origin") == o) & (C("window") == "test") & (C("scenario") == "base")).select(
            "btc_buy_hold", "eth_buy_hold").head(1)
        w = wf.filter(C("origin") == o).row(0, named=True)
        for name, col in (("matched_random_k_median", "matched_rk_median"), ("ab_random_k_median", "ab_rk_median")):
            if w.get(col) is not None and bh.height:
                mr.append({"origin": o, "series": name, "scenario": "base", "addresses": w["k"],
                           "copy_return": w[col], "btc_buy_hold": bh["btc_buy_hold"][0],
                           "eth_buy_hold": bh["eth_buy_hold"][0],
                           "return_over_btc": w[col] - bh["btc_buy_hold"][0],
                           "return_over_eth": w[col] - bh["eth_buy_hold"][0]})
    market = pl.DataFrame(mr, infer_schema_length=None).sort("origin", "scenario", "series")
    capture = pl.concat(caps, how="diagonal_relaxed").sort("origin", "scenario", "level", "series")
    capture_daily = pl.concat(cdaily, how="diagonal_relaxed").select(
        "origin", "scenario", "series", "day", "addresses", "follower_pnl", "benchmark_pnl", "leader_twr_mean"
    ).sort("origin", "scenario", "series", "day")
    medians = pl.DataFrame(med, infer_schema_length=None).sort("origin", "scenario", "scope")
    trl = []
    for name, acc in (("basket", daily_basket), ("equal_weight", daily_eq)):
        x = pl.concat(acc)["daily_twr"].to_numpy() if acc else np.array([])
        trl.append({"series": name + ("_coin_filtered" if filtered else ""),
                    "sample": "development test windows (used for tuning: optimistic)",
                    **E.mintrl(x.astype(float))})
    write(market, out / "market_relative.csv")
    write(capture, out / "capture.csv")
    write(capture_daily, out / "capture_daily.csv")
    write(medians, out / "capture_medians.csv")
    write(pl.DataFrame(iv), out / "intervals.csv")
    write(pl.DataFrame(trl, infer_schema_length=None), out / "min_trl.csv")
    diagnostics(ctx, data, tables, outcomes, chosen, out / "diagnostics", crash)
    shortlist = tables[(chosen, SHORTLIST_ORIGIN)]["decisions"]
    write(shortlist, ctx.root / "research/selection/shortlist_2025-12-03.csv")
    return {"intervals": pl.DataFrame(iv), "market": market, "capture": capture, "medians": medians,
            "min_trl": pl.DataFrame(trl, infer_schema_length=None), "shortlist": shortlist}


def diagnostics(ctx, data, tables, outcomes, chosen: str, out: Path, crash: list[date]) -> None:
    all_o = origins(ctx)
    devs = dev_origins(ctx)
    frames = {o: D.predictor_frame(ctx, o, tables[(chosen, o)]["candidates"], outcomes[o]) for o in devs}
    write(D.persistence(frames), out / "persistence.csv")
    write(D.feature_screen(frames), out / "feature_screen.csv")
    write(D.gate_audit(frames), out / "gate_audit.csv")
    write(pl.concat([D.attribution(ctx, o, E.test_end(all_o, o), tables[(chosen, o)]["candidates"], crash)
                     for o in devs]), out / "attribution.csv")
    write(D.capture_drivers(frames), out / "capture_drivers.csv")
    write(pl.concat([D.alpha_beta(ctx, o, tables[(chosen, o)]["candidates"], S.selected(tables[(chosen, o)]))
                     for o in devs]), out / "alpha_beta.csv")
    write(pl.concat([D.crowding(o, data[o], sorted(tables[(chosen, o)]["candidates"].filter("eligible")["trader"]),
                                S.selected(tables[(chosen, o)])) for o in devs]), out / "crowding.csv")
    write(pl.concat([D.tail(o, data[o], tables[(chosen, o)]["candidates"], crash) for o in devs],
                    how="diagonal_relaxed"), out / "tail.csv")
    write(D.decay(frames), out / "decay.csv")


def run(ctx, evaluate_dev: bool = True) -> dict[str, Any]:
    out = ctx.root / OUT
    inp = load_inputs(ctx)
    data = {tree: origin_data(ctx_for(ctx, tree), inp) for tree in sorted({t for _, _, t in plan(ctx)})}
    tables = select_all(ctx, data, out)
    if not evaluate_dev:
        return {"tables": tables}
    res = evaluate(ctx, data, tables, out)
    res["tables"] = tables
    return res


def combos(n: int, k: int) -> int:
    return math.comb(n, k) if n >= k else 0
