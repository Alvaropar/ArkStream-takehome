"""Holdout freeze (plan "Freeze hash before the holdout"; ADR-0065, the joint freeze of ADR-0091, details ADR-0097).

`write_freeze` records the SHA-256 of every file in the frozen set in `provenance/HOLDOUT_FREEZE.txt`, with a
timestamp, the environment block and one `freeze_hash` over the sorted list and the environment:
* the configuration (`CONFIG_FILES`) and the 3 Dec v2 hand-off (`SHORTLIST`);
* every source the holdout path imports: the source globs, the Phase 5 modules, their static import closure within
  `src/arkstream`, and the command-line entry point (`ENTRY_FILES`);
* the frozen documents: ADRs 0065-0084 and 0086-0097, the Phase 4 v2 and Phase 5 methodologies and the Phase 5
  development results;
* the data, replay and selection manifests (`MANIFEST_FILES`), including the output manifest of the trees the holdout
  path reads (`OUTPUT_MANIFEST`, written by `write_output_manifest`).

It refuses unless `frozen: true` is set in `decision_context.yaml`, no value in `risk.yaml` is `OPEN`,
`POLARS_MAX_THREADS` is set and the output manifest matches the disk.

`guard(ctx, window_end)` is called by every selection and replay entry point with the end of the window it is about
to compute. A window ending at or before the holdout start (3 Dec 2025 00:00 UTC) runs freely. A later one runs only
if the freeze file exists, the config says `frozen: true`, every recorded hash matches the current file and the
environment matches (every line but the OS, which is recorded): moving the cutoff, editing a threshold or a frozen
document, or changing a package version is refused.
"""

from __future__ import annotations

import ast
import hashlib
import os
import platform
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path

from arkstream.timeparse import parse_one_utc

FREEZE_FILE = "provenance/HOLDOUT_FREEZE.txt"
SHORTLIST = "research/selection_v2/origin=2025-12-03/eligible.parquet"
RULE = ("phase4-v2 select-v2 run 4 with ADR-0084 (ADRs 0066-0084); phase5 revision 4 two-sleeve scheme "
        "(ADRs 0086-0097); holdout runs A, B, C and the v2 entry point (ADRs 0098-0099); the cutoff selection "
        "and deliverables (ADR-0100)")
CONFIG_FILES = ("config/decision_context.yaml", "config/execution.yaml", "config/instruments.yaml",
                "config/risk.yaml")
SOURCE_GLOBS = ("selection*.py", "freeze.py", "replay*.py", "drift.py", "prices.py", "hlprices.py", "refprices.py",
                "leader*.py", "copiers.py", "quality.py", "positions.py", "book_state.py", "funding.py",
                "pipeline.py", "config.py", "timeparse.py",
                # Phase 5 (ADR-0091 item 3)
                "risk_model.py", "portfolio_*.py", "phase5_*.py", "holdout_report.py",
                # runs B and C and the v2 holdout entry point (ADR-0098 item 8, ADR-0099)
                "cost_*.py", "holdout.py",
                # the cutoff selection and the cutoff deliverables (ADR-0100)
                "cutoff.py")
ENTRY_FILES = ("__init__.py", "__main__.py", "cli.py")  # hashed, their imports not followed (ADR-0097 item 2)
FROZEN_ADRS = (*range(65, 85), *range(86, 101))
DOC_FILES = ("decision/phase-4-v2-methodology.md", "decision/phase-5-methodology.md", "decision/phase-5-results.md")
OUTPUT_MANIFEST = "provenance/HOLDOUT_OUTPUT_MANIFEST.txt"
MANIFEST_FILES = ("provenance/CHECKSUMS.txt", "data/reference/prices/MANIFEST.yaml",
                  "data/reference/binance/CHECKSUMS.txt", "data/reference/binance/aggtrades/MANIFEST.csv",
                  "data/reference/hyperliquid/funding/MANIFEST.csv",
                  "data/reference/hyperliquid/candles_4h/MANIFEST.csv",
                  "data/reference/hyperliquid/user_funding/MANIFEST.csv",
                  "provenance/PRE_PHASE4_OUTPUT_CHECKSUMS.txt", OUTPUT_MANIFEST)
