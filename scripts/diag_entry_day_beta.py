"""Diagnostic for the ADR-0082 bias (not a rule change): on a coin-day that opens from flat, the market component uses
the start-of-day exposure, which is 0, so the market move between the fill and the close stays in alpha.

Reruns the full Phase 4 v2 pipeline (`selection_v2.run`) into research/audit/diag_entry_beta_<variant>/ with only the
market component swapped, and compares every origin's categories, tau2, Q and hand-off with research/selection_v2:
- `entry_end`: on coin-days with e = 0 and an end-of-day holding H != 0, the market component uses H (the only
  exposure that day). Every other coin-day is unchanged. This isolates the ADR-0082 bias.
- `mean_exposure`: every coin-day uses (e + H) / 2. This is a broader sensitivity.
- `ex_funding`: the published market component, with funding moved out of the residual (funding treated as a separate
  source of return, not skill). Output folder research/audit/diag_entry_beta_ex_funding/.
Nothing under research/selection_v2 is written. Usage: uv run python scripts/diag_entry_day_beta.py [variant ...]
"""

import sys

sys.path.insert(0, "src")
from pathlib import Path

import polars as pl

from arkstream import selection_v2 as V2
from arkstream import selection_v2_stats as ST
from arkstream.config import load_context
from arkstream.selection_v2_market import FACTORS, KEY, beta_lookup

C = pl.col
OUT = Path("research/audit")


def make_residual(variant: str):
    def residual_coin_days(cd, betas, factors, returns):
        b = beta_lookup(betas, cd["coin"].unique().to_list())
        x = (cd.join(b, on="coin", how="left").join(factors.select("t", *FACTORS), on="t", how="left")
             .join(returns.select("coin", "t", r_coin="r"), on=["coin", "t"], how="left"))
        beta_r = sum((C(f"beta_{f}") * C(f) for f in FACTORS), pl.lit(0.0))
        if variant == "ex_funding":
            # funding as a separate source of return: the residual excludes it (market adjustment as published)
            exposure = C("e")
            market = pl.when(exposure == 0).then(0.0).otherwise(exposure * beta_r)
            return x.with_columns(market=market).with_columns(U=C("pnl") - C("market") - C("funding"),
                                                              beta_r=beta_r).select(
                *KEY, "t", "e", "H", "cash", "funding", "bad", "pnl", "market", "U", "r_coin", "beta_r",
                *[f"beta_{f}" for f in FACTORS])
        if variant == "entry_end":
            exposure = pl.when((C("e") == 0) & (C("H") != 0)).then(C("H")).otherwise(C("e"))
        elif variant == "mean_exposure":
            exposure = (C("e") + C("H")) / 2
        else:
            raise ValueError(variant)
        market = pl.when(exposure == 0).then(0.0).otherwise(exposure * beta_r)
        return x.with_columns(market=market).with_columns(U=C("pnl") - C("market"), beta_r=beta_r).select(
            *KEY, "t", "e", "H", "cash", "funding", "bad", "pnl", "market", "U", "r_coin", "beta_r",
            *[f"beta_{f}" for f in FACTORS])
    return residual_coin_days


def summary(root: Path) -> pl.DataFrame:
    rows = []
    for d in sorted(root.glob("origin=*")):
        ev = pl.read_parquet(d / "evidence.parquet")
        cat = [c for c in ev.columns if c == "category"][0]
        el = pl.read_parquet(d / "eligible.parquet") if (d / "eligible.parquet").exists() else pl.DataFrame()
        rows.append({"origin": d.name[7:], **{f"n_{k}": v for k, v in ev[cat].value_counts().rows()},
                     "handoff": ",".join(sorted(t[:6] for t in el["trader"].to_list())) if el.height else ""})
    return pl.DataFrame(rows).fill_null(0)


def main() -> None:
    variants = sys.argv[1:] or ["entry_end", "mean_exposure"]
    ctx = load_context()
    base = summary(ctx.root / ctx.raw["selection_v2"]["out_dir"])
    with pl.Config(tbl_cols=20, tbl_width_chars=220):
        print("published (ADR-0082):")
        print(base)
    original = ST.residual_coin_days
    for v in variants:
        ST.residual_coin_days = make_residual(v)
        try:
            out = OUT / f"diag_entry_beta_{v}"
            V2.run(ctx, out=out, verbose=False)
        finally:
            ST.residual_coin_days = original
        s = summary(out)
        with pl.Config(tbl_cols=20, tbl_width_chars=220):
            print(f"{v}:")
            print(s)
        a = pl.concat([pl.read_parquet(d / "evidence.parquet").with_columns(origin=pl.lit(d.name[7:]))
                       for d in sorted((ctx.root / ctx.raw["selection_v2"]["out_dir"]).glob("origin=*"))],
                      how="diagonal_relaxed")
        b = pl.concat([pl.read_parquet(d / "evidence.parquet").with_columns(origin=pl.lit(d.name[7:]))
                       for d in sorted(out.glob("origin=*"))], how="diagonal_relaxed")
        j = a.select("origin", "trader", cat_pub="category").join(
            b.select("origin", "trader", cat_diag="category"), on=["origin", "trader"], how="inner")
        moved = j.filter(C("cat_pub") != C("cat_diag"))
        moved.write_csv(OUT / f"diag_entry_beta_{v}_moves.csv")
        print(f"{v}: category moves {moved.height} of {j.height};",
              moved.group_by("cat_pub", "cat_diag").len().sort("len", descending=True).rows())


if __name__ == "__main__":
    main()
