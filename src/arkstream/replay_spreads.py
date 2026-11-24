"""Frozen one-minute print spread calibration and matched print-count simulation (ADR-0031)."""

import numpy as np
import polars as pl

C = pl.col


def pair_estimates(h0, l0, c0, h1, l1):
    """qh_compute.spreads Corwin–Schultz and Abdi–Ranaldo expressions in numpy."""
    beta = np.log(h0 / l0) ** 2 + np.log(h1 / l1) ** 2
    gamma = np.log(np.maximum(h0, h1) / np.minimum(l0, l1)) ** 2
    k = 3 - 2 * np.sqrt(2)
    alpha = (np.sqrt(2 * beta) - np.sqrt(beta)) / k - np.sqrt(gamma / k)
    cs = np.maximum(2 * np.tanh(alpha / 2), 0)
    s2 = 4 * np.log(c0 / ((h0 + l0) / 2)) * np.log(c0 / ((h1 + l1) / 2))
    return cs, s2


def simulated_bias(pairs, sigma, half_bps, seed, trials):
    rng = np.random.default_rng(seed)
    counts = pairs[rng.integers(len(pairs), size=trials)]
    first, second = [], []
    for n0, n1 in counts:
        increments = rng.normal(size=n0 + n1) * sigma / np.sqrt(np.repeat([n0, n1], [n0, n1]))
        mid = np.exp(np.cumsum(increments))
        px = mid * (1 + rng.choice([-1, 1], len(mid)) * half_bps / 1e4)
        first.append((px[:n0].max(), px[:n0].min(), px[n0 - 1]))
        second.append((px[n0:].max(), px[n0:].min()))
    cs, _ = pair_estimates(*np.array(first).T, *np.array(second).T)
    return float(np.mean(cs) * 5000 - half_bps), float(np.std(cs, ddof=1) * 5000 / np.sqrt(trials))


def fit_spreads(fills, coins, start, asof, rules, base):
    prints = (
        fills.filter((C("ts") >= start) & (C("ts") < asof) & C("eligible") & (C("event_kind") == "trade"))
        .sort("ts", "src_row")
        .unique(["symbol", "ts", "tid", "price", "size"], maintain_order=True)
    )
    bars = (
        prints.group_by("symbol", C("ts").dt.truncate("1m"), maintain_order=True)
        .agg(h=C("price").max(), l=C("price").min(), c=C("price").last(), n=pl.len())
        .sort("symbol", "ts")
        .with_columns(C("ts", "h", "l", "c", "n").shift().over("symbol").name.suffix("0"))
        .filter((C("ts") - C("ts0") == pl.duration(minutes=1)) & (pl.min_horizontal("n", "n0") >= rules["min_prints"]))
    )
    rows = []
    for coin in sorted(coins):
        sample = bars.filter(C("symbol") == coin)
        row = dict(
            coin=coin,
            fit_start=start,
            known_at=asof,
            pairs=len(sample),
            min_prints=rules["min_prints"],
            cs_half_bps=None,
            ar_half_bps=None,
            gap_half_bps=None,
            simulated_bias_bps=None,
            simulation_se_bps=None,
            downward_bias=False,
        )
        if len(sample) >= rules["min_pairs"]:
            cs, s2 = pair_estimates(*(sample[k].to_numpy() for k in ("h0", "l0", "c0", "h", "l")))
            half = float(cs.mean() * 5000)
            ar = float(np.sqrt(max(0, s2.mean())) * 5000)
            known = base["majors" if coin in ("BTC", "ETH") else "other"]
            sigma = np.sqrt(np.mean(np.log(sample["c"].to_numpy() / sample["c0"].to_numpy()) ** 2))
            bias, se = simulated_bias(
                sample.select("n0", "n").to_numpy(), sigma, known, rules["seed"], rules["simulation_pairs"]
            )
            row.update(
                cs_half_bps=half,
                ar_half_bps=ar,
                gap_half_bps=half - ar,
                simulated_bias_bps=bias,
                simulation_se_bps=se,
                downward_bias=bias + 1.96 * se < 0,
            )
        rows.append(row)
    return pl.DataFrame(rows, infer_schema_length=None).sort("coin")
