from finfacts.warehouse import latest_per_cik


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
