{{ config(materialized='view') }}
-- Current value of every certified metric: the open version of each fact.
select *
from {{ ref('fct_financials') }}
where valid_to is null
