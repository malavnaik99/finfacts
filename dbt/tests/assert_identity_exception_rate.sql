{{ config(tags=['full_data']) }}
-- Each accounting identity may fail on at most its max_failure_rate of checked
-- company-periods (see quality.identity_checks for the limits and the failing rows).
select
    check_name,
    count(*) as checked,
    sum(case when passed then 0 else 1 end) as failed,
    1.0 * sum(case when passed then 0 else 1 end) / count(*) as failure_rate,
    max(max_failure_rate) as max_failure_rate
from {{ ref('identity_checks') }}
group by check_name
having 1.0 * sum(case when passed then 0 else 1 end) / count(*) > max(max_failure_rate)
