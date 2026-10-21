{{ config(tags=['full_data']) }}
-- At least 95% of company fiscal years must have revenue, net income and total assets.
-- Denominator: company-years with a full-year period in the fiscal calendar, up to the
-- last fiscal year most companies have completed.
with company_years as (
    select cik, fiscal_year
    from {{ ref('dim_fiscal_period') }}
    where fiscal_period = 'FY'
        and fiscal_year < extract(year from current_date)
),

present as (
    select cik, fiscal_year, metric_id
    from {{ ref('fct_financials_latest') }}
    where fiscal_period = 'FY'
        and metric_id in ('revenue', 'net_income', 'total_assets')
),

coverage as (
    select
        m.metric_id,
        count(*) as company_years,
        count(p.cik) as covered
    from company_years as y
    cross join (
        select 'revenue' as metric_id union all select 'net_income' union all select 'total_assets'
    ) as m
    left join present as p
        on y.cik = p.cik and y.fiscal_year = p.fiscal_year and m.metric_id = p.metric_id
    group by m.metric_id
)

select *, 1.0 * covered / company_years as coverage_rate
from coverage
where 1.0 * covered / company_years < 0.95
