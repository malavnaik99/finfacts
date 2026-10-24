# FinFacts – Plan

> Status: **DRAFT – waiting for approval.** No code, packages or cloud resources have been created.
> Author: Malav Naik · Repo: `malavnaik99/finfacts` · Plan date: 2026-10-20 · Budget: 6 weeks × 8–10 h

---

## 1. Problem, users, success metrics

### Problem
SEC filings are the source of truth for US company fundamentals, but they are hard to query consistently:

- **Tags vary.** "Revenue" appears as `Revenues`, `RevenueFromContractWithCustomerExcludingAssessedTax`, `SalesRevenueNet` and others, depending on the company, the year (ASC 606 changed tags in 2018) and the sector.
- **Figures get restated.** The same period's value changes in later filings. A naive query silently mixes vintages.
- **Periods don't line up.** Fiscal years end in different months. Q4 is rarely reported directly (it is FY minus 9M YTD). The `fy`/`fp` fields in `companyfacts` describe the *filing*, not the fact, which is a common and silent source of bugs.

Analysts and LLM agents asking the same question get different answers.

FinFacts publishes **one certified, point-in-time-correct fundamentals mart plus a semantic layer**. A human with SQL, a text-to-SQL agent (project 3) and an MCP server (project 4) then all get the same number, with a traceable source concept and accession number.

### Users
| User | Needs |
|---|---|
| Analyst / data scientist | Clean SQL tables and "as-of" queries without XBRL knowledge |
| LLM agent (text-to-SQL, MCP) | A small, documented, unambiguous schema and metric definitions |
| Hiring manager / reviewer | Evidence of production habits: tests, lineage, cost control, docs |

### Success metrics (measured, shown on the data-health page)
| Metric | Target | How it is measured |
|---|---|---|
| Freshness SLA | New 10-K/10-Q facts in the gold mart within **24 h** of SEC acceptance on ≥ 95% of days | `max(published_at − filing accepted_at)` per daily run |
| Blocking test pass rate on published data | **100%** (guaranteed by write-audit-publish) | dbt `run_results.json` |
| Warn-level test pass rate | ≥ 98% | dbt `run_results.json` |
| Full backfill time (S&P 500, FY2015+) | < 30 min locally from bulk zips; < 10 min BigQuery load | Timed `make backfill` |
| Bytes scanned per daily run | < 2 GB (→ < 60 GB/month, inside the 1 TB free tier) | `INFORMATION_SCHEMA.JOBS` by run label |
| Metric coverage | ≥ 95% of company-years have revenue, net income and total assets | dbt test on `fct_financials` |
| Mapping accuracy | 30/30 hand-checked values match the filed 10-K | `tests/golden/hand_checked.csv` |
| Text-to-SQL execution accuracy | Report **before vs after** the semantic layer on the eval set. Hypothesis: +20 pp | `make eval` |
| GCP cost | < EUR 5/month (hard alert at EUR 15) | Billing budget |

---

## 2. Prerequisites

**Detected OS:** Windows 11 Home (10.0.26300), 12 CPU threads. Commands below are for **Git Bash** unless marked PowerShell. I recommend running everything natively on Windows from Git Bash, with Airflow inside Docker through the Astro CLI. WSL2 is already present (Docker Desktop backend) but not required.

### Tools
| Tool | Version | Status today | Install (PowerShell) | Verify |
|---|---|---|---|---|
| Git | ≥ 2.40 | ✅ 2.45.1 | — | `git --version` |
| Python | 3.11.x | ✅ 3.11.9 | — | `python --version` |
| uv (Python env + lockfile) | ≥ 0.5 | ✅ 0.12.23 | — | `uv --version` |
| Docker Desktop | ≥ 4.30 (engine ≥ 25) | ⚠️ installed (29.7.2), daemon looked stopped | Start Docker Desktop; give it ≥ 6 GB RAM (Settings → Resources) | `docker run --rm hello-world` |
| Node.js (Evidence site) | ≥ 20 | ✅ 24.4.1 | — | `node --version` |
| GNU Make | ≥ 4.3 | ❌ missing | `winget install ezwinports.make` | `make --version` |
| GitHub CLI | ≥ 2.50 | ❌ missing | `winget install GitHub.cli` then `gh auth login` | `gh auth status` |
| Google Cloud CLI | latest | ❌ missing | `winget install Google.CloudSDK` | `gcloud --version` |
| Terraform | ≥ 1.9 | ❌ missing | `winget install Hashicorp.Terraform` | `terraform -version` |
| Astro CLI (local Airflow) | ≥ 1.30 | ❌ missing | `winget install -e --id Astronomer.Astro` | `astro version` |
| DuckDB CLI (optional, for poking at data) | ≥ 1.1 | ❌ missing | `winget install DuckDB.cli` | `duckdb --version` |

