"""Text-to-SQL before/after the semantic layer, scored by execution accuracy.

The same model answers every question twice:
  before: given only the raw SEC XBRL facts (`raw` schema), as an analyst would get them
  after:  given FinFacts' certified tables and metric definitions (`semantic` schema)
Each generated query runs read-only on the frozen snapshot (60 s limit, one repair attempt
on error) and its first result is compared with the gold answer.
"""

import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import duckdb
import httpx

log = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "anthropic/claude-haiku-5.5"
QUERY_TIMEOUT_S = 60
NUMBER_TOLERANCE = 0.005

INSTRUCTIONS = """You write one DuckDB SQL query that answers a question about US public companies.
Rules:
- Use only the tables described below. Return exactly one SQL query in a ```sql block.
- The first column of the first row must be the answer. Monetary values in USD (not millions),
  percentages as numbers like 12.5, tickers as text. For "list" questions return one row per item.
- Companies are identified in questions by name and ticker; look the company up in the companies
  table (tickers is a ';'-separated list, the first is the main ticker)."""

RAW_SCHEMA = """Tables (schema `raw`): SEC XBRL company facts as published by SEC,
one row per fact per filing.

raw.facts(cik BIGINT, taxonomy VARCHAR -- 'us-gaap' or 'dei',
  concept VARCHAR -- XBRL tag e.g. 'Revenues', unit VARCHAR -- 'USD', 'USD/shares', 'shares',
  period_start DATE -- null for balance-sheet values, period_end DATE, value DOUBLE,
  accession_number VARCHAR -- the filing, form VARCHAR -- '10-K', '10-Q', ..., filed_date DATE,
  filing_fiscal_year INT -- SEC 'fy' of the FILING,
  filing_fiscal_period VARCHAR -- 'FY', 'Q1'.., frame VARCHAR)
raw.companies(cik BIGINT, name VARCHAR, tickers VARCHAR, gics_sector VARCHAR,
  gics_sub_industry VARCHAR, fiscal_year_end VARCHAR -- 'MMDD')

The same fact appears in many filings (comparatives); later filings may report restated values."""

SEMANTIC_SCHEMA = """Tables (schema `semantic`): FinFacts certified fundamentals for S&P 500
companies.

semantic.financials(cik BIGINT, metric_id VARCHAR, fiscal_year INT, fiscal_period VARCHAR,
  period_start DATE, period_end DATE, value DOUBLE, unit VARCHAR, is_derived BOOLEAN,
  source_concept VARCHAR)
  -- current certified value, one row per company x metric x fiscal period
semantic.financials_history(same columns as financials plus version_no INT, valid_from DATE,
  valid_to DATE, is_restatement BOOLEAN, accession_number VARCHAR)
  -- every reported value over time; version_no 1 = as first reported, valid_to null = current
semantic.companies(cik BIGINT, name VARCHAR, tickers VARCHAR, gics_sector VARCHAR,
  gics_sub_industry VARCHAR, fiscal_year_end VARCHAR -- 'MMDD')
semantic.metrics(metric_id VARCHAR, name VARCHAR, unit VARCHAR, period_type VARCHAR,
  statement VARCHAR, definition VARCHAR)

fiscal_period: 'FY' (full year), 'Q1'..'Q4' (3-month quarters; Q4 usually derived as FY - 9M),
  'Q2_YTD', 'Q3_YTD' (year to date). Balance-sheet metrics use the period-end value (FY = year end).
fiscal_year is named by the calendar year in which the fiscal year ends (Walmart's year ending
  January 2025 is fiscal_year 2025). Ratios (margins) are fractions (0.25 = 25%).

Metrics:
{metrics}"""


def _sql_from(text: str) -> str:
    m = re.search(r"```(?:sql)?\s*(.*?)```", text, re.S | re.I)
    return (m.group(1) if m else text).strip().rstrip(";")


def _tickers(v: Any) -> set[str]:
    return {t.strip().upper() for t in str(v).replace(",", ";").split(";") if t.strip()}


def score(rows: list[tuple[Any, ...]], gold: Any, answer_type: str) -> bool:
    """Execution accuracy: compare the query's first column with the gold answer."""
    if not rows:
        return False
    first = rows[0][0]
    try:
        if answer_type == "number":
            v = float(first)
            return bool(abs(v - gold) <= max(abs(gold) * NUMBER_TOLERANCE, 0.005))
        if answer_type == "integer":
            return round(float(first)) == int(gold)
        if answer_type == "ticker":
            return bool(_tickers(first) & _tickers(gold))
        if answer_type == "ticker_set":
            pred = [_tickers(r[0]) for r in rows]
            golds = [_tickers(g) for g in gold]
            return len(pred) == len(golds) and all(any(p & g for p in pred) for g in golds)
        if answer_type == "text":
            return str(first).strip().lower() == str(gold).strip().lower()
    except (TypeError, ValueError):
        return False
    raise ValueError(f"unknown answer_type {answer_type}")


