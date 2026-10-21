{#-
  Point-in-time derivation over a long "metric versions" relation with columns
  (cik, metric_id, fiscal_year, fiscal_period, value, valid_from, valid_to).

  derive(rel, target, a, b, expr, b_optional=false)
    target, a, b: {'metric': ..., 'period': ...}; inputs share cik and fiscal_year with target.
    expr: SQL over the input values `a` and `b`, e.g. 'a - b' or 'a / nullif(b, 0)'.

  The derived value gets a new version every time either input changes (restatements of an
  input flow through), and exists only while input `a` (and `b`, unless optional) is known.
  Consecutive identical values are collapsed into one version.
-#}
{% macro derive(rel, target, a, b, expr, b_optional=false) %}
    select
        cik,
        '{{ target.metric }}' as metric_id,
        fiscal_year,
        '{{ target.period }}' as fiscal_period,
        value,
        valid_from,
        valid_to,
        'derived: {{ expr }} | a={{ a.metric }}.{{ a.period }} b={{ b.metric }}.{{ b.period }}'
            as source_concept,
        cast(null as {{ dbt.type_string() }}) as accession_number,
        true as is_derived
    from (
    -- valid_to is computed while null-valued rows are still present, so a value never
    -- stretches across a span where the derivation was undefined (e.g. revenue = 0)
    select *, lead(valid_from) over (partition by cik, fiscal_year order by valid_from) as valid_to
    from (
        select *, lag(value) over (partition by cik, fiscal_year order by valid_from) as prev_value
        from (
            select pts.cik, pts.fiscal_year, pts.t as valid_from, {{ expr }} as value
            from (
                select cik, fiscal_year, valid_from as t from {{ rel }}
                where metric_id = '{{ a.metric }}' and fiscal_period = '{{ a.period }}'
                union distinct
                select cik, fiscal_year, valid_from as t from {{ rel }}
                where metric_id = '{{ b.metric }}' and fiscal_period = '{{ b.period }}'
            ) as pts
            inner join (
                select cik, fiscal_year, value as a, valid_from, valid_to from {{ rel }}
                where metric_id = '{{ a.metric }}' and fiscal_period = '{{ a.period }}'
            ) as ta
                on ta.cik = pts.cik and ta.fiscal_year = pts.fiscal_year
                and ta.valid_from <= pts.t and (ta.valid_to is null or ta.valid_to > pts.t)
            {{ 'left' if b_optional else 'inner' }} join (
                select cik, fiscal_year, value as b, valid_from, valid_to from {{ rel }}
                where metric_id = '{{ b.metric }}' and fiscal_period = '{{ b.period }}'
            ) as tb
                on tb.cik = pts.cik and tb.fiscal_year = pts.fiscal_year
                and tb.valid_from <= pts.t and (tb.valid_to is null or tb.valid_to > pts.t)
        ) as vals
    ) as changes
    where prev_value is null or value is null or value != prev_value
    ) as versions
    where value is not null
{% endmacro %}

{#- The same derivation for each fiscal period in `periods` (inputs from the same period). -#}
{% macro per_period(rel, periods, target, a, b, expr, b_optional=false) -%}
    {%- for p in periods %}
    {{ derive(rel, {'metric': target, 'period': p}, {'metric': a, 'period': p},
              {'metric': b, 'period': p}, expr, b_optional) }}
    {%- if not loop.last %} union all {% endif -%}
    {%- endfor %}
{%- endmacro %}

{#- Rows of `derived` for keys that `base` does not already have: reported values win. -#}
{% macro fill_missing(base, derived) %}
    select * from {{ base }}
    union all
    select d.* from {{ derived }} as d
    where not exists (
        select 1 from {{ base }} as b
        where b.cik = d.cik and b.metric_id = d.metric_id
            and b.fiscal_year = d.fiscal_year and b.fiscal_period = d.fiscal_period
    )
{% endmacro %}

{#- Point-in-time filter: the version that was known on `as_of_date`. -#}
{% macro as_of(as_of_date, alias=none) -%}
    {%- set p = alias ~ '.' if alias else '' -%}
    ({{ p }}valid_from <= cast({{ as_of_date }} as date)
     and ({{ p }}valid_to is null or {{ p }}valid_to > cast({{ as_of_date }} as date)))
{%- endmacro %}
