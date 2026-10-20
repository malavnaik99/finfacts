-- One row per (CIK, accession). An accession can be co-filed by several registrants.
select
    {{ surrogate_key(['cik', 'accession_number']) }} as filing_id,
    cast(cik as bigint) as cik,
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
from {{ source('flat', 'filings') }}
where true  -- BigQuery requires WHERE/GROUP BY/HAVING alongside QUALIFY
qualify row_number() over (
    partition by cik, accession_number order by ingest_date desc, source_file desc
) = 1
