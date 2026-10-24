---
license: cc-by-4.0
language:
  - en
pretty_name: FinFacts – SEC fundamentals eval set and 10-K chunks
size_categories:
  - 10K<n<100K
task_categories:
  - table-question-answering
  - text-retrieval
tags:
  - finance
  - sec-edgar
  - xbrl
  - text-to-sql
  - point-in-time
configs:
  - config_name: eval
    data_files: eval/questions.jsonl
  - config_name: financials
    data_files: tables/financials.parquet
  - config_name: financials_history
    data_files: tables/financials_history.parquet
  - config_name: companies
    data_files: tables/companies.parquet
  - config_name: metrics
    data_files: tables/metrics.parquet
  - config_name: tenk_chunks
    data_files: tenk/tenk_chunks.parquet
---

# FinFacts: SEC fundamentals eval set and 10-K chunks

Built by [FinFacts](https://github.com/malavnaik99/finfacts), a pipeline that turns SEC EDGAR XBRL filings for the S&P 500 into certified, point-in-time-correct fundamentals. Snapshot date: **{snapshot_date}**.

## What's inside

| Config | Rows | What it is |
|---|---|---|
| `eval` | {n_questions} | Natural-language questions with **gold SQL** and **gold answers** |
| `financials` | {n_financials} | Current certified value per company × metric × fiscal period |
| `financials_history` | {n_history} | Every value over time (`version_no` 1 = as first reported) |
| `companies` | {n_companies} | Companies, tickers, GICS sector, fiscal year end |
| `metrics` | {n_metrics} | Metric definitions |
| `tenk_chunks` | {n_chunks} | 10-K Item 1A (Risk Factors) and Item 7 (MD&A), FY2024+, ~600-word chunks with `BAAI/bge-small-en-v1.5` embeddings |

## Eval set

- **{n_template} templated questions**: single values, quarters, growth, margins, sector totals, rankings, as-originally-reported and restatement counts.
- **{n_hand} hand-written hard questions**: fiscal-calendar traps (Walmart's FY2025 ends in January 2025; J&J's 52/53-week years), bank revenue, a company that re-registered under a new CIK (ExxonMobil), derived Q4s, medians, CAGR, top-N and restatements.
- Each row has `question`, `gold_sql` (DuckDB, against the tables in this dataset loaded as schema `semantic`), `gold_answer`, `answer_type` (`number` scored within 0.5%, `integer` exact, `ticker` any of the company's tickers, `ticker_set` same companies in any order, `text` exact) and `category`.
- **Verification:** 15 answers (10%) were cross-checked against SEC's own `companyconcept` API, a different access path from the bulk files the pipeline uses. Result: 15/15 match (`eval/verification.csv`).

### Text-to-SQL baseline

{eval_results}

## Point-in-time

`financials_history` keeps every version of every value with `valid_from` / `valid_to` (SEC acceptance dates). "What was known on 2021-06-01?" is `valid_from <= '2021-06-01' and (valid_to is null or valid_to > '2021-06-01')`.

## Sources and licence

- Financial facts and 10-K text: SEC EDGAR (public data; accessed under SEC's fair-access policy). Company list: S&P 500 constituents from `datasets/s-and-p-500-companies` (ODC-PDDL). "S&P 500" is a trademark of S&P Dow Jones Indices; this dataset is not affiliated with or endorsed by S&P.
- The questions, gold SQL, derived tables and documentation are released under **CC BY 4.0**.
- Not investment advice. Values come from companies' XBRL tags and FinFacts' documented mapping rules; see the [concept mapping](https://github.com/malavnaik99/finfacts/blob/main/docs/concept_mapping.md) for known limitations.
