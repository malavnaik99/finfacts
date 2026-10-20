{#- Small cross-engine helpers so the same models run on DuckDB (local/CI) and BigQuery (prod). -#}

{#- Null-safe, delimiter-separated hash of columns: a stable surrogate key. -#}
{% macro surrogate_key(cols) -%}
    {%- set parts = [] -%}
    {%- for c in cols -%}
        {%- do parts.append("coalesce(cast(" ~ c ~ " as " ~ dbt.type_string() ~ "), '_null_')") -%}
        {%- if not loop.last -%}{%- do parts.append("'|'") -%}{%- endif -%}
    {%- endfor -%}
    {{ dbt.hash(dbt.concat(parts)) }}
{%- endmacro %}

{% macro make_date(year, month, day) -%}
    {{ return(adapter.dispatch('make_date')(year, month, day)) }}
{%- endmacro %}

{% macro default__make_date(year, month, day) -%}
    make_date(cast({{ year }} as integer), cast({{ month }} as integer), cast({{ day }} as integer))
{%- endmacro %}

{% macro bigquery__make_date(year, month, day) -%}
    date(cast({{ year }} as int64), cast({{ month }} as int64), cast({{ day }} as int64))
{%- endmacro %}
