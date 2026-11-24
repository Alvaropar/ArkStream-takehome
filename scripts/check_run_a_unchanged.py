"""Run A unchanged (ADR-0098 hard constraint, ADR-0099): rerun the P5-5 S*, U* and G* runs on the four development
test windows in the four scenarios with the current engine, and compare every output file byte for byte with
`research/portfolio_replay`, and the summary rows with `pair_summary.csv`. Development data only.

Writes `research/audit/run_a_unchanged.md`; exits 1 on any difference.
Usage: POLARS_MAX_THREADS=8 uv run python scripts/check_run_a_unchanged.py
"""

import sys

sys.path.insert(0, "src")
import json
import tempfile
from pathlib import Path

import polars as pl

from arkstream import phase5_pair as P
from arkstream import portfolio_replay as PR
from arkstream.config import load_context

ROOT = Path(".").resolve()
REF = ROOT / "research/portfolio_replay"


def main() -> int:
    ctx = load_context()
    gray = int(json.loads((REF / "gray_size.json").read_text(encoding="utf-8"))["chosen"])
    lines = ["# Run A unchanged (ADR-0098, ADR-0099)", "",
             "The P5-5 S\\*, U\\* and G\\* runs rerun with the current engine (cost-run hooks off) on the four "
             "development test windows in the four scenarios, compared byte for byte with `research/portfolio_replay`.",
             "", "| Window | Files compared | Identical | Differ |", "| --- | ---: | ---: | --- |"]
    bad = 0
    rows: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="run_a_check_") as tmp:
        out = Path(tmp)
        runner = P.Runner(ctx, out)
        for win in PR.dev_windows(ctx):
            rows += runner.window(win, PR.SCENARIOS, (gray,))
            new = sorted((out / f"origin={win.origin}").rglob("*.*"))
            same, diff = 0, []
            for f in new:
                ref = REF / f.relative_to(out)
                if ref.is_file() and ref.read_bytes() == f.read_bytes():
                    same += 1
                else:
                    diff.append(str(f.relative_to(out)))
            missing = [str(p.relative_to(REF)) for p in sorted((REF / f"origin={win.origin}").rglob("*.*"))
                       if not (out / p.relative_to(REF)).is_file()]
            bad += len(diff) + len(missing)
            lines.append(f"| {win.origin} | {len(new)} | {same} | {'; '.join((diff + missing)[:5]) or 'none'} |")
            print(win.origin, len(new), same, len(diff), len(missing), flush=True)
    summary = pl.DataFrame(rows, infer_schema_length=None)
    ref = pl.read_csv(REF / "pair_summary.csv", try_parse_dates=True)
    cols = [c for c in ref.columns if c in summary.columns]
    key = ["origin", "config", "scenario", "scope"]
    a = summary.select(cols).with_columns(pl.col("origin").cast(pl.Date)).sort(key)
    tmpcsv = Path(tempfile.gettempdir()) / "run_a_check_summary.csv"
    a.write_csv(tmpcsv)
    a = pl.read_csv(tmpcsv, try_parse_dates=True).sort(key)
    b = ref.select(cols).sort(key)
    equal = a.equals(b)
    bad += 0 if equal else 1
    lines += ["", f"- summary rows ({a.height}) equal to `pair_summary.csv` (same columns, written and read back as "
              f"CSV): **{equal}**", "", f"**Result: {'PASS' if bad == 0 else 'FAIL'}**"]
    (ROOT / "research/audit").mkdir(parents=True, exist_ok=True)
    (ROOT / "research/audit/run_a_unchanged.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(lines))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
