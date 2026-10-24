"""Cross-check 10% of the eval answers against SEC's companyconcept API.

For 15 sampled single-value questions, fetch the concept FinFacts used directly from
data.sec.gov/api/xbrl/companyconcept (a different access path from the bulk pipeline) and
compare the latest value SEC holds for the same period, as of the snapshot date.
Writes eval/v1/verification.csv. Usage: uv run python scripts/verify_eval_sample.py
"""

import csv
import json
import random
import re
import sys
from pathlib import Path

import duckdb
import httpx

from finfacts.eval.snapshot import SNAPSHOT_DATE
from finfacts.sec.client import SecClient
from finfacts.settings import Settings

SNAPSHOT = Path("data/eval/finfacts_eval_v1.duckdb")
QUESTIONS = Path("eval/v1/questions.jsonl")
OUT = Path("eval/v1/verification.csv")
PREDECESSORS = {
    int(r["successor_cik"]): int(r["predecessor_cik"])
    for r in csv.DictReader(
        Path("config/universe/predecessors.csv").read_text(encoding="utf-8").splitlines()
    )
}
SQL_KEYS = re.compile(r"cik = (\d+) and metric_id = '(\w+)'\s+and fiscal_year = (\d+)")


def main() -> int:
    qs = [json.loads(line) for line in QUESTIONS.read_text(encoding="utf-8").splitlines()]
    candidates = [q for q in qs if q["category"] == "value"]
    random.Random(7).shuffle(candidates)  # noqa: S311 - reproducible sample, not security
    s = Settings()  # type: ignore[call-arg]
    rows = []
    skipped: list[str] = []
    with duckdb.connect(str(SNAPSHOT), read_only=True) as con, SecClient(s.sec_user_agent) as sec:
        for q in candidates:
            if len(rows) == 15:
                break
            m = SQL_KEYS.search(q["gold_sql"])
            assert m, q["gold_sql"]
            cik, metric, fy = int(m.group(1)), m.group(2), int(m.group(3))
            src, start, end, derived = con.execute(
                "select source_concept, period_start, period_end, is_derived from "
                "semantic.financials where cik = ? and metric_id = ? and fiscal_year = ? "
                "and fiscal_period = 'FY'",
                [cik, metric, fy],
            ).fetchone()
            if derived:
                continue  # computed by FinFacts: no single SEC concept to compare with
            taxonomy, concept = src.split(":")
            unit = "USD/shares" if metric == "eps_diluted" else "USD"
            facts = []
            # A re-registered company's older values were filed under its predecessor CIK.
            for filer in (cik, PREDECESSORS.get(cik)):
                if filer is None:
                    continue
                try:
                    doc = sec.get_json(
                        "https://data.sec.gov/api/xbrl/companyconcept/"
                        f"CIK{filer:010d}/{taxonomy}/{concept}.json"
                    )
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 404:
                        continue
                    raise
                facts += doc["units"].get(unit, [])
            if not facts:
                # SEC's per-concept endpoint sometimes returns no facts for a concept that its
                # companyfacts file contains (seen for KO PaymentsOfDividends): not comparable.
                skipped.append(f"{q['id']} {src}: companyconcept returned no facts")
                continue
            facts = [
                f
                for f in facts
                if f["end"] == str(end)
                and f.get("start") == (str(start) if start else None)
                and f["filed"] <= SNAPSHOT_DATE
            ]
            latest = max(facts, key=lambda f: f["filed"]) if facts else None
            sec_value = latest["val"] if latest else None
            ok = sec_value is not None and abs(sec_value - q["gold_answer"]) <= 0.5
            status = "match" if ok else "MISMATCH"
            rows.append(
                {
                    "id": q["id"],
                    "question": q["question"],
                    "gold_answer": q["gold_answer"],
                    "sec_companyconcept_value": sec_value,
                    "source_concept": src,
                    "status": status,
                }
            )
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    bad = [r for r in rows if r["status"] == "MISMATCH"]
    print(f"verified {len(rows)} answers: {len(rows) - len(bad)} ok, {len(bad)} mismatches")
    for r in rows:
        print(
            f"  {r['status']:8} {r['id']} {r['gold_answer']:>20,.2f}  "
            f"{r['sec_companyconcept_value']}"
        )
    for note in skipped:
        print(f"  skipped  {note}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
