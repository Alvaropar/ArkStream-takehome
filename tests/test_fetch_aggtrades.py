"""aggTrades downloader: checksum mismatch refused, resume reuses verified files, seeds verified, cutoff."""

import hashlib
from datetime import date

import pytest

from arkstream_fetch import fetch_aggtrades as fa


class FakeHttp:
    """Serves zips and their .CHECKSUM from a dict; counts every request."""

    def __init__(self, files: dict[str, bytes], wrong_checksum: set[str] | None = None):
        self.files, self.wrong = files, wrong_checksum or set()
        self.calls: list[str] = []

    def _name(self, url: str) -> str:
        fa._check_url(url)
        return url.rsplit("/", 1)[1]

    def get_text(self, url: str) -> str:
        self.calls.append(url)
        name = self._name(url).removesuffix(".CHECKSUM")
        if name not in self.files:
            raise FileNotFoundError(url)
        h = hashlib.sha256(b"tampered" if name in self.wrong else self.files[name]).hexdigest()
        return f"{h}  {name}\n"

    def content_length(self, url: str) -> int | None:
        self.calls.append("HEAD " + url)
        return len(self.files[self._name(url)])

    def stream(self, url: str):
        self.calls.append(url)
        data = self.files[self._name(url)]
        for i in range(0, len(data), 3):
            yield data[i:i + 3]


def _todo():
    return fa.items(["BTCUSDT"], date(2025, 10, 8), date(2025, 10, 10))


def _files():
    return {it.name: f"zip-bytes-{it.name}".encode() for it in _todo()}


def test_download_verify_and_manifest(tmp_path):
    http = FakeHttp(_files())
    res = fa.run(_todo(), tmp_path, None, http, log=lambda s: None)
    assert len(res["downloaded"]) == 3 and not res["failed"]
    man = fa.read_manifest(tmp_path)
    for it in _todo():
        row = man[("BTCUSDT", it.day.isoformat())]
        assert row["sha256"] == row["published_sha256"] == fa.sha256_file(it.target(tmp_path))
        assert row["source"] == "download" and row["retrieved_on"] and row["verified_on"]
        assert it.target(tmp_path).with_name(it.name + ".CHECKSUM").exists()


def test_checksum_mismatch_refused(tmp_path):
    bad = _todo()[1].name
    http = FakeHttp(_files(), wrong_checksum={bad})
    res = fa.run(_todo(), tmp_path, None, http, log=lambda s: None)
    assert res["failed"] == [bad]
    assert not (tmp_path / "BTCUSDT" / bad).exists()                         # never moved into place
    assert not list(tmp_path.rglob("*.part"))                                # partial file removed
    assert ("BTCUSDT", "2025-10-09") not in fa.read_manifest(tmp_path)
    assert fa.main(["--out", str(tmp_path), "--no-seed", "--dry-run", "--offline", "--start", "2025-10-08",
                    "--end", "2025-10-10", "--symbols", "BTCUSDT"]) == 0       # dry-run still plans it


def test_resume_reuses_verified_files_without_network(tmp_path):
    fa.run(_todo(), tmp_path, None, FakeHttp(_files()), log=lambda s: None)
    http = FakeHttp(_files())
    res = fa.run(_todo(), tmp_path, None, http, log=lambda s: None)
    assert len(res["reused"]) == 3 and not res["downloaded"]
    assert http.calls == []                                                  # nothing fetched at all


def test_resume_reverifies_a_changed_file(tmp_path):
    fa.run(_todo(), tmp_path, None, FakeHttp(_files()), log=lambda s: None)
    t = _todo()[0].target(tmp_path)
    t.write_bytes(b"corrupted on disk")                                       # no longer matches manifest
    http = FakeHttp(_files())
    res = fa.run(_todo(), tmp_path, None, http, log=lambda s: None)
    assert res["failed"] == [t.name] and len(res["reused"]) == 2              # refused, not trusted
    assert not t.exists()
    res = fa.run(_todo(), tmp_path, None, http, log=lambda s: None)           # next run downloads it again
    assert res["downloaded"] == [t.name]


def test_seeds_copied_and_verified_not_downloaded(tmp_path):
    seed, out = tmp_path / "seed", tmp_path / "out"
    files = _files()
    first = _todo()[0]
    (seed / "BTCUSDT").mkdir(parents=True)
    (seed / "BTCUSDT" / first.name).write_bytes(files[first.name])
    http = FakeHttp(files)
    res = fa.run(_todo(), out, seed, http, log=lambda s: None)
    assert res["seeded"] == [first.name] and len(res["downloaded"]) == 2
    assert first.url not in http.calls and first.url + ".CHECKSUM" in http.calls  # verified, not downloaded
    assert (seed / "BTCUSDT" / first.name).exists()                              # seed left in place
    assert fa.read_manifest(out)[("BTCUSDT", "2025-10-08")]["source"] == "seed"


def test_bad_seed_refused(tmp_path):
    seed, out = tmp_path / "seed", tmp_path / "out"
    first = _todo()[0]
    (seed / "BTCUSDT").mkdir(parents=True)
    (seed / "BTCUSDT" / first.name).write_bytes(b"not the published file")
    res = fa.run(_todo(), out, seed, FakeHttp(_files()), log=lambda s: None)
    assert first.name in res["failed"] and not first.target(out).exists()


def test_dry_run_counts_and_sizes_without_writing(tmp_path):
    http = FakeHttp(_files())
    out = fa.dry_run(_todo(), tmp_path / "out", None, http, log=lambda s: None)
    assert out["files"] == 3 and out["download"] == 3
    assert out["download_bytes"] == sum(len(v) for v in _files().values())
    assert all(c.startswith("HEAD ") for c in http.calls)
    assert not (tmp_path / "out").exists()


def test_cutoff_and_host_guards():
    with pytest.raises(ValueError, match="cutoff"):
        fa.items(["BTCUSDT"], date(2026, 1, 1), date(2026, 1, 5))
    with pytest.raises(ValueError, match="only data.binance.vision"):
        fa._check_url("https://example.com/x.zip")
    assert len(fa.items(fa.DEFAULT_SYMBOLS, fa.DEFAULT_START, fa.DEFAULT_END)) == 4 * 119


def test_rename_waits_out_a_brief_windows_lock(tmp_path, monkeypatch):
    """A PermissionError from a momentary lock (antivirus, indexer) is retried; a lasting one names the file."""
    import os

    src, dst = tmp_path / "a.tmp", tmp_path / "a.csv"
    src.write_text("new")
    dst.write_text("old")
    real, calls = os.replace, []

    def flaky(a, b):
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError(5, "Access is denied")
        real(a, b)

    monkeypatch.setattr(fa.os, "replace", flaky)
    fa._replace(src, dst, sleep=lambda s: None)
    assert dst.read_text() == "new" and len(calls) == 3

    def locked(a, b):
        raise PermissionError(5, "Access is denied")

    monkeypatch.setattr(fa.os, "replace", locked)
    src.write_text("x")
    with pytest.raises(PermissionError, match="still locked"):
        fa._replace(src, dst, tries=3, sleep=lambda s: None)
