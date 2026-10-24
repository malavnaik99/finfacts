"""10-K text for retrieval: Item 1A (Risk Factors) and Item 7 (MD&A), chunked and embedded.

1. extract: edgartools parses each 10-K into items; the two sections land in bronze as
   filings_text/<accession>.json.gz (write-once, so reruns skip done filings).
2. chunk:   ~600 words (~800 tokens) per chunk with ~75 words (~100 tokens) of overlap, each
            chunk tagged with company, fiscal year, item and accession.
3. embed:   BAAI/bge-small-en-v1.5 (384 dims) into a LanceDB table, plus a parquet export.
"""

import gzip
import json
import logging
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from finfacts.storage import write_once

log = logging.getLogger(__name__)

ITEMS = {"1A": "Item 1A", "7": "Item 7"}
CHUNK_WORDS = 600
OVERLAP_WORDS = 75
EMBED_MODEL = "BAAI/bge-small-en-v1.5"


@dataclass(frozen=True)
class Target:
    accession: str
    cik: int
    filing_date: str
    report_date: str


def text_path(bronze_dir: Path, accession: str) -> Path:
    return bronze_dir / "filings_text" / f"{accession}.json.gz"


def extract_one(target: Target, bronze_dir: Path) -> bool:
    """Fetch one 10-K and store its Item 1A and Item 7. Returns True if a file was written."""
    from edgar import Filing, find  # local import: heavy, only needed here

    dest = text_path(bronze_dir, target.accession)
    if dest.exists():
        return False
    filing = find(target.accession)
    if not isinstance(filing, Filing):
        raise ValueError(f"{target.accession} did not resolve to a filing: {type(filing).__name__}")
    tenk = filing.obj()  # type: ignore[no-untyped-call]  # untyped in edgartools
    sections = {}
    for key, label in ITEMS.items():
        try:
            sections[key] = tenk[label] or ""
        except Exception:  # an item edgartools cannot locate is recorded as missing
            sections[key] = ""
    doc = {**target.__dict__, "sections": sections}
    return write_once(dest, gzip.compress(json.dumps(doc).encode(), mtime=0))


def extract_all(targets: list[Target], bronze_dir: Path, user_agent: str, workers: int = 4) -> None:
    from edgar import set_identity

    set_identity(user_agent)  # SEC fair access: declared User-Agent on every request
    todo = [t for t in targets if not text_path(bronze_dir, t.accession).exists()]
    log.info("10-K text: %d targets, %d to fetch", len(targets), len(todo))
    done = failed = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(extract_one, t, bronze_dir): t for t in todo}
        for fut in as_completed(futures):
            try:
                fut.result()
                done += 1
            except Exception as exc:  # one bad filing must not stop the batch
                failed += 1
                log.warning("10-K text failed for %s: %s", futures[fut].accession, exc)
            if (done + failed) % 50 == 0:
                log.info("10-K text: %d done, %d failed", done, failed)
    log.info("10-K text finished: %d fetched, %d failed", done, failed)


def chunk_words(text: str, size: int = CHUNK_WORDS, overlap: int = OVERLAP_WORDS) -> list[str]:
    """Split on whitespace into overlapping windows of `size` words."""
    words = text.split()
    if not words:
        return []
    step = size - overlap
    return [" ".join(words[i : i + size]) for i in range(0, max(len(words) - overlap, 1), step)]


def iter_chunks(bronze_dir: Path, meta: dict[str, dict[str, Any]]) -> Iterator[dict[str, Any]]:
    """Chunks with metadata. `meta` maps accession -> {ticker, company, fiscal_year}."""
    for path in sorted((bronze_dir / "filings_text").glob("*.json.gz")):
        doc = json.loads(gzip.decompress(path.read_bytes()))
        m = meta.get(doc["accession"], {})
        for item, text in doc["sections"].items():
            for i, chunk in enumerate(chunk_words(text)):
                yield {
                    "chunk_id": f"{doc['accession']}-{item}-{i:04d}",
                    "cik": doc["cik"],
                    "ticker": m.get("ticker"),
                    "company": m.get("company"),
                    "fiscal_year": m.get("fiscal_year"),
                    "item": item,
                    "accession": doc["accession"],
                    "filing_date": doc["filing_date"],
                    "chunk_index": i,
                    "text": chunk,
                }


def embed_and_store(chunks: list[dict[str, Any]], lancedb_dir: Path, parquet_out: Path) -> int:
    import lancedb
    import pyarrow as pa
    import pyarrow.parquet as pq
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(EMBED_MODEL)
    vectors = model.encode(
        [c["text"] for c in chunks],
        batch_size=64,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    rows = [{**c, "vector": v.tolist()} for c, v in zip(chunks, vectors, strict=True)]
    table = pa.Table.from_pylist(rows)
    parquet_out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, parquet_out, compression="zstd")
    db = lancedb.connect(str(lancedb_dir))
    db.create_table("tenk_chunks", data=table, mode="overwrite")
    return len(rows)


def search(lancedb_dir: Path, query: str, k: int = 5) -> list[dict[str, Any]]:
    """Top-k chunks for a natural-language query (bge expects this query prefix)."""
    import lancedb
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(EMBED_MODEL)
    q = model.encode(
        "Represent this sentence for searching relevant passages: " + query,
        normalize_embeddings=True,
    )
    tbl = lancedb.connect(str(lancedb_dir)).open_table("tenk_chunks")
    hits: list[dict[str, Any]] = tbl.search(q.tolist()).limit(k).to_list()
    return hits
