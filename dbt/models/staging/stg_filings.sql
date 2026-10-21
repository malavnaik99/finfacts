-- One row per (CIK, accession). An accession can be co-filed by several registrants.
-- Predecessor CIKs map to their successor up to the succession date (stg_predecessors).
with src as (
    select
        f.*,
        coalesce(p.successor_cik, cast(f.cik as bigint)) as mapped_cik
    from {{ source('flat', 'filings') }} as f
    left join {{ ref('stg_predecessors') }} as p on cast(f.cik as bigint) = p.predecessor_cik
    where p.predecessor_cik is null or cast(f.filing_date as date) < p.cutoff_date
)

select
    {{ surrogate_key(['mapped_cik', 'accession_number']) }} as filing_id,
    mapped_cik as cik,
    accession_number,
    cast(filing_date as date) as filing_date,
    cast(report_date as date) as report_date,
    -- SEC gives UTC with a trailing Z
    cast(replace(acceptance_datetime, 'Z', '') as timestamp) as accepted_at,
    form,
    coalesce(is_xbrl = 1, false) as is_xbrl,
    coalesce(is_inline_xbrl = 1, false) as is_inline_xbrl,
    primary_document,
    primary_doc_description,
    items,
    cast(ingest_date as date) as ingest_date
from src
where true  -- BigQuery requires WHERE/GROUP BY/HAVING alongside QUALIFY
qualify row_number() over (
    partition by mapped_cik, accession_number order by ingest_date desc, source_file desc
) = 1
