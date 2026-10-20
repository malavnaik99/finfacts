# Silver layer: restatements, periods and data quirks

The silver layer turns SEC company facts into **point-in-time-correct history**. This page explains the rules and records the real data problems found while building it (2026-10-20 snapshot, 500 S&P 500 companies).

## Pipeline

```
bronze JSON (immutable) ──finfacts flatten──▶ parquet (1 row per fact, no logic)
  ──dbt──▶ stg_companyfacts ─▶ int_fact_versions ─▶ dim_period
           stg_filings ───────┘                    dim_company ◀── stg_company + stg_universe
```

| Model | Grain | Rows (2026-10-20) |
|---|---|---|
| `stg_companyfacts` | fact × filing (accession) | ~9.5 M |
| `int_fact_versions` | distinct value of a fact over time | 5.17 M versions of 4.92 M facts |
| `dim_period` | company × (period_start, period_end) | ~92 k |
| `dim_company` | company version (SCD2) | 500 |

## How a restatement becomes a version

A *fact* is `(cik, taxonomy, concept, unit, period_start, period_end)`. Companies repeat the same fact as a comparative in later filings. **A new version starts only when a later filing reports a different value.** Repeating the same number does not create one.

Each version is valid from the SEC **acceptance date** of the filing that first reported it (inclusive) until the next version's acceptance date (exclusive). "What did the market know on date D?" is:

```sql
where valid_from <= D and (valid_to is null or valid_to > D)
```

### Worked example: JPMorgan Chase FY2019 `Revenues`

| Version | Value (USD) | Reported in | Valid from | Valid to |
|---|---|---|---|---|
| 1 | 115,627,000,000 | 10-K for FY2019 (`0000019617-20-000257`) | 2020-02-26 | 2021-02-24 |
| 2 | 115,399,000,000 | 10-K for FY2020 (`0000019617-21-000236`) | 2021-02-24 | 2022-02-23 |
| 3 | 115,720,000,000 | 10-K for FY2021 (`0000019617-22-000272`) | 2022-02-23 | — (current) |

An analyst asking on 2021-06-01 gets **115.399 bn**. Asking today gets **115.720 bn**. A naive `max(filed)` query silently gives today's number for every historical question. Across the S&P 500, **228,594 facts (4.6%) have been restated at least once**.

## Data quirks found and how they are handled

| # | Quirk | Evidence | Handling |
|---|---|---|---|
| 1 | **Proxy statements look like restatements.** Pay-versus-performance tables in DEF 14A tag `NetIncomeLoss` rounded to $0.1 bn. | JPMorgan FY2021 net income: 10-K says 48,334 m; the 2026 DEF 14A says 48,300 m and became the "current" value. 332 false restatements came from proxy forms. | Silver keeps only financial-statement forms (`financial_statement_forms` var: 10-K/Q, amendments, transition reports, 20-F/40-F, 8-K). 8-K stays because it carries real recasts of prior periods. |
| 2 | **Stale `filed` dates in companyfacts.** | Salesforce (CIK 1108524) accessions accepted 2022-02-24 carry `filed = 2021-03-17`, so versions ordered by acceptance time overlapped. Caught by `assert_versions_do_not_overlap`. | Versions are ordered by **and** dated with the acceptance timestamp from `submissions`, falling back to `filed` only when no filing record exists. |
| 3 | **`fy` / `fp` describe the filing, not the fact.** | Apple's FY2018 10-K reports the FY2016 revenue with `fy=2018, fp=FY`. | Fiscal labels in `dim_period` are derived from period dates and the company's fiscal year end. `fy`/`fp` are kept only as `filing_fiscal_*` columns. |
| 4 | **52/53-week fiscal years.** | Apple's FYE is listed as `0926` but its years end between Sep 24 and Oct 1. | ±7 days tolerance on the fiscal year end; quarters labelled only if they end within 10 days of a fiscal quarter end. |
| 5 | **Non-fiscal periods.** | Trailing-12-month and acquiree periods (e.g. CIK 4281 reports Oct–Sep 12-month figures beside its Jan–Dec fiscal year); cover-page dates for share counts. | Labelled `OTHER`, never `FY`/`Qn`. 27 k of 92 k periods. |
| 6 | **Forward-looking facts.** | 423 facts end after their filing date (e.g. `RestructuringAndRelatedCostExpectedCost`), one at 2199-12-31. | Dropped in `stg_companyfacts` (`period_end <= filed_date`). |
| 7 | **Near-duplicate period ends.** | The same quarter's balance sheet dated 2022-03-31 by one filing and 2022-04-01 by another. ~2.8 k groups. | `assert_fiscal_period_unique` (warn). Week 3 picks the canonical quarter end from the filing's `reportDate` when mapping metrics. |

## Known limitations

- `dim_period` uses the **current** fiscal year end. Companies that changed their year end are mislabelled before the change (surfaced by the warn test).
- The incremental load watches only 10-K/10-Q-type filings. A recast filed on an 8-K is picked up at the company's next periodic filing or the next bulk backfill.
- Facts from the `ifrs-full` taxonomy (a handful of S&P 500 members file 20-F) are out of scope for v1.