Python libraries (dbt-core, dbt-duckdb, dbt-bigquery, dbt-metricflow, httpx, tenacity, pydantic, typer, edgartools, lancedb, sentence-transformers and others) are **not** prerequisites. They are pinned in `pyproject.toml` / `uv.lock` in Week 1 and installed with `uv sync`. Exact versions get locked then.

### Accounts and keys
| Account / key | Needed from | Cost | Where it lives | Verify |
|---|---|---|---|---|
| GitHub (`malavnaik99`) | Week 1 | free | already have | `gh auth status` |
| SEC User-Agent string, e.g. `FinFacts/0.1 your-email@example.com` | Week 1 | free, no key | `.env` → `SEC_USER_AGENT` (never committed) | `make check-env` |
| Google Cloud project with **billing enabled** (sandbox cannot run DML/MERGE) | Week 4 | ~EUR 0–2/mo | `gcloud auth login` + `gcloud auth application-default login` | `gcloud projects describe $GCP_PROJECT_ID` |
| GCP budget alerts at EUR 5 and EUR 15 | Week 4 (created by Terraform) | free | Terraform | `gcloud billing budgets list --billing-account=$BILLING_ACCOUNT` |
| Hugging Face account + **write** token | Week 6 | free | `.env` → `HF_TOKEN` | `uv run huggingface-cli whoami` |
| OpenRouter API key for the before/after text-to-SQL baseline (Q4) | Week 6 | ~EUR 1–3 total (prepaid credits) | `.env` → `OPENROUTER_API_KEY`; model id in `.env` → `EVAL_MODEL` | `curl -s -o /dev/null -w "%{http_code}\n" https://openrouter.ai/api/v1/key -H "Authorization: Bearer $OPENROUTER_API_KEY"` → `200` |

GitHub Actions authenticates to GCP with **Workload Identity Federation** (no JSON service-account keys anywhere).

---

## 3. Architecture

```mermaid
flowchart LR
  subgraph SEC["SEC EDGAR (public)"]
    BZ[companyfacts.zip<br/>submissions.zip]
    API[data.sec.gov<br/>submissions / companyfacts / frames]
    DOC[10-K HTML<br/>sec.gov/Archives]
  end

  subgraph ING["Ingestion (Python CLI: finfacts)"]
    CL[SEC client<br/>8 req/s token bucket · retries · UA]
    BF[backfill: bulk zips → per-CIK files]
    INC[incremental: accession high-water mark]
    TX[text: Item 1A + Item 7 extract]
  end

  subgraph BRZ["Bronze – immutable (GCS / local data/)"]
    B1[(companyfacts/ingest_date=…/CIK.json.gz)]
    B2[(submissions/…)]
    B3[(filings_text/accn.json.gz)]
  end

  subgraph WH["Warehouse – dbt (DuckDB local+CI · BigQuery prod)"]
    S[silver: stg_facts · int_fact_versions<br/>dedup + restatement history]
    AUD[audit dataset<br/>gold built here first]
    T{dbt tests + contracts<br/>freshness · volume · identities}
    G[gold: dim_company · dim_period · dim_concept<br/>fct_financials · fct_financials_latest]
    SL[semantic layer<br/>MetricFlow YAML]
  end

  subgraph OUT["Outputs"]
    H[data-health page<br/>Evidence → GitHub Pages]
    E[eval set 150–300 Q<br/>Hugging Face]
    V[(10-K chunks + embeddings<br/>LanceDB + HF parquet)]
    P3[project 3: text-to-SQL]
    P4[project 4: MCP server]
  end

  BZ --> BF --> B1 & B2
  API --> CL --> INC --> B1 & B2
  DOC --> CL --> TX --> B3
  B1 & B2 --> S --> AUD --> T
  T -- pass --> G --> SL
  T -- fail --> ALERT[alert: failed GH Actions run → email]
  G --> H & E
  B3 --> V
  SL --> P3 & P4
  G -.OpenLineage.-> MQ[Marquez (local)]
```

