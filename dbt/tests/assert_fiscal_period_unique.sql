{{ config(severity='warn') }}
-- Standard periods (Q1-Q4, FY, instants) should map to one date range per company.
-- Failures usually mean a fiscal-year-end change; reviewed in Week 3 mapping work.
select cik, fiscal_year, fiscal_period, period_type, count(*) as n
from {{ ref('dim_period') }}
where fiscal_period != 'OTHER'
    and {{ bucket_test_scope() }}  -- only rebuilt companies on incremental runs
group by cik, fiscal_year, fiscal_period, period_type
having count(*) > 1
