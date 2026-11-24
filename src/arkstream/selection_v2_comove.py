"""Phase 4 v2 duplicates and co-movement (ADRs 0074, 0079).

Phase 4 removes only near-duplicates: same-coin overlap ≥ 0.7, the 95% Fisher lower bound of the daily copy-return
correlation on days both copies hold exposure without 10-11 Oct ≥ 0.5, on at least 20 such days. Everything else is
measured and handed to Phase 5, including an exposure-based risk correlation on a coin covariance fitted once at the
origin (Ledoit-Wolf constant-correlation shrinkage, 90 days before the origin). An unmeasured pair gets no credit.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any

import numpy as np
import polars as pl

from arkstream.selection_v2_market import epoch_day
from arkstream.selection_v2_math import fisher_bounds, pearson

C = pl.col


def ledoit_wolf_cc(x: np.ndarray) -> tuple[np.ndarray, float]:
    """Ledoit and Wolf (2004) shrinkage of the sample covariance toward the constant-correlation target. `x` is
    T x N (complete cases). Returns (Σ*, δ)."""
    t, n = x.shape
    y = x - x.mean(axis=0)
    s = y.T @ y / t
    var = np.diag(s).copy()
    sd = np.sqrt(var)
    if n == 1:
        return s, 0.0
    corr = s / np.outer(sd, sd)
    rbar = (corr.sum() - n) / (n * (n - 1))
    f = rbar * np.outer(sd, sd)
    np.fill_diagonal(f, var)
    y2 = y ** 2
    pi_mat = (y2.T @ y2) / t - s ** 2
    pi_hat = pi_mat.sum()
    theta = ((y ** 3).T @ y) / t - var[:, None] * s
    np.fill_diagonal(theta, 0.0)
    # Σ_{i≠j} (rbar / 2) (√(s_jj/s_ii) ϑ_ii,ij + √(s_ii/s_jj) ϑ_jj,ij)
    ratio = np.outer(1 / sd, sd)  # √(s_jj / s_ii) at (i, j)
    off = (ratio * theta + ratio.T * theta.T)
    np.fill_diagonal(off, 0.0)
    rho_hat = np.diag(pi_mat).sum() + rbar / 2 * off.sum()
    gamma_hat = ((f - s) ** 2).sum()
    kappa = (pi_hat - rho_hat) / gamma_hat if gamma_hat > 0 else 0.0
    delta = float(max(0.0, min(1.0, kappa / t)))
    return delta * f + (1 - delta) * s, delta


def risk_cov(returns: pl.DataFrame, coins: list[str], origin: date, lookback: int, min_days: int,
             min_complete: int) -> tuple[list[str], np.ndarray | None, dict]:
    """Σ on the origin's pooled tradable coins with returns on ≥ `min_days` of the `lookback` days before it, over
    the days every such coin has a return (ADR-0079 item 6)."""
    o = epoch_day(origin)
    r = returns.filter(C("t").is_between(o - lookback, o - 1) & C("coin").is_in(coins))
    n = r.group_by("coin").len()
    keep = sorted(n.filter(C("len") >= min_days)["coin"].to_list())
    info: dict[str, Any] = {"coins_requested": len(coins), "coins_used": len(keep), "complete_days": 0, "delta": None,
            "fit_date": origin, "last_day": None}
    if not keep:
        return keep, None, info
    wide = (r.filter(C("coin").is_in(keep)).pivot(on="coin", index="t", values="r").sort("t")
            .select("t", *keep).drop_nulls())
    info["complete_days"] = wide.height
    if wide.height < min_complete:
        return keep, None, info
    sigma, delta = ledoit_wolf_cc(wide.select(keep).to_numpy())
    info.update(delta=delta, last_day=int(wide["t"].to_numpy().max()))
    return keep, sigma, info


def exposure_vectors(profile: pl.DataFrame, coins: list[str]) -> dict[str, tuple[np.ndarray, bool]]:
    """Mean signed exposure by coin on Σ's coins; the flag is False when the copy held a coin outside Σ."""
    idx = {c: i for i, c in enumerate(coins)}
    out = {}
    for tr, items in profile.select("trader", "exposure_by_coin").rows():
        v = np.zeros(len(coins))
        inside = True
        for it in items or []:
            c, e = it["coin"], it["mean_exposure_usdc"]
            if c in idx:
                v[idx[c]] = e
            elif e:
                inside = False
        out[tr] = (v, inside)
    return out


