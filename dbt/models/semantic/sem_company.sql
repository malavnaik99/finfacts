-- Current version of each company: MetricFlow needs one row per company entity, while
-- dim_company keeps SCD2 history (several rows per CIK after a rename).
select
    cik,
    name,
    tickers,
    gics_sector,
    gics_sub_industry,
    sic_description
from {{ ref('dim_company') }}
where is_current