### Data flow
1. **Universe.** A dated S&P 500 constituent snapshot (CSV in `config/universe/`) is joined to SEC `company_tickers.json` to get the CIKs (~503).
2. **Backfill (once).** Download `companyfacts.zip` and `submissions.zip` (≈1–2 GB each). Extract only in-scope CIKs, gzip them, and write to bronze under `ingest_date=YYYY-MM-DD/`. Bronze is write-once: if the object exists, skip it.
3. **Daily incremental.** For each CIK, call `submissions/CIK##########.json` (503 calls ≈ 65 s at 8 req/s). Compare against the stored **accession high-water mark** in `ops.ingest_state`. Only CIKs with new 10-K/10-Q/8-K-with-XBRL accessions get a fresh `companyfacts` pull. That is typically 0–60 CIKs a day, so a run takes a couple of minutes. Reruns of the same day are no-ops.
4. **Flatten + silver.** `finfacts flatten` turns each bronze JSON file into a long parquet file (one row per fact, no business logic), so DuckDB and BigQuery read the same input. *(Changed 2026-10-20, approved: flattening dynamic-key JSON in SQL would need separate DuckDB and BigQuery code.)* Then in dbt: Remove exact duplicates (the same fact repeats as comparatives in later filings). Build `int_fact_versions` with `version_no`, `valid_from = filed`, `valid_to`, `is_restatement`.
5. **Write-audit-publish.** dbt builds gold into the **audit** dataset and runs all tests. Only if every `error`-severity test passes does `finfacts publish` swap tables into the public `gold` dataset. BigQuery table copies are free and atomic per table. On failure the run exits non-zero, the GitHub Actions failure email fires, and the last good gold stays live.
6. **Semantic layer.** MetricFlow YAML on top of gold defines the ~20 certified metrics once.
7. **Outputs.** The health page is built from dbt artifacts plus an `ops.run_log` table. The eval set and text chunks are exported to Hugging Face.

**Point-in-time correctness:** every gold fact carries `accession_number`, `filed_date`, `valid_from` and `valid_to`. "What did we know on 2021-03-01?" becomes `WHERE valid_from <= '2021-03-01' AND (valid_to IS NULL OR valid_to > '2021-03-01')`. A dbt macro `as_of(date)` wraps this, and `fct_financials_latest` is the convenience view.

---

## 4. Stack choices

| Layer | Choice | Why (one line) |
|---|---|---|
| Language | Python 3.11 + uv | Fast reproducible envs with a lockfile; matches Airflow images |
| HTTP | httpx + tenacity + a token-bucket limiter | Simple, typed, testable throttling (8 req/s) with exponential backoff on 429/5xx |
| CLI | Typer (`finfacts backfill|incremental|publish|text|eval`) | One entry point shared by Make, Airflow and GitHub Actions |
| Transform | dbt Core | Industry standard; tests, contracts, docs and lineage built in |
| Local/CI warehouse | DuckDB (dbt-duckdb) | Zero cost, reads the same bronze files, CI runs in seconds |
| Prod warehouse | BigQuery (US multi-region) | Free 1 TB/month queries + 10 GB storage; MERGE needs billing enabled |
| Raw storage | GCS bucket (us-central1) | GCS free tier only applies in US regions; bronze stays tiny |
| Orchestration (local) | ~~Airflow 3 via Astro CLI~~ *(cut 2026-10-21, approved: a local-only demo DAG; Make targets + GitHub Actions run everything)* | — |
| Scheduling (prod) | **GitHub Actions cron** | Free for public repos. Hosted Airflow (Composer) costs ≈ EUR 300+/month — see Q1 |
| Semantic layer | dbt MetricFlow (`dbt-metricflow`, `mf` CLI) | Works with dbt Core on both DuckDB and BigQuery |
| Data quality | dbt tests + dbt_utils + model contracts | One tool instead of two; enough for identities, freshness and volume |
| Lineage | dbt docs lineage graph (`dbt docs generate`) *(OpenLineage + Marquez cut 2026-10-21, approved: local-only demo)* | Free, already produced by dbt |
| 10-K section extraction | edgartools (MIT) for Item 1A / Item 7 | Section parsing in 10-K HTML is notoriously messy; don't rebuild it |
| Embeddings | `BAAI/bge-small-en-v1.5` locally (sentence-transformers) | Free, good retrieval quality, runs on a CPU |
| Vector store | LanceDB (local files) + parquet on Hugging Face | Free and portable; projects 3 and 4 can load it directly |
| Health page / dashboard | Evidence (static) → GitHub Pages | Zero hosting cost, no live credentials, SQL-native |
| IaC | Terraform (google provider) | Bucket, datasets, service account, WIF, budgets in code |
| Lint / types / tests | ruff, mypy (strict on `src/`), pytest, sqlfluff (dbt templater) | Standard, fast, enforced in CI |

