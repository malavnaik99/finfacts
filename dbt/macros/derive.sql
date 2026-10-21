{#-
  Point-in-time derivations over a long "metric versions" table with columns
  (cik, metric_id, fiscal_year, fiscal_period, value, valid_from, valid_to, source_concept).

  derive(rel, rules, expr, b_optional=false, same_source=false)
    rules: list of {'out': (metric, period), 'a': (metric, period), 'b': (metric, period)};
           build them with quarter_rules() or period_rules(). Inputs share cik and fiscal_year
           with the output.
    expr:  SQL over the input values `a` and `b`, e.g. 'a - b' or 'a / nullif(b, 0)'.
    b_optional:  derive even when `b` is unknown (expr must handle a null b).
    same_source: derive only when a and b use the same XBRL concept, so a total is never
                 combined with a subset tag (e.g. FY `Revenues` minus 9M contract revenue).

  All rules run in one pass over `rel`, which must be a stored table (a CTE would be
  re-evaluated per reference on BigQuery). A derived value gets a new version every time an
  input changes, so restatements flow through; it exists only while its inputs are known.
  Consecutive identical values collapse into one version.
-#}
{% macro derive(rel, rules, expr, b_optional=false, same_source=false) %}
    {%- set s = dbt.type_string() -%}
    {%- set rows = [] -%}
    {%- for r in rules -%}
        {%- do rows.append((r.a[0], r.a[1], 'a', r.out[0], r.out[1])) -%}
        {%- do rows.append((r.b[0], r.b[1], 'b', r.out[0], r.out[1])) -%}
    {%- endfor %}
    -- wrapped as a subquery so several derive() calls can be combined with union all
    select * from (
    with rule_inputs as (
        {%- for in_metric, in_period, role, out_metric, out_period in rows %}
        select cast('{{ in_metric }}' as {{ s }}) as in_metric, cast('{{ in_period }}' as {{ s }}) as in_period,
               cast('{{ role }}' as {{ s }}) as role,
               cast('{{ out_metric }}' as {{ s }}) as out_metric, cast('{{ out_period }}' as {{ s }}) as out_period
        {%- if not loop.last %} union all {% endif -%}
        {%- endfor %}
    ),

    inputs as (
        select
            r.cik, r.fiscal_year, m.out_metric, m.out_period, m.role,
            concat(m.in_metric, '.', m.in_period) as input_name,
            r.value, r.valid_from, r.valid_to, r.source_concept
        from {{ rel }} as r
        inner join rule_inputs as m
            on r.metric_id = m.in_metric and r.fiscal_period = m.in_period
    ),

    points as (
        select distinct cik, fiscal_year, out_metric, out_period, valid_from as t from inputs
    ),

    joined as (
        select
            p.cik, p.fiscal_year, p.out_metric, p.out_period, p.t as valid_from,
            ta.value as a,
            tb.value as b,
            concat('derived: {{ expr }} | a=', ta.input_name,
                   case when tb.input_name is not null then concat(' b=', tb.input_name) else '' end)
                as source_concept
        from points as p
        inner join inputs as ta
            on ta.role = 'a' and ta.cik = p.cik and ta.fiscal_year = p.fiscal_year
            and ta.out_metric = p.out_metric and ta.out_period = p.out_period
            and ta.valid_from <= p.t and (ta.valid_to is null or ta.valid_to > p.t)
        {{ 'left' if b_optional else 'inner' }} join inputs as tb
            on tb.role = 'b' and tb.cik = p.cik and tb.fiscal_year = p.fiscal_year
            and tb.out_metric = p.out_metric and tb.out_period = p.out_period
            and tb.valid_from <= p.t and (tb.valid_to is null or tb.valid_to > p.t)
            {%- if same_source %} and tb.source_concept = ta.source_concept{% endif %}
    ),

    vals as (
        select cik, fiscal_year, out_metric, out_period, valid_from, source_concept,
               {{ expr }} as value
        from joined
    ),

    changes as (
        select
            *,
            lag(value) over (
                partition by cik, fiscal_year, out_metric, out_period order by valid_from
            ) as prev_value
        from vals
    ),

    versions as (
        -- valid_to is computed while null-valued rows are still present, so a value never
        -- stretches across a span where the derivation was undefined (e.g. revenue = 0)
        select
            *,
            lead(valid_from) over (
                partition by cik, fiscal_year, out_metric, out_period order by valid_from
            ) as valid_to
        from changes
        where prev_value is null or value is null or value != prev_value
    )

    select
        cik,
        out_metric as metric_id,
        fiscal_year,
        out_period as fiscal_period,
        value,
        valid_from,
        valid_to,
        source_concept,
        cast(null as {{ s }}) as accession_number,
        true as is_derived
    from versions
    where value is not null
    ) as derived_rows
{% endmacro %}

{#- Q2 = Q2_YTD - Q1, Q3 = Q3_YTD - Q2_YTD, Q4 = FY - Q3_YTD for each metric. -#}
{% macro quarter_rules(metrics) -%}
    {%- set rules = [] -%}
    {%- for m in metrics -%}
        {%- do rules.append({'out': (m, 'Q2'), 'a': (m, 'Q2_YTD'), 'b': (m, 'Q1')}) -%}
        {%- do rules.append({'out': (m, 'Q3'), 'a': (m, 'Q3_YTD'), 'b': (m, 'Q2_YTD')}) -%}
        {%- do rules.append({'out': (m, 'Q4'), 'a': (m, 'FY'), 'b': (m, 'Q3_YTD')}) -%}
    {%- endfor -%}
    {{ return(rules) }}
{%- endmacro %}

{#- target = f(a, b) within each fiscal period in `periods`. -#}
{% macro period_rules(target, a, b, periods) -%}
    {%- set rules = [] -%}
    {%- for p in periods -%}
        {%- do rules.append({'out': (target, p), 'a': (a, p), 'b': (b, p)}) -%}
    {%- endfor -%}
    {{ return(rules) }}
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