def masked_corr(ra: np.ndarray, rb: np.ndarray, mask: np.ndarray, min_n: int
                ) -> tuple[int, float | None, float | None, float | None]:
    """(days, Pearson, Fisher 95% low, high) on the masked days; null under `min_n` days."""
    n = int(mask.sum())
    r = pearson(ra[mask], rb[mask]) if n >= min_n else None
    lo, hi = fisher_bounds(r, n) if r is not None else (None, None)
    return n, r, lo, hi


def pair_table(cands: list[str], resid: pl.DataFrame, daily: pl.DataFrame, rc: pl.DataFrame,
               factors: pl.DataFrame, start: date, end: date, crash: list[date], sigma_coins: list[str],
               sigma: np.ndarray | None, profile: pl.DataFrame, rules: dict) -> pl.DataFrame:
    """Every pair of `cands`: correlations (full calendar, both exposed, both exposed without the crash) with
    Fisher 95% intervals, downside correlation, joint large-loss frequency, overlap and direction share, and the
    exposure-based risk correlation."""
    s, e = epoch_day(start), epoch_day(end)
    cr = {epoch_day(d) for d in crash}
    d = (daily.with_columns(t=C("day").cast(pl.Int64)).filter(C("t").is_between(s, e - 1))
         .select("trader", "t", "daily_twr").drop_nulls("daily_twr"))
    g = resid.select("trader", "t", "exposed")
    series = {}
    for (tr,), x in d.join(g, on=["trader", "t"], how="left").sort("trader", "t").group_by("trader",
                                                                                               maintain_order=True):
        series[tr] = {int(t): (float(r), bool(v)) for t, r, v in x.select("t", "daily_twr", "exposed").rows()}
    alt = factors.filter(C("t").is_between(s, e - 1)).drop_nulls("ALT")
    low = set(alt.filter(C("ALT") <= alt["ALT"].quantile(float(rules["downside_share"]), "linear"))["t"].to_list()) \
        if alt.height else set()
    p10 = {tr: float(np.quantile([v[0] for v in sv.values()], float(rules["large_loss_quantile"])))
           for tr, sv in series.items() if sv}
    pos = rc.join(resid.filter("valid").select("trader", "t"), on=["trader", "t"], how="semi").filter(C("e") != 0)
    vec = {tr: {(int(t), c): float(v) for c, t, v in x.select("coin", "t", "e").rows()}
           for (tr,), x in pos.sort("trader", "t", "coin").group_by("trader", maintain_order=True)}
    ev = exposure_vectors(profile, sigma_coins) if sigma is not None else {}
    min_both = int(rules["min_common_exposed_days"])
    rows = []
    for i, a in enumerate(cands):
        for b in cands[i + 1:]:
            sa, sb = series.get(a, {}), series.get(b, {})
            common = sorted(set(sa) & set(sb))
            ra = np.array([sa[t][0] for t in common])
            rb = np.array([sb[t][0] for t in common])
            both = np.array([sa[t][1] and sb[t][1] for t in common], dtype=bool)
            nocr = np.array([t not in cr for t in common], dtype=bool)
            dn = np.array([t in low for t in common], dtype=bool)

            full = masked_corr(ra, rb, np.ones(len(common), dtype=bool), 4)
            be = masked_corr(ra, rb, both, 4)
            bex = masked_corr(ra, rb, both & nocr, min_both)
            down = masked_corr(ra, rb, dn, int(rules["min_downside_days"]))
            joint = None
            if common and a in p10 and b in p10:
                joint = float(np.mean((ra < p10[a]) & (rb < p10[b])))
            va, vb = vec.get(a, {}), vec.get(b, {})
            na = math.sqrt(sum(v * v for v in va.values()))
            nb = math.sqrt(sum(v * v for v in vb.values()))
            shared = set(va) & set(vb)
            dot = sum(va[k] * vb[k] for k in shared)
            mag = sum(abs(va[k] * vb[k]) for k in shared)
            overlap = dot / (na * nb) if na > 0 and nb > 0 else None
            same_dir = sum(abs(va[k] * vb[k]) for k in shared if va[k] * vb[k] > 0) / mag if mag > 0 else None
            risk = None
            if sigma is not None and a in ev and b in ev and ev[a][1] and ev[b][1]:
                xa, xb = ev[a][0], ev[b][0]
                den = math.sqrt(float(xa @ sigma @ xa) * float(xb @ sigma @ xb))
                risk = float(xa @ sigma @ xb) / den if den > 0 else None
            dup = (overlap is not None and overlap >= float(rules["min_overlap"]) and bex[2] is not None
                   and bex[2] >= float(rules["min_corr_lower95"]) and bex[0] >= min_both)
            measured = bex[1] is not None
            rows.append((a, b, *full, *be, *bex, *down[:2], joint, overlap, same_dir, len(shared), risk, measured,
                         dup, bex[1] if measured else 1.0, risk if risk is not None else 1.0))
    names = ["trader_a", "trader_b",
             "full_days", "corr_full", "corr_full_lo95", "corr_full_hi95",
             "both_days", "corr_both", "corr_both_lo95", "corr_both_hi95",
             "both_ex_crash_days", "corr_both_ex_crash", "corr_both_ex_crash_lo95", "corr_both_ex_crash_hi95",
             "downside_days", "corr_downside", "joint_large_loss_freq", "overlap", "overlap_same_direction_share",
             "shared_coin_days", "risk_corr", "measured", "near_duplicate", "corr_for_phase5", "risk_corr_for_phase5"]
    types = [pl.String, pl.String, pl.Int64, pl.Float64, pl.Float64, pl.Float64, pl.Int64, pl.Float64, pl.Float64,
             pl.Float64, pl.Int64, pl.Float64, pl.Float64, pl.Float64, pl.Int64, pl.Float64, pl.Float64, pl.Float64,
             pl.Float64, pl.Int64, pl.Float64, pl.Boolean, pl.Boolean, pl.Float64, pl.Float64]
    return pl.DataFrame(rows, schema=dict(zip(names, types, strict=True)), orient="row")


def duplicate_screen(cands: pl.DataFrame, pairs: pl.DataFrame) -> pl.DataFrame:
    """Greedy from the strongest member (category E2 before E1, then posterior mean m, then address): an address is
    removed when it is a near-duplicate of an address already kept; the pair is named."""
    order = {"E2": 0, "E1": 1}
    ranked = sorted(cands.select("trader", "category", "m").rows(),
                    key=lambda r: (order.get(r[1], 9), -(r[2] if r[2] is not None else -1e18), r[0]))
    dup = {(a, b) for a, b in pairs.filter("near_duplicate").select("trader_a", "trader_b").rows()}
    dup |= {(b, a) for a, b in dup}
    kept: list[str] = []
    rows: list[tuple[Any, ...]] = []
    for tr, cat, _ in ranked:
        hit = next((k for k in kept if (tr, k) in dup), None)
        if hit is None:
            kept.append(tr)
            rows.append((tr, cat, "kept", None))
        else:
            rows.append((tr, cat, "near_duplicate", hit))
    return pl.DataFrame(rows, schema={"trader": pl.String, "category": pl.String, "duplicate_decision": pl.String,
                                      "duplicate_of": pl.String}, orient="row")