def _execute(db: Path, sql: str) -> list[tuple[Any, ...]]:
    with duckdb.connect(str(db), read_only=True) as con:
        timer = threading.Timer(QUERY_TIMEOUT_S, con.interrupt)
        timer.start()
        try:
            return con.sql(sql).fetchmany(50)
        finally:
            timer.cancel()


class Llm:
    def __init__(self, api_key: str, model: str) -> None:
        self.model = model
        self.http = httpx.Client(
            timeout=120, headers={"Authorization": f"Bearer {api_key}", "X-Title": "FinFacts eval"}
        )
        self.tokens_in = self.tokens_out = 0
        self.cost_usd = 0.0
        self._lock = threading.Lock()

    def ask(self, messages: list[dict[str, str]]) -> str:
        for attempt in range(4):
            resp = self.http.post(
                OPENROUTER_URL,
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0,
                    "usage": {"include": True},
                },
            )
            if resp.status_code in (429, 500, 502, 503) and attempt < 3:
                time.sleep(2**attempt)
                continue
            resp.raise_for_status()
            body = resp.json()
            usage = body.get("usage", {})
            with self._lock:
                self.tokens_in += usage.get("prompt_tokens", 0)
                self.tokens_out += usage.get("completion_tokens", 0)
                self.cost_usd += float(usage.get("cost", 0) or 0)
            return str(body["choices"][0]["message"]["content"])
        raise RuntimeError("unreachable")


def answer_one(llm: Llm, db: Path, schema: str, q: dict[str, Any]) -> dict[str, Any]:
    messages = [
        {"role": "system", "content": INSTRUCTIONS + "\n\n" + schema},
        {"role": "user", "content": q["question"]},
    ]
    sql, error, rows, repaired = "", None, [], False
    for attempt in range(2):  # one repair attempt, the same for both conditions
        sql = _sql_from(llm.ask(messages))
        try:
            rows = _execute(db, sql)
            error = None
            break
        except Exception as exc:
            error = str(exc).splitlines()[0][:300]
            repaired = attempt == 0
            messages += [
                {"role": "assistant", "content": f"```sql\n{sql}\n```"},
                {
                    "role": "user",
                    "content": f"That query failed: {error}\nReturn a corrected query.",
                },
            ]
    correct = error is None and score(rows, q["gold_answer"], q["answer_type"])
    return {
        "id": q["id"],
        "category": q["category"],
        "source": q["source"],
        "sql": sql,
        "error": error,
        "repaired": repaired,
        "first_row": [str(v) for v in rows[0]] if rows else None,
        "correct": correct,
    }


def run(
    questions: Path, db: Path, out_dir: Path, model: str, api_key: str, workers: int = 4
) -> dict[str, Any]:
    qs = [json.loads(line) for line in questions.read_text(encoding="utf-8").splitlines()]
    with duckdb.connect(str(db), read_only=True) as con:
        metrics = "\n".join(
            f"- {m}: {n} ({u}). {d}"
            for m, n, u, d in con.sql(
                "select metric_id, name, unit, definition from semantic.metrics order by 1"
            ).fetchall()
        )
    schemas = {"before": RAW_SCHEMA, "after": SEMANTIC_SCHEMA.format(metrics=metrics)}
    llm = Llm(api_key, model)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {"model": model, "questions": len(qs), "conditions": {}}
    for condition, schema in schemas.items():
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(lambda q, s=schema: answer_one(llm, db, s, q), qs))
        path = out_dir / f"{condition}.jsonl"
        path.write_text("".join(json.dumps(r) + "\n" for r in results), encoding="utf-8")
        by_cat: dict[str, list[bool]] = {}
        for r in results:
            by_cat.setdefault(r["category"], []).append(r["correct"])
        summary["conditions"][condition] = {
            "accuracy": sum(r["correct"] for r in results) / len(results),
            "sql_errors": sum(r["error"] is not None for r in results),
            "by_category": {c: sum(v) / len(v) for c, v in sorted(by_cat.items())},
        }
        log.info(
            "%s: accuracy %.1f%%", condition, 100 * summary["conditions"][condition]["accuracy"]
        )
    summary["usage"] = {
        "tokens_in": llm.tokens_in,
        "tokens_out": llm.tokens_out,
        "cost_usd": round(llm.cost_usd, 4),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary
