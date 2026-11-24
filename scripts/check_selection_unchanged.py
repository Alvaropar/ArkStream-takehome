"""The development selection unchanged (ADR-0100): rerun `selection_v2.run` at every development origin with the
current code (its `only` and `research_dir` parameters at their defaults) and compare every output file byte for
byte with `research/selection_v2`. Development data only.

Writes `research/audit/selection_unchanged.md`; exits 1 on any difference.
Usage: POLARS_MAX_THREADS=8 uv run python scripts/check_selection_unchanged.py
"""

import sys

sys.path.insert(0, "src")
import tempfile
from pathlib import Path

from arkstream import selection_v2
from arkstream.config import load_context

ROOT = Path(".").resolve()
REF = ROOT / "research/selection_v2"


def main() -> int:
    ctx = load_context()
    with tempfile.TemporaryDirectory(prefix="selection_check_") as tmp:
        out = Path(tmp)
        selection_v2.run(ctx, out=out, verbose=False)
        new = sorted(p.relative_to(out) for p in out.rglob("*") if p.is_file())
        ref = sorted(p.relative_to(REF) for p in REF.rglob("*") if p.is_file() and p.suffix in (".parquet", ".csv"))
        same = [p for p in new if (REF / p).is_file() and (REF / p).read_bytes() == (out / p).read_bytes()]
        diff = [str(p) for p in new if p not in same]
        missing = [str(p) for p in ref if not (out / p).is_file()]
    bad = len(diff) + len(missing)
    lines = ["# Development selection unchanged (ADR-0100)", "",
             "`selection_v2.run` rerun at every development origin with the current code, compared byte for byte with "
             "`research/selection_v2`.", "",
             f"- files written: {len(new)}; identical: {len(same)}; differ: {len(diff)}"
             + "".join(f"\n  - `{d}`" for d in diff[:10]),
             f"- published files not written: {len(missing)}" + "".join(f"\n  - `{m}`" for m in missing[:10]),
             "", f"**Result: {'PASS' if bad == 0 else 'FAIL'}**"]
    (ROOT / "research/audit").mkdir(parents=True, exist_ok=True)
    (ROOT / "research/audit/selection_unchanged.md").write_text("\n".join(lines) + "\n", encoding="utf-8",
                                                                 newline="\n")
    print("\n".join(lines))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
