# Case study: FinFacts – one certified answer from SEC filings

**Role:** sole designer and engineer · **Time:** 6 weeks part-time (~55 hours) · **Cost:** EUR 0–2 per month · **Code:** [github.com/malavnaik99/finfacts](https://github.com/malavnaik99/finfacts) · **Live health page:** [malavnaik99.github.io/finfacts](https://malavnaik99.github.io/finfacts/)

## Context

SEC EDGAR is the source of truth for US company fundamentals, and every 10-K and 10-Q carries machine-readable XBRL. In practice two analysts, or two LLM agents, asking "what was Apple's revenue in 2024?" against the raw data often get different numbers.

## Problem

- **Tags vary.** Revenue appears under at least seven different XBRL concepts depending on company, year and sector. Some are totals, some are subsets.
- **Numbers get restated.** 4.6% of all facts change value in a later filing. A naive query mixes vintages without saying so.
- **Periods don't line up.** Fiscal years end in different months. Q4 is almost never filed as a 3-month number. SEC's own `fy` field describes the *filing*, not the fact.

## Constraints

About 10 hours a week for 6 weeks, a budget of EUR 0–15 a month, public data only, and production habits throughout: tests, idempotent jobs, infrastructure as code, no secrets in the repo.

## Approach

```
SEC bulk zips + daily submissions API (8 req/s)
  → bronze: immutable, append-only files in GCS
  → flatten to parquet → BigQuery raw (free load jobs)
  → dbt: silver (restatement history) → gold (21 certified metrics, point-in-time)
  → every test in an `audit` dataset → publish to `gold` only if all pass
  → MetricFlow semantic layer → eval set, text-to-SQL baseline, 10-K embeddings
```

One `finfacts` CLI runs locally on DuckDB and in production on BigQuery from a daily GitHub Actions workflow with keyless Workload Identity.

## Key decisions and trade-offs

| Decision | Why | Trade-off |
|---|---|---|
| Version every fact by SEC acceptance date | Answers "what did we know on date X?" and keeps restatements visible | 660k versioned rows instead of 600k |
| One XBRL concept per company, metric and period, totals before subsets | A number is never a blend of tags, and `source_concept` shows where it came from | Some company-years stay empty rather than guessed |
| Derive missing quarters (Q4 = FY − 9M) only from the *same* concept | Subtracting a subset from a total produced 909 wrong quarters, 18 of them negative revenue | About 900 quarters stay empty |
| Write-audit-publish with BigQuery copy jobs | Consumers never see untested data; copies are free and atomic | Two copies of gold tables in storage (free tier) |
| GitHub Actions instead of hosted Airflow | Hosted Airflow costs about EUR 300 a month for one daily job | Airflow was cut from scope |
| Calibrated identity-check gates (balance sheet ≤ 2.5%, gross profit ≤ 6%) instead of 1% | Remaining failures are company tagging errors and businesses where gross profit isn't revenue − cost | Every failing row is published instead of hidden |
| Load only the newest companyfacts file per company | Each file holds the full history; scans stay flat as snapshots pile up (3.8 GB → 1.9 GB) | Relies on SEC keeping full history in each file |

## Results

| | |
|---|---|
| Coverage | 498 companies, FY2015 to today, 21 certified metrics; revenue, net income and total assets for ≥ 97.7% of company-years |
| Correctness | 30/30 golden values read from 10-K statements match *as known the day after filing*; the semantic layer equals plain SQL for 5,320 company-years |
| Reliability | Daily runs green since launch; a deliberate test failure (WAP drill) left `gold` untouched |
| 10-K retrieval | 87,082 chunks of Item 1A and Item 7 from 1,067 FY2024+ 10-Ks; 10/10 smoke-test questions retrieve a relevant company's text in the top 5 |
| Cost | ~9 GB scanned per daily run (~270 GB/month, inside BigQuery's free 1 TB); EUR 0 so far |
| Eval set | 150 questions with gold SQL; text-to-SQL execution accuracy with the same model (`anthropic/claude-haiku-5.5`) rose from **67.3% on raw XBRL facts to 100.0% on the semantic layer** (raw: 0% on derived Q4s, top-N, sector shares and ExxonMobil's pre-2025 history). Total LLM cost: US$0.21 |

## What broke and how I fixed it

1. **Proxy statements looked like restatements.** Pay-versus-performance tables tag net income rounded to $0.1B, so JPMorgan's 2021 net income "changed" from $48,334M to $48,300M. Fixed by keeping only financial-statement filings.
2. **J&J was a year off every year.** SEC lists its fiscal year end as `0103` (one 52/53-week year ended on 3 January). The golden-value test caught it, and the same bug affected 11 companies.
3. **ExxonMobil had no history.** It re-registered under a new CIK in 2026. A checked mapping of 12 predecessor CIKs, cut off at each 8-K12B, restored FY2015+ for ExxonMobil, Disney, Broadcom and others. One CIK I had remembered was wrong, and checking against SEC caught it.
4. **The gold build would have failed on BigQuery.** A chain of CTEs referenced one CTE 170 times. Split into stored layers; locally the build also went from 13 s to 3 s.
5. **"Revenue by year" merged two fiscal years** for 25 company-years of 52/53-week companies. Annual semantic-layer metrics now use a fiscal-year time axis, and the check compares against fiscal year so this class of error can't return.

### How to read the eval result

The questions and gold SQL were written against FinFacts' semantic schema, and FinFacts' mapping defines the gold value (e.g. which revenue tag counts). That favours the "after" condition by design. The result measures how much the certified layer helps a model answer correctly, not how hard raw XBRL is in general. The categories where raw data scores 0% (derived Q4s, top-N, sector shares, a company that changed CIK) are the problems FinFacts was built to solve.

## What I'd do next

- Incremental dbt models, to bring the ~9 GB per run under 2 GB.
- Historical index membership, to remove survivorship bias.
- Use the eval set as the regression suite for the text-to-SQL agent and the MCP server built on top.
