"""P5-9 check (ADR-0094 Consequences): the parameters in `decision/deployment-protocol.md` section 9 match
`config/risk.yaml` exactly.

Reads the table rows `| `key.path` | value | source |`, looks each key up in `config/risk.yaml` and compares:
numbers as numbers, lists element by element, everything else as text. Writes `research/audit/protocol_parameters.md`;
exits 1 on any difference or missing key.
Usage: uv run python scripts/check_protocol_parameters.py
"""

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "decision/deployment-protocol.md"
RISK = ROOT / "config/risk.yaml"
OUT = ROOT / "research/audit/protocol_parameters.md"
ROW = re.compile(r"^\| `([A-Za-z0-9_.]+)` \| ([^|]+) \| [^|]+ \|$")


def lookup(cfg: dict, key: str):
    node = cfg
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(key)
        node = node[part]
    return node


def parse(text: str):
    text = text.strip()
    if text.startswith("[") and text.endswith("]"):
        return [parse(x) for x in text[1:-1].split(",")]
    try:
        return float(text)
    except ValueError:
        return text


def same(doc, cfg) -> bool:
    if isinstance(doc, list):
        return isinstance(cfg, list) and len(doc) == len(cfg) and all(same(a, b) for a, b in zip(doc, cfg, strict=True))
    if isinstance(doc, float):
        return isinstance(cfg, (int, float)) and not isinstance(cfg, bool) and float(cfg) == doc
    return str(cfg) == doc


def main() -> int:
    cfg = yaml.safe_load(RISK.read_text(encoding="utf-8"))
    rows = [m.groups() for line in PROTOCOL.read_text(encoding="utf-8").splitlines() if (m := ROW.match(line))]
    lines, bad = [], 0
    for key, value in rows:
        try:
            actual = lookup(cfg, key)
            ok = same(parse(value), actual)
        except KeyError:
            actual, ok = "missing", False
        bad += not ok
        lines.append(f"| `{key}` | {value.strip()} | {actual} | {'match' if ok else 'DIFFERS'} |")
    report = ["# Protocol parameters against `config/risk.yaml` (ADR-0094)", "",
              f"`decision/deployment-protocol.md` section 9: {len(rows)} parameters, {len(rows) - bad} match, "
              f"{bad} differ or are missing.", "",
              "| Key | Protocol | risk.yaml | Result |", "| --- | --- | --- | --- |", *lines, "",
              f"**Result: {'PASS' if rows and not bad else 'FAIL'}**"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(report) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(report))
    return 0 if rows and not bad else 1


if __name__ == "__main__":
    sys.exit(main())
