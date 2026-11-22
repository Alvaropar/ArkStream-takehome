"""Checksums of raw inputs and of built outputs (rule 4: determinism)."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


def checksum_lines(paths: Iterable[Path], root: Path) -> list[str]:
    out = []
    for p in sorted(paths, key=lambda x: x.relative_to(root).as_posix()):
        out.append(f"{sha256_file(p)}  {p.stat().st_size:>12d}  {p.relative_to(root).as_posix()}")
    return out


def write_checksums(paths: Iterable[Path], root: Path, dest: Path, header: str) -> list[str]:
    lines = checksum_lines(paths, root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(f"# {header}\n# sha256  bytes  path\n" + "\n".join(lines) + "\n", encoding="utf-8")
    return lines
