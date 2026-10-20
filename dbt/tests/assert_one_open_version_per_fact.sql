-- Every fact must have exactly one current version (valid_to is null).
select fact_key, count(*) as versions,
       sum(case when valid_to is null then 1 else 0 end) as open_versions
from {{ ref('int_fact_versions') }}
group by fact_key
having sum(case when valid_to is null then 1 else 0 end) != 1
