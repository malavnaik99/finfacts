-- Certified fundamentals, point-in-time. One row per company x metric x fiscal period x
-- version. A version is the value known from valid_from (inclusive) to valid_to (exclusive).
-- Use fct_financials_latest for current values, or the as_of(date) macro for history.
{%- set duration_periods = ['Q1', 'Q2', 'Q3', 'Q4', 'Q2_YTD', 'Q3_YTD', 'FY'] %}

with v as (
    select * from {{ ref('int_metric_values') }}
),

fcf as (
    {{ per_period('v', duration_periods, 'free_cash_flow', 'operating_cash_flow', 'capex', 'a - b') }}
),

v_fcf as (select * from v union all select * from fcf),

margins as (
    {{ per_period('v_fcf', duration_periods, 'gross_margin', 'gross_profit', 'revenue', 'a / nullif(b, 0)') }}
    union all
    {{ per_period('v_fcf', duration_periods, 'operating_margin', 'operating_income', 'revenue', 'a / nullif(b, 0)') }}
    union all
    {{ per_period('v_fcf', duration_periods, 'net_margin', 'net_income', 'revenue', 'a / nullif(b, 0)') }}
),

certified as (
    select a.*, m.unit, m.period_type
    from (select * from v_fcf union all select * from margins) as a
    inner join {{ ref('metrics') }} as m on a.metric_id = m.metric_id
    where m.is_certified
),

versioned as (
    select
        *,
        row_number() over (
            partition by cik, metric_id, fiscal_year, fiscal_period order by valid_from
        ) as version_no
    from certified
)

select
    {{ surrogate_key(['v.cik', 'v.metric_id', 'v.fiscal_year', 'v.fiscal_period', 'v.version_no']) }}
        as financial_fact_id,
    cast(v.cik as bigint) as cik,
    v.metric_id,
    cast(v.fiscal_year as integer) as fiscal_year,
    v.fiscal_period,
    {{ surrogate_key(['v.cik', 'v.fiscal_year', 'v.fiscal_period']) }} as fiscal_period_key,
    -- balance-sheet values are as of period_end; they have no start
    case when v.period_type = 'duration' then p.period_start end as period_start,
    p.period_end,
    p.calendar_frame,
    v.value,
    v.unit,
    cast(v.version_no as integer) as version_no,
    v.valid_from,
    v.valid_to,
    v.version_no > 1 as is_restatement,
    v.is_derived,
    v.source_concept,
    v.accession_number
from versioned as v
left join {{ ref('dim_fiscal_period') }} as p
    on v.cik = p.cik and v.fiscal_year = p.fiscal_year and v.fiscal_period = p.fiscal_period
