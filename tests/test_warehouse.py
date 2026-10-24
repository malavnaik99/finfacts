import json
from pathlib import Path

from finfacts.warehouse import dbt_counts, latest_per_cik


def test_latest_per_cik_prefers_newest_date_then_incremental_file() -> None:
    names = [
        "flat/companyfacts/ingest_date=2026-10-20/CIK0000320193.parquet",
        "flat/companyfacts/ingest_date=2026-10-21/CIK0000320193.parquet",
        "flat/companyfacts/ingest_date=2026-10-21/CIK0000320193_0000320193-26-000001.parquet",
        "flat/companyfacts/ingest_date=2026-10-20/CIK0000789019.parquet",
        "flat/companyfacts/",  # the folder placeholder object
    ]
    assert latest_per_cik(names) == [
        "flat/companyfacts/ingest_date=2026-10-20/CIK0000789019.parquet",
        "flat/companyfacts/ingest_date=2026-10-21/CIK0000320193_0000320193-26-000001.parquet",
    ]


def test_dbt_counts(tmp_path: Path) -> None:
    rr = tmp_path / "run_results.json"
    rr.write_text(
        json.dumps(
            {
                "results": [
                    {"unique_id": "model.finfacts.a", "status": "success"},
                    {"unique_id": "seed.finfacts.s", "status": "success"},
                    {"unique_id": "model.finfacts.b", "status": "error"},
                    {"unique_id": "test.finfacts.t1", "status": "pass"},
                    {"unique_id": "test.finfacts.t2", "status": "warn"},
                    {"unique_id": "test.finfacts.t3", "status": "fail"},
                    {"unique_id": "unit_test.finfacts.u", "status": "pass"},
                ]
            }
        ),
        encoding="utf-8",
    )
    assert dbt_counts(rr) == {
        "models_ok": 2,
        "models_error": 1,
        "tests_pass": 2,
        "tests_warn": 1,
        "tests_fail": 1,
    }
    assert dbt_counts(tmp_path / "missing.json")["tests_pass"] == 0
