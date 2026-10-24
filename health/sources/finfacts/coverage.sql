-- Share of company fiscal years with each core metric in gold.
with years as (
    select cik, fiscal_year from gold.dim_fiscal_period where fiscal_period = 'FY'
),
present as (
    select cik, fiscal_year, metric_id from gold.fct_financials_latest
    where fiscal_period = 'FY' and metric_id in ('revenue', 'net_income', 'total_assets')
)
select
    y.fiscal_year,
    metric_id,
    count(*) as company_years,
    count(p.cik) as covered,
    count(p.cik) / count(*) as coverage
from years as y
cross join unnest(['revenue', 'net_income', 'total_assets']) as metric_id
left join present as p
    on p.cik = y.cik and p.fiscal_year = y.fiscal_year and p.metric_id = metric_id
group by 1, 2
