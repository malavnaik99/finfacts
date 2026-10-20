-- One row per CIK per snapshot date.
select
    cast(cik as bigint) as cik,
    name,
    tickers,
    exchanges,
    sic,
    sic_description,
    coalesce(fiscal_year_end, '1231') as fiscal_year_end,
    state_of_incorporation,
    category,
    entity_type,
    cast(ingest_date as date) as ingest_date
from {{ source('flat', 'company') }}
where true  -- BigQuery requires WHERE/GROUP BY/HAVING alongside QUALIFY
-- incremental files (CIK_<accn>) sort after the backfill file (CIK.json) for the same day
qualify row_number() over (partition by cik, ingest_date order by source_file desc) = 1
