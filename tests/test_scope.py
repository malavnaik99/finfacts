from finfacts.scope import changed_ciks, manifest_from, plan_scope


def test_manifest_groups_objects_by_cik() -> None:
    m = manifest_from(
        [
            "flat/companyfacts/ingest_date=2026-10-21/CIK0000320193_0000320193-26-1.parquet",
            "flat/filings/ingest_date=2026-10-20/CIK0000320193-submissions-001.parquet",
            "flat/filings/ingest_date=2026-10-20/CIK0000789019.parquet",
            "flat/filings/",
        ]
    )
    assert sorted(m) == [320193, 789019]
    assert len(m[320193]) == 2


def test_changed_ciks_detects_new_changed_and_removed() -> None:
    built = {1: ["a"], 2: ["b"], 3: ["c"]}
    current = {1: ["a"], 2: ["b", "b2"], 4: ["d"]}
    assert changed_ciks(current, built) == {2, 3, 4}


def test_plan_scope_maps_predecessors_and_fills_buckets() -> None:
    universe = {2115436, 320193, 1320193, 789019}
    predecessors = {34088: 2115436}  # Exxon Mobil Corp -> ExxonMobil Holdings
    vars_ = plan_scope({34088, 320193}, universe, predecessors)
    assert vars_["changed_buckets"] == [193, 436]
    # 1320193 shares bucket 193 with Apple, so it is rebuilt too
    assert vars_["scope_ciks"] == [320193, 1320193, 2115436]
    assert vars_["scope_raw_ciks"] == [34088, 320193, 1320193, 2115436]


def test_plan_scope_with_no_changes_is_empty() -> None:
    assert plan_scope(set(), {1, 2}, {}) == {
        "changed_buckets": [],
        "scope_ciks": [],
        "scope_raw_ciks": [],
    }
