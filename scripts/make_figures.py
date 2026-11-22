"""Key review figures for the ArkStream copy pilot, read from the saved research outputs (no recomputation).

    uv run --group figures python scripts/make_figures.py

Writes PNGs to decision/figures/. Palette: the validated reference categorical order (blue, orange, aqua) on a
light surface; one axis per chart; grid and axes recessive; series identified by legend and direct labels.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import polars as pl  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "decision" / "figures"
LEADER = ROOT / "research" / "leader"
REPLAY = ROOT / "research" / "replay"
SIZING = ROOT / "research" / "replay_sizing"  # archived dynamic vs frozen comparison (ADRs 0116, 0119)
FROZEN = ROOT / "research" / "replay_frozen"  # the current replay: frozen E_ref only (ADRs 0119, 0122)
ORIGINS = ["2025-10-08", "2025-10-22", "2025-11-05", "2025-11-19", "2025-12-03"]
TESTS = ORIGINS[:-1]

SURFACE, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8984", "#e6e5e0"
S1, S2, S3 = "#2a78d6", "#eb6834", "#1baf7a"
SUITABILITY = ["gate_hold", "gate_order_rate", "gate_maker", "gate_active", "gate_evidence", "gate_rebuild_fit"]
VARIANTS = [
    ("original", "Original\n(linear impact)"),
    ("sqrt", "√ impact"),
    ("cap", "1.5× cap"),
    ("sqrt_cap", "Combined\n(√ + cap)"),
    ("part", "+ participation\ncap"),
    ("part_ns", "+ no\nscale-up"),
    ("part_ns_sweep", "+ leader sweep\n(full)"),
]


def style(ax, title, subtitle=None):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    pad = (34 if "\n" in subtitle else 22) if subtitle else 10
    ax.set_title(title, loc="left", fontsize=12, color=INK, pad=pad, fontweight="bold")
    if subtitle:
        ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=9, color=INK2, va="bottom")


def figure(w=9.0, h=4.8):
    fig, ax = plt.subplots(figsize=(w, h), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    return fig, ax


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / name, facecolor=SURFACE)
    plt.close(fig)


def gate_funnel():
    rows = []
    for o in ORIGINS:
        e = pl.read_parquet(LEADER / f"origin={o}" / "evidence.parquet")
        suit = pl.all_horizontal([pl.col(g) == "pass" for g in SUITABILITY])
        rows.append((o, e.height, e.filter(suit).height, int(e["all_gates_pass"].sum())))
    fig, ax = figure()
    x = range(len(rows))
    w = 0.26
    series = [("Graded A or B", 1, S1), ("Pass the suitability gates", 2, S2), ("Pass every gate", 3, S3)]
    for k, (label, col, color) in enumerate(series):
        vals = [r[col] for r in rows]
        bars = ax.bar([i + (k - 1) * w for i in x], vals, w - 0.02, color=color, label=label)
        for b, v in zip(bars, vals, strict=True):
            ax.text(b.get_x() + b.get_width() / 2, v + 4, str(v), ha="center", fontsize=8, color=INK2)
    ax.set_xticks(list(x), [f"{r[0]}" + ("\n(holdout start)" if r[0] == ORIGINS[-1] else "") for r in rows])
    ax.set_ylabel("Addresses", color=INK2)
    ax.legend(frameon=False, fontsize=9, loc="upper left", ncol=3)
    style(ax, "Phase 2: how many addresses survive the gates at each test date",
          "Suitability = holding time, order rate, maker share, active, 20+ round trips, rebuild fit. "
          "All thresholds are placeholders.")
    ax.set_ylim(0, max(r[1] for r in rows) * 1.18)
    save(fig, "p2_gate_funnel.png")


def rebuild_example():
    o = ORIGINS[-1]
    g = pl.read_parquet(LEADER / f"origin={o}" / "evidence.parquet")
    b = pl.read_parquet(LEADER / f"origin={o}" / "book_vs_account.parquet")
    b = b.filter(pl.col("fit_eligible") & pl.col("book_pnl").is_not_null() & pl.col("account_pnl").is_not_null())
    passers = g.filter("all_gates_pass")["trader"]
    counts = b.filter(pl.col("trader").is_in(passers.implode())).group_by("trader").len().sort("len", descending=True)
    tr = counts["trader"][0]
    x = b.filter(pl.col("trader") == tr).sort("ts").with_columns(
        acct=pl.col("account_pnl").cum_sum(), book=pl.col("book_pnl").cum_sum())
    fig, ax = figure()
    ax.plot(x["ts"], x["acct"], color=S1, linewidth=2, label="Snapshots: equity change minus net deposits")
    ax.plot(x["ts"], x["book"], color=S2, linewidth=2, linestyle=(0, (4, 2)),
            label="Rebuilt from fills, marked at each snapshot time, with funding")
    ax.set_ylabel("Cumulative PnL (USDC)", color=INK2)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    miss = (x["account_pnl"] - x["book_pnl"]).abs().median()
    style(ax, f"Phase 2: rebuilt book vs snapshots, one gate-passing address ({tr[:10]}…)",
          f"{x.height} checked intervals up to 3 Dec 2025; median miss per interval {miss:,.2f} USDC.")
    save(fig, "p2_rebuild_vs_snapshots.png")


def worstcase_scatter():
    e = pl.read_parquet(LEADER / f"origin={ORIGINS[-1]}" / "evidence.parquet").filter(
        pl.col("wc_max_dd").is_not_null() & pl.col("intraday_max_dd").is_not_null())
    fig, ax = figure(7.5, 6.0)
    for label, mask, color, size in (("Other A/B addresses", ~pl.col("all_gates_pass"), S1, 14),
                                     ("Pass every gate", pl.col("all_gates_pass"), S2, 36)):
        d = e.filter(mask)
        ax.scatter(d["intraday_max_dd"] * 100, d["wc_max_dd"] * 100, s=size, color=color, alpha=0.75,
                   edgecolors=SURFACE, linewidths=0.8, label=f"{label} ({d.height})")
    ax.plot([-100, 0], [-100, 0], color=MUTED, linewidth=1, linestyle=":")
    ax.text(-97, -91, "same as hourly", color=MUTED, fontsize=8, rotation=38)
    ax.axhline(-50, color=INK2, linewidth=1, linestyle="--")
    ax.text(-99, -48, "gate: worst case must stay above −50%", color=INK2, fontsize=8)
    ax.set_xlim(-100, 2)
    ax.set_ylim(-100, 2)
    ax.set_xlabel("Max drawdown at hourly closes (%)", color=INK2)
    ax.set_ylabel("Worst-case drawdown inside 4h bars (%)", color=INK2)
    ax.legend(frameon=False, fontsize=9, loc="lower right")
    style(ax, "Phase 2: wicks inside the bar make drawdowns deeper",
          "3 Dec 2025. Each position valued at its bar's low (longs) or high (shorts), Hyperliquid 4h OHLC.")
    save(fig, "p2_worstcase_vs_hourly.png")


def cost_per_side():
    c = pl.read_csv(REPLAY / "sensitivity_costs.csv").filter(
        (pl.col("scenario") == "base") & (pl.col("coins") == "all") & (pl.col("universe") == "all_ab"))
    rows = []
    for v, label in VARIANTS:
        d = c.filter(pl.col("variant") == v)
        n = d["notional"].sum()
        parts = [float((d[k] * d["notional"]).sum() / n) for k in ("fee_bps", "spread_bps", "impact_bps")]
        rows.append((label, *parts))
    fig, ax = figure(9.5, 5.0)
    y = list(range(len(rows)))[::-1]
    left = [0.0] * len(rows)
    for k, (label, color) in enumerate((("Taker fee", S1), ("Half-spread", S2), ("Market impact", S3))):
        vals = [r[k + 1] for r in rows]
        ax.barh(y, vals, 0.62, left=left, color=color, label=label, edgecolor=SURFACE, linewidth=2)
        left = [a + b for a, b in zip(left, vals, strict=True)]
    for yy, tot in zip(y, left, strict=True):
        ax.text(tot + 0.4, yy, f"{tot:.1f}", va="center", fontsize=9, color=INK2)
    ax.set_yticks(y, [r[0].replace("\n", " ") for r in rows])
    ax.set_xlabel("Cost per filled side, bps (notional-weighted)", color=INK2)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.grid(axis="y", visible=False)
    ax.legend(frameon=False, fontsize=9, loc="lower right")
    style(ax, "Phase 3: where the copy cost goes, by variant",
          "Base scenario, all A/B addresses, four development test windows. Drift (≈0 bps) not shown.")
    save(fig, "p3_cost_per_side.png")


def returns_by_variant():
    r = pl.read_csv(REPLAY / "sensitivity_returns.csv").filter(pl.col("scenario") == "base")
    wc = pl.read_csv(REPLAY / "sensitivity_returns_worstcase_gate.csv").filter(
        (pl.col("scenario") == "base") & (pl.col("gates") == "after"))
    wc = wc.select("origin", mean_return=pl.col("mean").cast(pl.Float64), measured="n")
    items = [(lab, r.filter(pl.col("variant") == v).sort("origin")) for v, lab in VARIANTS]
    items.append(("Full +\nworst-case\ngate", wc.sort("origin")))
    fig, ax = figure(11, 5.6)
    for i, (_, d) in enumerate(items):
        pooled = float((d["mean_return"] * d["measured"]).sum() / d["measured"].sum() * 100)
        ax.bar(i, pooled, 0.6, color=S1 if pooled >= 0 else S2)
        ax.text(i, pooled + (0.12 if pooled >= 0 else -0.25), f"{pooled:+.2f}%", ha="center", fontsize=9, color=INK)
        ax.scatter([i] * d.height, d["mean_return"] * 100, color=INK2, s=14, zorder=3,
                   label="One test window" if i == 0 else None)
    ax.axhline(0, color=MUTED, linewidth=1)
    ax.set_xticks(range(len(items)), [lab for lab, _ in items], fontsize=8)
    ax.set_ylabel("Mean funded copy return (%)", color=INK2)
    ax.legend(frameon=False, fontsize=9, loc="lower right")
    style(ax, "Phase 3: mean copy return across gate-passers, by cost and sizing variant",
          "Base scenario, $10,000 per address per two-week test window. Bars pool the address-windows (68; 56 with "
          "the worst-case gate);\ndots are the four tests. From '+ participation cap' on, each variant adds to the "
          "one before.")
    save(fig, "p3_return_by_variant.png")


def holding_bands():
    b = pl.read_csv(REPLAY / "sensitivity_bands.csv").filter(
        (pl.col("scenario") == "base") & (pl.col("variant") == "part_ns_sweep"))
    order = ["<1m", "1-15m", "15m-1h", "1-6h", "6-24h", "1-7d", ">7d"]
    fig, ax = figure(9.5, 5.0)
    for i, band in enumerate(order):
        d = b.filter(pl.col("hold_band") == band)
        mean = float((d["net_bps"] * d["completed"]).sum() / d["completed"].sum())
        all_pos = bool((d["net_bps"] > 0).all())
        ax.bar(i, mean, 0.6, color=S3 if all_pos else (S1 if mean >= 0 else S2))
        ax.scatter([i] * d.height, d["net_bps"], color=INK2, s=14, zorder=3,
                   label="One test window" if i == 0 else None)
        ax.text(i + 0.33, mean, f"{mean:+.0f}", ha="left", va="center", fontsize=9, color=INK)
    ax.axhline(0, color=MUTED, linewidth=1)
    ax.set_xticks(range(len(order)), [f"{o}" for o in order])
    ax.set_xlabel("Leader's median holding time", color=INK2)
    ax.set_ylabel("Net result per completed round trip (bps)", color=INK2)
    ax.legend(frameon=False, fontsize=9, loc="lower left")
    style(ax, "Phase 3: only the 1-24 hour holding bands clear costs in every test",
          "Full variant, base scenario, after fees, spread, impact, drift and funding. Green = positive in all four "
          "tests; bars are trip-weighted means.")
    save(fig, "p3_holding_bands.png")


def frozen_vs_dynamic():
    """Archived record (ADR-0116/0119): the chosen policy against the dynamic denominator, base, gate-passers."""
    p = pl.read_csv(SIZING / "sizing_comparison_pooled.csv", try_parse_dates=True).filter(
        (pl.col("universe") == "gate_passers") & (pl.col("scenario") == "base")
        & pl.col("window").is_in(["test", "all_tests"]))
    labels = [*TESTS, "All four tests"]
    fig, ax = figure(9.5, 5.0)
    w = 0.36
    seen = []
    for k, (variant, name, color) in enumerate((("frozen", "Frozen E_ref (chosen)", S1),
                                                 ("dynamic", "Dynamic denominator", MUTED))):
        d = p.filter(pl.col("variant") == variant)
        vals = [float(d.filter(pl.col("origin").cast(pl.String) == o)["mean_copy_return"][0] * 100) for o in TESTS]
        vals.append(float(d.filter(pl.col("window") == "all_tests")["mean_copy_return"][0] * 100))
        seen += vals
        xs = [i + (k - 0.5) * w for i in range(len(labels))]
        ax.bar(xs, vals, w - 0.03, color=color, label=name)
        for x, v in zip(xs, vals, strict=True):
            ax.text(x, v + (0.03 if v >= 0 else -0.03), f"{v:+.2f}", ha="center", va="bottom" if v >= 0 else "top",
                    fontsize=8, color=INK2)
    ax.set_ylim(min(0.0, min(seen)) - 0.15, max(seen) + 0.15)
    ax.axhline(0, color=MUTED, linewidth=1)
    ax.set_xticks(range(len(labels)), labels)
    ax.set_ylabel("Mean funded copy return (%)", color=INK2)
    ax.legend(frameon=False, fontsize=9, loc="upper right")
    frz = p.filter((pl.col("variant") == "frozen") & (pl.col("window") == "all_tests")).row(0, named=True)
    dyn = p.filter((pl.col("variant") == "dynamic") & (pl.col("window") == "all_tests")).row(0, named=True)
    style(ax, "Archived (ADR-0119): the chosen frozen sizing against the dynamic denominator",
          f"Base scenario, gate-passers, $10,000 per address per test window. Headroom per filled side: frozen "
          f"{frz['cost_to_absorb_bps']:.1f} bps,\ndynamic {dyn['cost_to_absorb_bps']:.1f} bps; worst follower "
          f"leverage {frz['max_leverage']:.2f}x vs {dyn['max_leverage']:.2f}x.")
    save(fig, "p4_frozen_vs_dynamic.png")


def cost_surface_frozen():
    s = pl.read_csv(FROZEN / "cost_surface.csv", infer_schema_length=10000).filter(pl.col("origin") == "all_tests")
    frz = s.filter(pl.col("policy") == "frozen").sort("mean_return")
    names = {"centre": "Centre: Y 1, 0.5%, 1.5x", "most_favourable": "Most favourable corner",
             "least_favourable": "Least favourable corner", "y=0.5": "Impact Y 0.5", "y=2.0": "Impact Y 2",
             "participation=0.0025": "Participation 0.25%", "participation=0.01": "Participation 1%",
             "participation=none": "No participation cap", "cap_x=1.0": "Address cap 1.0x",
             "cap_x=2.0": "Address cap 2.0x"}
    fig, ax = figure(10.5, 5.6)
    column = max(frz["mean_return"]) * 100 + 0.05  # labels right of every bar
    for i, r in enumerate(frz.iter_rows(named=True)):
        v = r["mean_return"] * 100
        low = r["point"] == "least_favourable"
        ax.barh(i, v, 0.62, color=S2 if low else (S3 if r["point"] == "centre" else S1))
        ax.text(column, i, f"{v:+.2f}%  ({r['absorb_bps']:+.1f} bps)", va="center", ha="left", fontsize=8,
                color=INK if low else INK2, fontweight="bold" if low else "normal")
    ax.set_yticks(range(frz.height), [names.get(p, p) for p in frz["point"]])
    ax.set_xlim(min(0.0, min(frz["mean_return"]) * 100) - 0.05, column + 0.32)
    ax.axvline(0, color=MUTED, linewidth=1)
    ax.set_xlabel("Mean funded base return (1.2 s delay) over 56 gate-passing test windows (%)", color=INK2)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.grid(axis="y", visible=False)
    style(ax, "ADR-0150/0160/0161: cost surface under the frozen sizing, base at 1.2 s",
          "One cost placeholder at a time, plus the best and worst corners (ADR-0117).\n"
          "Labels: mean return and the extra cost per filled side that would absorb the profit.")
    save(fig, "p4_cost_surface_frozen.png")


def holding_bands_frozen():
    b = pl.read_csv(FROZEN / "sensitivity_bands.csv").filter(
        (pl.col("scenario") == "base") & (pl.col("variant") == "part_ns_sweep_frozen"))
    order = ["<1m", "1-15m", "15m-1h", "1-6h", "6-24h", "1-7d", ">7d"]
    fig, ax = figure(9.5, 5.0)
    for i, band in enumerate(order):
        d = b.filter(pl.col("hold_band") == band)
        mean = float((d["net_bps"] * d["completed"]).sum() / d["completed"].sum())
        all_pos = bool((d["net_bps"] > 0).all())
        ax.bar(i, mean, 0.6, color=S3 if all_pos else (S1 if mean >= 0 else S2))
        ax.scatter([i] * d.height, d["net_bps"], color=INK2, s=14, zorder=3,
                   label="One test window" if i == 0 else None)
        ax.text(i + 0.33, mean, f"{mean:+.0f}", ha="left", va="center", fontsize=9, color=INK)
    ax.axhline(0, color=MUTED, linewidth=1)
    ax.set_xticks(range(len(order)), order)
    ax.set_xlabel("Leader's median holding time", color=INK2)
    ax.set_ylabel("Net result per completed round trip (bps)", color=INK2)
    ax.legend(frameon=False, fontsize=9, loc="lower left")
    style(ax, "ADR-0150/0160/0161: holding bands under the frozen sizing",
          "Base scenario (1.2 s), all A/B addresses, four test windows, after fees, spread, impact, drift and funding. "
          "Green = positive in all four tests.")
    save(fig, "p4_holding_bands_frozen.png")


def stress_coverage():
    """ADR-0122 safeguard 1 and 3: the frozen stress result under both coverage measures, with the worst-measured
    sensitivity, per test and pooled (gate-passers)."""
    c = pl.read_csv(FROZEN / "stress_coverage.csv").filter(pl.col("scenario") == "stress")  # ADR-0150: 5 s
    labels = [*TESTS, "all_tests"]
    fig, ax = figure(10.0, 5.2)
    w = 0.36
    seen = []
    measures = (("broad_adr0115", "ADR-0115: every unfilled intent counts as unpriced (except minimum size, unsized)",
                 MUTED),
                ("pricing_failures_adr0122", "ADR-0122: only pricing failures count as unpriced", S1))
    for k, (measure, name, color) in enumerate(measures):
        d = {r["origin"]: r for r in c.filter(pl.col("measure") == measure).iter_rows(named=True)}
        xs = [i + (k - 0.5) * w for i in range(len(labels))]
        vals = [d[o]["mean_return"] * 100 for o in labels]
        seen += vals
        ax.bar(xs, vals, w - 0.03, color=color, label=name)
        for x, o, v in zip(xs, labels, vals, strict=True):
            r = d[o]
            ax.text(x, v - 0.08, f"{v:+.2f}%\n{r['measured']}/{r['gate_passers']}", ha="center", va="top",
                    fontsize=7.5, color=INK2)
        if measure == "pricing_failures_adr0122":
            pts = [(x, d[o]["mean_return_worst_imputed"] * 100) for x, o in zip(xs, labels, strict=True)
                   if d[o]["imputed"] > 0]  # only where an unmeasured window was filled in
            seen += [v for _, v in pts]
            ax.scatter([x for x, _ in pts], [v for _, v in pts], marker="D", s=22, color=S2, zorder=3,
                       label="ADR-0122, unmeasured windows at the worst measured return of their test")
    ax.set_ylim(min(seen) - 1.1, 0.6)
    ax.axhline(0, color=MUTED, linewidth=1)
    ax.set_xticks(range(len(labels)), [*TESTS, "All four tests"])
    ax.set_ylabel("Mean funded stress return, measured windows (%)", color=INK2)
    ax.legend(frameon=False, fontsize=8, loc="lower left")
    n = c.filter((pl.col("measure") == "pricing_failures_adr0122") & (pl.col("origin") == "all_tests")).row(
        0, named=True)
    style(ax, "ADR-0150/0160/0161: frozen stress result at 5 s under both coverage measures",
          f"Gate-passers, labels: mean and measured / gate-passing windows. Stress check (drawdown within -10%, "
          f"unmeasured fails): {n['stress_check_pass']} of\n{n['gate_passers']} pass, {n['stress_check_fail_loss']} "
          f"fail on loss, {n['stress_check_fail_unmeasured']} fail as unmeasured (ADR-0122 measure).")
    save(fig, "p4_stress_coverage.png")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for f in (gate_funnel, rebuild_example, worstcase_scatter, cost_per_side, returns_by_variant, holding_bands,
              frozen_vs_dynamic, cost_surface_frozen, holding_bands_frozen, stress_coverage):
        f()
        print("wrote", f.__name__)


if __name__ == "__main__":
    main()
