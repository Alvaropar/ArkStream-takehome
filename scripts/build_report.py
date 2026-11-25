# ruff: noqa: E501  (the Chinese strings count two columns per character, so many pairs pass 120 columns)
"""Build the reviewer's Word reports, in English and in Simplified Chinese, and their figures.

    uv run python scripts/rerun.py reports              # the usual way (adds python-docx for this run only)
    python scripts/build_report.py [--lang en|zh|both]  # any Python with python-docx, matplotlib, pandas, pyarrow

Writes ArkStream_Assignment_Report.docx (English) and ArkStream_Assignment_Report_zh-CN.docx (Chinese), with the figures
in decision/figures/report/ (`*_zh.png` for the Chinese labels). Both reports have the same six sections: the answer;
the data, the validation method and the latency; the address selection; the risk and portfolio rules; the holdout
results and the decision; how to read the repository. The detailed, authoritative texts are decision/decision-memo.md
and decision/deployment-protocol.md; where a report and a file differ, the file is right.

Every string is written once as an English/Chinese pair (`t(en, zh)`), so the two reports cannot drift apart in
structure. Figures are drawn from saved outputs under research/. The holdout NAV figure reads run A's hourly tables
(research/holdout/portfolio/run=A/...), which the submission zip does not ship (rerun.py holdout rebuilds them);
without them the saved PNG is reused. python-docx is not in uv.lock on purpose: the lock's hash is part of the frozen
environment that the holdout commands check.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from docx import Document  # noqa: E402
from docx.enum.table import WD_TABLE_ALIGNMENT  # noqa: E402
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK  # noqa: E402
from docx.oxml import OxmlElement  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402
from docx.shared import Cm, Pt, RGBColor  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = {"en": ROOT / "ArkStream_Assignment_Report.docx", "zh": ROOT / "ArkStream_Assignment_Report_zh-CN.docx"}
FIG = ROOT / "decision" / "figures" / "report"
RUN_A = ROOT / "research" / "holdout" / "portfolio" / "run=A" / "origin=2025-12-03"
WINDOW = ROOT / "research" / "holdout" / "window_report"
FREEZE_HASH = "62eba6dab41bf74838957d355538796fd59f30876317691219600755687b6648"
DECISION_SHA = "cb3dd576b3880ddfdf7459fd8dc97297fb93bfe249082cb15c731448586e7c2f"
ZH_FONT = "Microsoft YaHei"

NAVY, TEAL, AMBER, RED, GREY, LIGHT, INK = "#1B365D", "#2A9D8F", "#E9A23B", "#C8553D", "#8D99AE", "#EEF2F6", "#22252B"
BASE_RC = {
    "font.size": 9, "axes.titlesize": 10, "axes.titleweight": "bold", "axes.spines.top": False,
    "axes.spines.right": False, "axes.edgecolor": "#555555", "axes.titlelocation": "left", "savefig.dpi": 200,
    "savefig.bbox": "tight", "legend.frameon": False,
}
LANG = "en"


def t(en: str, zh: str) -> str:
    """The string in the language being built."""
    return zh if LANG == "zh" else en


def set_language(lang: str) -> None:
    global LANG
    LANG = lang
    plt.rcParams.update(BASE_RC)
    if lang == "zh":  # a CJK font first, with fallbacks for other systems
        plt.rcParams["font.family"] = [ZH_FONT, "PingFang SC", "Noto Sans CJK SC", "SimHei", "Arial Unicode MS",
                                       "DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = False
    else:
        plt.rcParams["font.family"] = ["Arial", "DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = True


# ---------------------------------------------------------------------------------------------------------- figures
def _name(stem: str) -> str:
    return f"{stem}{'_zh' if LANG == 'zh' else ''}.png"


def _save(fig, stem: str) -> Path:
    FIG.mkdir(parents=True, exist_ok=True)
    p = FIG / _name(stem)
    fig.savefig(p, facecolor="white")
    plt.close(fig)
    return p


def fig_timeline() -> Path:
    d = lambda s: datetime.strptime(s, "%Y-%m-%d")  # noqa: E731
    fig, ax = plt.subplots(figsize=(6.6, 2.05))
    ax.barh(3, (d("2025-12-03") - d("2025-07-27")).days, left=d("2025-07-27"), height=0.5, color=LIGHT,
            edgecolor=GREY)
    ax.text(d("2025-07-30"), 3, t("first fill 27 Jul; the training window grows to each decision date",
                                  "首笔成交 7 月 27 日；训练窗口延伸至每个决策日"), va="center", fontsize=7.3, color=INK)
    for o in ["2025-10-08", "2025-10-22", "2025-11-05", "2025-11-19"]:
        ax.barh(2, 14, left=d(o), height=0.5, color=NAVY, edgecolor="white")
    ax.barh(1, (d("2026-01-04") - d("2025-12-03")).days, left=d("2025-12-03"), height=0.5, color=AMBER)
    for o in ["2025-10-08", "2025-10-22", "2025-11-05", "2025-11-19", "2025-12-03"]:
        ax.axvline(d(o), color=GREY, lw=0.6, ls=":", zorder=0)
    ax.axvspan(d("2025-10-10"), d("2025-10-12"), color=RED, alpha=0.15, lw=0)
    ax.text(d("2025-10-13"), 1.0, t("10-11 Oct crash:\nleft out of cost estimates", "10 月 10–11 日暴跌：\n不用于成本估计"),
            fontsize=7, color=RED, va="center")
    ax.axvline(d("2026-01-04"), color=RED, lw=1.4)
    ax.text(d("2026-01-05"), 2.0, t("cutoff\n4 Jan 2026\n23:59 UTC", "截止\n2026-01-04\n23:59 UTC"), color=RED,
            fontsize=7.3, va="center")
    ax.set_yticks([3, 2, 1])
    ax.set_yticklabels([t("Training", "训练期"), t("Development tests\n(4 x 14 days)", "开发测试\n（4 × 14 天）"),
                        t("Holdout\n(32 days, opened once)", "留出期\n（32 天，仅打开一次）")], fontsize=7.8)
    ax.set_ylim(0.45, 3.55)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter(t("%b %Y", "%Y-%m")))
    ax.set_xlim(d("2025-07-20"), d("2026-01-26"))
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    return _save(fig, "r02_timeline")


def fig_funnel() -> Path:
    f = pd.read_csv(ROOT / "research/cutoff/selection_v2/funnel_v2.csv").iloc[0]
    n_all = len(pd.read_csv(ROOT / "research/cutoff/deliverables/trader_decisions.csv"))
    stages = [
        (t("Addresses with data before 4 Jan", "1 月 4 日前有数据的地址"), n_all, NAVY),
        (t("Data grade A or B", "数据等级 A 或 B"), int(f.ab_universe), NAVY),
        (t("Pass every rule on the trader's record", "通过交易员记录的全部规则"), int(f.s2_pass), NAVY),
        (t("Copyable", "可跟单"), int(f.s1_s3_pass), TEAL),
        (t("Positive skill estimate (E1 or E2)", "技能估计为正（E1 或 E2）"), int(f.qualified_E1 + f.qualified_E2), TEAL),
        (t("Not a near-duplicate: handed off", "非近似重复：移交"), int(f.eligible), TEAL),
        (t("Live in the gray launch", "灰度上线实盘"), 2, AMBER),
    ][::-1]
    fig, ax = plt.subplots(figsize=(6.6, 2.75))
    ax.barh([s for s, _, _ in stages], [v for _, v, _ in stages], color=[c for _, _, c in stages], height=0.62)
    for i, (_, v, _) in enumerate(stages):
        ax.text(v * 1.12, i, f"{v:,}", va="center", fontsize=8.5, fontweight="bold", color=INK)
    ax.set_xscale("log")
    ax.set_xlim(1, 3300)
    ax.set_xticks([1, 10, 100, 1000])
    ax.set_xticklabels(["1", "10", "100", "1,000"])
    ax.set_xlabel(t("addresses (log scale)", "地址数（对数刻度）"))
    ax.tick_params(axis="y", length=0)
    ax.text(0.99, 0.30, t("rule-based screening (navy)\nperformance on the follower copy (teal)",
                          "基于规则的筛选（深蓝）\n跟单表现（青绿）"), transform=ax.transAxes, ha="right", fontsize=7.5,
            color="#444444")
    return _save(fig, "r03_funnel")


def fig_capital() -> Path:
    fig, (ax, tx) = plt.subplots(1, 2, figsize=(6.6, 2.6), gridspec_kw={"width_ratios": [1, 1.25]})
    ax.pie([95_000, 2_500, 2_500], colors=[GREY, TEAL, NAVY], startangle=90, counterclock=False,
           wedgeprops=dict(width=0.38, edgecolor="white"))
    ax.text(0, 0.08, "100,000", ha="center", fontsize=11, fontweight="bold", color=INK)
    ax.text(0, -0.16, "USDC", ha="center", fontsize=8, color=INK)
    ax.set_aspect("equal")
    tx.axis("off")
    lines = [
        (GREY, t("Reserve: 95,000 USDC", "储备金：95,000 USDC"),
         t("off the exchange; not margin for the live book", "存放在交易所之外；不作为实盘账本的保证金")),
        (TEAL, t("Live sleeve 0x2cd9: 2,500 USDC", "实盘子仓 0x2cd9：2,500 USDC"),
         t("copies its trader on the venue", "在交易所上跟单该交易员")),
        (NAVY, t("Live sleeve 0x971f: 2,500 USDC", "实盘子仓 0x971f：2,500 USDC"),
         t("copies its trader on the venue", "在交易所上跟单该交易员")),
        (RED, t("Loss budget: 750 USDC (0.75%)", "亏损预算：750 USDC（0.75%）"),
         t("shared by both live sleeves; at 750 all is closed", "两个实盘子仓共用；达到 750 即全部平仓")),
        (AMBER, t("Paper: 0x3a12 and 0xe65c", "模拟盘：0x3a12 和 0xe65c"),
         t("10,000 each, simulated only: no money", "各 10,000，仅模拟，不投入资金")),
    ]
    for i, (c, head, sub) in enumerate(lines):
        y = 0.92 - i * 0.2
        in_ring = i < 3  # the last two are not slices of the ring: drawn hollow
        tx.add_patch(plt.Rectangle((0.0, y - 0.05), 0.05, 0.1, facecolor=c if in_ring else "none", edgecolor=c,
                                   lw=0 if in_ring else 1.8, transform=tx.transAxes, clip_on=False))
        tx.text(0.09, y + 0.015, head, fontsize=8.6, fontweight="bold", color=INK, transform=tx.transAxes,
                va="center")
        tx.text(0.09, y - 0.065, sub, fontsize=7.6, color="#444444", transform=tx.transAxes, va="center")
    return _save(fig, "r04_capital")


def fig_ic() -> Path:
    h5 = pd.read_csv(WINDOW / "h5_cross_section.csv")
    hold = float(h5.loc[h5.test == "ic_alpha", "value"].iloc[0])
    labels = [t("8 Oct", "10-08"), t("22 Oct", "10-22"), t("5 Nov", "11-05"), t("19 Nov", "11-19"),
              t("Holdout\n3 Dec - 4 Jan", "留出期\n12-03 至 01-04")]
    vals = [0.098, -0.029, -0.038, -0.150, hold]  # decision/phase-4-v2-results.md P4-5; holdout: h5_cross_section.csv
    fig, ax = plt.subplots(figsize=(6.6, 2.4))
    bars = ax.bar(labels, vals, color=[NAVY] * 4 + [AMBER], width=0.55)
    for b, v in zip(bars, vals, strict=True):
        ax.text(b.get_x() + b.get_width() / 2, v + (0.008 if v >= 0 else -0.008), f"{v:+.3f}", ha="center",
                va="bottom" if v >= 0 else "top", fontsize=8.5, fontweight="bold", color=INK)
    ax.axhline(0, color="#555555", lw=0.8)
    ax.axhline(0.05, color=TEAL, lw=1.1, ls="--")
    ax.text(4.45, 0.056, t("average needed to use the ranking: +0.05", "采用排序所需的平均值：+0.05"), color=TEAL,
            fontsize=7.8, ha="right")
    ax.set_ylim(-0.2, 0.14)
    ax.set_ylabel(t("rank correlation (IC)", "排序相关系数（IC）"))
    return _save(fig, "r05_ranking_ic")


def fig_holdout_nav() -> Path:
    if not (RUN_A / "config=S" / "scenario=base" / "hourly.parquet").is_file():
        print(f"  {_name('r07_holdout_nav')}: run A's hourly tables are not here; keeping the saved figure")
        return FIG / _name("r07_holdout_nav")
    fig, ax = plt.subplots(figsize=(6.6, 2.8))
    for cfg, col, lab in [("U", AMBER, t("without limits", "无限额")), ("S", TEAL, t("with the limits", "有限额"))]:
        for scen, ls, slab in [("base", "-", t("base costs", "基准成本")), ("stress", "--", t("stress costs", "压力成本"))]:
            h = pd.read_parquet(RUN_A / f"config={cfg}" / f"scenario={scen}" / "hourly.parquet", columns=["t", "nav"])
            s = h.groupby("t").nav.sum()
            tt = pd.to_datetime(s.index, unit="ms", utc=True)
            ax.plot(tt, s.values, color=col, ls=ls, lw=1.4, label=f"{lab}{t(', ', '，')}{slab}")
    ax.axhline(20_000, color="#555555", lw=0.7, ls=":")
    ax.xaxis.set_major_formatter(mdates.DateFormatter(t("%d %b", "%m-%d")))
    ax.set_ylabel(t("book value (USDC)", "账本价值（USDC）"))
    ax.legend(fontsize=7.5, ncol=2, loc="lower left")
    return _save(fig, "r07_holdout_nav")


def fig_sleeves() -> Path:
    h2 = pd.read_csv(WINDOW / "h2_risk.csv")
    live, paper = t("(live)", "（实盘）"), t("(paper)", "（模拟盘）")
    sleeves = [("G2500", f"0x2cd9\n{live}"), ("G2500_0x971f", f"0x971f\n{live}"), ("G2500_0x3a12", f"0x3a12\n{paper}"),
               ("G2500_0xe65c", f"0xe65c\n{paper}")]
    fig, ax = plt.subplots(figsize=(6.6, 2.5))
    w = 0.36
    for k, (scen, col, lab) in enumerate([("base", NAVY, t("base costs", "基准成本")),
                                          ("stress", RED, t("stress costs", "压力成本"))]):
        vals = [float(h2[(h2.config == c) & (h2.scenario == scen)].max_loss_incl_exit_usdc.iloc[0]) for c, _ in sleeves]
        xs = [i + (k - 0.5) * w for i in range(len(sleeves))]
        ax.bar(xs, vals, width=w, color=col, label=lab)
        for x, v in zip(xs, vals, strict=True):
            ax.text(x, v + 12, f"{v:.0f}", ha="center", fontsize=8, color=INK)
    ax.axhline(750, color=AMBER, lw=1.6)
    ax.text(len(sleeves) - 0.5, 765, t("loss budget 750 USDC", "亏损预算 750 USDC"), color=AMBER, ha="right", fontsize=8,
            fontweight="bold")
    ax.set_xticks(range(len(sleeves)))
    ax.set_xticklabels([n for _, n in sleeves])
    ax.set_ylim(0, 840)
    ax.set_ylabel(t("worst loss incl. exit (USDC)", "含平仓的最大亏损（USDC）"))
    ax.legend(fontsize=7.5, loc="center right")
    return _save(fig, "r08_sleeves")


def fig_costs() -> Path:
    h3 = pd.read_csv(WINDOW / "h3_costs.csv").sort_values("coin")
    fig, ax = plt.subplots(figsize=(6.6, 2.4))
    xs = range(len(h3))
    cols = [NAVY if m else LIGHT for m in h3.measured]
    ax.bar(xs, h3.median_cost_bps, color=cols, width=0.55, edgecolor=[NAVY if m else GREY for m in h3.measured])
    has = [(x, v) for x, v in zip(xs, h3.dev_p90_bps, strict=True) if pd.notna(v)]
    ax.scatter([x for x, _ in has], [v for _, v in has], marker="_", s=900, color=RED, lw=2.4, zorder=3)
    handles = [plt.Rectangle((0, 0), 1, 1, color=NAVY), plt.Line2D([0], [0], color=RED, lw=2.4)]
    ax.legend(handles, [t("holdout median cost per side", "留出期每边成本中位数"),
                        t("limit: the development 90th percentile", "限额：开发期第 90 百分位")], fontsize=7.5,
              loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=2)
    for x, (v, n) in enumerate(zip(h3.median_cost_bps, h3.orders, strict=True)):
        ax.text(x, v / 2, f"{v:.1f}", ha="center", color="white" if h3.measured.iloc[x] else INK, fontsize=8,
                fontweight="bold")
        ax.text(x, -1.6, t(f"{n} orders", f"{n} 笔订单"), ha="center", fontsize=7, color="#555555")
    ax.text(list(h3.coin).index("AAVE"), 13.6, t("no development\nbaseline", "无开发期\n基准"), ha="center", fontsize=7,
            color=GREY)
    ax.set_xticks(list(xs))
    ax.set_xticklabels(h3.coin)
    ax.set_ylim(-2.6, 16.5)
    ax.set_ylabel(t("bp per side (1 bp = 0.01%)", "每边 bp（1 bp = 0.01%）"))
    return _save(fig, "r09_costs")


def fig_cross_section() -> Path:
    h5 = pd.read_csv(WINDOW / "h5_cross_section.csv")

    def v(test, group):
        r = h5[(h5.test == test) & (h5.group.astype(str).str.lower() == group.lower())].iloc[0]
        return float(r.value) * 1e4, int(r.n)

    rows = [
        (t("Category E1 (selected)", "E1 类别（入选）"), *v("category_mean_next_alpha", "E1"), True),
        (t("Category E0 (unmeasured)", "E0 类别（未测量）"), *v("category_mean_next_alpha", "E0"), False),
        (t("Category E- (negative)", "E- 类别（为负）"), *v("category_mean_next_alpha", "E-"), False),
        (t("Robust", "稳健"), *v("robust_mean_next_alpha", "true"), True),
        (t("Not robust", "不稳健"), *v("robust_mean_next_alpha", "false"), False),
        (t("Pass break-even after delay", "通过延迟后盈亏平衡"), *v("break_even_pass_mean_next_alpha", "true"), True),
        (t("Fail break-even after delay", "未通过延迟后盈亏平衡"), *v("break_even_pass_mean_next_alpha", "false"), False),
        (t("Trading books", "交易型账本"), *v("carry_book_mean_next_alpha", "false"), True),
        (t("Carry books (funding income)", "套息型账本（资金费收入）"), *v("carry_book_mean_next_alpha", "true"), False),
    ]
    fig, ax = plt.subplots(figsize=(6.6, 3.0))
    ys = list(range(len(rows)))[::-1]
    for y, (_lab, val, n, pref) in zip(ys, rows, strict=True):
        ax.barh(y, val, color=TEAL if pref else GREY, height=0.6)
        ax.text(val + (1 if val >= 0 else -1), y, f"{val:+.1f}  (n={n})", va="center",
                ha="left" if val >= 0 else "right", fontsize=7.8, color=INK)
    for y in (ys[2] - 0.5, ys[4] - 0.5, ys[6] - 0.5):
        ax.axhline(y, color="#DDDDDD", lw=0.8)
    ax.set_yticks(ys)
    ax.set_yticklabels([r[0] for r in rows], fontsize=8)
    ax.axvline(0, color="#555555", lw=0.8)
    ax.set_xlim(-48, 52)
    ax.set_xlabel(t("mean skill (α) in the holdout window, bp per day of exposure",
                    "留出窗口内的平均技能（α），每日每单位敞口 bp"))
    ax.tick_params(axis="y", length=0)
    return _save(fig, "r10_cross_section")


# ---------------------------------------------------------------------------------------------------------- document
def _shade(cell, hex_fill: str) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill.lstrip("#"))
    tcPr.append(shd)


def _borders(table, color="BFC8D2", size=4) -> None:
    tblPr = table._tbl.tblPr
    b = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement(f"w:{edge}")
        e.set(qn("w:val"), "single")
        e.set(qn("w:sz"), str(size))
        e.set(qn("w:color"), color)
        b.append(e)
    # Schema order: tblBorders comes before shd, tblLayout, tblCellMar, tblLook, tblCaption and tblDescription.
    later = {qn(f"w:{x}") for x in ("shd", "tblLayout", "tblCellMar", "tblLook", "tblCaption", "tblDescription")}
    nxt = next((ch for ch in tblPr if ch.tag in later), None)
    if nxt is None:
        tblPr.append(b)
    else:
        nxt.addprevious(b)


def _runs(par, text: str, size=None, color=None, italic=False, font=None) -> None:
    """Add text with **bold** spans."""
    for i, chunk in enumerate(text.split("**")):
        if not chunk:
            continue
        r = par.add_run(chunk)
        r.bold = i % 2 == 1
        r.italic = italic
        if size:
            r.font.size = Pt(size)
        if color:
            r.font.color.rgb = RGBColor.from_string(color.lstrip("#"))
        if font:
            r.font.name = font  # Chinese characters in a monospace run take the CJK font
            r._element.rPr.rFonts.set(qn("w:eastAsia"), ZH_FONT if LANG == "zh" else font)


class Report:
    def __init__(self) -> None:
        self.doc = Document()
        self.fig_n = 0
        self.tab_n = 0
        self.east = ZH_FONT if LANG == "zh" else "Calibri"
        self._setup()

    def _setup(self) -> None:
        d = self.doc
        sec = d.sections[0]
        sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
        sec.left_margin = sec.right_margin = Cm(2.0)
        sec.top_margin, sec.bottom_margin = Cm(2.0), Cm(1.8)
        st = d.styles
        # The default template gives the body a theme font (Cambria), and in Word a theme attribute overrides an
        # explicit font name: drop every theme attribute, then name the fonts.
        themes = ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme")
        for rf in st.element.iter(qn("w:rFonts")):
            for att in themes:
                rf.attrib.pop(qn(att), None)
            if rf.getparent().getparent().tag == qn("w:rPrDefault"):
                for att in ("w:ascii", "w:hAnsi", "w:cs"):
                    rf.set(qn(att), "Calibri")
                rf.set(qn("w:eastAsia"), self.east)
        if LANG == "zh":  # Chinese line breaking and proofing
            for lang in st.element.iter(qn("w:lang")):
                if lang.getparent().getparent().tag == qn("w:rPrDefault"):
                    lang.set(qn("w:eastAsia"), "zh-CN")
        normal = st["Normal"]
        normal.font.name = "Calibri"
        normal.element.rPr.rFonts.set(qn("w:eastAsia"), self.east)
        normal.font.size = Pt(10.5)
        normal.paragraph_format.space_after = Pt(5)
        normal.paragraph_format.line_spacing = 1.1
        for name, size, color, before, after in [("Title", 26, NAVY, 0, 6), ("Heading 1", 16, NAVY, 16, 6),
                                                 ("Heading 2", 12, NAVY, 10, 4), ("Heading 3", 11, TEAL, 8, 3)]:
            s = st[name]
            s.font.name = "Calibri"
            s.element.rPr.rFonts.set(qn("w:eastAsia"), self.east)
            s.font.size = Pt(size)
            s.font.bold = True
            s.font.color.rgb = RGBColor.from_string(color.lstrip("#"))
            s.paragraph_format.space_before = Pt(before)
            s.paragraph_format.space_after = Pt(after)
            s.paragraph_format.keep_with_next = True
        st["Heading 1"].paragraph_format.page_break_before = True  # each section starts on a new page
        st["List Bullet"].paragraph_format.space_after = Pt(2.5)
        cap = st["Caption"]
        cap.font.size = Pt(9)
        cap.font.italic = False
        cap.font.bold = False
        cap.font.color.rgb = RGBColor.from_string("444444")
        self._footer()

    def _footer(self) -> None:
        p = self.doc.sections[0].footer.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _runs(p, t("ArkStream Hyperliquid copy pilot · assignment report · page ",
                   "ArkStream Hyperliquid 跟单试点 · 笔试报告 · 第 "), size=8, color="#777777")
        r = p.add_run()
        r.font.size = Pt(8)
        r.font.color.rgb = RGBColor.from_string("777777")
        for kind, text in (("begin", None), (None, "PAGE"), ("end", None)):
            if kind:
                e = OxmlElement("w:fldChar")
                e.set(qn("w:fldCharType"), kind)
            else:
                e = OxmlElement("w:instrText")
                e.set(qn("xml:space"), "preserve")
                e.text = text
            r._r.append(e)
        if LANG == "zh":
            _runs(p, " 页", size=8, color="#777777")

    # --- blocks
    def h1(self, x):
        self.doc.add_heading(x, level=1)

    def h2(self, x):
        self.doc.add_heading(x, level=2)

    def h3(self, x):
        self.doc.add_heading(x, level=3)

    def p(self, text, size=None, color=None, italic=False, after=None):
        par = self.doc.add_paragraph()
        _runs(par, text, size=size, color=color, italic=italic)
        if after is not None:
            par.paragraph_format.space_after = Pt(after)
        return par

    def bullets(self, items):
        for it in items:
            _runs(self.doc.add_paragraph(style="List Bullet"), it)

    def table(self, header, rows, widths, size=9, first_bold=False, caption=None, source=None, mono=()):
        if caption:
            self.tab_n += 1
            cp = self.doc.add_paragraph(style="Caption")
            _runs(cp, t(f"**Table {self.tab_n}.** {caption}", f"**表 {self.tab_n}.** {caption}"))
            cp.paragraph_format.keep_with_next = True
            cp.paragraph_format.space_before = Pt(6)
        tb = self.doc.add_table(rows=1 + len(rows), cols=len(header))
        tb.alignment = WD_TABLE_ALIGNMENT.CENTER
        tb.autofit = False
        _borders(tb)
        for j, h in enumerate(header):
            c = tb.rows[0].cells[j]
            c.width = Cm(widths[j])
            _shade(c, NAVY)
            c.paragraphs[0].paragraph_format.space_after = Pt(0)
            if h:
                _runs(c.paragraphs[0], f"**{h}**", size=size, color="#FFFFFF")
        trPr = tb.rows[0]._tr.get_or_add_trPr()
        hdr = OxmlElement("w:tblHeader")
        hdr.set(qn("w:val"), "true")
        trPr.append(hdr)
        for i, row in enumerate(rows, start=1):
            for j, val in enumerate(row):
                c = tb.rows[i].cells[j]
                c.width = Cm(widths[j])
                if i % 2 == 0:
                    _shade(c, LIGHT)
                par = c.paragraphs[0]
                par.paragraph_format.space_after = Pt(0)
                par.paragraph_format.line_spacing = 1.0
                s = str(val)
                if s:
                    _runs(par, f"**{s}**" if first_bold and j == 0 and "**" not in s else s,
                          size=size - 0.5 if j in mono else size, font="Consolas" if j in mono else None)
        if source:
            sp = self.doc.add_paragraph()
            _runs(sp, t("Source: ", "来源：") + source, size=8, color="#666666", italic=True)
            sp.paragraph_format.space_before = Pt(2)
        else:
            self.doc.add_paragraph().paragraph_format.space_after = Pt(2)
        return tb

    def figure(self, path: Path, caption: str, source: str | None = None, width_cm=16.5):
        par = self.doc.add_paragraph()
        par.alignment = WD_ALIGN_PARAGRAPH.CENTER
        par.paragraph_format.keep_with_next = True
        par.paragraph_format.space_after = Pt(0)
        par.add_run().add_picture(str(path), width=Cm(width_cm))
        self.fig_n += 1
        cp = self.doc.add_paragraph(style="Caption")
        _runs(cp, t(f"**Figure {self.fig_n}.** {caption}", f"**图 {self.fig_n}.** {caption}"))
        if source:
            _runs(cp, t("  Source: ", "  来源：") + source, size=8, color="#666666", italic=True)

    def callout(self, title, lines, fill="#E8F4F2", bar=TEAL):
        tb = self.doc.add_table(rows=1, cols=1)
        tb.alignment = WD_TABLE_ALIGNMENT.CENTER
        c = tb.rows[0].cells[0]
        c.width = Cm(17.0)
        tcPr = c._tc.get_or_add_tcPr()
        b = OxmlElement("w:tcBorders")
        for edge, sz in (("top", 0), ("left", 36), ("bottom", 0), ("right", 0)):  # schema order
            e = OxmlElement(f"w:{edge}")
            e.set(qn("w:val"), "single" if sz else "nil")
            if sz:
                e.set(qn("w:sz"), str(sz))
                e.set(qn("w:color"), bar.lstrip("#"))
            b.append(e)
        tcPr.append(b)
        _shade(c, fill)  # after tcBorders: the schema puts shd after it
        par = c.paragraphs[0]
        _runs(par, f"**{title}**", size=10.5, color=NAVY)
        par.paragraph_format.space_after = Pt(3)
        for ln in lines:
            q = c.add_paragraph(style="List Bullet") if ln.startswith("- ") else c.add_paragraph()
            _runs(q, ln[2:] if ln.startswith("- ") else ln, size=10)
            q.paragraph_format.space_after = Pt(2)
        self.doc.add_paragraph().paragraph_format.space_after = Pt(2)

    def code(self, lines):
        tb = self.doc.add_table(rows=1, cols=1)
        c = tb.rows[0].cells[0]
        c.width = Cm(17.0)
        _shade(c, "#F3F4F6")
        for k, ln in enumerate(lines):
            par = c.paragraphs[0] if k == 0 else c.add_paragraph()
            par.paragraph_format.space_after = Pt(1)
            par.paragraph_format.line_spacing = 1.0
            _runs(par, ln, size=8, font="Consolas")
        self.doc.add_paragraph().paragraph_format.space_after = Pt(2)

    def page_break(self):
        self.doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    def save(self, path: Path):
        cp = self.doc.core_properties
        cp.title = t("Hyperliquid Multi-Trader Copy Pilot: assignment report", "Hyperliquid 多交易员跟单试点：笔试报告")
        cp.subject = t("ArkStream Quantitative Researcher written test", "ArkStream 量化研究员笔试")
        cp.author = ""
        cp.language = t("en-US", "zh-CN")
        cp.comments = "Generated by scripts/build_report.py"
        cp.created = cp.modified = datetime(2026, 11, 25, tzinfo=UTC)
        zoom = self.doc.settings.element.find(qn("w:zoom"))
        if zoom is not None and zoom.get(qn("w:percent")) is None:
            zoom.set(qn("w:percent"), "100")  # the default template omits the required attribute
        self.doc.save(str(path))


# ---------------------------------------------------------------------------------------------------------- content
def holdout_rows() -> list[list[str]]:
    """Each basket address alone as a 2,500 USDC gray sleeve on the holdout (run A, H2 and H4)."""
    h2 = pd.read_csv(WINDOW / "h2_risk.csv")
    h4 = pd.read_csv(WINDOW / "h4_returns.csv")
    live, paper = t("Live", "实盘"), t("Paper", "模拟盘")
    rows = []
    for cfg, addr, role in [("G2500", "0x2cd9…946e", live), ("G2500_0x971f", "0x971f…77fa", live),
                            ("G2500_0x3a12", "0x3a12…5d69", paper), ("G2500_0xe65c", "0xe65c…8428", paper)]:
        ret, dd, loss = {}, {}, {}
        for sc in ("base", "stress"):
            r4 = h4[(h4.config == cfg) & (h4.scenario == sc) & (h4.scope == "combined")].raw_return.iloc[0]
            r2 = h2[(h2.config == cfg) & (h2.scenario == sc)].iloc[0]
            ret[sc] = f"{r4 * 100:+.2f}%"
            dd[sc] = f"{r2.max_drawdown_hourly * 100:.1f}%"
            loss[sc] = f"{r2.max_loss_incl_exit_usdc:.0f}"
        if cfg == "G2500_0x971f":
            ret["stress"] = "-0.32%*"  # the daily summary reads -100% (decision-memo.md section 2.6, item 1)
        rows.append([addr, role, ret["base"], ret["stress"], f"{dd['base']} / {dd['stress']}",
                     f"{loss['base']} / {loss['stress']}"])
    return rows


def write(r: Report, figs: dict[str, Path]) -> None:
    decision = json.loads((ROOT / "research/holdout/decision_A.json").read_text(encoding="utf-8"))
    verdict = decision.get("decision", "CONDITIONAL GO")

    # ---- title page
    for _ in range(5):
        r.p("")
    r.p(t("ArkStream · Quantitative Researcher written test", "ArkStream · 量化研究员笔试"), size=11, color=TEAL)
    _runs(r.doc.add_paragraph(style="Title"), t("Hyperliquid Multi-Trader Copy Pilot", "Hyperliquid 多交易员跟单试点"))
    r.p(t("Assignment report", "笔试报告"), size=14, color=INK, after=24)
    r.p(t("**Decision time:** the data cutoff, 4 January 2026, 23:59:42 UTC",
          "**决策时点：** 数据截止时间，2026 年 1 月 4 日 23:59:42 UTC"), size=11)
    r.p(t(f"**Decision:** {verdict}: a capped gray execution measurement, not a capital deployment",
          f"**决策：** {verdict}（有条件通过）：仅进行有亏损上限的灰度执行测量，不部署资金"), size=11)
    r.p(t("**Capital:** 100,000 USDC reserved for the pilot", "**资金：** 为试点预留 100,000 USDC"), size=11, after=30)
    r.callout(t("About this report", "关于本报告"), [
        t("This report summarises the whole assignment. The detailed documents are decision/decision-memo.md (the "
          "answer to each item of the test; Chinese: decision/decision-memo.zh-CN.md) and "
          "decision/deployment-protocol.md (the operating rules). Every decision is recorded in decision/adr/ and every "
          "run in provenance/trial_log.md.",
          "本报告概述整个笔试项目。详细文件为 decision/decision-memo.md（逐项回答笔试题；中文译本为 "
          "decision/decision-memo.zh-CN.md）和 decision/deployment-protocol.md（运行规则）。所有决策记录在 "
          "decision/adr/，所有运行记录在 provenance/trial_log.md。"),
        t("Each table and figure names the file it comes from. Where the report and a file differ, the file is right.",
          "每张表和图都注明了数据来源文件。报告与文件不一致时，以文件为准。本中文版译自英文报告，如有歧义，以英文版为准。"),
    ])
    r.h2(t("Contents", "目录"))
    for line in [t("1. The answer in one page", "1. 一页结论"),
                 t("2. Data, validation method and latency", "2. 数据、验证方法与延迟"),
                 t("3. Selecting the addresses", "3. 地址筛选"),
                 t("4. Risk management and portfolio rules", "4. 风险管理与组合规则"),
                 t("5. Holdout results and the decision", "5. 留出测试结果与决策"),
                 t("6. Reading the repository", "6. 如何阅读本仓库")]:
        r.p(line, size=11, after=2)

    # ---- 1
    r.h1(t("1. The answer in one page", "1. 一页结论"))
    r.p(t("ArkStream reserved 100,000 USDC to pilot a portfolio that copies several Hyperliquid traders. The task: "
          "decide, using only data available at the cutoff, whether to launch, which traders to copy, how much "
          "capital to use and under which risk rules.",
          "ArkStream 为一个跟单多位 Hyperliquid 交易员的组合预留了 100,000 USDC 作为试点资金。任务是：仅使用截止时点之前"
          "可得的数据，决定是否上线、跟哪些交易员、投入多少资金，以及采用哪些风险规则。"))
    r.callout(t("Recommendation", "建议"), [
        t("- **Do not deploy the 100,000 USDC as a copy basket.** No trader in the data shows skill that persists "
          "from one two-week window to the next, so there is no basis for committing capital.",
          "- **不将 100,000 USDC 作为跟单组合部署。** 数据中没有任何交易员表现出能从一个两周窗口延续到下一个窗口的技能，"
          "因此没有投入资金的依据。"),
        t("- **Run a small, controlled gray launch instead, as an execution measurement.** Two traders are copied "
          "live with 2,500 USDC each (5,000 in total), under one shared loss budget of 750 USDC: 0.75% of the "
          "reserved capital.",
          "- **改为进行一次小规模、受控的灰度上线，作为执行测量。** 两位交易员以各 2,500 USDC（合计 5,000）实盘跟单，"
          "共用一个 750 USDC 的亏损预算，即预留资金的 0.75%。"),
        t("- **Copy two more traders on paper** (simulated, no money) and keep the other **95,000 USDC off the "
          "exchange**.",
          "- **另外两位交易员以模拟盘跟单**（模拟，不投入资金），其余 **95,000 USDC 保留在交易所之外**。"),
        t("- **The gray run ends** after at least 4 weeks and 200 live orders, when the loss budget is used up, or "
          "after 12 weeks at most.",
          "- **灰度运行在以下情况结束：** 至少 4 周且至少 200 笔实盘订单之后；亏损预算用尽时；或最长 12 周。"),
    ])
    notional = t("10,000 notional, no money", "10,000 名义金额，无实际资金")
    r.table([t("Address", "地址"), t("Role", "角色"), t("Capital", "资金"), t("What it trades", "交易标的")], [
        ["0x2cd9f4645b14bf968212c7c108213eaeb193946e", t("Live", "实盘"), "2,500 USDC",
         t("HYPE, ETH, AAVE (long)", "HYPE、ETH、AAVE（做多）")],
        ["0x971fc0c9becffd708c52a195b8a87c27359e77fa", t("Live", "实盘"), "2,500 USDC",
         t("BNB, BTC (long)", "BNB、BTC（做多）")],
        ["0x3a122449de235a40481689442271c0731b805d69", t("Paper", "模拟盘"), notional, t("BTC (long)", "BTC（做多）")],
        ["0xe65c360b28bd3da42d9a07d97f500d8d480e8428", t("Paper", "模拟盘"), notional, t("ETH (short)", "ETH（做空）")],
        [t("Reserve", "储备金"), t("Off-exchange", "场外"), "95,000 USDC", ""],
    ], widths=[7.6, 2.0, 3.6, 3.8], size=8.5, caption=t("The basket at the cutoff", "截止时点的组合"),
        source=t("research/cutoff/deliverables/target_allocations.csv; coins from decision/decision-memo.md section 1.2",
                 "research/cutoff/deliverables/target_allocations.csv；币种见 decision/decision-memo.md 第 1.2 节"))
    r.figure(figs["capital"], t("Where the 100,000 USDC goes. Only 5% is on the exchange, and at most 750 USDC can be "
                                "lost before everything is closed and the scheme returns to paper.",
                                "100,000 USDC 的分配。只有 5% 在交易所内；最多亏损 750 USDC，之后全部平仓并回到模拟盘。"))
    r.h3(t("Why this answer", "为什么是这个结论"))
    r.bullets([
        t("**No persistent skill.** Ranking traders by their past skill estimate did not predict the next window, "
          "neither in development nor in the final test (sections 3.3 and 5.2).",
          "**没有可持续的技能。** 按过往技能估计对交易员排序，无论在开发期还是最终测试中，都无法预测下一个窗口"
          "（第 3.3 节和第 5.2 节）。"),
        t("**Costs decide the outcome.** After fees, spread and delay, copying is close to break-even: on the "
          "development tests an extra 0.075% of cost per trade would have erased the average profit.",
          "**成本决定结果。** 扣除手续费、价差和延迟后，跟单接近盈亏平衡：在开发期测试中，每笔交易只要再多 0.075% "
          "的成本，就会抹去平均利润。"),
        t("**Only real orders can measure real costs.** The research simulates fills; it cannot see how our own "
          "orders would fill. The gray launch pays at most 750 USDC to measure exactly that.",
          "**只有真实订单才能测量真实成本。** 研究中的成交都是模拟的，看不到我们自己的订单会如何成交。灰度上线最多花费 "
          "750 USDC，专门测量这一点。"),
        t(f"**The pre-registered test passed.** Before the final 32 days of data were opened, five pass/fail "
          f"conditions were written down. All five passed, which allows the gray launch ({verdict}). This says the "
          "system behaved as designed. It does **not** say that the traders have an edge.",
          f"**预先登记的测试已通过。** 在打开最后 32 天数据之前，已写下五个通过/不通过条件。五个条件全部通过，因此允许"
          f"灰度上线（{verdict}）。这说明系统按设计运行，**并不**说明这些交易员具有优势。"),
    ])
    r.h3(t("What would change the answer", "什么情况会改变结论"))
    r.p(t("More capital (a 15,000 USDC stage) is allowed only when all three conditions hold, and never because of "
          "profit:", "只有以下三个条件全部满足时，才允许增加资金（15,000 USDC 阶段），且绝不因为盈利而增加："))
    r.bullets([
        t("the skill ranking predicts the next window over at least six two-week windows, with statistical "
          "significance;", "技能排序在至少六个两周窗口内能预测下一个窗口，且具有统计显著性；"),
        t("at least one trader reaches the strongest evidence category (E2) and passes every check;",
          "至少一位交易员达到最强证据类别（E2）并通过所有检查；"),
        t("the engine has run without faults.", "引擎运行无故障。"),
    ])
    r.p(t("If these conditions are not met within six months, the project closes.", "如果六个月内未满足这些条件，项目关闭。"))
    r.h3(t("Holdout result of the selected basket", "所选组合的留出测试结果"))
    r.p(t("Each address in the basket was run alone as a 2,500 USDC gray sleeve over the holdout, 3 Dec 2025 to "
          "4 Jan 2026, with the gray limits. None came close to the 750 USDC loss budget.",
          "组合中的每个地址都以 2,500 USDC 灰度子仓的形式，在留出期（2025 年 12 月 3 日至 2026 年 1 月 4 日）单独运行，"
          "采用灰度限额。没有一个接近 750 USDC 的亏损预算。"))
    r.table([t("Address", "地址"), t("Role", "角色"), t("Return, base costs", "收益（基准成本）"),
             t("Return, stress costs", "收益（压力成本）"), t("Max drawdown, base / stress", "最大回撤（基准 / 压力）"),
             t("Worst loss incl. exit, base / stress (USDC)", "含平仓的最大亏损（基准 / 压力，USDC）")],
            holdout_rows(), widths=[2.6, 1.5, 2.3, 2.4, 3.6, 4.6], size=8.5, first_bold=True,
            caption=t("The basket on the holdout, each address alone at 2,500 USDC",
                      "组合在留出期的表现，每个地址单独以 2,500 USDC 运行"),
            source=t("research/holdout/window_report/h2_risk.csv and h4_returns.csv. Max drawdown is from the hourly "
                     "peak. *0x971f under stress is read from the hourly book value; the daily summary shows -100% "
                     "because unknown funding days were added as zero (decision-memo.md section 2.6).",
                     "research/holdout/window_report/h2_risk.csv 和 h4_returns.csv。最大回撤按逐小时峰值计算。"
                     "*0x971f 在压力成本下的数值取自逐小时账本价值；日度汇总显示 -100%，原因是资金费未知的日期被按零相加"
                     "（decision-memo.md 第 2.6 节）。"))
    r.table([t("Record", "记录"), t("Value", "值")], [
        [t("Freeze hash: code, rules, settings and data manifests (119 files), taken before the holdout was opened",
           "冻结哈希：代码、规则、配置和数据清单（119 个文件），在打开留出期之前生成"), FREEZE_HASH],
        [t("Decision entry research/holdout/decision_A.json (sha256), written before any other holdout result",
           "决策记录 research/holdout/decision_A.json（sha256），在任何其他留出期结果之前写入"), DECISION_SHA],
    ], widths=[5.4, 11.6], size=8, mono={1},
        caption=t("Fingerprints that make the result checkable", "使结果可核验的指纹"),
        source=t("provenance/HOLDOUT_FREEZE.txt; provenance/trial_log.md. Section 6 gives the command that checks both.",
                 "provenance/HOLDOUT_FREEZE.txt；provenance/trial_log.md。第 6 节给出了核验这两个值的命令。"))

    # ---- 2
    r.h1(t("2. Data, validation method and latency", "2. 数据、验证方法与延迟"))
    r.h2(t("2.1 The data provided", "2.1 提供的数据"))
    r.p(t("The package covers 1,500 addresses in two files. traders.csv holds 129,665 account snapshots from 10 Jul "
          "2025 to 4 Jan 2026, with equity, net deposits and cumulative profit. fills.csv holds 899,330 trades by 1,200 "
          "of those addresses on 325 symbols, from 27 Jul 2025 to the cutoff, each with price, size, fee, realised "
          "profit, the position before the trade and the maker or taker side. Only core perpetuals are copied; spot "
          "and HIP-3 trades are set aside. There are no market prices, funding rates or order books in the package.",
          "数据包在两个文件中覆盖 1,500 个地址。traders.csv 包含 2025 年 7 月 10 日至 2026 年 1 月 4 日的 129,665 条账户"
          "快照，含权益、净入金和累计盈亏。fills.csv 包含其中 1,200 个地址在 325 个交易对上的 899,330 笔成交，时间从 2025 "
          "年 7 月 27 日到截止时点，每笔含价格、数量、手续费、已实现盈亏、成交前持仓以及挂单/吃单方向。只跟单核心永续合约；"
          "现货和 HIP-3 成交不纳入。数据包中没有市场价格、资金费率或订单簿。"))
    r.h2(t("2.2 Data retrieved, and why", "2.2 补充获取的数据及原因"))
    r.table([t("Retrieved", "获取的数据"), t("Why it was needed", "原因")], [
        [t("Binance USD-M 1-minute prices (1,270 monthly files)", "Binance USD-M 1 分钟价格（1,270 个月度文件）"),
         t("Positions must be valued between trades to get hourly equity, drawdown and leverage. Each coin was checked "
           "against Hyperliquid's prints; 163 pass, the rest are valued daily and not copied.",
           "需要在两次成交之间为持仓估值，才能得到逐小时的权益、回撤和杠杆。每个币种都与 Hyperliquid 自身的成交价做了核对；"
           "163 个通过，其余按日估值且不跟单。")],
        [t("Binance trade-by-trade data for BTC, ETH, HYPE, SOL, BNB, AAVE and EIGEN from 8 Sep 2025",
           "Binance 逐笔成交数据：BTC、ETH、HYPE、SOL、BNB、AAVE 和 EIGEN，自 2025 年 9 月 8 日起"),
         t("Millisecond prices measure the price move during our copy delay, a cost the leader never pays. For other "
           "coins it is estimated from the leaders' own split orders.",
           "毫秒级价格用于测量跟单延迟期间的价格变动，这是交易员本人不承担的成本。其他币种则用交易员自身拆单的数据来估计。")],
        [t("Hyperliquid hourly funding and 4-hour candles", "Hyperliquid 逐小时资金费率和 4 小时 K 线"),
         t("Funding is part of every book's profit; volume and volatility set the market-impact cost and the 0.5% "
           "participation cap.", "资金费计入每个账本的盈亏；成交量和波动率决定市场冲击成本和 0.5% 的成交量参与上限。")],
    ], widths=[6.0, 11.0], size=8.5, source=t("data/reference/, with manifests and checksums",
                                              "data/reference/，附清单和校验和"))
    r.h2(t("2.3 Books built from the data", "2.3 基于数据构建的账本"))
    r.p(t("Two books were built for every address with usable data. The **leader book** rebuilds the trader's "
          "positions from the fills and values them hourly with the reference prices and actual funding. It matches "
          "the reported account value within 1% on about 98% of intervals and gives a clean history of return, "
          "drawdown and leverage even where transfers move the snapshots; the screening rules in section 3 read it. "
          "The **follower book** simulates our own copy: the trader's positions scaled to our capital, entered after "
          "the measured delay, paying the 4.5 bp taker fee, half the spread, market impact and the price move during "
          "the delay, in tradable coins only and within the limits of section 4, under four cost scenarios. It is what "
          "we would actually earn: a copier trades later than the leader, at worse prices and always as a taker, so "
          "the leader's profit is out of reach. Every performance test in this work uses the follower book.",
          "对每个数据可用的地址构建两个账本。**交易员账本**根据成交记录重建交易员的持仓，并用参考价格和实际资金费逐小时"
          "估值。它与账户报告的权益在约 98% 的区间内误差不超过 1%，即使快照受到转账影响，也能给出干净的收益、回撤和杠杆"
          "历史；第 3 节的筛选规则读取的就是这个账本。**跟单账本**模拟我们自己的跟单：按我们的资金缩放交易员的持仓，在"
          "实测延迟之后入场，支付 4.5 bp 的吃单手续费、一半价差、市场冲击以及延迟期间的价格变动，只交易可交易币种，遵守"
          "第 4 节的限额，并在四种成本情景下运行。这才是我们实际能赚到的：跟单者比交易员晚交易、价格更差、而且总是吃单，"
          "所以交易员的利润是拿不到的。本项目所有的绩效检验都基于跟单账本。"))
    r.h2(t("2.4 Latency", "2.4 延迟"))
    r.p(t("The copy delay runs from the trader's fill to the acknowledgement of our order. Hyperliquid's public fill "
          "feed, recorded from a home connection, delivered 284 fills with a median delay of 392 ms. Our own orders "
          "cannot be timed on Hyperliquid without trading, so the order leg uses a Binance futures demo account: "
          "354 ms median, 2.8 s at the 99th percentile. With a 250 ms wait to group fills and about 120 ms of "
          "computation, the total is about 1.2 s at the median and 4.4 s at the 99th percentile. The simulations use "
          "1 s (optimistic), 1.2 s (base), 5 s (stress, with crash-period price moves and three times the spread and "
          "impact) and 60 s as a severe check for the 2 to 17 s disconnects seen in the recordings. Between 1 and 60 s "
          "the result barely changes, because fees, spread and impact make up nearly all of the cost.",
          "跟单延迟是指从交易员成交到我们的订单被确认之间的时间。在家用网络下记录的 Hyperliquid 公开成交推送中，284 笔"
          "成交的中位延迟为 392 毫秒。不在 Hyperliquid 上实际交易就无法测量我们自己订单的耗时，因此下单环节采用 Binance "
          "合约模拟账户的数据：中位数 354 毫秒，第 99 百分位 2.8 秒。加上用于合并同一交易员多笔成交的 250 毫秒等待和约 "
          "120 毫秒的计算，总延迟的中位数约为 1.2 秒，第 99 百分位约为 4.4 秒。模拟采用 1 秒（乐观）、1.2 秒（基准）、"
          "5 秒（压力，配合暴跌期的价格变动以及三倍的价差和冲击），并以 60 秒作为严重情景，覆盖记录中出现的 2 至 17 秒"
          "断线。延迟在 1 到 60 秒之间时结果几乎不变，因为手续费、价差和冲击几乎构成了全部成本。"))
    r.h2(t("2.5 Data split and validation", "2.5 数据划分与验证"))
    r.p(t("The research is walk-forward. At five decision dates (8 Oct, 22 Oct, 5 Nov, 19 Nov and 3 Dec 2025) the "
          "whole pipeline is rerun on the data before that date, and the next 14 days test what it chose; cost "
          "parameters use only data before 3 Dec, without the 10-11 Oct crash. The last 32 days were the holdout. "
          "Nothing was computed on them during development, and the code, rules and settings were frozen with a hash "
          "and the decision conditions written down before they were opened, once. The final selection uses the data "
          "to 4 Jan 2026 00:00 UTC.",
          "研究采用滚动前推（walk-forward）方式。在五个决策日（2025 年 10 月 8 日、10 月 22 日、11 月 5 日、11 月 19 日"
          "和 12 月 3 日），仅用该日期之前的数据重新运行整个流程，再用之后 14 天检验其选择；成本参数只使用 12 月 3 日之前"
          "的数据，并剔除 10 月 10–11 日的暴跌。最后 32 天为留出期，开发期间从未在其上计算任何结果；在打开之前，代码、"
          "规则和配置已用哈希冻结，决策条件也已写下，之后只打开过一次。最终筛选使用截至 2026 年 1 月 4 日 00:00 UTC 的数据。"))
    r.figure(figs["timeline"], t("Training, the four development tests, the holdout and the cutoff.",
                                 "训练期、四个开发测试窗口、留出期与截止时点。"), width_cm=11.5)

    # ---- 3
    r.h1(t("3. Selecting the addresses", "3. 地址筛选"))
    r.p(t("Selection has two steps. The first screens each trader on their own record with fixed rules. The second "
          "judges the survivors on what our copy of them would have earned. No rule rewards high past returns, and "
          "the thresholds were set on development data before the results they affect were computed. Figure 3 shows "
          "how many addresses remain after each stage at the final selection on 4 Jan 2026.",
          "筛选分两步。第一步用固定规则审查每位交易员自身的记录；第二步根据我们跟单他们本可获得的收益，评估剩下的交易员。"
          "没有任何规则奖励过去的高收益，所有阈值都在其影响的结果计算之前，就已在开发数据上确定。图 3 显示了 2026 年 1 月 "
          "4 日最终筛选中每个阶段之后剩余的地址数。"))
    r.figure(figs["funnel"], t("Addresses remaining after each stage at the 4 Jan 2026 selection.",
                               "2026 年 1 月 4 日筛选中每个阶段之后剩余的地址数。"),
             "research/cutoff/selection_v2/funnel_v2.csv")
    r.h2(t("3.1 Rule-based screening", "3.1 基于规则的筛选"))
    r.p(t("An address first needs a data grade of A or B: its trades are complete, its reported profit reconciles "
          "with its deposits, and it has enough usable days. 423 of the 1,471 addresses pass. Each must then pass "
          "every rule in Table 4, measured on its leader book; a rule that cannot be measured counts as a failure. "
          "22 addresses pass them all. Most failures are for thin evidence (186 addresses with fewer than 20 completed "
          "trades), books that do not reconcile (45), exposure to unpriced coins (44) and inactivity (35).",
          "地址首先需要 A 或 B 的数据等级：成交记录完整，报告的盈亏与入金能够对账，且有足够的可用天数。1,471 个地址中有 "
          "423 个通过。随后每个地址必须通过表 4 中的全部规则，均在其交易员账本上测量；无法测量的规则按不通过处理。22 个"
          "地址全部通过。最常见的失败原因是证据不足（186 个地址完成的交易少于 20 笔）、账本无法对账（45）、在无可靠价格"
          "币种上的敞口过大（44）以及不活跃（35）。"))
    r.table([t("Group", "类别"), t("Rule", "规则"), t("Pass if", "通过条件")], [
        [t("Integrity", "完整性"), t("Reported profit matches the rebuilt book", "报告盈亏与重建账本一致"),
         t("most intervals within 1%", "大多数区间误差在 1% 以内")],
        ["", t("Account and rebuilt book move together", "账户与重建账本同步变动"), t("stable relationship", "关系稳定")],
        ["", t("Exposure in coins without a reliable price", "无可靠价格币种上的敞口"), t("at most 5%", "不超过 5%")],
        [t("Evidence", "证据"), t("Completed round-trip trades", "完成的往返交易"), t("at least 20", "至少 20 笔")],
        ["", t("Most recent trade", "最近一笔交易"), t("within 14 days", "14 天以内")],
        ["", t("History", "历史长度"), t("90 days, with 60 usable return days", "90 天，其中 60 个可用收益日")],
        [t("Risk", "风险"), t("Worst drawdown, hourly and at the worst price inside each 4-hour bar",
                              "最大回撤（逐小时，以及每根 4 小时 K 线内的最差价格）"), t("better than -50%", "优于 -50%")],
        ["", t("Worst day; worst three days", "最差单日；最差三日"), t("better than -25%; -35%", "优于 -25%；-35%")],
        ["", t("Liquidations", "强平"), t("none", "无")],
        ["", t("Profit from the top 1% of trades", "前 1% 交易贡献的利润"),
         t("at most half of all profit", "不超过全部利润的一半")],
        ["", t("Typical leverage (95th percentile)", "典型杠杆（第 95 百分位）"), t("at most 10x", "不超过 10 倍")],
        ["", t("Distance from liquidation", "距强平距离"), t("at least 5%", "至少 5%")],
        ["", t("Joint 24-hour market shock", "24 小时联合市场冲击"),
         t("account survives with margin left", "账户仍有剩余保证金")],
    ], widths=[2.4, 9.0, 5.6], size=8.5, first_bold=True,
        caption=t("Rules on the trader's own record", "交易员自身记录上的规则"),
        source=t("decision/full_selection_criteria.md section 2; config/decision_context.yaml",
                 "decision/full_selection_criteria.md 第 2 节；config/decision_context.yaml"))
    r.h2(t("3.2 Performance on the follower copy", "3.2 跟单表现"))
    r.p(t("The remaining traders are judged on their follower book, in three stages.",
          "剩余交易员按其跟单账本分三个阶段评估。"))
    r.p(t("**Copyability.** The trader must keep at least 90% of their exposure in the 27 coins we can trade at the "
          "cutoff (coins with a reliable price, enough liquidity and a typical cost under 25 bp per trade); hold an "
          "account between 5,000 and 2,000,000 USDC; leave a copy that is still profitable at our 1.2 s delay; keep "
          "the same market direction once the untradable coins are dropped; and not be the weaker of two accounts that "
          "copy each other. 5 addresses pass.",
          "**可跟单性。** 交易员至少 90% 的敞口须在截止时点我们能交易的 27 个币种中（价格可靠、流动性足够、典型成本低于"
          "每笔 25 bp）；账户规模在 5,000 至 2,000,000 USDC 之间；在 1.2 秒延迟下跟单仍然盈利；去掉不可交易币种后市场"
          "方向不变；且不是两个互相跟单账户中较弱的一方。5 个地址通过。"))
    r.p(t("**Skill.** For each copy we take its daily profit after costs, remove what its exposure to BTC, ETH and "
          "altcoins would have earned, remove funding (a premium for holding a position, not trading skill) and divide "
          "by the capital exposed. Over at least 20 active days, spread across 4 weeks or more, this gives a skill "
          "estimate α in bp per day, with its error. The estimate is then pulled toward the average of all traders by "
          "an amount that depends on how much traders really differ, and the trader is placed in a category: E2 when "
          "skill is positive with at least 80% probability and survives removing the best week, E1 when the estimate "
          "is positive but the evidence weak, E0 when there are too few active days, and E- when it is negative. E1 "
          "and E2 pass. 4 addresses pass, all of them E1.",
          "**技能。** 对每个跟单账本，取其扣除成本后的每日盈亏，减去其对 BTC、ETH 和山寨币的敞口本应获得的收益，再扣除"
          "资金费（资金费是持仓溢价，不是交易技能），然后除以所占用的资金。在至少 20 个活跃日、跨度至少 4 周的数据上，"
          "得到以每日 bp 计的技能估计 α 及其误差。随后按交易员之间真实差异的大小，把每个估计值向全体交易员的平均值收缩，"
          "并把交易员归入以下类别：E2 表示技能为正的概率至少为 80%，且去掉最佳一周后仍为正；E1 表示估计为正但证据较弱；"
          "E0 表示活跃天数不足；E- 表示估计为负。E1 和 E2 通过。4 个地址通过，全部为 E1。"))
    r.p(t("**Duplicates.** Two traders whose copies hold the same positions most of the time count once. None was "
          "removed, so 4 addresses are handed off.",
          "**重复。** 两位交易员的跟单账本大部分时间持仓相同时只算一个。没有地址因此被剔除，所以共移交 4 个地址。"))
    r.h2(t("3.3 Ranking was tested and not used", "3.3 排序经过检验但未采用"))
    r.p(t("The qualified traders could also be ranked and weighted. Before using a ranking we tested whether ordering "
          "all traders by their skill estimate predicted their skill over the next 14 days. The rule, fixed in "
          "advance, needed an average rank correlation of at least +0.05 and a positive value at three of the four "
          "test dates. The result was -0.03 on average and positive only once, so the ranking is not used and the "
          "sleeves are equal. The holdout gave -0.085. The reason is visible in the numbers: the spread of true skill "
          "between traders was 0 to 9 bp per day, while each trader's own estimate carries an error of 21 to 32 bp "
          "per day.",
          "合格的交易员还可以排序并加权。在采用任何排序之前，我们检验了按技能估计对所有交易员排序，能否预测他们在之后 14 "
          "天的技能。事先确定的规则要求平均排序相关系数至少为 +0.05，且四个测试日中至少三个为正。结果平均为 -0.03，只有一次"
          "为正，因此不采用排序，各子仓等权。留出期的结果为 -0.085。原因从数字中就能看出：交易员之间真实技能的离散度为每天 "
          "0 至 9 bp，而每位交易员自身估计的误差为每天 21 至 32 bp。"))
    r.figure(figs["ic"], t("Rank correlation between the skill estimate and the next window's skill, at each test "
                           "date and on the holdout.", "各测试日及留出期中，技能估计与下一窗口技能之间的排序相关系数。"),
             t("decision/phase-4-v2-results.md; research/holdout/window_report/h5_cross_section.csv",
               "decision/phase-4-v2-results.md；research/holdout/window_report/h5_cross_section.csv"))
    r.h2(t("3.4 The addresses handed off", "3.4 移交的地址"))
    r.table([t("Address", "地址"), t("Grade", "等级"), t("Skill estimate, bp/day (error)", "技能估计，bp/天（误差）"),
             t("Main exposure", "主要敞口"), t("Trader's median equity (USDC)", "交易员权益中位数（USDC）")], [
        ["0x2cd9…946e", "A", "121.8 (82.3)", t("HYPE, ETH, AAVE long", "HYPE、ETH、AAVE 做多"), "27,131"],
        ["0x971f…77fa", "A", "65.8 (31.2)", t("BNB, BTC long", "BNB、BTC 做多"), "7,719"],
        ["0xe65c…8428", "B", "6.2 (11.8)", t("ETH short", "ETH 做空"), "6,066"],
        ["0x3a12…5d69", "A", "0.6 (6.0)", t("BTC long", "BTC 做多"), "1,683,030"],
    ], widths=[2.9, 1.4, 4.4, 4.2, 4.1], size=8.5, first_bold=True,
        caption=t("The hand-off at 4 Jan 2026, all E1", "2026 年 1 月 4 日移交的地址，均为 E1"),
        source=t("research/cutoff/selection_v2/origin=2026-01-04/eligible.parquet; decision-memo.md section 1.2",
                 "research/cutoff/selection_v2/origin=2026-01-04/eligible.parquet；decision-memo.md 第 1.2 节"))
    r.p(t("The errors are wide: 122 ± 82 bp per day is still consistent with no skill, which is why these traders "
          "receive measurement capital only. The list also changes from date to date. It held 3, 2, 1, 1 and 1 "
          "addresses at the five development dates; at 3 Dec, the start of the holdout, it was 0x2cd9 alone. Every "
          "address has a row in research/cutoff/deliverables/trader_decisions.csv with its grade, category and the "
          "first rule it fails.",
          "误差很大：每天 122 ± 82 bp 仍与没有技能相容，这就是这些交易员只获得测量资金的原因。名单在不同日期之间也会变化："
          "五个开发决策日分别为 3、2、1、1、1 个地址；在留出期开始的 12 月 3 日，只有 0x2cd9 一个。每个地址在 "
          "research/cutoff/deliverables/trader_decisions.csv 中都有一行，列出其等级、类别和第一条未通过的规则。"))

    # ---- 4
    r.h1(t("4. Risk management and portfolio rules", "4. 风险管理与组合规则"))
    r.p(t("The live book holds two equal sleeves of 2,500 USDC. Each sleeve holds its trader's positions scaled by the "
          "trader's equity at the last 14-day review, and is never larger than the trader. The scale is fixed between "
          "reviews so that the copy does not add risk on its own when a trader loses money. The sleeves are equal "
          "because the ranking does not predict. When both sleeves trade the same coin, only the net order is sent, "
          "which saves fees. When a limit binds, the whole sleeve shrinks rather than one coin, so the copy keeps the "
          "shape of the book that was tested.",
          "实盘账本包含两个各 2,500 USDC 的等额子仓。每个子仓按交易员在最近一次 14 天复核时的权益缩放其持仓，且不会大于"
          "交易员本身。两次复核之间缩放比例固定，这样交易员亏钱时，跟单不会自动加大风险。子仓等权，是因为排序没有预测力。"
          "两个子仓交易同一币种时只发送净额订单，以节省手续费。某项限额触发时，整个子仓等比例缩小，而不是只缩小某一个币种，"
          "从而保持经过检验的账本结构。"))
    r.table([t("Limit", "限额"), t("Rule", "规则"), t("Why", "原因")], [
        [t("Loss budget", "亏损预算"), t("750 USDC for both sleeves; at 750 everything is closed and the scheme returns "
                                       "to paper", "两个子仓共 750 USDC；达到 750 时全部平仓并回到模拟盘"),
         t("Caps the cost of the measurement at 0.75% of the capital", "把测量成本限制在资金的 0.75%")],
        [t("Stress budget", "压力预算"), t("Loss in a joint 24-hour shock plus exit cost fits in the budget left; checked "
                                         "at every update and hourly",
                                         "24 小时联合冲击下的亏损加平仓成本必须在剩余预算之内；每次更新及每小时检查"),
         t("No single market move can exceed the budget", "任何单次市场波动都不能超出预算")],
        [t("Gross exposure", "总敞口"), t("At most 1.5 times the sleeve", "不超过子仓的 1.5 倍"),
         t("Caps our leverage whatever the trader uses", "无论交易员用多少杠杆，都限制我们的杠杆")],
        [t("Drawdown", "回撤"), t("Sleeve: -10% reduce only, -15% close and pause. Book: -5% halve new risk, -10% "
                                "reduce only, -15% close and stop",
                                "子仓：-10% 只减仓，-15% 平仓并暂停。账本：-5% 新增风险减半，-10% 只减仓，-15% 全部平仓并停止"),
         t("Cuts losses well before the budget is spent", "在预算用完之前就止损")],
        [t("Order size", "订单规模"), t("At most 0.5% of the coin's recent 4-hour volume; at least 10 USDC",
                                      "不超过该币种最近 4 小时成交量的 0.5%；至少 10 USDC"),
         t("Keeps market impact small; 10 USDC is the venue minimum", "控制市场冲击；10 USDC 是交易所的最小下单额")],
    ], widths=[2.7, 8.3, 6.0], size=8.5, first_bold=True, caption=t("Limits on the live book", "实盘账本的限额"),
        source=t("decision/deployment-protocol.md section 4; config/risk.yaml",
                 "decision/deployment-protocol.md 第 4 节；config/risk.yaml"))
    r.p(t("In the holdout the limits cut the stress drawdown of the two-sleeve book from 1,562 to 720 USDC, at a cost of "
          "3.9 points of return in base costs (section 5). Each order also carries a limit price, but it is set wide at "
          "the stress scenario's extreme and rarely binds; the budgets above do the protecting.",
          "在留出期中，这些限额把两子仓账本在压力情景下的回撤从 1,562 USDC 降到 720 USDC，代价是基准成本下少了 3.9 个"
          "百分点的收益（第 5 节）。每笔订单还带有一个限价，但它设在压力情景的极端值，很少触发；真正起保护作用的是上述预算。"))
    r.h3(t("Entry", "入场"))
    r.p(t("A trader enters only through the selection of section 3 at a 14-day review, after a loss check of a 2,500 "
          "USDC sleeve on recent data. Before the first live order the limits must be signed off, the pipeline rerun "
          "on current data and the venue's current rules checked. Capital grows to the next stage only under the three "
          "conditions in section 1, never because of profit.",
          "交易员只能在 14 天复核时通过第 3 节的筛选进入，并且要先在最近的数据上对一个 2,500 USDC 子仓做亏损检查。第一笔"
          "实盘订单之前，必须签署确认限额、用当前数据重新运行整个流程，并核对交易所当前的规则。资金只有在第 1 节所述的三个"
          "条件下才会进入下一阶段，绝不因盈利而增加。"))
    r.h3(t("Pause and exit", "暂停与退出"))
    r.p(t("Triggers watch for a change in the trader or in our ability to copy them:",
          "触发器监控交易员本身或我们跟单能力的变化："))
    trader, ours = t("Trader", "交易员"), t("Our copy", "我们的跟单")
    r.table([t("Watched", "监控对象"), t("Trigger", "触发条件"), t("Action", "动作")], [
        [trader, t("Drawdown beyond 1.5 times their worst; leverage above twice their usual peak; equity below 70% of "
                   "the reference; half the equity withdrawn in 24 hours",
                   "回撤超过其历史最差的 1.5 倍；杠杆超过其通常峰值的两倍；权益低于参考值的 70%；24 小时内提取一半权益"),
         t("Reduce only", "只减仓")],
        [trader, t("Liquidation or forced deleveraging", "被强平或被自动减仓"), t("Close and pause", "平仓并暂停")],
        [trader, t("More than 10% of exposure in untradable coins for 7 days; no trade for 14 days",
                   "7 天内超过 10% 的敞口在不可交易币种上；14 天无交易"),
         t("Reduce only; exit at the review", "只减仓；复核时退出")],
        [ours, t("Median cost per trade above the stress scenario over 14 days", "14 天内每笔交易成本中位数高于压力情景"),
         t("Reduce only", "只减仓")],
        [ours, t("Feed stale for 60 seconds, or positions that disagree", "行情推送 60 秒未更新，或持仓不一致"),
         t("Freeze increases and resynchronise", "冻结加仓并重新同步")],
    ], widths=[2.2, 10.6, 4.2], size=8.5, first_bold=True, caption=t("Pause triggers", "暂停触发器"),
        source=t("decision/deployment-protocol.md section 5", "decision/deployment-protocol.md 第 5 节"))
    r.p(t("Only a person, at a review, can lift a restriction. A sleeve exits at a review when it fails a selection "
          "rule, falls to E0 or E-, or was paused the whole period. The scheme returns to paper at the loss budget, or "
          "when real costs exceed the stress scenario at two reviews in a row. The measurement ends after at least 4 "
          "weeks and 200 orders, or after 12 weeks.",
          "只有人工在复核时才能解除限制。子仓在复核时如未通过某条筛选规则、降为 E0 或 E-，或整期都处于暂停状态，则退出。"
          "达到亏损预算，或真实成本连续两次复核都高于压力情景时，整个方案回到模拟盘。测量在至少 4 周且 200 笔订单之后结束，"
          "最长 12 周。"))

    # ---- 5
    r.h1(t("5. Holdout results and the decision", "5. 留出测试结果与决策"))
    r.h2(t("5.1 What was tested", "5.1 测试内容"))
    r.p(t("The selection made on 3 Dec 2025 was frozen and run over the 32-day holdout in all four cost scenarios. "
          "Three books were run: the two-sleeve paper scheme with the limits (0x2cd9, the 3 Dec selection, and 0x971f, "
          "named in advance as the second sleeve, at 10,000 USDC each), the same pair without limits, and 0x2cd9 alone "
          "as a 2,500 USDC gray sleeve. The three addresses that joined at the 4 Jan selection were then run alone as "
          "gray sleeves over the same days. Their selection used data up to 4 Jan, so for them the run is a loss check, "
          "not an out-of-sample test.",
          "2025 年 12 月 3 日的筛选结果被冻结，并在 32 天的留出期内以全部四种成本情景运行。共运行三个账本：带限额的两子仓"
          "模拟方案（0x2cd9，即 12 月 3 日的筛选结果；以及事先指定为第二子仓的 0x971f；各 10,000 USDC）、不带限额的同一"
          "组合，以及 0x2cd9 单独作为 2,500 USDC 的灰度子仓。随后，在 1 月 4 日筛选中新加入的三个地址也各自单独作为灰度"
          "子仓在同一期间运行。它们的筛选使用了截至 1 月 4 日的数据，因此对它们而言这只是亏损检查，而不是样本外检验。"))
    r.h2(t("5.2 Results", "5.2 结果"))
    r.figure(figs["holdout_nav"], t("The two-sleeve book (0x2cd9 and 0x971f, 20,000 USDC) over the holdout, with and "
                                    "without the limits.",
                                    "两子仓账本（0x2cd9 与 0x971f，20,000 USDC）在留出期内有无限额的表现。"),
             t("research/holdout/portfolio/run=A/ (hourly tables)", "research/holdout/portfolio/run=A/（逐小时表）"))
    r.table([t("Book", "账本"), t("Return, base", "收益（基准）"), t("Return, stress", "收益（压力）"),
             t("Worst drawdown, base / stress (USDC)", "最大回撤（基准 / 压力，USDC）")], [
        [t("Two sleeves with the limits (20,000)", "带限额的两子仓（20,000）"), "+0.78%", "-2.58%", "277 / 720"],
        [t("Same two sleeves without limits (20,000)", "不带限额的同一组合（20,000）"), "+4.69%", "-5.89%", "503 / 1,562"],
        [t("Gray sleeve 0x2cd9 (2,500)", "灰度子仓 0x2cd9（2,500）"), "+4.60%", "-3.19%", "121 / 181"],
    ], widths=[6.6, 2.8, 2.8, 4.8], size=8.5, first_bold=True,
        caption=t("Holdout returns over 32 days", "留出期 32 天的收益"),
        source=t("research/holdout/window_report/h2_risk.csv and h4_returns.csv",
                 "research/holdout/window_report/h2_risk.csv 和 h4_returns.csv"))
    r.p(t("Returns are thin. In base costs the limited book made 155 USDC on 20,000; under stress costs every book lost "
          "money. Each of the four basket addresses, run alone at 2,500 USDC, stayed far inside the 750 USDC budget "
          "(Figure 6; their returns are in Table 2).",
          "收益很薄。在基准成本下，带限额的账本在 20,000 上赚了 155 USDC；在压力成本下所有账本都亏损。组合中的四个地址各自"
          "单独以 2,500 USDC 运行，都远在 750 USDC 预算之内（图 6；其收益见表 2）。"))
    r.figure(figs["sleeves"], t("Worst loss of each basket address alone at 2,500 USDC on the holdout.",
                                "组合中每个地址单独以 2,500 USDC 在留出期中的最大亏损。"),
             "research/holdout/window_report/h2_risk.csv")
    r.p(t("Costs stayed inside their limits. The median cost per trade was below its development limit for every coin "
          "with at least 30 orders (Figure 7). These are simulated fills compared with the simulated cost model. Two "
          "further runs rebuilt each order's cost from the market data at its own time and changed no result; the "
          "frozen model was 1 to 2 bp per trade more conservative than the rebuild.",
          "成本保持在限额之内。对每个至少有 30 笔订单的币种，每笔交易成本的中位数都低于其开发期限额（图 7）。这里比较的是"
          "模拟成交与模拟成本模型。另外两次运行按每笔订单当时的市场数据重建成本，没有改变任何结果；冻结的模型比重建结果"
          "每笔保守 1 至 2 bp。"))
    r.figure(figs["costs"], t("Median cost per trade side on the holdout against the limit set in development.",
                              "留出期每边交易成本中位数与开发期设定的限额对比。"),
             "research/holdout/window_report/h3_costs.csv")
    r.p(t("Across all measured traders, the groups the selection prefers did no better on the holdout (Figure 8). "
          "Unmeasured E0 traders did best, E1 below them, and only the break-even rule pointed the right way.",
          "在所有可测量的交易员中，筛选偏好的组别在留出期中并没有表现更好（图 8）。未测量的 E0 交易员表现最好，E1 次之，"
          "只有盈亏平衡规则指向了正确的方向。"))
    r.figure(figs["cross"], t("Average skill on the holdout by group, all measured A/B addresses at 3 Dec. Teal marks "
                              "the group the selection prefers.",
                              "留出期内按组别的平均技能，12 月 3 日全部可测量的 A/B 地址。青绿色为筛选偏好的组别。"),
             "research/holdout/window_report/h5_cross_section.csv")
    r.h2(t("5.3 The decision", "5.3 决策"))
    r.p(t("The decision rule was written before the holdout was opened. A full GO had already been ruled out, because "
          "development found no evidence of persistent skill. The two possible outcomes were CONDITIONAL GO, which "
          "allows only the capped gray measurement and needs all five conditions in Table 9, or NO-GO, which keeps "
          "everything on paper. The verdict was written to research/holdout/decision_A.json and fingerprinted before "
          "any other holdout result was computed.",
          "决策规则在打开留出期之前就已写下。由于开发期没有发现可持续技能的证据，完全通过（GO）已事先排除。可能的结果只有"
          "两个：CONDITIONAL GO（有条件通过），只允许有上限的灰度测量，需要表 9 中五个条件全部满足；或 NO-GO（不通过），"
          "一切保持在模拟盘。裁定结果在计算任何其他留出期结果之前，就已写入 research/holdout/decision_A.json 并生成指纹。"))
    ok = t("pass", "通过")
    r.table(["", t("Condition", "条件"), t("Measured", "测量值"), t("Result", "结果")], [
        ["D1", t("The engine works on unseen data", "引擎在未见过的数据上正常运行"),
         t("24 runs complete, no faults", "24 次运行全部完成，无故障"), ok],
        ["D2a", t("The paper scheme's loss stays within 3,300 USDC, and every breached limit acts",
                  "模拟方案的亏损不超过 3,300 USDC，且每个被触及的限额都执行了相应动作"),
         t("Worst drawdown 277 (base) / 720 (stress)", "最大回撤 277（基准）/ 720（压力）"), ok],
        ["D2b", t("Each gray sleeve's loss stays within 750 USDC, and the stress budget is never breached",
                  "每个灰度子仓的亏损不超过 750 USDC，且从未突破压力预算"),
         t("Worst 113 (0x2cd9, stress); no breach", "最差 113（0x2cd9，压力）；无突破"), ok],
        ["D3", t("Median cost per trade stays under its development limit", "每笔交易成本中位数低于其开发期限额"),
         t("BNB, BTC, ETH, HYPE all under", "BNB、BTC、ETH、HYPE 均低于限额"), ok],
        ["D4", t("No strong evidence against the ranking", "没有反对排序的强证据"),
         t("-0.085, above the -0.14 guard", "-0.085，高于 -0.14 的警戒线"), ok],
        ["D5", t("The selection at the cutoff hands off at least one address", "截止时点的筛选至少移交一个地址"),
         t("4 addresses", "4 个地址"), ok],
    ], widths=[1.1, 7.0, 6.7, 2.2], size=8.5, first_bold=True,
        caption=t(f"Decision conditions: all pass, so the decision is {verdict}",
                  f"决策条件：全部通过，因此决策为 {verdict}"),
        source=t(f"research/holdout/decision_A.json (sha256 {DECISION_SHA[:8]}…{DECISION_SHA[-4:]}); decision/adr/0093",
                 f"research/holdout/decision_A.json（sha256 {DECISION_SHA[:8]}…{DECISION_SHA[-4:]}）；decision/adr/0093"))
    r.p(t(f"{verdict} means the engine, the limits and the cost model behaved as designed on data nobody had seen. "
          "It is not evidence that the traders have an edge: D4 only checks that the evidence against the ranking is "
          "not strong.",
          f"{verdict} 表示引擎、限额和成本模型在无人见过的数据上按设计运行。它并不证明这些交易员具有优势：D4 只检查反对"
          "排序的证据是否不强。"))
    r.h2(t("5.4 The basket at 4 Jan 2026", "5.4 2026 年 1 月 4 日的组合"))
    r.p(t("The 4 Jan selection handed off 0x2cd9, 0x971f, 0x3a12 and 0xe65c, and the gray envelope has room for two "
          "live sleeves. 0x2cd9 is live as the address selected before the holdout. For the second, the frozen code "
          "ordered by skill estimate (0x971f) while a frozen decision record ordered by address (0x3a12). 0x971f was "
          "chosen because the gray run exists to measure fills: on the holdout it placed 16 orders a week against 3.3, "
          "with less exposure (200 against 498 USDC) and a smaller worst loss (22 against 42 USDC in base). Its holdout "
          "return was lower than 0x3a12's and played no part. The choice is recorded in ADR-0101 and applies to this "
          "cutoff only. The final basket is the one in Table 1: 0x2cd9 and 0x971f live at 2,500 USDC each, 0x3a12 and "
          "0xe65c on paper, and 95,000 USDC in reserve.",
          "1 月 4 日的筛选移交了 0x2cd9、0x971f、0x3a12 和 0xe65c，而灰度额度只容纳两个实盘子仓。0x2cd9 作为留出期之前"
          "已入选的地址进入实盘。对于第二个子仓，冻结的代码按技能估计排序（0x971f），而一份冻结的决策记录按地址顺序排序"
          "（0x3a12）。选择 0x971f 是因为灰度运行的目的就是测量成交：在留出期内它每周下单 16 笔，而 0x3a12 只有 3.3 笔；"
          "它的敞口更小（200 对 498 USDC），最大亏损也更小（基准下 22 对 42 USDC）。它的留出期收益低于 0x3a12，但这不在"
          "考虑之列。该选择记录在 ADR-0101 中，仅适用于本次截止。最终组合即表 1 所示：0x2cd9 和 0x971f 各以 2,500 USDC "
          "实盘，0x3a12 和 0xe65c 为模拟盘，95,000 USDC 为储备金。"))
    r.h2(t("5.5 What the result does not show", "5.5 结果不能说明什么"))
    r.p(t("The holdout tests the machinery, not the traders. All fills are simulated, so real costs are still "
          "unmeasured. The two live sleeves were tested one at a time, never as one book sharing a budget. 0x2cd9 is "
          "concentrated in HYPE, so one coin can move most of the live book. A trader's positions in other accounts "
          "would make the copy wrong without showing in the data. These are the questions the gray measurement and its "
          "14-day reviews are there to answer.",
          "留出期检验的是系统机制，而不是交易员。所有成交都是模拟的，真实成本仍未测量。两个实盘子仓是分别检验的，从未作为"
          "共用预算的一个账本检验过。0x2cd9 集中于 HYPE，单一币种就可能主导大部分实盘账本。交易员在其他账户中的持仓会使"
          "跟单出错，而数据中看不出来。这些正是灰度测量及其 14 天复核要回答的问题。"))

    # ---- 6
    r.h1(t("6. Reading the repository", "6. 如何阅读本仓库"))
    r.p(t("Start with README.md at the top of the package: it gives the decision, the reading order and the rerun "
          "commands. The main documents, in reading order:",
          "从数据包顶层的 README.md 开始：其中给出了决策、阅读顺序和重新运行的命令。主要文件按阅读顺序如下："))
    r.table(["", t("Where", "位置"), t("What it holds", "内容")], [
        ["1", t("decision/decision-memo.md (Chinese: decision-memo.zh-CN.md)", "decision/decision-memo.zh-CN.md（英文原文："
                                                                            "decision-memo.md）"),
         t("The full answer to each item of the written test, with the evidence and its limits",
           "逐项完整回答笔试题，附证据及其局限")],
        ["2", "decision/deployment-protocol.md", t("The operating rules and every parameter", "运行规则及全部参数")],
        ["3", "research/cutoff/deliverables/", t("trader_decisions.csv (every address) and target_allocations.csv "
                                                 "(the books and capital)",
                                                 "trader_decisions.csv（每个地址）和 target_allocations.csv（账本与资金）")],
        ["4", "research/holdout/", t("The decision entry, the window report and the rebuilt-cost runs",
                                     "决策记录、窗口报告和成本重建运行")],
        ["5", "decision/adr/README.md", t("Every decision, in the order it was made", "所有决策，按做出的先后顺序")],
        ["6", "provenance/trial_log.md", t("Every run, logged before its result", "所有运行，均在得到结果之前记录")],
    ], widths=[0.8, 7.2, 9.0], size=8.5)
    r.p(t("To check or rerun everything, from the unzipped folder with uv installed (details in VERIFY.md):",
          "在解压后的文件夹中、安装 uv 之后，用以下命令核验或重新运行全部内容（详见 VERIFY.md）："))
    r.code([
        "uv sync",
        t("uv run python scripts/rerun.py check              # 1 min: checksums, freeze, decision entry, protocol",
          "uv run python scripts/rerun.py check              # 约 1 分钟：校验和、冻结哈希、决策记录、协议参数"),
        t("uv run python scripts/rerun.py fetch              # the public Binance data not shipped (~11 GB)",
          "uv run python scripts/rerun.py fetch              # 下载未随包提供的 Binance 公开数据（约 11 GB）"),
        t("uv run python scripts/rerun.py rebuild            # every development output, compared with the published lists",
          "uv run python scripts/rerun.py rebuild            # 重建全部开发期输出，并与公布的校验清单对比"),
        t("uv run python scripts/rerun.py holdout --confirm  # in a copy: the holdout and the cutoff, compared with the record",
          "uv run python scripts/rerun.py holdout --confirm  # 在副本中：重跑留出期与截止筛选，并与公布记录对比"),
    ])


def build(lang: str) -> list[Path]:
    set_language(lang)
    figs = {
        "timeline": fig_timeline(), "funnel": fig_funnel(), "capital": fig_capital(), "ic": fig_ic(),
        "holdout_nav": fig_holdout_nav(), "sleeves": fig_sleeves(), "costs": fig_costs(),
        "cross": fig_cross_section(),
    }
    r = Report()
    write(r, figs)
    r.save(OUT[lang])
    print(f"wrote {OUT[lang].relative_to(ROOT)} ({OUT[lang].stat().st_size / 1e6:.2f} MB, {r.fig_n} figures, "
          f"{r.tab_n} numbered tables)")
    return list(figs.values())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="build_report", description=__doc__.split("\n\n")[0])
    ap.add_argument("--lang", choices=["en", "zh", "both"], default="both")
    a = ap.parse_args(argv)
    langs = ["en", "zh"] if a.lang == "both" else [a.lang]
    made = [p for lang in langs for p in build(lang)]
    if a.lang == "both":  # figures of earlier layouts
        keep = {p.name for p in made}
        for old in FIG.glob("r*.png"):
            if old.name not in keep:
                old.unlink()
    print(f"figures in {FIG.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
