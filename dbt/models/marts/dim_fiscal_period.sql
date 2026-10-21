-- One row per (company, fiscal year, fiscal period): the fiscal calendar the fact table uses.
-- Quarter boundaries come from the canonical reported periods; quarters a company never
-- reports as a 3-month period (usually Q4) are reconstructed from the neighbouring ends.
with c as (
    select * from {{ ref('int_canonical_periods') }}
),

ends as (
    select
        cik,
        fiscal_year,
        max(case when fiscal_period = 'FY' and period_type = 'duration' then period_start end) as fy_start,
        max(case when fiscal_period = 'Q1' and period_type = 'duration' then period_start end) as q1_start,
        coalesce(
            max(case when fiscal_period = 'Q1' and period_type = 'duration' then period_end end),
            max(case when fiscal_period = 'Q1' and period_type = 'instant' then period_end end)
        ) as q1_end,
        coalesce(
            max(case when fiscal_period in ('Q2', 'Q2_YTD') and period_type = 'duration' then period_end end),
            max(case when fiscal_period = 'Q2' and period_type = 'instant' then period_end end)
        ) as q2_end,
        coalesce(
            max(case when fiscal_period in ('Q3', 'Q3_YTD') and period_type = 'duration' then period_end end),
            max(case when fiscal_period = 'Q3' and period_type = 'instant' then period_end end)
        ) as q3_end,
        coalesce(
            max(case when fiscal_period in ('FY', 'Q4') and period_type = 'duration' then period_end end),
            max(case when fiscal_period = 'Q4' and period_type = 'instant' then period_end end)
        ) as q4_end
    from c
    group by cik, fiscal_year
),

years as (
    select
        *,
        coalesce(
            fy_start,
            q1_start,
            case when lag(fiscal_year) over (partition by cik order by fiscal_year) = fiscal_year - 1
                 then {{ dbt.dateadd('day', 1, 'lag(q4_end) over (partition by cik order by fiscal_year)') }}
            end
        ) as year_start
    from ends
),

periods as (
    {%- set rows = [
        ('Q1', 'year_start', 'q1_end', 3),
        ('Q2', dbt.dateadd('day', 1, 'q1_end'), 'q2_end', 3),
        ('Q3', dbt.dateadd('day', 1, 'q2_end'), 'q3_end', 3),
        ('Q4', dbt.dateadd('day', 1, 'q3_end'), 'q4_end', 3),
        ('Q2_YTD', 'year_start', 'q2_end', 6),
        ('Q3_YTD', 'year_start', 'q3_end', 9),
        ('FY', 'year_start', 'q4_end', 12),
    ] -%}
    {%- for label, start_expr, end_expr, months in rows %}
    select cik, fiscal_year, '{{ label }}' as fiscal_period, {{ months }} as duration_months,
           {{ start_expr }} as period_start, {{ end_expr }} as period_end
    from years
    where {{ end_expr }} is not null
    {%- if not loop.last %} union all {% endif -%}
    {%- endfor %}
)

select
    {{ surrogate_key(['cik', 'fiscal_year', 'fiscal_period']) }} as fiscal_period_key,
    cast(cik as bigint) as cik,
    cast(fiscal_year as integer) as fiscal_year,
    fiscal_period,
    cast(duration_months as integer) as duration_months,
    cast(period_start as date) as period_start,
    cast(period_end as date) as period_end,
    {{ calendar_frame('period_start', 'period_end', 'duration_months') }} as calendar_frame
from periods