**Rejected or deferred**
- **Cloud Composer / Astro Cloud** – cost far above budget for one daily DAG.
- **Soda Core** – overlaps dbt tests. A second DSL adds learning time with no new signal.
- **PyIceberg** – kept as a stretch goal (Week 6+). BigQuery-native tables are enough for the core story. It can later be added as an Iceberg export of the gold mart.
- **BigQuery vector search** – it costs money per query and ties projects 3 and 4 to GCP. LanceDB is free.
- **Streamlit** – needs a running server and live warehouse credentials. A static Evidence site is safer and free.
- **Hand-written XBRL instance parsing (Arelle)** – the SEC JSON APIs already give normalised facts.

---

## 5. Data model

Data volume estimate: ~503 companies × ~40–80k facts each (us-gaap + dei, FY2015+) ≈ **20–40 M silver rows, ~3–6 GB**. Gold is ~1–2 M rows.

| Layer | Table | Grain | Key | Partition / cluster (BigQuery) |
|---|---|---|---|---|
| ops | `ingest_state` | 1 row per CIK | `cik` | — (tiny) |
| ops | `run_log` | 1 row per pipeline run | `run_id` | partition `DATE(started_at)` |
| bronze | files only | 1 file per CIK per ingest date | path | GCS prefix `ingest_date=` |
| silver | `stg_companyfacts` | 1 row per fact *as it appears in one filing* | `(cik, taxonomy, concept, unit, period_start, period_end, accn)` | partition `filed_date` (month), cluster `cik, concept` |
| silver | `stg_submissions` | 1 row per filing | `accn` | cluster `cik` |
| silver | `int_fact_versions` | 1 row per distinct value of a fact over time | `(fact_key, version_no)` | partition `period_end` (month), cluster `cik, concept` |
| gold | `dim_company` | 1 row per company (SCD2 on name/ticker/SIC) | `company_sk`; natural key `cik` | — |
| gold | `dim_period` | 1 row per company fiscal period | `period_sk`; `(cik, fiscal_year, fiscal_period)` | — |
| gold | `dim_concept` | 1 row per certified metric | `metric_id` | — |
| gold | `fct_financials` | 1 row per company × metric × fiscal period × version | `(cik, metric_id, period_sk, version_no)` | partition `period_end` (year), cluster `cik, metric_id` |
| gold | `fct_financials_latest` | Latest version only (view) | `(cik, metric_id, period_sk)` | view |

Key columns in `fct_financials`: `value`, `unit`, `source_taxonomy`, `source_concept`, `mapping_rule_id`, `accession_number`, `form`, `filed_date`, `valid_from`, `valid_to`, `is_restatement`, `is_derived` (e.g. Q4 = FY − 9M YTD, FCF = OCF − capex).

**Fiscal periods:** derived from `period_start`/`period_end` and the company's `fiscalYearEnd` from submissions, **not** from the fact's `fy`/`fp` fields. Duration facts are classified as 3M, 6M, 9M or 12M by day count (±10 days tolerance). `dim_period` also carries `calendar_quarter` using the SEC `frame` convention (CYyyyyQn), so companies with different year-ends can be compared.

**Concept mapping** (`dbt/seeds/concept_map.csv` + `docs/concept_mapping.md`): `metric_id, taxonomy, concept, priority, sign, valid_from_fy, valid_to_fy, sector_scope, rationale`. For each company-period the highest-priority concept that has a value wins, and the winner is recorded in `source_concept`. Initial ~20 metrics:

Revenue · Cost of revenue · Gross profit · Operating income · Net income (to parent) · Diluted EPS · Diluted shares · R&D · SG&A · Total assets · Total liabilities · Total equity · Cash & equivalents · Total debt · Operating cash flow · Capex · Dividends paid · **Derived:** Free cash flow, Gross margin, Operating margin, Net margin.

Financials (banks, insurers) do not have a clean "revenue" or "gross profit". They get explicit sector rules or a documented `NULL` rather than a wrong number (see Q3).

