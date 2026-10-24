"""Build eval/v1/questions.jsonl: templated + hand-written questions with gold SQL and answers.

Gold SQL is written against the `semantic` schema of the frozen snapshot (finfacts_eval_v1).
Gold answers are computed by running it there, so they match the published snapshot exactly.
Template sampling uses a fixed seed: rebuilding gives the same questions.
"""

import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import duckdb
import yaml

SEED = 2026
YEARS = range(2018, 2026)

# (cik, ticker, short name, sector). Well-known S&P 500 companies across all FYE patterns.
COMPANIES = [
    (320193, "AAPL", "Apple", "Information Technology"),
    (789019, "MSFT", "Microsoft", "Information Technology"),
    (1045810, "NVDA", "NVIDIA", "Information Technology"),
    (1018724, "AMZN", "Amazon", "Consumer Discretionary"),
    (1652044, "GOOGL", "Alphabet", "Communication Services"),
    (1326801, "META", "Meta Platforms", "Communication Services"),
    (19617, "JPM", "JPMorgan Chase", "Financials"),
    (2115436, "XOM", "ExxonMobil", "Energy"),
    (200406, "JNJ", "Johnson & Johnson", "Health Care"),
    (104169, "WMT", "Walmart", "Consumer Staples"),
    (80424, "PG", "Procter & Gamble", "Consumer Staples"),
    (21344, "KO", "Coca-Cola", "Consumer Staples"),
    (77476, "PEP", "PepsiCo", "Consumer Staples"),
    (1065280, "NFLX", "Netflix", "Communication Services"),
    (50863, "INTC", "Intel", "Information Technology"),
    (858877, "CSCO", "Cisco", "Information Technology"),
    (1341439, "ORCL", "Oracle", "Information Technology"),
    (796343, "ADBE", "Adobe", "Information Technology"),
    (1108524, "CRM", "Salesforce", "Information Technology"),
    (909832, "COST", "Costco", "Consumer Staples"),
    (354950, "HD", "Home Depot", "Consumer Discretionary"),
    (63908, "MCD", "McDonald's", "Consumer Discretionary"),
    (320187, "NKE", "Nike", "Consumer Discretionary"),
    (1744489, "DIS", "Disney", "Communication Services"),
    (12927, "BA", "Boeing", "Industrials"),
    (18230, "CAT", "Caterpillar", "Industrials"),
    (40545, "GE", "General Electric", "Industrials"),
    (51143, "IBM", "IBM", "Information Technology"),
    (78003, "PFE", "Pfizer", "Health Care"),
    (310158, "MRK", "Merck", "Health Care"),
    (731766, "UNH", "UnitedHealth", "Health Care"),
    (93410, "CVX", "Chevron", "Energy"),
    (732717, "T", "AT&T", "Communication Services"),
    (732712, "VZ", "Verizon", "Communication Services"),
    (70858, "BAC", "Bank of America", "Financials"),
    (72971, "WFC", "Wells Fargo", "Financials"),
    (886982, "GS", "Goldman Sachs", "Financials"),
    (1318605, "TSLA", "Tesla", "Consumer Discretionary"),
    (2488, "AMD", "AMD", "Information Technology"),
    (59478, "LLY", "Eli Lilly", "Health Care"),
]
SECTORS = sorted({c[3] for c in COMPANIES})
VALUE_METRICS = {
    "revenue": "revenue",
    "net_income": "net income",
    "total_assets": "total assets",
    "operating_cash_flow": "operating cash flow",
    "capex": "capital expenditure",
    "total_equity": "shareholders' equity",
    "cash_and_equivalents": "cash and cash equivalents",
    "research_and_development": "R&D expense",
    "eps_diluted": "diluted earnings per share",
    "long_term_debt": "long-term debt",
}
RANK_METRICS = {
    "revenue": "revenue",
    "net_income": "net income",
    "free_cash_flow": "free cash flow",
}


@dataclass
class Question:
    id: str
    question: str
    category: str
    source: str  # template | handwritten
    answer_type: str  # number | integer | ticker | ticker_set | text
    gold_sql: str
    gold_answer: Any = None


def _fy(cik: int, metric: str, fy: int, period: str = "FY") -> str:
    return (
        f"select value from semantic.financials where cik = {cik} and metric_id = '{metric}'\n"
        f"  and fiscal_year = {fy} and fiscal_period = '{period}'"
    )


