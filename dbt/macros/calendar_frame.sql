{#-
  SEC-style calendar frame for a period: CY2024 (12 months), CY2024Q3 (3 months),
  CY2024Q3I (instant). Durations use the calendar period they mostly cover (midpoint);
  instants use the nearest calendar quarter end. Other lengths get null.
-#}
{% macro calendar_frame(period_start, period_end, duration_months) -%}
    {%- set s = dbt.type_string() -%}
    {%- set mid = dbt.dateadd('day', 'cast(' ~ dbt.datediff(period_start, period_end, 'day') ~ ' / 2 as integer)', period_start) -%}
    {%- set near_q = dbt.dateadd('day', -46, period_end) -%}
    case
        when {{ duration_months }} = 12
            then concat('CY', cast(extract(year from {{ mid }}) as {{ s }}))
        when {{ duration_months }} = 3
            then concat('CY', cast(extract(year from {{ mid }}) as {{ s }}),
                        'Q', cast(extract(quarter from {{ mid }}) as {{ s }}))
        when {{ duration_months }} = 0
            then concat('CY', cast(extract(year from {{ near_q }}) as {{ s }}),
                        'Q', cast(extract(quarter from {{ near_q }}) as {{ s }}), 'I')
    end
{%- endmacro %}