---

## 6. Repo structure

```
finfacts/
├─ README.md · CHANGELOG.md · LICENSE (MIT) · DATA_LICENSES.md · PLAN.md
├─ Makefile · pyproject.toml · uv.lock · .env.example · .gitignore · .pre-commit-config.yaml
├─ config/
│  ├─ site.toml                 # site_url = "https://malavnaik99.github.io" (single source)
│  └─ universe/sp500_2026-10-20.csv
├─ src/finfacts/
│  ├─ cli.py · settings.py      # pydantic-settings, reads env only
│  ├─ sec/client.py · sec/rate_limit.py
│  ├─ ingest/universe.py · ingest/bulk.py · ingest/incremental.py · ingest/text.py
│  ├─ storage.py                # local dir or GCS behind one small interface
│  ├─ publish.py                # write-audit-publish swap
│  ├─ health.py                 # run_log, bytes billed, freshness
│  ├─ ai/chunk.py · ai/embed.py
│  └─ eval/build.py · eval/run.py
├─ dbt/
│  ├─ dbt_project.yml · profiles.yml (env-var driven: duckdb | bq_audit | bq_prod)
│  ├─ models/staging/ · intermediate/ · marts/ · semantic/
│  ├─ seeds/concept_map.csv · macros/as_of.sql · tests/ (singular tests)
├─ infra/terraform/             # bucket, datasets, SA, WIF, budgets
├─ health/                      # Evidence site → GitHub Pages
├─ eval/                        # questions/v1/*.yaml, gold SQL, gold answers
├─ tests/                       # pytest; fixtures/ = 5 real CIKs trimmed (public data)
├─ docs/                        # concept_mapping.md, adr/, case-study.md, demo-script.md
└─ .github/workflows/ ci.yml · daily.yml · pages.yml
```

---

## 7. Data quality and testing strategy

