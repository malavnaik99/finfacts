{{ config(**company_incremental_config()) }}
-- One row per fact as reported in one filing (accession).
-- The same fact repeats across snapshots; keep the copy from the newest snapshot.
-- Predecessor CIKs are mapped to their successor (see stg_predecessors), so a company's
-- history survives a re-registration and the successor's comparatives become new versions.
with src as (
    select
        coalesce(p.successor_cik, cast(f.cik as bigint)) as cik,
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
    from {{ source('flat', 'companyfacts') }} as f
    left join {{ ref('stg_predecessors') }} as p on cast(f.cik as bigint) = p.predecessor_cik
    where (p.predecessor_cik is null or cast(f.filed as date) < p.cutoff_date)
        and taxonomy in ('{{ var("in_scope_taxonomies") | join("', '") }}')
        and form in ('{{ var("financial_statement_forms") | join("', '") }}')
        and {{ company_scope('cast(f.cik as bigint)', 'raw') }}
)

select
    {{ surrogate_key(['cik', 'taxonomy', 'concept', 'unit', 'period_start', 'period_end']) }}
        as fact_key,
    {{ surrogate_key(['cik', 'taxonomy', 'concept', 'unit', 'period_start', 'period_end',
                      'accession_number']) }} as filing_fact_id,
    {{ cik_bucket('cik') }} as cik_bucket,
    *
from src
where period_end >= cast('{{ var("min_period_end") }}' as date)
    -- ~400 forward-looking facts (e.g. expected restructuring cost) end after filing; not history
    and period_end <= filed_date
qualify row_number() over (
    partition by cik, taxonomy, concept, unit, period_start, period_end, accession_number
    order by ingest_date desc
) = 1
