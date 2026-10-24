-- Versions of a fact must be contiguous and ordered: each version ends exactly where the
-- next one starts, and never before it starts.
with v as (
    select
        fact_key, version_no, valid_from, valid_to,
        lead(valid_from) over (partition by fact_key order by version_no) as next_from
    from {{ ref('int_fact_versions') }}
    where {{ bucket_test_scope() }}  -- only rebuilt companies on incremental runs
)
select *
from v
where valid_to < valid_from
   or (next_from is not null and valid_to != next_from)
