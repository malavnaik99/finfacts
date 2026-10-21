-- Latest committed S&P 500 snapshot only (filename sp500_YYYY-MM-DD.csv sorts by date).
-- On BigQuery `finfacts load-bq` loads only the latest file, so there is nothing to pick.
select
    cast(cik as bigint) as cik,
    tickers,
    name,
    gics_sector,
    gics_sub_industry
from {{ source('config', 'universe') }}
{%- if target.type != 'bigquery' %}
where true  -- BigQuery requires WHERE/GROUP BY/HAVING alongside QUALIFY
qualify filename = max(filename) over ()
{%- endif %}
