"""Bronze storage helpers. Bronze is immutable: an object, once written, is never overwritten."""

import os
from pathlib import Path


def cik10(cik: int) -> str:
    return f"CIK{cik:010d}"


def bronze_path(bronze_dir: Path, dataset: str, ingest_date: str, filename: str) -> Path:
    return bronze_dir / dataset / f"ingest_date={ingest_date}" / filename


def write_once(path: Path, data: bytes) -> bool:
    """Atomically write ``data`` to ``path`` unless it exists. Returns True if written."""
    # shortcut: local filesystem only; a GCS backend with if-generation-match=0 lands in Week 4.
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return True
