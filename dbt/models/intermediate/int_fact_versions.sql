-- Restatement history: one row per distinct value a fact has had over time.
-- A new version starts only when a later filing reports a DIFFERENT value for the same
-- fact; repeating the same number as a comparative does not create a version.
-- Point-in-time: a version is "known" from valid_from (inclusive) to valid_to (exclusive).
with facts as (
    select
        f.fact_key,
        f.cik,
        f.taxonomy,
        f.concept,
        f.unit,
        f.period_start,
        f.period_end,
        f.value,
        f.accession_number,
        f.form,
        f.filed_date,
        -- acceptance time orders two filings made on the same day
        coalesce(fl.accepted_at, cast(f.filed_date as timestamp)) as accepted_at
    from {{ ref('stg_companyfacts') }} as f
    left join {{ ref('stg_filings') }} as fl
        on f.cik = fl.cik and f.accession_number = fl.accession_number
),

flagged as (
    select
        *,
        lag(value) over (
            partition by fact_key order by accepted_at, accession_number
        ) as prev_value
    from facts
),

versions as (
    select
        fact_key, cik, taxonomy, concept, unit, period_start, period_end, value,
        accession_number, form, filed_date, accepted_at
    from flagged
    where prev_value is null or value != prev_value
)

select
    {{ surrogate_key(['fact_key', 'accession_number']) }} as fact_version_id,
    fact_key,
    {{ surrogate_key(['cik', 'period_start', 'period_end']) }} as period_key,
    cik,
    taxonomy,
    concept,
    unit,
    period_start,
    period_end,
    value,
    accession_number,
    form,
    filed_date,
    accepted_at,
    row_number() over w as version_no,
    -- Acceptance date, not companyfacts `filed`: `filed` is occasionally stale (e.g. CIK
    -- 1108524 accessions accepted in 2022 carry filed=2021-03-17), which would make versions
    -- overlap. Ordering and validity must come from the same clock.
    cast(accepted_at as date) as valid_from,
    lead(cast(accepted_at as date)) over w as valid_to,
    row_number() over w > 1 as is_restatement
from versions
window w as (partition by fact_key order by accepted_at, accession_number)
