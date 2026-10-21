-- One row per certified metric, with its definition and the XBRL concepts it accepts
-- (in priority order). Helper metrics used only for derivations are excluded.
select
    m.metric_id,
    m.name,
    m.unit,
    m.period_type,
    m.statement,
    m.definition,
    m.quarter_derivable,
    {{ dbt.listagg("c.taxonomy || ':' || c.concept", "' > '", "order by c.priority") }}
        as source_concepts
from {{ ref('metrics') }} as m
left join {{ ref('concept_map') }} as c on m.metric_id = c.metric_id
where m.is_certified
group by m.metric_id, m.name, m.unit, m.period_type, m.statement, m.definition, m.quarter_derivable
