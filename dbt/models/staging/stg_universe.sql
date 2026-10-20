-- Latest committed S&P 500 snapshot only (filename sp500_YYYY-MM-DD.csv sorts by date).
select
    cast(cik as bigint) as cik,
    tickers,
    name,
    gics_sector,
    gics_sub_industry,
    cast(regexp_extract(filename, 'sp500_([0-9-]+)\.csv', 1) as date) as snapshot_date
from {{ source('config', 'universe') }}
where true  -- BigQuery requires WHERE/GROUP BY/HAVING alongside QUALIFY
qualify filename = max(filename) over ()