OUTPUT_TREES = ("research/replay_tradable", "research/replay_allpriced", "research/selection_v2",
                "research/leader", "research/replay_gray", "research/risk_model",
                "research/phase5_population", "research/portfolio_replay", "research/window_report",
                "research/cost_runs")  # ADR-0099 item 5: the frozen O2 bounds and the development runs B and C
TEXT_SUFFIXES = (".py", ".md", ".yaml", ".yml", ".txt", ".csv", ".json", ".toml", ".lock")
ENV_PACKAGES = ("polars", "numpy", "pyarrow", "pyyaml", "scipy")
ENV_NOT_COMPARED = ("os",)


class FreezeError(RuntimeError):
    """A window after the holdout start was requested without a matching freeze."""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def content_sha256(path: Path) -> str:
    """The hash the freeze records (ADR-0097 item 10): a text file with CRLF line endings normalised to LF, as git
    stores it, so the same commit gives the same hash on any checkout; any other file byte for byte."""
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return sha256(path)
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


# ---------------------------------------------------------------------------------------------- the frozen set
def module_imports(path: Path, modules: set[str]) -> set[str]:
    """`arkstream` modules imported anywhere in a source file (top level or inside a function)."""
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "arkstream":
                out |= {a.name for a in node.names}
            elif node.module.startswith("arkstream."):
                out.add(node.module.split(".")[1])
        elif isinstance(node, ast.Import):
            out |= {a.name.split(".")[1] for a in node.names if a.name.startswith("arkstream.")}
    return out & modules


def source_modules(src: Path) -> list[str]:
    """The source globs and their static import closure within `src/arkstream` (ADR-0097 item 2)."""
    modules = {p.stem for p in src.glob("*.py")}
    todo = sorted({p.stem for pattern in SOURCE_GLOBS for p in src.glob(pattern)})
    seen: set[str] = set()
    while todo:
        m = todo.pop()
        if m in seen:
            continue
        seen.add(m)
        todo.extend(sorted(module_imports(src / f"{m}.py", modules) - seen))
    return sorted(seen)


def frozen_adrs(root: Path) -> list[str]:
    out = []
    for n in FROZEN_ADRS:
        hits = sorted((root / "decision" / "adr").glob(f"{n:04d}-*.md"))
        if len(hits) != 1:
            raise FreezeError(f"ADR-{n:04d}: expected one file in decision/adr, found {len(hits)}")
        out.append(hits[0].relative_to(root).as_posix())
    return out


def frozen_paths(root: Path) -> list[str]:
    """Relative POSIX paths of every hashed file, sorted (each must exist)."""
    src = root / "src" / "arkstream"
    files = set(CONFIG_FILES) | {SHORTLIST} | set(DOC_FILES) | set(MANIFEST_FILES) | set(frozen_adrs(root))
    files |= {f"src/arkstream/{m}.py" for m in source_modules(src)}
    files |= {f"src/arkstream/{f}" for f in ENTRY_FILES if (src / f).exists()}
    return sorted(files)


def digest_lines(root: Path) -> list[str]:
    return [f"{content_sha256(root / p)}  {p}" for p in frozen_paths(root)]


# ---------------------------------------------------------------------------------------------- environment
def environment(root: Path) -> list[tuple[str, str]]:
    """The environment block (ADR-0097 item 5): Python, package versions, the uv.lock hash, the OS, the threads."""
    out = [("python", platform.python_version())]
    for p in ENV_PACKAGES:
        try:
            out.append((p, metadata.version(p)))
        except metadata.PackageNotFoundError:
            continue
    out += [("uv.lock", content_sha256(root / "uv.lock")), ("os", platform.platform()),
            ("POLARS_MAX_THREADS", os.environ.get("POLARS_MAX_THREADS", "(unset)"))]
    return out


