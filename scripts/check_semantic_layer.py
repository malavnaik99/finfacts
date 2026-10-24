"""Semantic layer == gold: MetricFlow's revenue by company and year must equal plain SQL.

metric_time__year must be the FISCAL year: comparing with gold's fiscal_year (not the calendar
year of period_end) catches the 52/53-week companies whose two fiscal years can end in one
calendar year.

Runs `mf query --metrics revenue --group-by company__ticker,metric_time__year` against the
local DuckDB warehouse and compares every row with an independent SQL query on the gold
tables. Exits non-zero on any missing, extra or different value.

Usage: uv run python scripts/check_semantic_layer.py [path/to/finfacts.duckdb]
"""

import csv
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import duckdb

GOLD_SQL = """
select c.tickers as ticker, f.fiscal_year as year, sum(f.value) as revenue
from gold.fct_financials_latest as f
inner join gold.dim_company as c on f.cik = c.cik and c.is_current
where f.metric_id = 'revenue' and f.fiscal_period = 'FY'
group by 1, 2
"""


def main(db: Path) -> int:
    repo = Path(__file__).resolve().parent.parent
    env = {
        **os.environ,
        "DBT_PROFILES_DIR": ".",
        "FINFACTS_DUCKDB_PATH": str(db.resolve()),
        "PYTHONIOENCODING": "utf-8",
    }
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "mf.csv"
        mf_exe = shutil.which("mf")
        if mf_exe is None:
            raise SystemExit("MetricFlow CLI `mf` not found; run inside `uv run`")
        subprocess.run(  # noqa: S603 - fixed argument list, no shell
            [
                mf_exe,
                "query",
                "--metrics",
                "revenue",
                "--group-by",
                "company__ticker,metric_time__year",
                "--csv",
                str(out),
            ],
            cwd=repo / "dbt",
            env=env,
            check=True,
            capture_output=True,
        )
        with out.open(encoding="utf-8") as fh:
            mf = {
                (r["company__ticker"], int(r["metric_time__year"][:4])): float(r["revenue"])
                for r in csv.DictReader(fh)
                if r["revenue"]
            }

    with duckdb.connect(str(db), read_only=True) as con:
        gold = {(t, int(y)): float(v) for t, y, v in con.sql(GOLD_SQL).fetchall()}

    missing = gold.keys() - mf.keys()
    extra = mf.keys() - gold.keys()
    diff = [k for k in gold.keys() & mf.keys() if abs(gold[k] - mf[k]) > 0.5]
    print(
        f"semantic layer check: {len(gold)} company-years, missing={len(missing)} "
        f"extra={len(extra)} different={len(diff)}"
    )
    for k in sorted(missing)[:5] + sorted(extra)[:5] + sorted(diff)[:5]:
        print("  ", k, gold.get(k), mf.get(k))
    return 0 if gold and not (missing or extra or diff) else 1


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "data/finfacts.duckdb")))
