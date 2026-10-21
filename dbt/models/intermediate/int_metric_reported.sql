-- Reported metric versions: XBRL facts mapped to metrics via the concept map, on canonical
-- periods only. Per company, metric and fiscal period exactly one concept is used: the
-- highest-priority concept the company ever reported for it, recorded in source_concept.
with candidates as (
    select
        v.cik,
        m.metric_id,
        p.fiscal_year,
        p.fiscal_period,
        m.priority,
        v.taxonomy,
        v.concept,
        v.value,
        v.valid_from,
        v.valid_to,
        v.accession_number
    from {{ ref('int_fact_versions') }} as v
    inner join {{ ref('concept_map') }} as m
        on v.taxonomy = m.taxonomy and v.concept = m.concept and v.unit = m.unit
    inner join {{ ref('metrics') }} as mt on m.metric_id = mt.metric_id
    inner join {{ ref('int_canonical_periods') }} as p
        on v.period_key = p.period_key and p.period_type = mt.period_type
),

chosen as (
    select cik, metric_id, fiscal_year, fiscal_period, min(priority) as priority
    from candidates
    group by cik, metric_id, fiscal_year, fiscal_period
)

select
    c.cik,
    c.metric_id,
    c.fiscal_year,
    c.fiscal_period,
    c.value,
    c.valid_from,
    c.valid_to,
    concat(c.taxonomy, ':', c.concept) as source_concept,
    c.accession_number,
    false as is_derived
from candidates as c
inner join chosen as h
    on c.cik = h.cik and c.metric_id = h.metric_id and c.fiscal_year = h.fiscal_year
    and c.fiscal_period = h.fiscal_period and c.priority = h.priority
