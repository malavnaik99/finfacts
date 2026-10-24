# Demo video script (4–5 minutes)

**Setup:** terminal in the repo, browser tabs open on the health page, BigQuery console, GitHub Actions and the Hugging Face dataset.

## 0:00 – Hook (40 s)
- Ask: "What was ExxonMobil's revenue in fiscal 2016?" Show three raw-XBRL answers: `Revenues` from the 2017 10-K, the restated value from the 2018 10-K, and nothing at all under ExxonMobil's current CIK.
- Line: "Same question, same source, three answers. FinFacts gives one certified answer, and tells you when it changed."

## 0:40 – Architecture (40 s)
- README diagram: SEC → append-only GCS → BigQuery raw → dbt silver/gold → audit → publish → semantic layer → eval and embeddings.
- Point out: daily GitHub Actions, keyless Workload Identity, about EUR 0 a month.

## 1:20 – Write-audit-publish (70 s)
- GitHub Actions: run `daily` with `wap_drill = true`. The dbt step fails on the drill test and publish is skipped.
- BigQuery console: `gold.fct_financials` last-modified time is unchanged. "Consumers never see untested data."
- Health page: the failed run appears in "Recent runs".

## 2:30 – Point-in-time (40 s)
- `make demo-query`: Apple quarterly revenue with derived Q4s marked.
- SQL: IBM FY2019 revenue as first reported ($77.1B) vs today ($57.7B, after the Kyndryl spin-off).

## 3:10 – Semantic layer (40 s)
- `mf query --metrics revenue,net_margin --group-by company__ticker,metric_time__year` for AAPL.
- `make semantic-check`: 5,320 company-years equal plain SQL. Margins are ratio metrics, weighted correctly across companies.

## 3:50 – AI outputs (40 s)
- Hugging Face dataset: 150 questions with gold SQL; 15/15 cross-checked against SEC's API.
- `make eval`: the same model before vs after the semantic layer.
- `finfacts search "Medicare Advantage medical cost trends"`: top 10-K chunks from managed-care companies.

## 4:30 – Close (20 s)
- Cost per run on the health page, about EUR 0 a month.
- "Projects 3 and 4 – a text-to-SQL agent and an MCP server – are built on exactly this layer."
