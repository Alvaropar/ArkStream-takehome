"""Leader evidence, trade level: round trips flat to flat per coin, at the leader's own prices and fees.

Round trips come from `positions.rebuild` (via pipeline.positions_asof). No follower delay or cost here
(Phase 3). Method (ADR-0016):

* A fill that crosses zero is split: the part that closes the old trip and the part that opens the new one,
  fee pro rata to size. Trip PnL = cash of its parts (-delta x price - fee) plus, for a trip open at asof,
  the position valued at the price grid at asof (reference, else package print, else unpriced and excluded).
* Return = PnL / peak notional (max |position| x fill price over the trip's fills). Return per day held =
  return / max(hold, `min_hold_for_per_day_s`).
* MAE / best unrealised gain: trip-to-date PnL at each hourly mark inside the trip, over peak notional;
  labelled `excursion_resolution = 1h` (intra-hour extremes are not seen).
* Left-censored trips (entry before the first observed fill) have no measurable return and are excluded,
  counted. Production returns include published funding on each position held through an accrual hour.
"""

from __future__ import annotations

import math
from datetime import datetime

import polars as pl

KEYS = ["trader", "symbol", "trip_no"]


def trip_parts(ledger: pl.DataFrame) -> pl.DataFrame:
    """Each fill as one or two parts (a zero-crossing fill closes one trip and opens the next)."""
    led = ledger.with_columns(crossed=(pl.col("pos_before") * pl.col("pos_after")) < 0)
    share = pl.when(pl.col("delta").abs() > 0).then(pl.col("d").abs() / pl.col("delta").abs()).otherwise(1.0)
    main = led.with_columns(d=pl.when("crossed").then(-pl.col("pos_before")).otherwise("delta"),
                            part=pl.lit(0), pos=pl.when("crossed").then(0.0).otherwise("pos_after"))
    opn = led.filter("crossed").with_columns(trip_no=pl.col("trip_no") + 1, d=pl.col("pos_after"), part=pl.lit(1),
                                             pos=pl.col("pos_after"))
    p = pl.concat([main, opn]).with_columns(fee_part=pl.col("fee") * share).with_columns(
        cash=-pl.col("d") * pl.col("price") - pl.col("fee_part"))
    return p.select("trader", "symbol", "trip_no", "ts", "seq", "part", "src_row", "tid", "oid", "d", "price",
                    "fee_part", "cash", "pos").sort("trader", "symbol", "trip_no", "seq", "part")


