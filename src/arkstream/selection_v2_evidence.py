"""Phase 4 v2 evidence (ADRs 0072, 0078) and ranking validation (ADRs 0075, 0078).

Order at each origin: DerSimonian-Laird τ² and Cochran's Q over every measured A/B address first; then the
normal-normal posterior with a prior mean that never assumes skill; then robustness on the address's own unshrunk
record; then the evidence categories; then the synchronized 7-day moving-block bootstrap check (5- and 10-day blocks
only when τ² > 0). `ranking_validation` applies the pre-declared IC rule on the flat-start test windows.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any

import numpy as np
import polars as pl

from arkstream.selection_v2_market import epoch_day, week_index
from arkstream.selection_v2_math import chi2_sf, norm_cdf, spearman
from arkstream.selection_v2_stats import alpha_core

C = pl.col
CATEGORY_ORDER = {"E0": 0, "E-": 1, "E1": 2, "E2": 3}


def dersimonian_laird(alpha: np.ndarray, s: np.ndarray, p_homog: float) -> dict:
    """τ², Q and the means of ADR-0072 item 2 (weights 1 / s²)."""
    alpha, s = np.asarray(alpha, dtype=float), np.asarray(s, dtype=float)
    k = len(alpha)
    out: dict[str, Any] = {"k": k, "fe_mean": None, "Q": None, "df": k - 1, "Q_p": None, "tau2": None, "re_mean": None,
           "mu0": None, "robust_zero": None}
    if k < 2:
        return out
    w = 1.0 / s ** 2
    fe = float((w * alpha).sum() / w.sum())
    q = float((w * (alpha - fe) ** 2).sum())
    c = float(w.sum() - (w ** 2).sum() / w.sum())
    tau2 = max(0.0, (q - (k - 1)) / c) if c > 0 else 0.0
    wr = 1.0 / (s ** 2 + tau2)
    re = float((wr * alpha).sum() / wr.sum())
    p = chi2_sf(q, k - 1)
    out.update(fe_mean=fe, Q=q, Q_p=p, tau2=tau2, re_mean=re, mu0=min(0.0, re),
               robust_zero=bool(tau2 == 0.0 and p >= p_homog))
    return out


def posterior(alpha: float, s: float, tau2: float, mu0: float) -> tuple[float, float, float, float]:
    """(w*, m, v, P(α > 0)); a point-mass posterior (τ² = 0) gives P = 1 if m > 0 else 0 (ADR-0078)."""
    w = tau2 / (tau2 + s ** 2) if tau2 + s ** 2 > 0 else 0.0
    m = w * alpha + (1 - w) * mu0
    v = math.sqrt(w) * s
    p = norm_cdf(m / v) if v > 0 else (1.0 if m > 0 else 0.0)
    return w, m, v, p


def robustness(t: np.ndarray, U: np.ndarray, G: np.ndarray, conf: float, crash: list[date],
               trip_pnl: np.ndarray) -> dict:
    """ADR-0072 item 4 on the own record (valid exposed days): binding α without the best week, and the reported
    variants."""
    out: dict[str, float | bool | None] = {k: None for k in (
        "alpha_ex_best_week", "s_ex_best_week", "p_own_ex_best_week", "alpha_ex_crash", "alpha_ex_best3_weeks",
        "alpha_ex_best_trip", "best_week_share", "top5_trip_share")}
    out["robust"] = False
    if len(t) == 0 or G.sum() <= 0:
        return out
    wk = week_index(t)
    weeks, inv = np.unique(wk, return_inverse=True)
    su = np.bincount(inv, weights=U, minlength=len(weeks))
    order = np.lexsort((weeks, -su))  # largest weekly residual PnL first, earliest week on ties

    def without(drop: set[int]) -> dict:
        keep = ~np.isin(inv, list(drop))
        return alpha_core(t[keep], U[keep], G[keep], conf)

    ex1 = without({int(order[0])})
    out["alpha_ex_best_week"], out["s_ex_best_week"] = ex1["alpha"], ex1["s"]
    if ex1["alpha"] is not None and ex1["s"]:
        out["p_own_ex_best_week"] = norm_cdf(ex1["alpha"] / ex1["s"])
    out["robust"] = bool(ex1["alpha"] is not None and ex1["alpha"] > 0)
    out["alpha_ex_best3_weeks"] = without({int(i) for i in order[:3]})["alpha"]
    cr = np.isin(t, [epoch_day(d) for d in crash])
    out["alpha_ex_crash"] = alpha_core(t[~cr], U[~cr], G[~cr], conf)["alpha"]
    total = float(su.sum())
    out["best_week_share"] = float(su[order[0]] / total) if total > 0 else None
    if len(trip_pnl):
        out["alpha_ex_best_trip"] = (float(U.sum()) - float(trip_pnl.max())) / float(G.sum())
        pos = np.sort(trip_pnl[trip_pnl > 0])[::-1]
        out["top5_trip_share"] = float(pos[:5].sum() / pos.sum()) if len(pos) else None
    return out


def block_counts(n_days: int, block: int, draws: int, rng: np.random.Generator) -> np.ndarray:
    """draws x n_days: how often each calendar day enters each synchronized moving-block resample."""
    nb = math.ceil(n_days / block)
    counts = np.zeros((draws, n_days))
    starts = rng.integers(0, max(n_days - block, 0) + 1, size=(draws, nb))
    for b in range(draws):
        idx = (starts[b][:, None] + np.arange(block)[None, :]).ravel()[:n_days]
        counts[b] = np.bincount(idx, minlength=n_days)
    return counts


def bootstrap(resid: pl.DataFrame, traders: list[str], days: list[int], block: int, draws: int,
              rng: np.random.Generator) -> pl.DataFrame:
    """Per address: the bootstrap SE, 20th percentile and share of draws with α* > 0 (same blocks for all)."""
    idx = {d: i for i, d in enumerate(days)}
    pos = {t: i for i, t in enumerate(traders)}
    U = np.zeros((len(traders), len(days)))
    G = np.zeros((len(traders), len(days)))
    ex = resid.filter(C("exposed") & C("trader").is_in(traders))
    for tr, t, u, g in ex.select("trader", "t", "U", "G").rows():
        U[pos[tr], idx[t]] = u
        G[pos[tr], idx[t]] = g
    cnt = block_counts(len(days), block, draws, rng)
    su, sg = U @ cnt.T, G @ cnt.T
    rows = []
    for i, tr in enumerate(traders):
        ok = sg[i] > 0
        a = su[i][ok] / sg[i][ok]
        rows.append((tr, int(ok.sum()), float(a.std(ddof=1)) if len(a) >= 2 else None,
                     float(np.quantile(a, 0.2)) if len(a) else None, float((a > 0).mean()) if len(a) else None))
    return pl.DataFrame(rows, schema={"trader": pl.String, f"boot{block}_draws": pl.Int64,
                                      f"boot{block}_se": pl.Float64, f"boot{block}_p20": pl.Float64,
                                      f"boot{block}_share_pos": pl.Float64}, orient="row")


def category(measured: bool, alpha: float | None, p_post: float | None, robust_zero: bool, robust: bool,
             conf: float = 0.8) -> str:
    if not measured or alpha is None:
        return "E0"
    if alpha <= 0:
        return "E-"
    if p_post is not None and p_post >= conf and not robust_zero and robust:
        return "E2"
    return "E1"


def evidence(ctx, origin: date, stats: pl.DataFrame, resid: pl.DataFrame, trips: pl.DataFrame,
             clusters: pl.DataFrame | None = None) -> tuple[pl.DataFrame, dict]:
    """evidence.parquet rows (every A/B address) and the τ² / Q row of the origin."""
    v2 = ctx.raw["selection_v2"]
    ev = v2["evidence"]
    conf, p_homog = float(ev["category_conf"]), float(ev["homogeneity_p"])
    crash = [date.fromisoformat(d) for d in ctx.raw["selection"]["crash_dates"]]
    m = stats.filter(C("measured") & C("s").is_not_null() & (C("s") > 0)).sort("trader")
    dl = dersimonian_laird(m["alpha"].to_numpy(), m["s"].to_numpy(), p_homog)
    tau2 = dl["tau2"] or 0.0
    robust_zero = bool(dl["robust_zero"]) if dl["robust_zero"] is not None else True
    # ADR-0072 item 3: behaviour clusters as prior groups only when τ² > 0 and each has >= the minimum size
    groups = {t: "pool" for t in m["trader"]}
    group_dl = {"pool": dl}
    used_clusters = False
    if tau2 > 0 and clusters is not None:
        cm = m.join(clusters.select("trader", "behaviour_cluster"), on="trader", how="left")
        sizes = cm.group_by("behaviour_cluster").len()
        if sizes.height and int(sizes["len"].to_numpy().min()) >= int(ev["min_cluster_prior_size"]) and \
                cm["behaviour_cluster"].null_count() == 0:
            used_clusters = True
            for (name,), cg in cm.group_by("behaviour_cluster", maintain_order=True):
                group_dl[name] = dersimonian_laird(cg["alpha"].to_numpy(), cg["s"].to_numpy(), p_homog)
            groups = dict(cm.select("trader", "behaviour_cluster").rows())
    tp = {t: g["pnl"].to_numpy() for (t,), g in trips.sort("trader", "pnl").group_by("trader", maintain_order=True)}
    rows = []
    srows = {r["trader"]: r for r in stats.iter_rows(named=True)}
    by = {t: g for (t,), g in resid.filter("exposed").sort("trader", "t").group_by("trader", maintain_order=True)}
    for tr in stats["trader"].to_list():
        r = srows[tr]
        g = by.get(tr)
        t = g["t"].to_numpy() if g is not None else np.zeros(0, dtype=np.int64)
        U = g["U"].to_numpy().astype(float) if g is not None else np.zeros(0)
        G = g["G"].to_numpy().astype(float) if g is not None else np.zeros(0)
        rob = robustness(t, U, G, conf, crash, tp.get(tr, np.zeros(0)))
        w = mm = v = p = None
        grp = groups.get(tr)
        if r["measured"] and r["s"] and grp is not None:
            gd = group_dl[grp]
            w, mm, v, p = posterior(r["alpha"], r["s"], gd["tau2"] or 0.0, gd["mu0"] if gd["mu0"] is not None else 0.0)
        cat = category(bool(r["measured"]), r["alpha"], p, robust_zero, bool(rob["robust"]), conf)
        rows.append({"trader": tr, "measured": bool(r["measured"]), "alpha": r["alpha"], "s": r["s"],
                     "alpha_funding": r["alpha_funding"], "alpha_ex_funding": r["alpha_ex_funding"],
                     "s_ex_funding": r["s_ex_funding"], "alpha_incl_funding": r["alpha_incl_funding"],
                     "s_incl_funding": r["s_incl_funding"], "carry_book": r["carry_book"],
                     "prior_group": grp, "shrink_weight": w, "m": mm, "v": v, "p_post": p, **rob, "category": cat})
    schema = {"trader": pl.String, "measured": pl.Boolean, "alpha": pl.Float64, "s": pl.Float64,
              "alpha_funding": pl.Float64, "alpha_ex_funding": pl.Float64, "s_ex_funding": pl.Float64,
              "alpha_incl_funding": pl.Float64, "s_incl_funding": pl.Float64,
              "carry_book": pl.Boolean, "prior_group": pl.String, "shrink_weight": pl.Float64, "m": pl.Float64,
              "v": pl.Float64,
              "p_post": pl.Float64, "alpha_ex_best_week": pl.Float64, "s_ex_best_week": pl.Float64,
              "p_own_ex_best_week": pl.Float64, "alpha_ex_crash": pl.Float64, "alpha_ex_best3_weeks": pl.Float64,
              "alpha_ex_best_trip": pl.Float64, "best_week_share": pl.Float64, "top5_trip_share": pl.Float64,
              "robust": pl.Boolean, "category": pl.String}
    out = pl.DataFrame(rows, schema=schema).with_columns(
        tau2=pl.lit(tau2), robust_zero=pl.lit(robust_zero), mu0=pl.lit(dl["mu0"], pl.Float64),
        prior_groups=pl.lit("behaviour_clusters" if used_clusters else "one_pool"), origin=pl.lit(origin))
    # bootstrap check: 7-day blocks always; 5 and 10 only when τ² > 0 (ADR-0072 item 1)
    start, end = stats["window_start"][0], stats["window_end"][0]
    days = list(range(epoch_day(start), epoch_day(end) + 1))
    traders = m["trader"].to_list()
    blocks = [int(ev["bootstrap_block_days"])] + ([5, 10] if tau2 > 0 else [])
    for b in blocks:
        rng = np.random.default_rng([int(ev["seed"]), origin.toordinal(), b])
        if traders:
            out = out.join(bootstrap(resid, traders, days, b, int(ev["bootstrap_draws"]), rng), on="trader",
                           how="left")
    if "boot7_se" in out.columns:
        out = out.with_columns(boot7_se_ratio=C("boot7_se") / C("s"))
    row = {"origin": origin, **{k: dl[k] for k in ("k", "fe_mean", "Q", "df", "Q_p", "tau2", "re_mean", "mu0")},
           "robust_zero": robust_zero, "prior_groups": "behaviour_clusters" if used_clusters else "one_pool",
           "bootstrap_blocks": ",".join(map(str, blocks))}
    counts = out.group_by("category").len()
    for c in CATEGORY_ORDER:
        hit = counts.filter(C("category") == c)
        row[f"n_{c}"] = int(hit["len"][0]) if hit.height else 0
    return out.sort("trader"), row


def placebo(rc: pl.DataFrame, resid: pl.DataFrame, market, start: date, end: date, traders: list[str],
            seed: int, origin: date, shifts: int = 20, days: tuple[int, int] = (1, 7)) -> pl.DataFrame:
    """ADR-0081: each copy's start-of-day exposure path shifted circularly by d days inside the window (same coins,
    sizes and costs: `O_t = U_t - H_t` and `G_t` stay on their days); α^(d) against the real α."""
    from arkstream.selection_v2_market import FACTORS, beta_lookup

    s, e = epoch_day(start), epoch_day(end)
    n_days = e - s
    ex = resid.filter(C("exposed") & C("trader").is_in(traders))
    pos = rc.join(ex.select("trader", "t"), on=["trader", "t"], how="semi").filter(C("e") != 0)
    coins = pos["coin"].unique().to_list()
    b = beta_lookup(market.betas, coins)
    rho = (market.returns.filter(C("coin").is_in(coins) & C("t").is_between(s, e - 1)).join(b, on="coin")
           .join(market.factors.select("t", *FACTORS), on="t", how="left")
           .with_columns(rho=C("r") - sum((C(f"beta_{f}") * C(f) for f in FACTORS), pl.lit(0.0)))
           .drop_nulls("rho"))
    rmap = {(c, int(t)): float(v) for c, t, v in rho.select("coin", "t", "rho").rows()}
    rows = []
    for tr in sorted(traders):
        d = ex.filter(C("trader") == tr)
        p = pos.filter(C("trader") == tr).select("coin", "t", "e").rows()
        su, sg = float(d["U"].sum()), float(d["G"].sum())
        if sg <= 0:
            continue
        h_real = sum(v * rmap.get((c, int(t)), 0.0) for c, t, v in p)
        other = su - h_real
        rng = np.random.default_rng([seed, int(tr[2:10], 16), origin.toordinal()])
        ds = rng.integers(days[0], days[1] + 1, size=shifts)
        alphas, missing = [], 0
        for dd in ds:
            h = 0.0
            for c, t, v in p:
                key = (c, s + (int(t) - s + int(dd)) % n_days)
                if key in rmap:
                    h += v * rmap[key]
                else:
                    missing += 1
            alphas.append((h + other) / sg)
        a = np.array(alphas)
        real = su / sg
        rows.append((tr, origin, real, float(np.median(a)), float(np.quantile(a, 0.2)), float(np.quantile(a, 0.8)),
                     float((a < real).mean()), bool(real > float(np.median(a))), ",".join(map(str, ds)), missing,
                     h_real / sg, other / sg))
    return pl.DataFrame(rows, schema={"trader": pl.String, "origin": pl.Date, "alpha": pl.Float64,
                                      "placebo_median": pl.Float64, "placebo_p20": pl.Float64,
                                      "placebo_p80": pl.Float64, "share_below_real": pl.Float64,
                                      "placebo_pass": pl.Boolean, "shifts_days": pl.String,
                                      "missing_coin_days": pl.Int64, "alpha_holding_part": pl.Float64,
                                      "alpha_other_part": pl.Float64}, orient="row")


def hit_rate(key: np.ndarray, outcome: np.ndarray, traders: list[str], share: float) -> float | None:
    """Share of the top `share` by key (ties by address) whose next α is above the median next α."""
    n = len(key)
    if n < 5:
        return None
    order = sorted(range(n), key=lambda i: (-key[i], traders[i]))
    top = order[: max(1, math.ceil(share * n))]
    med = float(np.median(outcome))
    return float(np.mean([outcome[i] > med for i in top]))


def ranking_validation(per_origin: dict[date, tuple[pl.DataFrame, pl.DataFrame]], rules: dict
                       ) -> tuple[pl.DataFrame, dict]:
    """ADR-0075 / ADR-0078: per development origin and key, the Spearman IC with the next window's α; the decision
    on the posterior mean m (undefined counts as 0 in the mean and as not positive)."""
    keys = ("m", "alpha", "info_ratio", "t_stat", "nav_key", "trip_key")
    rows = []
    for origin, (cur, nxt) in sorted(per_origin.items()):
        j = cur.join(nxt.select("trader", next_alpha="alpha"), on="trader", how="inner").filter(
            C("next_alpha").is_not_null())
        for k in keys:
            x = j.filter(C(k).is_not_null() & C(k).is_finite()).sort("trader")
            ic = spearman(x[k].to_numpy(), x["next_alpha"].to_numpy()) if x.height else None
            hr = hit_rate(x[k].to_numpy(), x["next_alpha"].to_numpy(), x["trader"].to_list(),
                          float(rules["hit_quantile"])) if x.height else None
            rows.append((origin, k, x.height, ic, ic is not None and ic > 0, hr))
    t = pl.DataFrame(rows, schema={"origin": pl.Date, "key": pl.String, "n": pl.Int64, "ic": pl.Float64,
                                   "positive": pl.Boolean, "top_quintile_hit_rate": pl.Float64}, orient="row")
    mk = t.filter(C("key") == "m")
    mean_ic = float(mk["ic"].fill_null(0.0).to_numpy().mean()) if mk.height else 0.0
    positive = int(mk["positive"].sum())
    used = mean_ic >= float(rules["min_mean_ic"]) and positive >= int(rules["min_positive_origins"])
    decision = {"mean_ic_m": mean_ic, "positive_origins_m": positive, "origins": mk.height,
                "undefined_origins_m": int(mk["ic"].null_count()), "ordering_used": used}
    return t, decision
