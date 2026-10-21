-- One row per (company, period_start, period_end) seen in the facts.
-- Fiscal labels come from the period DATES and the company's fiscal year end, never from
-- the fact's fy/fp fields (those describe the filing the fact appeared in).
-- Fiscal year is named by the calendar year in which it ends (Apple FY ending Sep 2024 = 2024).
-- shortcut: uses the CURRENT fiscal year end; companies that changed FYE get mislabelled
-- periods before the change (caught by the warn test assert_fiscal_period_unique).
with periods as (
    select distinct cik, period_key, period_start, period_end
    from {{ ref('int_fact_versions') }}
),

fye_raw as (
    select
        cik,
        cast(substr(fiscal_year_end, 1, 2) as integer) as mm,
        cast(substr(fiscal_year_end, 3, 2) as integer) as dd
    from {{ ref('dim_company') }}
    where is_current
),

-- A year end in the first week of a month is a 52/53-week year that ended around the
-- previous month end (J&J's FYE is listed as 0103 because one year ended on Jan 3).
-- Normalise it to that month end, or every year would be labelled one year too late.
fye as (
    select
        cik,
        case when dd <= 7 then (case when mm = 1 then 12 else mm - 1 end) else mm end as fye_month,
        case
            when dd <= 7 then
                case (case when mm = 1 then 12 else mm - 1 end)
                    when 2 then 28 when 4 then 30 when 6 then 30 when 9 then 30 when 11 then 30
                    else 31
                end
            -- Feb 29 year ends are treated as Feb 28 so make_date works every year
            when mm = 2 and dd = 29 then 28
            else dd
        end as fye_day
    from fye_raw
),

base as (
    select
        p.*,
        f.fye_month,
        f.fye_day,
        extract(year from p.period_end) as end_year,
        case when p.period_start is null then null
             else {{ dbt.datediff('p.period_start', 'p.period_end', 'day') }} end as duration_days
    from periods as p
    inner join fye as f on p.cik = f.cik
),

fiscal_year as (
    select
        *,
        -- 52/53-week years drift up to a week from the nominal year-end date
        case
            when period_end <= {{ dbt.dateadd('day', 7, make_date('end_year - 1', 'fye_month', 'fye_day')) }}
                then end_year - 1
            when period_end <= {{ dbt.dateadd('day', 7, make_date('end_year', 'fye_month', 'fye_day')) }}
                then end_year
            else end_year + 1
        end as fiscal_year
    from base
),

quarters as (
    select
        *,
        {{ dbt.datediff(make_date('fiscal_year - 1', 'fye_month', 'fye_day'), 'period_end', 'day') }}
            as days_into_year
    from fiscal_year
),

labelled as (
    select
        *,
        least(greatest(cast(round(days_into_year / 91.31) as integer), 1), 4) as fiscal_quarter,
        -- only periods ending within 10 days of a fiscal quarter end get a fiscal label
        abs(days_into_year - round(days_into_year / 91.31) * 91.31) <= 10 as is_quarter_aligned,
        case
            when duration_days is null then 0
            when duration_days between 80 and 100 then 3
            when duration_days between 170 and 200 then 6
            when duration_days between 260 and 290 then 9
            when duration_days between 350 and 380 then 12
        end as duration_months
    from quarters
)

select
    period_key,
    cast(cik as bigint) as cik,
    period_start,
    period_end,
    case when period_start is null then 'instant' else 'duration' end as period_type,
    cast(duration_days as integer) as duration_days,
    cast(duration_months as integer) as duration_months,
    cast(fiscal_year as integer) as fiscal_year,
    cast(fiscal_quarter as integer) as fiscal_quarter,
    -- Anything not aligned with the fiscal calendar (trailing-12-month figures, acquiree
    -- periods, cover-page dates) is OTHER rather than a misleading Qn/FY label.
    case
        when not is_quarter_aligned then 'OTHER'
        when duration_months in (0, 3) then concat('Q', cast(fiscal_quarter as {{ dbt.type_string() }}))
        when duration_months = 6 and fiscal_quarter = 2 then 'Q2_YTD'
        when duration_months = 9 and fiscal_quarter = 3 then 'Q3_YTD'
        when duration_months = 12 and fiscal_quarter = 4 then 'FY'
        else 'OTHER'
    end as fiscal_period,
    {{ calendar_frame('period_start', 'period_end', 'duration_months') }} as calendar_frame
from labelled
