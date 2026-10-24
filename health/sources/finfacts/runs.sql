-- Last 90 pipeline runs from the run log written by `finfacts record-run`.
select
    run_id, trigger, status, started_at, finished_at,
    timestamp_diff(finished_at, started_at, second) / 60.0 as minutes,
    models_ok, models_error, tests_pass, tests_warn, tests_fail,
    queries, bytes_billed / pow(1024, 3) as gb_billed,
    bytes_billed / pow(1024, 4) * 6.25 as usd_list_price,
    latest_filing_accepted_at,
    timestamp_diff(finished_at, latest_filing_accepted_at, hour) as freshness_hours
from ops.run_log
order by started_at desc
limit 90
