-- One row per fact as reported in one filing (accession).
-- The same fact repeats across snapshots; keep the copy from the newest snapshot.
with src as (
    select
        cast(cik as bigint) as cik,
        taxonomy,
        concept,
        unit,
        cast(period_start as date) as period_start,
        cast(period_end as date) as period_end,
        value,
        accn as accession_number,
        form,
        cast(filed as date) as filed_date,
        fy as filing_fiscal_year,  -- fiscal year of the FILING, not of the fact
        fp as filing_fiscal_period,
        frame,
        cast(ingest_date as date) as ingest_date
    from {{ source('flat', 'companyfacts') }}
    where taxonomy in ('{{ var("in_scope_taxonomies") | join("', '") }}')
        and form in ('{{ var("financial_statement_forms") | join("', '") }}')
)

select
    {{ surrogate_key(['cik', 'taxonomy', 'concept', 'unit', 'period_start', 'period_end']) }}
        as fact_key,
    {{ surrogate_key(['cik', 'taxonomy', 'concept', 'unit', 'period_start', 'period_end',
                      'accession_number']) }} as filing_fact_id,
    *
from src
where period_end >= cast('{{ var("min_period_end") }}' as date)
    -- ~400 forward-looking facts (e.g. expected restructuring cost) end after filing; not history
    and period_end <= filed_date
qualify row_number() over (
    partition by cik, taxonomy, concept, unit, period_start, period_end, accession_number
    order by ingest_date desc
) = 1
