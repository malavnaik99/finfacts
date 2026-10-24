"""Which companies a daily run must rebuild, as dbt vars (dbt/macros/incremental_by_company.sql).

A company is rebuilt when the set of GCS files loaded for it differs from the set used by the
last successful build. The manifests map CIK -> sorted object names; the built one is saved
append-only after each successful publish, so a failed run is simply redone next time.
"""

import re
from collections.abc import Iterable

BUCKETS = 1000  # must match cik_bucket() in dbt/macros/incremental_by_company.sql
_CIK = re.compile(r"CIK(\d{10})")

Manifest = dict[int, list[str]]


def manifest_from(object_names: Iterable[str]) -> Manifest:
    """CIK -> sorted object names (objects without a CIK in their name are ignored)."""
    out: dict[int, list[str]] = {}
    for name in object_names:
        m = _CIK.search(name)
        if m:
            out.setdefault(int(m.group(1)), []).append(name)
    return {cik: sorted(names) for cik, names in out.items()}


def changed_ciks(current: Manifest, built: Manifest) -> set[int]:
    return {c for c in current.keys() | built.keys() if current.get(c) != built.get(c)}


def plan_scope(
    changed_raw: set[int], universe: set[int], predecessors: dict[int, int]
) -> dict[str, list[int]]:
    """dbt vars for an incremental run. `predecessors` maps old CIK -> successor CIK.

    Every universe company in a touched bucket is rebuilt (a bucket is replaced as a whole);
    raw-table filters also need the predecessor CIKs of those companies.
    """
    successors = {predecessors.get(c, c) for c in changed_raw}
    buckets = sorted({c % BUCKETS for c in successors})
    scope = sorted(c for c in universe if c % BUCKETS in set(buckets))
    raw = sorted(set(scope) | {old for old, new in predecessors.items() if new in set(scope)})
    return {"changed_buckets": buckets, "scope_ciks": scope, "scope_raw_ciks": raw}
