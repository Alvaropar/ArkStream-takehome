"""Check 2: measured diversification statistics for every pair in the 3 Dec shortlist (training window only).

Same inputs as the ADR-A0132 walk for `rule_b_coin_filter`: `research/replay_coinfilter`, origin 3 Dec, training window,
base scenario; daily copy TWR and signed exposures by (coin, UTC midnight) at the Hyperliquid daily mark.

Per pair: the walk's correlation and its common days; the days both copies have a valid return; the days both actually
hold exposure (and the days either does); correlation on the both-exposed days, on days from 8 Sep (first executable
day), Spearman, and without 10-11 Oct; position overlap (cosine, as the walk) and the shared (coin, day) cells, shared
coins and the same-direction share. Per address: exposure days and coin / direction concentration.
Writes research/audit/basket_pairs_2025-12-03.csv and basket_concentration_2025-12-03.csv.
Usage: uv run python scripts/audit_basket_pairs.py
"""

import sys

sys.path.insert(0, "src")
import math
from datetime import date
from itertools import combinations
from pathlib import Path

import numpy as np
import polars as pl

from arkstream import selection as S
from arkstream.config import load_context

C = pl.col
ORIGIN = date(2025, 12, 3)
TREE = "research/replay_coinfilter"
FIRST_EXEC = date(2025, 9, 8)
CRASH = [date(2025, 10, 10), date(2025, 10, 11)]


def corr(x: np.ndarray, y: np.ndarray) -> float | None:
    return float(np.corrcoef(x, y)[0, 1]) if len(x) >= 3 and x.std() > 0 and y.std() > 0 else None


def spearman(x: np.ndarray, y: np.ndarray) -> float | None:
    rank = lambda v: pl.Series(v).rank("average").to_numpy()  # noqa: E731
    return corr(rank(x), rank(y)) if len(x) >= 3 else None


def main() -> None:
    ctx = load_context()
    ctx = type(ctx)(raw={**ctx.raw, "selection": {**ctx.raw["selection"], "replay_dir": TREE}}, root=ctx.root)
    rules = S.Rules.from_config(ctx.raw, "rule_b_coin_filter")
    short = pl.read_csv("research/selection/shortlist_2025-12-03.csv").filter(C("decision") == "selected")
    sel = sorted(short["trader"].to_list())
    daily = pl.read_parquet(S.scenario_dir(ctx, ORIGIN, "training", rules.scenario) / "daily_copy_twr.parquet",
                            columns=["trader", "day", "daily_twr"]).filter(C("trader").is_in(sel))
    f, _ = S.load_ledger(ctx, ORIGIN, "training", rules.scenario, S.training_end(ORIGIN))
    marks = pl.read_parquet(S.replay_dir(ctx) / "valuation_marks.parquet")
    pos = S.daily_positions(f.filter(C("trader").is_in(sel)), marks).with_columns(
        day=(C("boundary") - 1).cast(pl.Date))  # exposure held through the midnight that ends `day`
    exposed = pos.group_by("trader", "day").agg(gross=C("exposure").abs().sum())
    walk = pl.read_parquet(f"research/selection/origin={ORIGIN}/variant=rule_b_coin_filter/comovement.parquet")

    rows = []
    for a, b in combinations(sel, 2):
        j = (daily.filter(C("trader") == a).drop_nulls("daily_twr")
             .join(daily.filter(C("trader") == b).drop_nulls("daily_twr"), on="day", suffix="_b"))
        ea = set(exposed.filter(C("trader") == a)["day"].to_list())
        eb = set(exposed.filter(C("trader") == b)["day"].to_list())
        j = j.with_columns(both=C("day").is_in(list(ea & eb)), either=C("day").is_in(list(ea | eb)))
        x, y = j["daily_twr"].to_numpy(), j["daily_twr_b"].to_numpy()
        jb = j.filter("both")
        je = j.filter(C("day") >= FIRST_EXEC)
        jc = j.filter(~C("day").is_in(CRASH))
        va = pos.filter(C("trader") == a).select("coin", "boundary", "exposure")
        vb = pos.filter(C("trader") == b).select("coin", "boundary", "exposure")
        sh = va.join(vb, on=["coin", "boundary"], suffix="_b")
        na, nb = math.sqrt(float((va["exposure"] ** 2).sum())), math.sqrt(float((vb["exposure"] ** 2).sum()))
        overlap = float((sh["exposure"] * sh["exposure_b"]).sum()) / (na * nb) if na > 0 and nb > 0 else None
        w = walk.filter(((C("trader_a") == a) & (C("trader_b") == b)) | ((C("trader_a") == b) & (C("trader_b") == a)))
        rows.append({
            "trader_a": a, "trader_b": b,
            "walk_common_days": w["common_days"].item(), "walk_corr": w["corr"].item(),
            "walk_overlap": w["overlap"].item(),
            "valid_both_days": j.height, "both_exposed_days": jb.height, "either_exposed_days": j["either"].sum(),
            "exposed_a_days": len(ea), "exposed_b_days": len(eb),
            "corr_all_valid": corr(x, y),
            "corr_both_exposed": corr(jb["daily_twr"].to_numpy(), jb["daily_twr_b"].to_numpy()),
            "corr_from_8sep": corr(je["daily_twr"].to_numpy(), je["daily_twr_b"].to_numpy()),
            "corr_ex_10_11oct": corr(jc["daily_twr"].to_numpy(), jc["daily_twr_b"].to_numpy()),
            "spearman_from_8sep": spearman(je["daily_twr"].to_numpy(), je["daily_twr_b"].to_numpy()),
            "overlap": overlap, "shared_coin_days": sh.height,
            "shared_coins": ",".join(sorted(sh["coin"].unique().to_list())),
            "same_direction_share": (float(((sh["exposure"] * sh["exposure_b"]) > 0).mean()) if sh.height else None),
        })
    pairs = pl.DataFrame(rows)
    conc = (pos.group_by("trader", "coin").agg(gross=C("exposure").abs().sum(), net=C("exposure").sum(),
                                               days=C("day").n_unique())
            .with_columns(share=C("gross") / C("gross").sum().over("trader"),
                          long_share=(C("net") / C("gross") + 1) / 2)
            .sort("trader", "share", descending=[False, True]))
    out = Path("research/audit")
    out.mkdir(parents=True, exist_ok=True)
    pairs.write_csv(out / f"basket_pairs_{ORIGIN}.csv", float_precision=4)
    conc.write_csv(out / f"basket_concentration_{ORIGIN}.csv", float_precision=4)
    with pl.Config(tbl_cols=30, tbl_width_chars=260, fmt_str_lengths=40, float_precision=3, tbl_rows=40):
        print(pairs.with_columns(C("trader_a", "trader_b").str.slice(0, 6)).transpose(include_header=True))
        print(conc.with_columns(C("trader").str.slice(0, 6)).group_by("trader", maintain_order=True).head(5))


if __name__ == "__main__":
    main()
