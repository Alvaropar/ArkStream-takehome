"""Audit assertions: headline counts must reproduce exactly, so any data change fails loudly."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from arkstream.pipeline import Result


def load_expected(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def check(res: Result, expected: dict[str, Any]) -> list[tuple[str, Any, Any, bool]]:
    rows = []
    for k, v in expected["counts"].items():
        got = res.headline.get(k)
        rows.append((k, v, got, got == v))
    cl = res.tables["copier_clusters"]
    for anchor, members in expected.get("copier_clusters", {}).items():
        a = cl.filter(cl["trader"].str.starts_with(anchor))
        got_members: list[str] = []
        if a.height:
            cid = a["cluster_id"][0]
            got_members = sorted(t[:6] for t in cl.filter(cl["cluster_id"] == cid)["trader"].to_list())
        want = sorted(m[:6] for m in [anchor, *members])
        rows.append((f"copier_cluster[{anchor}]", want, got_members, set(want) <= set(got_members)))
    return rows


def format_rows(rows: list[tuple[str, Any, Any, bool]]) -> str:
    w = max(len(r[0]) for r in rows)
    out = [f"{'check'.ljust(w)}  {'expected':>14}  {'got':>14}  ok"]
    for k, v, g, ok in rows:
        out.append(f"{k.ljust(w)}  {str(v):>14}  {str(g):>14}  {'OK' if ok else 'FAIL'}")
    return "\n".join(out)
