-- Certified fundamentals, point-in-time. One row per company x metric x fiscal period x
-- version. A version is the value known from valid_from (inclusive) to valid_to (exclusive).
-- Use fct_financials_latest for current values, or the as_of(date) macro for history.
-- All derivations happen upstream (int_metric_values); this model only certifies and versions.
with certified as (
    select a.*, m.unit, m.period_type
    from {{ ref('int_metric_values') }} as a
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
    cast(v.fiscal_year as bigint) as fiscal_year,
    v.fiscal_period,
    {{ surrogate_key(['v.cik', 'v.fiscal_year', 'v.fiscal_period']) }} as fiscal_period_key,
    -- balance-sheet values are as of period_end; they have no start
    case when v.period_type = 'duration' then p.period_start end as period_start,
    p.period_end,
    p.calendar_frame,
    v.value,
    v.unit,
    cast(v.version_no as bigint) as version_no,
    v.valid_from,
    v.valid_to,
    v.version_no > 1 as is_restatement,
    v.is_derived,
    v.source_concept,
    v.accession_number
from versioned as v
left join {{ ref('dim_fiscal_period') }} as p
    on v.cik = p.cik and v.fiscal_year = p.fiscal_year and v.fiscal_period = p.fiscal_period
