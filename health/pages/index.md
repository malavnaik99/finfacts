---
title: FinFacts data health
---

Live health of the [FinFacts](https://github.com/malavnaik99/finfacts) pipeline: certified, point-in-time SEC EDGAR fundamentals for the S&P 500. The page is rebuilt after every daily run. Nothing reaches the published `gold` dataset unless every dbt test passes first (write-audit-publish).

```sql latest
select * from finfacts.runs order by started_at desc limit 1
```

```sql last_success
select * from finfacts.runs where status = 'success' order by started_at desc limit 1
```

```sql pass_rate
select
    sum(tests_pass) as passed,
    sum(tests_pass + tests_warn + tests_fail) as total,
    sum(tests_pass) / nullif(sum(tests_pass + tests_warn + tests_fail), 0) as pass_rate
from finfacts.runs
where run_id = (select run_id from finfacts.runs order by started_at desc limit 1)
```

```sql headline
select * from finfacts.headline
```

<BigValue data={latest} value=status title="Last run" />
<BigValue data={last_success} value=finished_at title="Last published" fmt="yyyy-mm-dd hh:mm" />
<BigValue data={last_success} value=freshness_hours title="Freshness (hours since newest filing)" />
<BigValue data={pass_rate} value=pass_rate title="Tests passing (last run)" fmt=pct1 />
<BigValue data={latest} value=usd_list_price title="BigQuery cost of last run (list price)" fmt=usd2 />

<BigValue data={headline} value=companies title="Companies" />
<BigValue data={headline} value=metrics title="Certified metrics" />
<BigValue data={headline} value=fact_versions title="Fact versions" fmt=num0 />
<BigValue data={headline} value=restatements title="Restated values" fmt=num0 />

## Cost and duration per run

BigQuery bytes billed per daily run. A hard project quota stops queries at 50 GB a day, and budget alerts fire at EUR 5 and EUR 15 a month.

```sql runs_chart
select started_at, gb_billed, minutes, status from finfacts.runs order by started_at
```

<LineChart data={runs_chart} x=started_at y=gb_billed yAxisTitle="GB billed" />

## Coverage of core metrics

Share of company fiscal years with revenue, net income and total assets. Gate: at least 95% overall.

```sql coverage
select fiscal_year, metric_id, coverage from finfacts.coverage order by fiscal_year
```

<LineChart data={coverage} x=fiscal_year y=coverage series=metric_id yFmt=pct0 yMin=0.8 />

## Accounting identity checks

Current values where every input was reported (not derived). The failing rows stay listed in `gold.identity_checks`, and the build fails if a rate goes above its limit.

```sql identity
select * from finfacts.identity
```

<DataTable data={identity}>
  <Column id=check_name title="Check" />
  <Column id=checked fmt=num0 />
  <Column id=failed fmt=num0 />
  <Column id=failure_rate fmt=pct2 title="Failure rate" />
  <Column id=failure_limit fmt=pct1 title="Limit" />
</DataTable>

## Recent runs

```sql recent
select started_at, trigger, status, minutes, models_ok, tests_pass, tests_warn, tests_fail, gb_billed
from finfacts.runs order by started_at desc limit 20
```

<DataTable data={recent} rows=20>
  <Column id=started_at fmt="yyyy-mm-dd hh:mm" />
  <Column id=trigger />
  <Column id=status />
  <Column id=minutes fmt=num1 />
  <Column id=models_ok title="Models" />
  <Column id=tests_pass title="Pass" />
  <Column id=tests_warn title="Warn" />
  <Column id=tests_fail title="Fail" />
  <Column id=gb_billed fmt=num2 title="GB billed" />
</DataTable>
