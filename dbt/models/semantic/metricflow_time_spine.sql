-- One row per day: MetricFlow's calendar for metric_time. Covers FY2014 comparatives to 2030.
select cast(date_day as date) as date_day
from (
    {{ dbt.date_spine('day', "cast('2013-01-01' as date)", "cast('2031-01-01' as date)") }}
) as spine