def env_lines(root: Path) -> list[str]:
    return [f"env: {k}={v}" for k, v in environment(root)]


def parse_env(lines: list[str]) -> dict[str, str]:
    return dict(ln[len("env: "):].split("=", 1) for ln in lines)


def combined(lines: list[str]) -> str:
    return hashlib.sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------------------------- output manifest
def tree_files(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for t in OUTPUT_TREES if (root / t).exists()
                  for p in (root / t).rglob("*") if p.is_file())


def size(path: Path) -> int:
    """Bytes as git stores the file (text with LF line endings), matching `content_sha256`."""
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return path.stat().st_size
    data = path.read_bytes()
    return len(data) - data.count(b"\r\n")


def hash_many(root: Path, rels: list[str]) -> dict[str, tuple[str, int]]:
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(lambda r: (content_sha256(root / r), size(root / r)), rels))
    return dict(zip(rels, res, strict=True))


def write_output_manifest(root: Path) -> tuple[Path, int]:
    """`provenance/HOLDOUT_OUTPUT_MANIFEST.txt`: SHA-256 and size of every file under the output trees."""
    rels = tree_files(root)
    got = hash_many(root, rels)
    text = "\n".join([
        "# ArkStream holdout output manifest (ADR-0097 item 4): every file under the trees the holdout path reads",
        "# trees: " + ", ".join(OUTPUT_TREES),
        "# sha256  bytes  path (text files with LF line endings, as git stores them; ADR-0097 item 10)",
        *(f"{got[r][0]}  {got[r][1]}  {r}" for r in rels),
        "",
    ])
    path = root / OUTPUT_MANIFEST
    path.write_text(text, encoding="utf-8", newline="\n")
    return path, len(rels)


def read_output_manifest(root: Path) -> dict[str, tuple[str, int]]:
    out = {}
    for ln in (root / OUTPUT_MANIFEST).read_text(encoding="utf-8").splitlines():
        if not ln.strip() or ln.startswith("#"):
            continue
        digest, size, rel = ln.split("  ", 2)
        out[rel] = (digest, int(size))
    return out


def check_output_manifest(root: Path) -> list[str]:
    """Every listed output matches the disk and no file under the output trees is unlisted."""
    if not (root / OUTPUT_MANIFEST).exists():
        return [f"no {OUTPUT_MANIFEST} (select --output-manifest writes it)"]
    want = read_output_manifest(root)
    present = [r for r in want if (root / r).exists()]
    problems = [f"missing output {r}" for r in want if not (root / r).exists()]
    sized = [r for r in present if size(root / r) == want[r][1]]
    same_size = set(sized)
    problems += [f"size differs {r}" for r in present if r not in same_size]
    got = hash_many(root, sized)
    problems += [f"sha256 differs {r}" for r in sized if got[r][0] != want[r][0]]
    problems += [f"unlisted output {r}" for r in tree_files(root) if r not in want]
    return sorted(problems)


# ---------------------------------------------------------------------------------------------- write and verify
def open_values(obj, path: str = "") -> list[str]:
    """Keys of `risk.yaml` whose value is still an `OPEN` choice (ADR-0091 item 4)."""
    if isinstance(obj, dict):
        return [k for key, v in obj.items() for k in open_values(v, f"{path}.{key}" if path else str(key))]
    if isinstance(obj, list):
        return [k for i, v in enumerate(obj) for k in open_values(v, f"{path}[{i}]")]
    return [path] if isinstance(obj, str) and obj.startswith("OPEN") else []


def holdout_start(raw: dict) -> datetime:
    """The holdout start. A run context that moves the replay boundary (the cutoff selection, ADR-0100 item 2)
    keeps the real one in `freeze_holdout_start`, so every guard inside the pipeline still needs the freeze."""
    start = str(raw.get("freeze_holdout_start", raw["splits"]["holdout"]["start"]))
    return parse_one_utc(start + "T00:00:00Z")