def round_trips(trips: pl.DataFrame, ledger: pl.DataFrame, marks: pl.DataFrame, open_marks: pl.DataFrame,
                asof: datetime, rules: dict, funding: pl.DataFrame | None = None) -> pl.DataFrame:
    """One row per round trip (closed or open at asof), with return, excursions and a usable flag.

    `trips`: pipeline.positions_asof trips (core perps). `marks`: leader_returns hourly marks
    (trader, symbol, trip_no, m, pos, p_m). `open_marks`: (trader, symbol, mark_price, mark_source) at asof.
    """
    t = rules["trips"]
    parts = trip_parts(ledger)
    per = parts.with_columns(notional=(pl.col("pos").abs() * pl.col("price"))).group_by(KEYS).agg(
        cash=pl.col("cash").sum(), fees_part=pl.col("fee_part").sum(), peak_notional=pl.col("notional").max(),
        end_pos=pl.col("pos").last(),
    )
    cum = parts.with_columns(cash_cum=pl.col("cash").cum_sum().over(KEYS)).select(
        *KEYS, "ts", "seq", "part", "cash_cum").sort("ts", "seq", "part")
    mk = (marks.select(*KEYS, "m", "pos", "p_m").sort("m")
          .join_asof(cum.rename({"ts": "fill_ts"}), left_on="m", right_on="fill_ts", by=KEYS, strategy="backward",
                     check_sortedness=False)
          .with_columns(upnl=pl.col("cash_cum") + pl.col("pos") * pl.col("p_m")))
    if funding is not None:
        payments = funding.rename({"coin": "symbol"}).sort(*KEYS, "ts_hour")
        sums = payments.group_by(KEYS).agg(funding_paid=pl.col("payment").sum(),
                                          missing_funding=pl.col("payment").is_null().sum())
        per = per.join(sums, on=KEYS, how="left").with_columns(pl.col("funding_paid", "missing_funding").fill_null(0))
        path = payments.with_columns(fund_path=pl.col("payment").fill_null(0).cum_sum().over(KEYS),
                                     missing_path=pl.col("payment").is_null().cast(pl.Int64).cum_sum().over(KEYS))
        mk = (mk.sort("m").join_asof(path.select(*KEYS, "ts_hour", "fund_path", "missing_path").sort("ts_hour"),
                                     left_on="m", right_on="ts_hour", by=KEYS, check_sortedness=False)
              .with_columns(upnl=pl.when(pl.col("missing_path").fill_null(0) == 0)
                            .then(pl.col("upnl") + pl.col("fund_path").fill_null(0))))
    else:
        per = per.with_columns(funding_paid=pl.lit(0.), missing_funding=pl.lit(0))
    fee_scope = ledger.with_columns(bad=(pl.col("fee_token") != "USDC") & (pl.col("fee") != 0))
    fee_scope = (parts.join(fee_scope.select("src_row", "bad"), on="src_row")
                 .group_by(KEYS).agg(bad_fee=pl.col("bad").any()))
    per = per.join(fee_scope, on=KEYS)
    exc = mk.group_by(KEYS).agg(
        n_marks=pl.len(), n_marks_unpriced=pl.col("upnl").is_null().sum(),
        worst_upnl=pl.col("upnl").min(), best_upnl=pl.col("upnl").max(),
    )
    tr = (trips.join(per, on=KEYS, how="left").join(exc, on=KEYS, how="left")
          .join(open_marks.select("trader", "symbol", "mark_price", "mark_source"), on=["trader", "symbol"],
                how="left"))
    is_open = pl.col("close_ts").is_null()
    tr = tr.with_columns(
        status=pl.when(is_open).then(pl.lit("open_at_asof")).otherwise(pl.lit("closed")),
        mark_price=pl.when(is_open).then("mark_price"), mark_source=pl.when(is_open).then("mark_source"),
        hold_s=pl.when(is_open).then((pl.lit(asof) - pl.col("open_ts")).dt.total_milliseconds() / 1000)
        .otherwise((pl.col("close_ts") - pl.col("open_ts")).dt.total_milliseconds() / 1000),
        n_marks=pl.col("n_marks").fill_null(0), n_marks_unpriced=pl.col("n_marks_unpriced").fill_null(0),
    ).with_columns(
        net_pnl=pl.when(~is_open).then("cash").otherwise(pl.col("cash") + pl.col("end_pos") * pl.col("mark_price"))
        + pl.col("funding_paid"),
    )
    tr = tr.with_columns(pnl_with_known_funding=pl.when(~pl.col("left_censored") & ~pl.col("bad_fee")).then("net_pnl"))
    reason = (pl.when(pl.col("left_censored")).then(pl.lit("left_censored_entry_unknown"))
              .when(is_open & pl.col("mark_price").is_null()).then(pl.lit("open_unpriced_at_asof"))
              .when(pl.col("missing_funding") > 0).then(pl.lit("funding_unknown"))
              .when(pl.col("bad_fee")).then(pl.lit("non_usdc_fee"))
              .when(~(pl.col("peak_notional") > 0)).then(pl.lit("no_notional"))
              .otherwise(pl.lit("")))
    complete_excursion = (~pl.col("left_censored") & ~pl.col("bad_fee") & (pl.col("peak_notional") > 0)
                          & (pl.col("n_marks") > 0) & (pl.col("n_marks_unpriced") == 0))
    floor_s = float(t["min_hold_for_per_day_s"])
    tr = tr.with_columns(exclude_reason=reason).with_columns(usable=pl.col("exclude_reason") == "").with_columns(
        ret_with_known_funding=pl.when(pl.col("peak_notional") > 0)
        .then(pl.col("pnl_with_known_funding") / pl.col("peak_notional")),
        ret=pl.when("usable").then(pl.col("net_pnl") / pl.col("peak_notional")),
    ).with_columns(
        ret_per_day=pl.col("ret") / (pl.max_horizontal(pl.col("hold_s"), pl.lit(floor_s)) / 86400),
        mae=pl.when(complete_excursion).then(pl.min_horizontal(pl.col("worst_upnl").fill_null(0.0), pl.lit(0.0))
                                   / pl.col("peak_notional")),
        best_gain=pl.when(complete_excursion).then(pl.max_horizontal(pl.col("best_upnl").fill_null(0.0), pl.lit(0.0))
                                         / pl.col("peak_notional")),
        excursion_resolution=pl.lit("1h"), funding=pl.lit("included" if funding is not None else "omitted"),
        net_pnl=pl.when(pl.col("usable")).then("net_pnl"),
        asof=pl.lit(asof).dt.cast_time_unit("ms"),
    )
    return tr.select(
        "trader", "symbol", "trip_no", "side", "status", "open_ts", "close_ts", "hold_s", "left_censored",
        "entry_src_row", "entry_tid", "entry_oid", "exit_src_row", "exit_tid", "exit_oid", "n_fills",
        "peak_notional", "net_pnl", "pnl_with_known_funding", "closed_pnl", "fees", "rebuilt_realized",
        "mark_price", "mark_source", "ret_with_known_funding",
        "ret", "ret_per_day", "mae", "best_gain", "n_marks", "n_marks_unpriced", "excursion_resolution",
        "usable", "exclude_reason", "funding", "funding_paid", "missing_funding", "asof",
    ).sort(KEYS)


def _top_k(n: int, share: float) -> int:
    return max(1, math.ceil(n * share)) if n else 0


