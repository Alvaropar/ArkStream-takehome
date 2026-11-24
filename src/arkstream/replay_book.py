"""Fixed-allocation daily wealth, published hourly accruals and completed follower trips."""

from datetime import timedelta

import polars as pl

from arkstream.replay_market import DAY, ms
from arkstream.replay_orders import BPS, EXCLUDED, KEY, VOL_NOTE

C = pl.col
HOUR = 3_600_000


def ledger(orders, end):
    f = orders.filter((C("status") == "filled") & (C("ack_ms") < ms(end))).sort(
        *KEY, "ack_ms", "decision_ms", "batch", "oid"
    )
    return f.with_columns(
        pos=C("quantity").cum_sum().over(KEY),
        cash=-C("quantity") * C("fill_px") - C("fee"),
        day=(C("ack_ms") // DAY).cast(pl.Date),
        turnover=C("quantity").abs() * C("fill_px"),
    ).with_columns(
        pos=pl.when(C("pos").abs() < 1e-10).then(0.0).otherwise("pos"),
        next_ms=C("ack_ms").shift(-1).over(KEY).fill_null(ms(end)),
    )


def funding_entries(f, funding, end):
    # Funding accrues on the position strictly before h. Publication, including midnight, drives cash.
    last_hour = (ms(end) - 1) // HOUR
    held = (
        f.filter(C("pos") != 0)
        .select(
            *KEY,
            "ack_ms",
            "batch",
            "oid",
            "pos",
            hour=pl.int_ranges(C("ack_ms") // HOUR + 1, pl.min_horizontal(C("next_ms") // HOUR, last_hour) + 1),
        )
        .explode("hour", empty_as_null=False)
        .drop_nulls("hour")
    )
    return (
        held.join(funding.filter(C("known_ms") < ms(end)), on=["coin", "hour"], how="left")
        .with_columns(
            payment=-C("pos") * C("proxy") * C("funding_rate"),
            posting_ms=C("known_ms").fill_null(C("hour") * HOUR),
            missing_reason=pl.when(C("funding_rate").is_null())
            .then(pl.lit("rate_unknown"))
            .when(C("proxy").is_null())
            .then(pl.lit("proxy_unpriced"))
            .otherwise(pl.lit("")),
        )
        .with_columns(day=(C("posting_ms") // DAY).cast(pl.Date))
        .sort(*KEY, "hour")
    )


def value_book(orders, universe, marks, funding, start, end, allocation):
    f = ledger(orders, end)
    fund = funding_entries(f, funding, end)
    posts = fund.group_by("trader", "day").agg(funding=C("payment").sum(), unknown_funding=C("payment").null_count())
    # Mark the position *before* each midnight. A fill at midnight belongs to the new day.
    held = (
        f.filter(C("pos") != 0)
        .select(*KEY, "pos", "batch", "oid", boundary=pl.int_ranges(C("ack_ms") // DAY + 1, C("next_ms") // DAY + 1))
        .explode("boundary", empty_as_null=False)
        .drop_nulls("boundary")
        .join(marks, on=["coin", "boundary"], how="left")
        .with_columns(day=(C("boundary") - 1).cast(pl.Date))
    )
    bal = (
        held.sort("trader", "day", "coin")
        .group_by("trader", "day", maintain_order=True)
        .agg(holding=(C("pos") * C("mark")).sum(), gross_held=(C("pos").abs() * C("mark")).sum(),
             missing_marks=C("mark").null_count())
    )
    flow = f.group_by("trader", "day", maintain_order=True).agg(
        cash=C("cash").sum(),
        turnover=C("turnover").sum(),
        fees=C("fee").sum(),
        traded=pl.len(),
        execution_cost=(C("quantity") * (C("fill_px") - C("anchor_px")) + C("fee")).sum(),
    )
    days = pl.date_range(start.date(), end.date() - timedelta(days=1), eager=True)
    daily = (
        universe.select("trader")
        .join(pl.DataFrame({"day": days}), how="cross")
        .join(flow, on=["trader", "day"], how="left")
        .join(bal, on=["trader", "day"], how="left")
        .join(posts, on=["trader", "day"], how="left")
        .with_columns(
            C(
                "cash",
                "turnover",
                "fees",
                "traded",
                "execution_cost",
                "funding",
                "holding",
                "missing_marks",
                "unknown_funding",
            ).fill_null(0)
        )
        .sort("trader", "day")
        .with_columns(
            pre_equity=pl.when(C("missing_marks") == 0).then(
                allocation + C("cash").cum_sum().over("trader") + C("holding")
            ),
            cum_funding=C("funding").cum_sum().over("trader"),
            unknown=C("unknown_funding").cum_sum().over("trader"),
        )
        .with_columns(equity=pl.when(C("unknown") == 0).then(C("pre_equity") + C("cum_funding")))
        # Gross exposure at the closing marks; unknown when any held coin lacks its mark.
        .with_columns(gross=pl.when(C("missing_marks") == 0).then(C("gross_held").fill_null(0.0)))
        .with_columns(leverage=pl.when(C("equity") > 0).then(C("gross") / C("equity")))
        .drop("gross_held")
    )
    for name, eq in (("daily_twr", "equity"), ("daily_twr_before_funding", "pre_equity")):
        opening = C(eq).shift().over("trader")
        opening = pl.when(C("day") == start.date()).then(allocation).otherwise(opening)
        daily = daily.with_columns(pl.when(opening > 0).then(C(eq) / opening - 1).alias(name))
    return daily, fund, f


UNSIZED = ("unusable_equity", "reduce_only")  # no usable leader equity (dynamic) or reference (frozen, ADR-A0116)
# ADR-0055 (amends ADR-0049): only intents the replay could not price or cost are unpriced. Every other status is
# a measured outcome: a fill or the strategy's own policy. A status in neither class stops the run.
PRICING_FAILURES = (
    "no_drift_cell",
    "stress_sample_unavailable",
    "no_eligible_aggtrade",
    "outside_mapping_window",
    "missing_sqrt_inputs",
    "missing_impact_volume",
    "missing_participation_volume",
    "missing_order_budget",
    "missing_cap_mark",
    "invalid_scenario_price",
)
MEASURED_OUTCOMES = ("filled", "below_minimum", "below_minimum_at_ack", "cap_headroom", *EXCLUDED, *UNSIZED)
SMALL = ("below_minimum", "below_minimum_at_ack")


def check_statuses(orders) -> None:
    known = {"at_target", *PRICING_FAILURES, *MEASURED_OUTCOMES}
    unknown = sorted(set(orders["status"].unique().drop_nulls()) - known)
    if unknown or orders["status"].null_count():
        raise ValueError(f"unclassified order status (ADR-0055): {unknown or 'null'}")


def summaries(daily, orders, universe, allocation, min_priced_share=None):
    """Per address. `min_priced_share` (stress, ADR-0049): below it the result is `unmeasured_low_coverage` and
    every return-like field is null, so it is never counted as positive or negative. The priced share counts only
    pricing failures as unpriced (ADR-0055); the ADR-0049 share is kept beside it as `priced_share_broad`."""
    check_statuses(orders)
    intents = orders.filter(C("status") != "at_target")
    filled = C("status") == "filled"
    notional = C("quantity").abs() * C("fill_px")
    x = intents.group_by("trader").agg(
        orders=pl.len(),
        filled=filled.sum(),
        small=C("status").is_in(SMALL).sum(),
        unpriced=C("status").is_in(PRICING_FAILURES).sum(),
        unpriced_broad=(~C("status").is_in(["filled", *SMALL, *UNSIZED])).sum(),
        cap_headroom=(C("status") == "cap_headroom").sum(),
        unsized=C("status").is_in(UNSIZED).sum(),
        reduce_only=(C("status") == "reduce_only").sum(),
        excluded=C("status").is_in(EXCLUDED).sum(),
        excluded_notional=C("intended_notional").filter(C("status").is_in(EXCLUDED)).sum(),
        parameterised_fills=(filled & (C("price_source") == "parameterised")).sum(),
        filled_notional=notional.filter(filled).sum(),
        parameterised_notional=notional.filter(filled & (C("price_source") == "parameterised")).sum(),
    )
    d = daily.group_by("trader", maintain_order=True).agg(
        days=pl.len(),
        valid_days=C("daily_twr").count(),
        pre_valid_days=C("daily_twr_before_funding").count(),
        final_equity=C("equity").last(),
        pre_final_equity=C("pre_equity").last(),
        daily_vol=C("daily_twr").std(),
        daily_mean=C("daily_twr").mean(),
        max_drawdown=(C("equity") / C("equity").cum_max().clip(lower_bound=allocation) - 1).min(),
        mean_gross=C("gross").mean(),
        max_gross=C("gross").max(),
        mean_leverage=C("leverage").mean(),
        max_leverage=C("leverage").max(),
        total_turnover=C("turnover").sum(),
        fees=C("fees").sum(),
        execution_cost=C("execution_cost").sum(),
        funding_paid=pl.when(C("unknown_funding").sum() == 0).then(C("funding").sum()),
        exhausted=(C("equity") <= 0).any(),
    )
    z = (
        universe.join(d, on="trader")
        .join(x, on="trader", how="left")
        .with_columns(
            C(
                "orders",
                "filled",
                "small",
                "unpriced",
                "unpriced_broad",
                "cap_headroom",
                "unsized",
                "reduce_only",
                "excluded",
                "excluded_notional",
                "parameterised_fills",
                "filled_notional",
                "parameterised_notional",
            ).fill_null(0)
        )
    )
    pnl = C("final_equity") - allocation
    priced = pl.when(C("orders") > 0).then(1 - C("unpriced") / C("orders")).otherwise(1.0)
    broad = pl.when(C("orders") > 0).then(1 - C("unpriced_broad") / C("orders")).otherwise(1.0)
    low = pl.lit(False) if min_priced_share is None else priced < min_priced_share
    measured = ~low
    complete = (C("valid_days") == C("days")) & ~C("exhausted") & measured
    return (
        z.with_columns(
            priced_share=priced,
            priced_share_broad=broad,
            measurement=pl.when(low).then(pl.lit("unmeasured_low_coverage")).otherwise(pl.lit("measured")),
            parameterised_notional_share=pl.when(C("filled_notional") > 0).then(
                C("parameterised_notional") / C("filled_notional")),
            copy_return=pl.when(complete).then(pnl / allocation),
            before_funding=pl.when((C("pre_valid_days") == C("days")) & measured).then(
                C("pre_final_equity") / allocation - 1),
            max_drawdown=pl.when(measured).then("max_drawdown"),
            daily_sharpe=pl.when((C("daily_vol") > 0) & measured).then(C("daily_mean") / C("daily_vol")),
            min_size_share=pl.when(C("orders") > 0).then(C("small") / C("orders")),
            unpriced_share=pl.when(C("orders") > 0).then(C("unpriced") / C("orders")),
            unpriced_share_broad=pl.when(C("orders") > 0).then(C("unpriced_broad") / C("orders")),
            excluded_share=pl.when(C("orders") > 0).then(C("excluded") / C("orders")),
            break_even_cost_bps=pl.when(complete & (C("total_turnover") > 0)).then(
                (pnl + C("execution_cost")) / C("total_turnover") * BPS
            ),
            additional_cost_to_zero_bps=pl.when(complete & (C("total_turnover") > 0)).then(
                pnl / C("total_turnover") * BPS
            ),
            volatility_note=pl.lit(VOL_NOTE),
        )
        .with_columns(
            copy_efficiency=pl.when(C("leader_return") != 0).then(C("copy_return") / C("leader_return")),
            pre_funding_efficiency=pl.when(C("leader_return") != 0).then(C("before_funding") / C("leader_return")),
        )
        .sort("trader")
    )


def completed_trips(f, fund, universe):
    """Split reversals at zero and apportion fees. Attach each accrual to its holding lot's trip."""
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
            gross=(-C("q") * C("anchor_px")).sum(),
            cost=(C("q") * (C("fill_px") - C("anchor_px")) + C("fee") * (C("q") / C("quantity")).abs()).sum(),
            peak=(pl.max_horizontal(C("after").abs(), C("before").abs()) * C("anchor_px")).max(),
        )
        .filter(C("closed") & (C("peak") > 0))
        .join(funding, on=[*KEY, "trip"], how="left")
        .with_columns(C("funding", "unknown").fill_null(0))
        .filter(C("unknown") == 0)
        .join(universe.select("trader", "hold_band"), on="trader")
    )
    return (
        trips.group_by("hold_band", maintain_order=True)
        .agg(
            completed=pl.len(),
            addresses=C("trader").n_unique(),
            gross_bps=(C("gross") / C("peak")).mean() * BPS,
            cost_bps=(C("cost") / C("peak")).mean() * BPS,
            funding_bps=(C("funding") / C("peak")).mean() * BPS,
        )
        .with_columns(net_bps=C("gross_bps") - C("cost_bps") + C("funding_bps"))
        .sort("hold_band")
    )
