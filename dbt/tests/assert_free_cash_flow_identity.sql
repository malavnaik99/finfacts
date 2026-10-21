-- Free cash flow must equal operating cash flow minus capex exactly, for current values.
-- Guards the point-in-time derivation join in macros/derive.sql.
with l as (
    select cik, metric_id, fiscal_year, fiscal_period, value
    from {{ ref('fct_financials_latest') }}
    where metric_id in ('free_cash_flow', 'operating_cash_flow', 'capex')
)

select f.cik, f.fiscal_year, f.fiscal_period, f.value as fcf, o.value - c.value as expected
from l as f
inner join l as o
    on o.metric_id = 'operating_cash_flow' and o.cik = f.cik
    and o.fiscal_year = f.fiscal_year and o.fiscal_period = f.fiscal_period
inner join l as c
    on c.metric_id = 'capex' and c.cik = f.cik
    and c.fiscal_year = f.fiscal_year and c.fiscal_period = f.fiscal_period
where f.metric_id = 'free_cash_flow'
    and f.value != o.value - c.value
