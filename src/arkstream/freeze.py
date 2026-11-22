"""Holdout freeze (plan "Freeze hash before the holdout", ADR-0139).

`write_freeze` records SHA-256 hashes of the decision context, the other config files, the selection, replay, drift,
price and leader source files and the 3 Dec shortlist in `provenance/HOLDOUT_FREEZE.txt`, with a timestamp and one
`freeze_hash` over the sorted list. It refuses unless `frozen: true` is already set in `decision_context.yaml`, so the
hashed config is the frozen one.

`guard(ctx, window_end)` is called by every selection and replay entry point with the end of the window it is
about to compute. A window ending at or before the holdout start (3 Dec 2025 00:00 UTC) runs freely. A later one runs
only if the freeze file exists, the config says `frozen: true` and every recorded hash matches the current file:
moving the cutoff or editing a threshold changes `decision_context.yaml` and is refused.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from arkstream.timeparse import parse_one_utc

FREEZE_FILE = "provenance/HOLDOUT_FREEZE.txt"
SHORTLIST = "research/selection/shortlist_2025-12-03.csv"
CONFIG_FILES = ("config/decision_context.yaml", "config/execution.yaml", "config/instruments.yaml",
                "config/risk.yaml")
SOURCE_GLOBS = ("selection*.py", "freeze.py", "replay*.py", "drift.py", "prices.py", "hlprices.py", "refprices.py",
                "leader*.py", "copiers.py", "quality.py", "positions.py", "book_state.py", "funding.py",
                "pipeline.py", "config.py", "timeparse.py")


class FreezeError(RuntimeError):
    """A window after the holdout start was requested without a matching freeze."""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def frozen_paths(root: Path) -> list[str]:
    """Relative POSIX paths of every hashed file, sorted (the shortlist must exist)."""
    src = root / "src" / "arkstream"
    files = set(CONFIG_FILES) | {SHORTLIST}
    for pattern in SOURCE_GLOBS:
        files |= {p.relative_to(root).as_posix() for p in src.glob(pattern)}
    return sorted(files)


def digest_lines(root: Path) -> list[str]:
    return [f"{sha256(root / p)}  {p}" for p in frozen_paths(root)]


def combined(lines: list[str]) -> str:
    return hashlib.sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()


def holdout_start(raw: dict) -> datetime:
    return parse_one_utc(raw["splits"]["holdout"]["start"] + "T00:00:00Z")


def write_freeze(ctx, rule: str, now: datetime | None = None) -> tuple[Path, str]:
    if ctx.raw.get("frozen") is not True:
        raise FreezeError("set frozen: true in decision_context.yaml before writing the freeze")
    root = ctx.root
    lines = digest_lines(root)
    stamp = (now or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ")
    h = combined(lines)
    text = "\n".join([
        "# ArkStream holdout freeze (plan: Freeze hash before the holdout; ADR-0139)",
        f"frozen_at: {stamp}",
        f"rule: {rule}",
        f"cutoff: {ctx.raw['cutoff']}",
        f"holdout: {ctx.raw['splits']['holdout']['start']}..{ctx.raw['splits']['holdout']['end']}",
        f"files: {len(lines)}",
        *lines,
        f"freeze_hash: {h}",
        "",
    ])
    path = root / FREEZE_FILE
    path.write_text(text, encoding="utf-8", newline="\n")
    return path, h


def read_freeze(root: Path) -> tuple[list[str], str]:
    text = (root / FREEZE_FILE).read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if len(ln) > 66 and ln[64:66] == "  "]
    h = next(ln.split(": ", 1)[1] for ln in text.splitlines() if ln.startswith("freeze_hash: "))
    return lines, h


def verify(ctx) -> str:
    """The freeze hash if the freeze holds; raises FreezeError naming every mismatch otherwise."""
    root = ctx.root
    if not (root / FREEZE_FILE).exists():
        raise FreezeError(f"no {FREEZE_FILE}: the holdout is not frozen")
    if ctx.raw.get("frozen") is not True:
        raise FreezeError("decision_context.yaml does not say frozen: true")
    recorded, h = read_freeze(root)
    if combined(recorded) != h:
        raise FreezeError("freeze file edited: freeze_hash does not match its own list")
    problems = []
    want = {ln[66:]: ln[:64] for ln in recorded}
    now = set(frozen_paths(root))
    for p in sorted(now - set(want)):
        problems.append(f"new file {p}")
    for p, digest in sorted(want.items()):
        f = root / p
        if not f.exists():
            problems.append(f"missing {p}")
        elif sha256(f) != digest:
            problems.append(f"changed {p}")
    if problems:
        raise FreezeError("holdout freeze does not match: " + "; ".join(problems))
    return h


def guard(ctx, window_end: datetime) -> str | None:
    """Refuse a window ending after the holdout start unless the freeze holds (returns the freeze hash then)."""
    if window_end <= holdout_start(ctx.raw):
        return None
    return verify(ctx)