def write_freeze(ctx, rule: str, now: datetime | None = None) -> tuple[Path, str]:
    import yaml

    if ctx.raw.get("frozen") is not True:
        raise FreezeError("set frozen: true in decision_context.yaml before writing the freeze")
    root = ctx.root
    still_open = open_values(yaml.safe_load((root / "config/risk.yaml").read_text(encoding="utf-8")))
    if still_open:
        raise FreezeError("risk.yaml still holds an OPEN value: " + ", ".join(still_open))
    if not os.environ.get("POLARS_MAX_THREADS"):
        raise FreezeError("set POLARS_MAX_THREADS before the freeze (ADR-0051 item 5: byte comparisons use 8)")
    problems = check_output_manifest(root)
    if problems:
        raise FreezeError("output manifest does not match the disk: " + "; ".join(problems[:20])
                          + (f" (+{len(problems) - 20} more)" if len(problems) > 20 else ""))
    lines = digest_lines(root)
    env = env_lines(root)
    stamp = (now or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ")
    h = combined(lines + env)
    text = "\n".join([
        "# ArkStream holdout freeze (plan: Freeze hash before the holdout; ADRs 0065, 0091, 0097)",
        f"frozen_at: {stamp}",
        f"rule: {rule}",
        f"cutoff: {ctx.raw['cutoff']}",
        f"holdout: {ctx.raw['splits']['holdout']['start']}..{ctx.raw['splits']['holdout']['end']}",
        f"files: {len(lines)}",
        *lines,
        *env,
        f"freeze_hash: {h}",
        "",
    ])
    path = root / FREEZE_FILE
    path.write_text(text, encoding="utf-8", newline="\n")
    return path, h


def read_freeze(root: Path) -> tuple[list[str], list[str], str]:
    """(digest lines, environment lines, freeze_hash) of the freeze file."""
    text = (root / FREEZE_FILE).read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if len(ln) > 66 and ln[64:66] == "  "]
    env = [ln for ln in text.splitlines() if ln.startswith("env: ")]
    h = next(ln.split(": ", 1)[1] for ln in text.splitlines() if ln.startswith("freeze_hash: "))
    return lines, env, h


def verify(ctx) -> str:
    """The freeze hash if the freeze holds; raises FreezeError naming every mismatch otherwise."""
    root = ctx.root
    if not (root / FREEZE_FILE).exists():
        raise FreezeError(f"no {FREEZE_FILE}: the holdout is not frozen")
    if ctx.raw.get("frozen") is not True:
        raise FreezeError("decision_context.yaml does not say frozen: true")
    recorded, env, h = read_freeze(root)
    if combined(recorded + env) != h:
        raise FreezeError("freeze file edited: freeze_hash does not match its own list")
    problems = []
    want = {ln[66:]: ln[:64] for ln in recorded}
    try:
        now = set(frozen_paths(root))
    except FreezeError as e:
        problems.append(str(e))
        now = set(want)
    for p in sorted(now - set(want)):
        problems.append(f"new file {p}")
    for p, digest in sorted(want.items()):
        f = root / p
        if not f.exists():
            problems.append(f"missing {p}")
        elif content_sha256(f) != digest:
            problems.append(f"changed {p}")
    frozen_env, current = parse_env(env), dict(environment(root))
    for k in sorted(set(frozen_env) | set(current)):
        if k not in ENV_NOT_COMPARED and frozen_env.get(k) != current.get(k):
            problems.append(f"environment {k}: frozen {frozen_env.get(k)}, now {current.get(k)}")
    if problems:
        raise FreezeError("holdout freeze does not match: " + "; ".join(problems))
    return h


def guard(ctx, window_end: datetime) -> str | None:
    """Refuse a window ending after the holdout start unless the freeze holds (returns the freeze hash then)."""
    if window_end <= holdout_start(ctx.raw):
        return None
    return verify(ctx)
