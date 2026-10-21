{{ config(tags=['full_data']) }}
-- Fails on purpose only when run with --vars '{wap_drill: true}': proves that a failing test
-- stops the pipeline before `finfacts publish`, so gold keeps its last good version.
select 'write-audit-publish drill: deliberate failure' as reason
from (select 1 as one) as t
where {{ 'true' if var('wap_drill', false) else 'false' }}
