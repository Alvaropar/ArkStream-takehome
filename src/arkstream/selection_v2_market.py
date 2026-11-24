"""Phase 4 v2 market model (ADRs 0071, 0077): coin returns from Hyperliquid daily marks, the BTC / ETH / ALT factors,
coin betas fitted once per origin on the 90 days before it, and each copy's daily exposures and residual PnL.

Day t is a UTC calendar day; boundary b is the midnight starting day b (epoch days). The mark at boundary b is the
Hyperliquid daily close the replay values its ledger at. Then:

* `e_{c,t}` = position held through boundary t x mark(t) (start-of-day exposure), `G_t = Σ_c |e_{c,t}|`;
* `r_{c,t}` = mark(t + 1) / mark(t) - 1;
* `PnL_{c,t}` = cash of fills acknowledged on day t + funding posted on day t + H_{c,t} - H_{c,t-1}, with
  `H_{c,t}` = position held through boundary t + 1 x mark(t + 1): the replay's own valuation (`value_book`);
* `U_{c,t} = PnL_{c,t} - e_{c,t} Σ_f β_{c,f} r_{f,t}`.

Everything an origin's statistic uses comes from marks up to the origin's boundary (the training ledger's own closing
mark); the test window uses the same origin's betas and ALT membership.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from arkstream.replay_book import ledger
from arkstream.replay_market import DAY

C = pl.col
KEY = ["trader", "coin"]
FACTORS = ("BTC", "ETH", "ALT")
IDENTITY = {"BTC": (1.0, 0.0, 0.0), "ETH": (0.0, 1.0, 0.0)}
SUFFIX = "_sqrt_cap_part_ns_sweep_frozen"
BENCH = "benchmark=unattainable_frozen"


def epoch_day(d: date) -> int:
    return (d - date(1970, 1, 1)).days


def coin_returns(marks: pl.DataFrame) -> pl.DataFrame:
    """Daily return of every coin with marks: day t = mark(t + 1) / mark(t) - 1 (null when either is missing)."""
    m = marks.select("coin", "boundary", "mark").filter(C("mark").is_not_null() & (C("mark") > 0))
    nxt = m.with_columns(boundary=C("boundary") - 1).rename({"mark": "mark_next"})
    r = m.join(nxt, on=["coin", "boundary"], how="inner").select(
        "coin", t=C("boundary"), r=C("mark_next") / C("mark") - 1)
    return r.sort("coin", "t")


def factor_returns(returns: pl.DataFrame, members: list[str]) -> pl.DataFrame:
    """BTC, ETH and ALT (equal-weight mean of the members' returns valid that day) by epoch day t."""
    alt_members = sorted(set(members) - {"BTC", "ETH"})
    alt = (returns.filter(C("coin").is_in(alt_members)).sort("t", "coin")
           .group_by("t", maintain_order=True).agg(ALT=C("r").mean(), alt_n=pl.len()))
    btc = returns.filter(C("coin") == "BTC").select("t", BTC="r")
    eth = returns.filter(C("coin") == "ETH").select("t", ETH="r")
    days = pl.concat([btc.select("t"), eth.select("t"), alt.select("t")]).unique().sort("t")
    return (days.join(btc, on="t", how="left").join(eth, on="t", how="left").join(alt, on="t", how="left")
            .with_columns(C("alt_n").fill_null(0)).sort("t"))


def fit_betas(returns: pl.DataFrame, factors: pl.DataFrame, origin: date, coins: list[str] | None = None,
              lookback: int = 90, shrink_days: int = 30, min_fit: int = 10) -> pl.DataFrame:
    """ADR-0071 / ADR-0077: per coin, OLS with intercept of r_c on (BTC, ETH, ALT) over the days o - lookback .. o - 1
    where all four are valid, shrunk toward the cross-coin median (OLS coins other than BTC and ETH) with weight
    n / (n + shrink_days); n < min_fit or a singular design gives weight 0. BTC and ETH carry identity betas.
    `coins` adds rows (prior only) for coins without marks."""
    o = epoch_day(origin)
    lo, hi = o - lookback, o - 1
    f = factors.filter(C("t").is_between(lo, hi)).drop_nulls(["BTC", "ETH", "ALT"])
    r = returns.filter(C("t").is_between(lo, hi)).join(f.select("t", *FACTORS), on="t", how="inner")
    names = sorted(set(r["coin"].unique().to_list()) | set(coins or []))
    by = {c: g for (c,), g in r.sort("coin", "t").group_by("coin", maintain_order=True)}
    ols: dict[str, tuple[int, np.ndarray | None, int | None, int | None]] = {}
    for c in names:
        g = by.get(c)
        if g is None or g.height == 0:
            ols[c] = (0, None, None, None)
            continue
        n = g.height
        est = None
        if n >= min_fit:
            x = np.column_stack([np.ones(n), g.select(FACTORS).to_numpy()])
            if np.linalg.matrix_rank(x) == x.shape[1]:
                est = np.linalg.lstsq(x, g["r"].to_numpy(), rcond=None)[0][1:]
        tt = g["t"].to_numpy()
        ols[c] = (n, est, int(tt.min()), int(tt.max()))
    fitted = [v[1] for c, v in ols.items() if v[1] is not None and c not in IDENTITY]
    med = np.median(np.vstack(fitted), axis=0) if fitted else np.zeros(3)
    rows = []
    for c in names:
        n, est, first, last = ols[c]
        if c in IDENTITY:
            beta, w, kind = np.array(IDENTITY[c]), 1.0, "identity"
        elif est is None:
            beta, w, kind = med, 0.0, "prior" if n < min_fit else "singular_prior"
        else:
            w = n / (n + shrink_days)
            beta, kind = w * est + (1 - w) * med, "shrunk_ols"
        o_b = est if est is not None else np.full(3, np.nan)
        rows.append((c, n, kind, float(w), *map(float, beta), *map(float, o_b), first, last, origin))
    schema = {"coin": pl.String, "n_days": pl.Int64, "kind": pl.String, "weight": pl.Float64,
              "beta_BTC": pl.Float64, "beta_ETH": pl.Float64, "beta_ALT": pl.Float64,
              "ols_BTC": pl.Float64, "ols_ETH": pl.Float64, "ols_ALT": pl.Float64,
              "first_day": pl.Int64, "last_day": pl.Int64, "fit_date": pl.Date}
    out = pl.DataFrame(rows, schema=schema, orient="row").with_columns(
        C("ols_BTC", "ols_ETH", "ols_ALT").fill_nan(None))
    return out.with_columns(prior_BTC=pl.lit(float(med[0])), prior_ETH=pl.lit(float(med[1])),
                            prior_ALT=pl.lit(float(med[2]))).sort("coin")


def beta_lookup(betas: pl.DataFrame, coins: list[str]) -> pl.DataFrame:
    """Betas for `coins`; a coin absent from the fit takes the prior (the cross-coin median)."""
    prior = betas.select("prior_BTC", "prior_ETH", "prior_ALT").row(0)
    want = pl.DataFrame({"coin": sorted(set(coins))}, schema={"coin": pl.String})
    b = want.join(betas.select("coin", "beta_BTC", "beta_ETH", "beta_ALT"), on="coin", how="left")
    return b.with_columns(*[C(f"beta_{f}").fill_null(p) for f, p in zip(FACTORS, prior, strict=True)])


def scenario_dir(tree: Path, origin: date, window: str, scenario: str | None) -> Path:
    base = tree / f"origin={origin}" / f"window={window}"
    return base / BENCH if scenario is None else base / f"scenario={scenario}{SUFFIX}"


ORDER_COLS = ["trader", "coin", "status", "quantity", "fill_px", "fee", "anchor_px", "ack_ms", "decision_ms",
              "batch", "oid", "source_rows", "source_tids", "leader_notional"]


def load_window(tree: Path, origin: date, window: str, scenario: str | None, end: date
                ) -> tuple[pl.DataFrame, pl.DataFrame]:
    """The filled ledger (`replay_book.ledger`) and funding rows of one replay window and scenario."""
    d = scenario_dir(tree, origin, window, scenario)
    cols = ORDER_COLS if scenario is not None else [c for c in ORDER_COLS if c not in ("source_rows", "source_tids")]
    orders = pl.read_parquet(d / "follower_orders.parquet", columns=cols)
    f = ledger(orders, datetime(end.year, end.month, end.day, tzinfo=UTC))
    fund = pl.read_parquet(d / "funding_payments.parquet", columns=["trader", "coin", "batch", "payment", "day"])
    return f, fund


def group_sum(df: pl.DataFrame, keys: list[str], values: dict[str, pl.Expr],
              counts: dict[str, pl.Expr] | None = None) -> pl.DataFrame:
    """Per group of `keys`: float sums of `values` (nulls count as 0) and integer sums of `counts`, added in row order
    with `numpy.bincount` so a rerun is byte-identical (a threaded polars group-by can change the order of a float
    sum). Groups are formed by a stable sort on `keys`, so the caller's order within a group is kept."""
    counts = counts or {}
    x = df.select(*keys, **values, **counts).sort(keys, maintain_order=True)
    schema: dict[str, Any] = {**{k: x.schema[k] for k in keys}, **dict.fromkeys(values, pl.Float64),
                              **dict.fromkeys(counts, pl.Int64)}
    if x.height == 0:
        return pl.DataFrame(schema=schema)
    gid = x.select(pl.struct(keys).rle_id())[:, 0].to_numpy()
    first = np.r_[0, np.flatnonzero(np.diff(gid)) + 1]
    out = x.select(keys)[first.tolist()]
    n = int(gid[-1]) + 1
    cols = [pl.Series(k, np.bincount(gid, weights=x[k].fill_null(0).cast(pl.Float64).to_numpy(), minlength=n))
            for k in values]
    cols += [pl.Series(k, np.bincount(gid, weights=x[k].fill_null(0).cast(pl.Float64).to_numpy(), minlength=n)
                       .round().astype(np.int64)) for k in counts]
    return out.with_columns(cols).select(list(schema))


def coin_days(f: pl.DataFrame, fund: pl.DataFrame, marks: pl.DataFrame, start: date, end: date) -> pl.DataFrame:
    """Per (trader, coin, day t) in [start, end): start-of-day exposure e, end-of-day holding H, cash, funding and
    PnL_{c,t}; `bad` when a needed mark (boundary t or t + 1 while held) or a funding payment of the day is unknown."""
    s, e = epoch_day(start), epoch_day(end)
    mk = marks.select("coin", "boundary", "mark")
    held = (f.filter(C("pos") != 0)
            .select(*KEY, "pos", boundary=pl.int_ranges(C("ack_ms") // DAY + 1, C("next_ms") // DAY + 1))
            .explode("boundary", empty_as_null=False).drop_nulls("boundary")
            .filter(C("boundary").is_between(s, e))
            .join(mk, on=["coin", "boundary"], how="left")
            .select(*KEY, "boundary", "pos", "mark", value=C("pos") * C("mark")))
    # start of day t: boundary t; end of day t: boundary t + 1
    start_rows = held.select(*KEY, t=C("boundary"), e_pos="pos", e_val="value", e_mark="mark")
    end_rows = held.select(*KEY, t=C("boundary") - 1, h_pos="pos", h_val="value", h_mark="mark")
    cash = (f.with_columns(t=C("ack_ms") // DAY).filter(C("t").is_between(s, e - 1))
            .sort(*KEY, "t", "ack_ms", "batch", "oid").group_by(*KEY, "t", maintain_order=True)
            .agg(cash=C("cash").sum(), fills=pl.len()))
    fu = (fund.with_columns(t=C("day").cast(pl.Int64)).filter(C("t").is_between(s, e - 1))
          .sort(*KEY, "t", "batch", "payment", nulls_last=True).group_by(*KEY, "t", maintain_order=True)
          .agg(funding=C("payment").sum(), unknown_funding=C("payment").null_count()))
    keys = pl.concat([start_rows.select(*KEY, "t"), end_rows.select(*KEY, "t"), cash.select(*KEY, "t"),
                      fu.select(*KEY, "t")]).filter(C("t").is_between(s, e - 1)).unique().sort(*KEY, "t")
    x = (keys.join(start_rows, on=[*KEY, "t"], how="left").join(end_rows, on=[*KEY, "t"], how="left")
         .join(cash, on=[*KEY, "t"], how="left").join(fu, on=[*KEY, "t"], how="left")
         .with_columns(C("cash", "funding").fill_null(0.0), C("fills", "unknown_funding").fill_null(0)))
    held_start = C("e_pos").is_not_null()
    held_end = C("h_pos").is_not_null()
    bad = ((held_start & C("e_mark").is_null()) | (held_end & C("h_mark").is_null())
           | (C("unknown_funding") > 0))
    return x.with_columns(
        e=pl.when(held_start).then(C("e_val")).otherwise(0.0),
        H=pl.when(held_end).then(C("h_val")).otherwise(0.0),
        bad=bad,
    ).with_columns(
        pnl=pl.when(~C("bad")).then(C("cash") + C("funding") + C("H") - C("e")),
    ).select(*KEY, "t", "e", "H", "cash", "funding", "fills", "unknown_funding", "bad", "pnl").sort(*KEY, "t")


def residual_coin_days(cd: pl.DataFrame, betas: pl.DataFrame, factors: pl.DataFrame,
                       returns: pl.DataFrame, funding_in_alpha: bool = True) -> pl.DataFrame:
    """Adds the market component m = e Σ_f β_f r_f and U = PnL - m per coin-day (null when a factor return is missing
    on a day with exposure), and the coin's own return (for the static replica). ADR-0084: with
    `funding_in_alpha=False` the residual also excludes the coin-day's funding, U = PnL - m - funding."""
    b = beta_lookup(betas, cd["coin"].unique().to_list())
    x = (cd.join(b, on="coin", how="left").join(factors.select("t", *FACTORS), on="t", how="left")
         .join(returns.select("coin", "t", r_coin="r"), on=["coin", "t"], how="left"))
    beta_r = sum((C(f"beta_{f}") * C(f) for f in FACTORS), pl.lit(0.0))
    market = pl.when(C("e") == 0).then(0.0).otherwise(C("e") * beta_r)
    funding = pl.lit(0.0) if funding_in_alpha else C("funding")
    return x.with_columns(market=market).with_columns(U=C("pnl") - C("market") - funding, beta_r=beta_r).select(
        *KEY, "t", "e", "H", "cash", "funding", "bad", "pnl", "market", "U", "r_coin", "beta_r",
        *[f"beta_{f}" for f in FACTORS])


def trader_days(rc: pl.DataFrame, traders: list[str], start: date, end: date, min_exposure: float = 0.0
                ) -> pl.DataFrame:
    """Per (trader, day): PnL, U, funding F, the start- and end-of-day grosses, G = max of the two (ADR-0082),
    validity and `exposed` (valid with G >= `min_exposure` and G > 0, ADRs 0080, 0082); every trader gets every day
    of [start, end)."""
    s, e = epoch_day(start), epoch_day(end)
    agg = group_sum(rc.sort("trader", "t", "coin"), ["trader", "t"],
                    {"pnl": C("pnl"), "U": C("U"), "F": C("funding"), "G_start": C("e").abs(),
                     "G_end": C("H").abs(), "net": C("e")},
                    {"n_bad": (C("bad") | C("U").is_null()).cast(pl.Int64), "coins": (C("e") != 0).cast(pl.Int64)})
    grid = pl.DataFrame({"trader": sorted(set(traders))}, schema={"trader": pl.String}).join(
        pl.DataFrame({"t": list(range(s, e))}, schema={"t": pl.Int64}), how="cross")
    d = grid.join(agg, on=["trader", "t"], how="left").with_columns(
        C("pnl", "U", "F", "G_start", "G_end", "net").fill_null(0.0), C("n_bad", "coins").fill_null(0))
    return d.with_columns(valid=C("n_bad") == 0, day=C("t").cast(pl.Date),
                          G=pl.max_horizontal("G_start", "G_end")).with_columns(
        pnl=pl.when("valid").then("pnl"), U=pl.when("valid").then("U"), F=pl.when("valid").then("F"),
        exposed=C("valid") & (C("G") > 0) & (C("G") >= min_exposure)).sort("trader", "t")


def week_index(t: np.ndarray) -> np.ndarray:
    """Calendar week (Monday UTC) of epoch days: 1970-01-01 was a Thursday."""
    return (t + 3) // 7


def window_bounds(origin: date, first_priced: date, weeks: int) -> tuple[date, date]:
    """ADR-0070: max(first_priced_day, origin - weeks) .. the day before the origin, as [start, origin)."""
    return max(first_priced, origin - timedelta(weeks=weeks)), origin
