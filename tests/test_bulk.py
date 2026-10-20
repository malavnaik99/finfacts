import gzip
import zipfile
from pathlib import Path

from finfacts.ingest.bulk import extract_members
from finfacts.storage import write_once


def _make_zip(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return path


def test_extracts_only_in_scope_ciks_and_is_idempotent(tmp_path: Path) -> None:
    zp = _make_zip(
        tmp_path / "submissions.zip",
        {
            "CIK0000320193.json": b'{"a":1}',
            "CIK0000320193-submissions-001.json": b'{"page":1}',
            "CIK0000000001.json": b"{}",
        },
    )
    bronze = tmp_path / "bronze"

    first = extract_members(zp, {320193, 999}, bronze, "submissions", "2026-10-20")
    assert (first.written, first.skipped, first.missing_ciks) == (2, 0, [999])

    part = bronze / "submissions" / "ingest_date=2026-10-20"
    assert gzip.decompress((part / "CIK0000320193.json.gz").read_bytes()) == b'{"a":1}'
    assert not (part / "CIK0000000001.json.gz").exists()

    second = extract_members(zp, {320193, 999}, bronze, "submissions", "2026-10-20")
    assert (second.written, second.skipped) == (0, 2)


def test_write_once_never_overwrites(tmp_path: Path) -> None:
    p = tmp_path / "a" / "b.json.gz"
    assert write_once(p, b"first") is True
    assert write_once(p, b"second") is False
    assert p.read_bytes() == b"first"
