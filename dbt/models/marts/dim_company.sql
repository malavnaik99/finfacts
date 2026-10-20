-- SCD2 on the attributes that matter for analysis: name, tickers, SIC, fiscal year end.
with snapshots as (
    select
        *,
        {{ surrogate_key(['name', 'tickers', 'sic', 'fiscal_year_end']) }} as attr_hash
    from {{ ref('stg_company') }}
),

changes as (
    select
        *,
        lag(attr_hash) over (partition by cik order by ingest_date) as prev_hash
    from snapshots
),

versions as (
    select * from changes where prev_hash is null or attr_hash != prev_hash
)

select
    {{ surrogate_key(['v.cik', 'v.ingest_date']) }} as company_sk,
    v.cik,
    v.name,
    v.tickers,
    v.exchanges,
    v.sic,
    v.sic_description,
    v.fiscal_year_end,
    v.state_of_incorporation,
    v.category,
    -- GICS comes from the latest universe snapshot and is not versioned
    u.gics_sector,
    u.gics_sub_industry,
    v.ingest_date as valid_from,
    lead(v.ingest_date) over (partition by v.cik order by v.ingest_date) as valid_to,
    lead(v.ingest_date) over (partition by v.cik order by v.ingest_date) is null as is_current
from versions as v
left join {{ ref('stg_universe') }} as u on v.cik = u.cik
