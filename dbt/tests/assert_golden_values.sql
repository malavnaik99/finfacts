{{ config(tags=['full_data']) }}
-- 30 values read from the financial statements in each company's 10-K (seeds/golden_values.csv,
-- with the statement URL). Each must match the value FinFacts knew the day after filing,
-- which tests mapping, fiscal periods and point-in-time versioning together.
-- Fails for any golden value that is missing or differs by more than its tolerance
-- (statements are in $ millions, so tolerance is half a million).
select
    g.ticker,
    g.metric_id,
    g.fiscal_year,
    g.fiscal_period,
    g.as_of_date,
    g.expected_value,
    f.value as actual_value,
    f.source_concept
from {{ ref('golden_values') }} as g
left join {{ ref('fct_financials') }} as f
    on f.cik = g.cik and f.metric_id = g.metric_id
    and f.fiscal_year = g.fiscal_year and f.fiscal_period = g.fiscal_period
    and {{ as_of('g.as_of_date', 'f') }}
where f.value is null
   or abs(f.value - g.expected_value) > g.tolerance
