"""Rule 4: same inputs give byte-identical outputs."""

from pathlib import Path

import pytest

from arkstream.config import ROOT
from arkstream.ingest import ingest_all
from arkstream.provenance import checksum_lines, sha256_file


def _tree_hashes(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): sha256_file(p) for p in sorted(root.rglob("*.parquet"))}


@pytest.mark.data
def test_ingest_byte_identical_and_raw_checksums_stable(ctx, tmp_path):
    raw = [ctx.path("traders"), ctx.path("fills")]
    before = checksum_lines(raw, ROOT)
    ingest_all(raw[0], raw[1], tmp_path / "a")
    ingest_all(raw[0], raw[1], tmp_path / "b")
    ha, hb = _tree_hashes(tmp_path / "a"), _tree_hashes(tmp_path / "b")
    assert ha and ha == hb
    assert checksum_lines(raw, ROOT) == before  # raw inputs untouched


@pytest.mark.data
def test_build_outputs_byte_identical(full_build, ctx, inputs, tmp_path):
    from arkstream.pipeline import build
    again = build(ctx, inputs)
    for name, df in full_build.tables.items():
        p1, p2 = tmp_path / f"{name}.1.parquet", tmp_path / f"{name}.2.parquet"
        df.write_parquet(p1, compression="zstd", statistics=True)
        again.tables[name].write_parquet(p2, compression="zstd", statistics=True)
        assert sha256_file(p1) == sha256_file(p2), name


@pytest.mark.data
def test_checksums_file_matches_raw(ctx):
    listed = (ROOT / "provenance" / "CHECKSUMS.txt").read_text(encoding="utf-8").splitlines()
    entries = {line.split()[2]: line.split()[0] for line in listed if line and not line.startswith("#")}
    for p in (ctx.path("traders"), ctx.path("fills")):
        assert entries[p.relative_to(ROOT).as_posix()] == sha256_file(p)
