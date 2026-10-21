-- One date range per (company, fiscal year, fiscal period, period type).
-- Near-duplicates (the same quarter dated 03-31 by one filing and 04-01 by another) are
-- resolved by taking the range with the most facts: the primary statements use it.
with fact_counts as (
    select period_key, count(distinct fact_key) as fact_count
    from {{ ref('int_fact_versions') }}
    group by period_key
),

ranked as (
    select
        p.cik,
        p.fiscal_year,
        p.fiscal_period,
        p.period_type,
        p.period_key,
        p.period_start,
        p.period_end,
        c.fact_count
    from {{ ref('dim_period') }} as p
    inner join fact_counts as c on p.period_key = c.period_key
    where p.fiscal_period != 'OTHER'
        and p.fiscal_year >= {{ var('min_fiscal_year') }}
    qualify row_number() over (
        partition by p.cik, p.fiscal_year, p.fiscal_period, p.period_type
        order by c.fact_count desc, p.period_end desc
    ) = 1
)

select * from ranked
union all
-- the full-year balance sheet is the year-end (Q4) instant
select cik, fiscal_year, 'FY' as fiscal_period, period_type, period_key, period_start, period_end, fact_count
from ranked
where period_type = 'instant' and fiscal_period = 'Q4'
