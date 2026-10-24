-- Every certified metric value in gold has exactly one current version (valid_to is null).
-- Guards the input validation in int_metric_reported: dropping a mis-tagged LATEST version
-- while older ones stay would leave a key with no current value and nothing filling it.
select cik, metric_id, fiscal_year, fiscal_period,
       sum(case when valid_to is null then 1 else 0 end) as current_versions
from {{ ref('fct_financials') }}
group by cik, metric_id, fiscal_year, fiscal_period
having sum(case when valid_to is null then 1 else 0 end) != 1
