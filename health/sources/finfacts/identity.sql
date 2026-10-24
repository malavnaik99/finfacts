-- Accounting identity checks on current values (failing rows stay listed in gold).
select
    check_name,
    count(*) as checked,
    countif(not passed) as failed,
    countif(not passed) / count(*) as failure_rate,
    max(max_failure_rate) as failure_limit
from gold.identity_checks
group by check_name
