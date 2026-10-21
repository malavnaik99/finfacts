-- Apple quarterly revenue, FY2015 to the latest quarter, as currently known.
-- Q4 is never filed as a 3-month figure; FinFacts derives it as FY - 9M (is_derived = true).
select
    fiscal_year,
    fiscal_period,
    period_end,
    round(value / 1e6) as revenue_usd_m,
    is_derived,
    source_concept
from gold.fct_financials_latest
where cik = 320193
    and metric_id = 'revenue'
    and fiscal_period in ('Q1', 'Q2', 'Q3', 'Q4')
order by fiscal_year, fiscal_period