| Level | What | Where | Blocks publish? |
|---|---|---|---|
| Unit | Rate limiter, retry policy, accession high-water mark logic, fiscal-period classifier, Q4 derivation, section chunker | pytest, recorded HTTP fixtures (respx); no network in CI | CI |
| Ingestion | HTTP 200 + JSON schema (pydantic); CIK in universe; file checksum before write | `finfacts` CLI | Run fails |
| Source | dbt source freshness (latest `filed_date` < 4 days on weekdays); volume (row count within ±20% of 7-day median, never shrinking in bronze) | dbt | **Yes** |
| Model contracts | Enforced column names, types, `not_null` on gold | dbt `contract: enforced` | **Yes** |
| Keys | `unique` + `not_null` on every grain key; relationships fct→dims | dbt | **Yes** |
| Accounting identities | `Assets = Liabilities + Equity` (incl. NCI) within 0.5%; `GrossProfit = Revenue − COGS` within 1%; `FCF = OCF − Capex` exactly | dbt singular tests | **Yes** for gold; failing rows listed in `quality.identity_checks`. *(Changed 2026-10-21, approved: the 1% exception cap became gates calibrated just above measured rates, balance sheet ≤ 2.5% and gross profit ≤ 6%. The remaining failures are company tagging errors and businesses where gross profit isn't revenue − cost.)* |
| Restatements | One open (`valid_to IS NULL`) version per fact key; versions non-overlapping | dbt | **Yes** |
| Golden values | 30 hand-checked numbers from 10-K PDFs (10 companies × 3 metrics) | dbt seed + test | **Yes** |
| Coverage | ≥ 95% of company-years have revenue / net income / assets | dbt | warn |
| CI | ruff, mypy, sqlfluff, pytest, `dbt build` on DuckDB against fixtures | GitHub Actions on every PR | merge |

Alerting: a failed `daily.yml` run sends GitHub's built-in failure email. If you want push notifications, an optional ntfy.sh topic is one extra step.

---

## 8. Milestones (6 weeks × 8–10 h)

Each week ends with green CI, README + CHANGELOG updated, a commit and a push.

**Week 1 – Foundations and ingestion (local)**
Scaffold the repo, add uv, ruff, mypy, pytest, pre-commit, Makefile and CI. Build the universe CSV → CIK mapping. Build the SEC client (8 req/s, retries, UA from env). Write the bulk backfill into local bronze, plus DATA_LICENSES.md.
*Done when:* `make backfill-local` writes ~503 gzipped CIK files to `data/bronze/`; rerunning it writes 0 new files; `make test` and the CI badge are green; `git grep -i "@"` shows no email or secret in tracked files.

**Week 2 – Silver and incremental**
dbt project on DuckDB: `stg_companyfacts`, `stg_submissions`, `int_fact_versions`, `dim_company`, `dim_period`. Incremental load driven by the accession high-water mark.
*Done when:* `make incremental` on an unchanged day makes ~503 submissions calls and pulls 0 companyfacts. `dbt build` passes the uniqueness and restatement tests. A known restatement (documented in `docs/`) shows 2 versions.

**Week 3 – Concept mapping and gold**
`concept_map.csv` plus `docs/concept_mapping.md` with every decision. Add `dim_concept`, `fct_financials`, the latest view, derived metrics (Q4, FCF, margins), contracts, identity tests and the 30 golden values.
*Done when:* 30/30 golden values pass, coverage ≥ 95%, identity exceptions ≤ 1%, and `make demo-query` prints Apple's quarterly revenue FY2015–latest matching the 10-Ks.

**Week 4 – GCP, write-audit-publish, scheduling** *(needs your OK before creating resources)*
Terraform: bucket, `raw`/`audit`/`gold`/`ops` datasets, service account, WIF, budgets at EUR 5/15 and a daily BigQuery query quota (hard cap). Predecessor-CIK mapping for companies that re-registered (e.g. ExxonMobil, Disney). dbt BigQuery target, `finfacts publish`, `daily.yml` cron. *(Airflow and OpenLineage/Marquez cut 2026-10-21, approved.)*
*Done when:* `terraform plan` shows only the expected resources. One full backfill is in BigQuery. A deliberately broken test leaves gold untouched and sends the alert email. 3 consecutive daily runs succeed. ExxonMobil has revenue back to FY2015.

**Week 5 – Semantic layer and health page**
MetricFlow semantic models and metrics for all ~20. Add `ops.run_log` with bytes billed, plus an Evidence health page (freshness, test pass rate, cost per run, coverage) deployed to GitHub Pages.
*Done when:* `mf query --metrics revenue --group-by company__ticker,metric_time__year` returns the same numbers as the gold SQL (a test asserts it). The health page is live at `<site_url>/finfacts/` and refreshes after each daily run.

**Week 6 – AI outputs and portfolio**
Eval set v1 (≥ 150 questions; ~110 templated plus ~40 hand-written hard ones, gold SQL, gold answers computed from gold, 10% manually verified). Item 1A + Item 7 extraction for FY2022+ 10-Ks, chunking (~350 words ≈ 470 tokens, 50-word overlap; *changed 2026-10-24, approved: the planned ~800 tokens exceeded bge-small's 512-token window*; metadata: cik, ticker, fy, item, accn), embeddings → LanceDB + HF parquet. Before/after text-to-SQL run. Write the README, case study and demo video script.
*Done when:* the HF dataset page is public with a dataset card and licence; `make eval` prints before/after execution accuracy; the retrieval smoke test returns relevant chunks for 10 sample queries; the README has the architecture diagram, results table and badges.

**Cut line if behind schedule:** drop in this order: Marquez UI demo → hand-written eval questions beyond 150 → 10-K text for years before FY2024 → Airflow (keep the GH Actions schedule). Never cut WAP, tests or the golden values.
**Stretch:** PyIceberg export of gold, eval set to 300 questions, Bluesky/RSS "new filing" feed.

---

## 9. Cost estimate

| Item | Monthly estimate | Notes |
|---|---|---|
| BigQuery storage (~6 GB) | EUR 0 | 10 GB free |
| BigQuery queries (~60 GB) | EUR 0 | 1 TB free; incremental models + partition pruning + `maximum_bytes_billed` on every job |
| GCS (~2–5 GB in us-central1) | EUR 0–0.20 | Raw 10-K HTML kept locally only; bronze stores extracted sections |
| Secret Manager | EUR 0 | Not needed with WIF; `.env` locally |
| GitHub Actions, Pages, HF | EUR 0 | Public repo |
| LLM calls for eval baseline | EUR 1–3 one-off | Small model, ~300 questions × 2 conditions |
| **Total** | **≈ EUR 0–2 / month** | |

Guardrails: budgets at EUR 5 and EUR 15 with email alerts. dbt BigQuery profile sets `maximum_bytes_billed = 5 GB` per query, so a bad query fails instead of costing money. No always-on compute. All jobs are labelled `app=finfacts` for cost per run.

---

## 10. Risks and open questions

| Risk | Impact | Mitigation |
|---|---|---|
| Scope is large for ~55 h | Slip | Weekly cut line (§8); WAP and tests protected |
| Bank/insurer metrics don't fit generic mappings | Wrong numbers | Sector rules or documented `NULL`; never a silent guess |
| 10-K section extraction fails on some filings | Gaps in retrieval data | Measure and report the extraction success rate; skip failures |
| Survivorship bias (current S&P 500 list applied to 2015) | Misleading history | Dated snapshot; documented limitation (Q2) |
| SEC blocks traffic (missing UA, bursts) | Ingestion stops | 8 req/s limiter, UA required at startup, backoff on 403/429 |
| BigQuery costs from a runaway query | Budget | `maximum_bytes_billed`, budgets, partitioning |
| Windows quirks (paths, Make, line endings) | Lost hours | `.gitattributes` (LF), Git Bash only, CI on Linux is the source of truth |

### Decisions (2026-10-20)
Q1 GitHub Actions cron for prod, Airflow local · Q2 current S&P 500 snapshot, survivorship bias documented · Q3 include financials, sector rules + documented `NULL` · Q4 OpenRouter (OpenAI-compatible API, one small model pinned in `EVAL_MODEL`, same model for both conditions) · Q5 US region · Q6 `https://malavnaik99.github.io/finfacts/`.

### Blocking questions for you
1. **Production scheduler:** OK to run the daily job on **GitHub Actions cron**, with Airflow used locally (Astro) to show DAG design? Hosted Airflow would cost ≈ EUR 300+/month. *(Recommended: yes.)*
2. **S&P 500 membership:** use one current constituent snapshot (simple, survivorship bias documented), or try historical membership (more correct, needs a source with a clear licence, adds ~1 week)? *(Recommended: current snapshot.)*
3. **Financial-sector companies (~70 of 503):** include with sector-specific rules where metrics apply and `NULL` elsewhere, or exclude them from v1? *(Recommended: include, with `NULL` + documentation.)*
4. **LLM for the before/after text-to-SQL metric:** OK to use the Anthropic API (small model, ~EUR 1–3 total)? Or do you prefer another provider, or a local model through Ollama (free, slower, lower accuracy)?
5. **GCP region:** OK with **US** (BigQuery US multi-region + GCS us-central1) for the free tier? The data is public US data, so EU residency doesn't matter. *(Recommended: yes.)*
6. **Health page URL:** publish under `https://malavnaik99.github.io/finfacts/` (this repo's GitHub Pages)?

---

## 11. Portfolio deliverables

**README outline**
1. One-line pitch + badges (CI, daily run, freshness, HF dataset)
2. The problem in 3 bullets (tags, restatements, periods) with one real example
3. Architecture diagram
4. Quickstart: `make setup && make backfill-local && make build` (DuckDB, no cloud needed)
5. Data model + the `as_of` example query
6. Data quality: WAP, test list, identity checks, live health page link
7. Results table: freshness, pass rate, backfill time, bytes/run, before/after text-to-SQL accuracy, cost/month
8. AI outputs: eval set and embeddings (HF links)
9. Decisions (links to ADRs) · Limitations · Licences

**Demo video script (4–5 min)**
1. 0:00 Hook: same question, three different answers from raw XBRL
2. 0:40 Architecture tour (diagram)
3. 1:20 Live: `make incremental`, Airflow DAG, a test failing and gold staying untouched (WAP)
4. 2:30 Point-in-time query: a restated figure, before and after
5. 3:10 Semantic layer: `mf query` = SQL = health page
6. 3:50 Eval set + before/after accuracy; what projects 3 and 4 build on it
7. 4:30 Cost: EUR ~0/month and how

**Case study outline** (published at `{site_url}/case-studies/finfacts`, relative links only)
Context → Problem → Constraints (time, EUR 15, public data) → Approach → Key decisions and trade-offs (scheduler, mapping rules, WAP) → Results with numbers → What broke and how I fixed it → What I'd do next.

**Blog post ideas**
1. "The `fy` field in SEC companyfacts lies to you: building point-in-time fundamentals from XBRL"
2. "Write-audit-publish on BigQuery for free with dbt and table copies"
3. "Does a semantic layer make text-to-SQL more accurate? 200 questions on SEC data, measured"