def trip_summary(rt: pl.DataFrame, rules: dict) -> pl.DataFrame:
    """Per address: counts, win rate, win/loss size, mean with the top 1% removed, PnL dependence on the top 1%."""
    share = float(rules["trips"]["top_share"])
    counts = rt.group_by("trader").agg(
        rt_closed=((pl.col("status") == "closed") & pl.col("usable")).sum(),
        rt_open_valued=((pl.col("status") == "open_at_asof") & pl.col("usable")).sum(),
        rt_open_pending_funding=((pl.col("status") == "open_at_asof")
                                 & (pl.col("exclude_reason") == "funding_unknown")).sum(),
        rt_open_unpriced=(pl.col("exclude_reason") == "open_unpriced_at_asof").sum(),
        rt_censored=pl.col("left_censored").sum(),
    )
    u = rt.filter("usable").sort("trader", "ret", "symbol", "trip_no", descending=[False, True, False, False])
    u = u.with_columns(rank=pl.int_range(pl.len()).over("trader"), n=pl.len().over("trader"))
    u = u.with_columns(top=pl.col("rank") < (pl.col("n") * share).ceil().clip(lower_bound=1))  # = _top_k
    s = u.group_by("trader").agg(
        rt_n=pl.len(), win_rate=(pl.col("ret") > 0).mean(),
        avg_win=pl.col("ret").filter(pl.col("ret") > 0).mean(),
        avg_loss=pl.col("ret").filter(pl.col("ret") <= 0).mean(),
        mean_ret=pl.col("ret").mean(), median_ret=pl.col("ret").median(),
        mean_ret_ex_top=pl.col("ret").filter(~pl.col("top")).mean(),
        mean_ret_per_day=pl.col("ret_per_day").mean(),
        pnl_total=pl.col("net_pnl").sum(), pnl_ex_top=pl.col("net_pnl").filter(~pl.col("top")).sum(),
        median_mae=pl.col("mae").median(), worst_mae=pl.col("mae").min(), median_best_gain=pl.col("best_gain").median(),
    ).with_columns(
        win_loss_ratio=pl.when(pl.col("avg_loss") < 0).then(pl.col("avg_win") / -pl.col("avg_loss")),
        top_pnl_share=pl.when(pl.col("pnl_total") > 0).then(1 - pl.col("pnl_ex_top") / pl.col("pnl_total")),
    )
    # ADR-0067 gate 17: concentration of *positive* trip profit (stable denominator), top-week share and the net PnL
    # without the best entry week (leave-one-event-out).
    by_pnl = rt.filter("usable").sort("trader", "net_pnl", "symbol", "trip_no", descending=[False, True, False, False])
    by_pnl = by_pnl.with_columns(rank=pl.int_range(pl.len()).over("trader"), n=pl.len().over("trader"))
    conc = by_pnl.group_by("trader").agg(
        gross_profit=pl.col("net_pnl").clip(lower_bound=0).sum(),
        top_profit=pl.col("net_pnl").clip(lower_bound=0).filter(
            pl.col("rank") < (pl.col("n") * share).ceil().clip(lower_bound=1)).sum(),
    ).with_columns(top_profit_share=pl.when(pl.col("gross_profit") > 0)
                   .then(pl.col("top_profit") / pl.col("gross_profit")))
    out = counts.join(s, on="trader", how="left").join(conc.select("trader", "gross_profit", "top_profit_share"),
                                                       on="trader", how="left")
    if "open_ts" not in rt.columns:  # synthetic frames without entry times: no week statistics
        return out.with_columns(top_week_share=pl.lit(None, pl.Float64), pnl_ex_best_week=pl.lit(None, pl.Float64),
                                trip_weeks=pl.lit(None, pl.UInt32),
                                ret_ci95_halfwidth=pl.lit(None, pl.Float64)).sort("trader")
    weeks = (rt.filter("usable").with_columns(week=pl.col("open_ts").dt.truncate("1w"))
             .group_by("trader", "week").agg(week_pnl=pl.col("net_pnl").sum())
             .group_by("trader").agg(
                 top_week_share=pl.when(pl.col("week_pnl").clip(lower_bound=0).sum() > 0)
                 .then(pl.col("week_pnl").max().clip(lower_bound=0) / pl.col("week_pnl").clip(lower_bound=0).sum()),
                 pnl_ex_best_week=pl.col("week_pnl").sum() - pl.col("week_pnl").max()))
    # ADR-0067 gate 1 (reported): independent entry weeks of completed trips and a week-clustered 95% half-width of
    # the mean trip return
    closed = rt.filter((pl.col("status") == "closed") & pl.col("usable")).with_columns(
        week=pl.col("open_ts").dt.truncate("1w"))
    closed = closed.with_columns(dev=pl.col("ret") - pl.col("ret").mean().over("trader"))
    cl = (closed.group_by("trader", "week").agg(s=pl.col("dev").sum(), m=pl.len())
          .group_by("trader").agg(trip_weeks=pl.len(), n=pl.col("m").sum(), ss=(pl.col("s") ** 2).sum())
          .with_columns(ret_ci95_halfwidth=pl.when(pl.col("trip_weeks") >= 2)
                        .then(1.96 * pl.col("ss").sqrt() / pl.col("n")))
          .select("trader", "trip_weeks", "ret_ci95_halfwidth"))
    return out.join(weeks, on="trader", how="left").join(cl, on="trader", how="left").sort("trader")
