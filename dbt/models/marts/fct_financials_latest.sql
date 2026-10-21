-- a table, not a view: publish copies it from audit to gold, and a view would keep
-- pointing at audit
{{ config(materialized='table') }}
-- Current value of every certified metric: the open version of each fact.
select *
from {{ ref('fct_financials') }}
where valid_to is null