def templated(rng: random.Random) -> list[Question]:
    qs: list[Question] = []

    def pick(n: int, make: Any) -> None:
        seen: set[str] = set()
        while sum(1 for q in qs if q.category == make.__name__) < n:
            q = make()
            if q.question not in seen:
                seen.add(q.question)
                qs.append(q)

    def value() -> Question:
        cik, tk, name, _ = rng.choice(COMPANIES)
        m = rng.choice(list(VALUE_METRICS))
        fy = rng.choice(YEARS)
        unit = " (USD per share)" if m == "eps_diluted" else " (USD)"
        return Question(
            "",
            f"What was {name}'s ({tk}) {VALUE_METRICS[m]} in fiscal year {fy}{unit}?",
            "value",
            "template",
            "number",
            _fy(cik, m, fy),
        )

    def quarterly() -> Question:
        cik, tk, name, _ = rng.choice(COMPANIES)
        fy, q = rng.choice(YEARS), rng.randint(1, 4)
        return Question(
            "",
            f"What was {name}'s ({tk}) revenue in fiscal Q{q} {fy} (USD)?",
            "quarterly",
            "template",
            "number",
            _fy(cik, "revenue", fy, f"Q{q}"),
        )

    def growth() -> Question:
        cik, tk, name, _ = rng.choice(COMPANIES)
        fy = rng.choice(YEARS)
        sql = (
            "select (cur.value / prev.value - 1) * 100 from\n"
            f"  ({_fy(cik, 'revenue', fy)}) as cur,\n"
            f"  ({_fy(cik, 'revenue', fy - 1)}) as prev"
        )
        return Question(
            "",
            f"By what percentage did {name}'s ({tk}) revenue change from fiscal {fy - 1} "
            f"to fiscal {fy}?",
            "growth",
            "template",
            "number",
            sql,
        )

    def margin() -> Question:
        cik, tk, name, _ = rng.choice(COMPANIES)
        fy = rng.choice(YEARS)
        sql = (
            f"select value * 100 from semantic.financials where cik = {cik}\n"
            f"  and metric_id = 'net_margin' and fiscal_year = {fy} and fiscal_period = 'FY'"
        )
        return Question(
            "",
            f"What was {name}'s ({tk}) net margin in fiscal {fy}, in percent?",
            "margin",
            "template",
            "number",
            sql,
        )

    def sector_total() -> Question:
        sector, fy = rng.choice(SECTORS), rng.choice(YEARS)
        sql = (
            "select sum(f.value) from semantic.financials as f\n"
            "  join semantic.companies as c using (cik)\n"
            f"where c.gics_sector = '{sector}' and f.metric_id = 'revenue'\n"
            f"  and f.fiscal_year = {fy} and f.fiscal_period = 'FY'"
        )
        return Question(
            "",
            f"What was the combined revenue of all S&P 500 companies in the {sector} sector "
            f"in fiscal year {fy} (USD)?",
            "sector_total",
            "template",
            "number",
            sql,
        )

    def ranking() -> Question:
        sector, fy = rng.choice(SECTORS), rng.choice(YEARS)
        m = rng.choice(list(RANK_METRICS))
        sql = (
            "select c.tickers from semantic.financials as f\n"
            "  join semantic.companies as c using (cik)\n"
            f"where c.gics_sector = '{sector}' and f.metric_id = '{m}'\n"
            f"  and f.fiscal_year = {fy} and f.fiscal_period = 'FY'\n"
            "order by f.value desc limit 1"
        )
        return Question(
            "",
            f"Which {sector} company in the S&P 500 had the highest {RANK_METRICS[m]} in "
            f"fiscal year {fy}? Answer with its ticker.",
            "ranking",
            "template",
            "ticker",
            sql,
        )

    def as_reported() -> Question:
        cik, tk, name, _ = rng.choice(COMPANIES)
        fy = rng.choice(YEARS)
        sql = (
            "select value from semantic.financials_history\n"
            f"where cik = {cik} and metric_id = 'revenue' and fiscal_year = {fy}\n"
            "  and fiscal_period = 'FY' and version_no = 1"
        )
        return Question(
            "",
            f"As originally reported (before any later restatement), what was {name}'s "
            f"({tk}) revenue for fiscal year {fy} (USD)?",
            "as_reported",
            "template",
            "number",
            sql,
        )

    def restatements() -> Question:
        cik, tk, name, _ = rng.choice(COMPANIES)
        fy = rng.choice(YEARS)
        sql = (
            "select max(version_no) - 1 from semantic.financials_history\n"
            f"where cik = {cik} and metric_id = 'revenue' and fiscal_year = {fy}\n"
            "  and fiscal_period = 'FY'"
        )
        return Question(
            "",
            f"How many times was {name}'s ({tk}) fiscal {fy} revenue revised after it was "
            "first reported?",
            "restatements",
            "template",
            "integer",
            sql,
        )

    for make, n in [
        (value, 40),
        (quarterly, 15),
        (growth, 15),
        (margin, 10),
        (sector_total, 10),
        (ranking, 10),
        (as_reported, 5),
        (restatements, 5),
    ]:
        pick(n, make)
    return qs


def handwritten(path: Path) -> list[Question]:
    rows = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [
        Question("", r["question"], r["category"], "handwritten", r["answer_type"], r["gold_sql"])
        for r in rows
    ]


def answer(con: duckdb.DuckDBPyConnection, q: Question) -> Any:
    rows = con.sql(q.gold_sql).fetchall()
    if q.answer_type == "ticker_set":
        return [r[0] for r in rows]
    if not rows or rows[0][0] is None:
        return None
    v = rows[0][0]
    return float(v) if q.answer_type == "number" else int(v) if q.answer_type == "integer" else v


def build(snapshot: Path, handwritten_path: Path, out: Path) -> list[Question]:
    """Templated questions are kept only if their gold answer exists (resampled otherwise)."""
    rng = random.Random(SEED)  # noqa: S311 - reproducible sampling, not security
    with duckdb.connect(str(snapshot), read_only=True) as con:
        kept: list[Question] = []
        # Oversample templates, then keep the first answerable ones per category.
        targets = {
            "value": 40,
            "quarterly": 15,
            "growth": 15,
            "margin": 10,
            "sector_total": 10,
            "ranking": 10,
            "as_reported": 5,
            "restatements": 5,
        }
        pool = templated(rng) + templated(rng) + templated(rng)
        for q in pool:
            if sum(1 for k in kept if k.category == q.category) >= targets[q.category]:
                continue
            if any(k.question == q.question for k in kept):
                continue
            q.gold_answer = answer(con, q)
            if q.gold_answer is not None:
                kept.append(q)
        for q in handwritten(handwritten_path):
            q.gold_answer = answer(con, q)
            if q.gold_answer is None or q.gold_answer == []:
                raise ValueError(f"hand-written question has no answer: {q.question}")
            kept.append(q)
    for i, q in enumerate(kept, 1):
        q.id = f"ff-v1-{i:03d}"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as fh:
        for q in kept:
            fh.write(json.dumps(asdict(q), ensure_ascii=False) + "\n")
    return kept
