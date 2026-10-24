-- a table, not a view: publish copies it from audit to gold, and a view would keep
-- pointing at audit
{{ config(materialized='table') }}
-- Current value of every certified metric: the open version of each fact.
-- fiscal_year_date (1 January of the fiscal year as FinFacts names it) is the time axis for
-- annual semantic-layer metrics: period_end would put two fiscal years in one calendar year
-- for 52/53-week companies whose year sometimes ends in early January (e.g. J&J 2023).
select
    *,
    {{ make_date('fiscal_year', 1, 1) }} as fiscal_year_date
from {{ ref('fct_financials') }}
where valid_to is null
