{#- DuckDB: the configured schema as-is (silver, gold, ...). BigQuery: everything goes to the
    target dataset (`audit`); `finfacts publish` copies the gold tables to `gold` only after
    the whole build and its tests pass (write-audit-publish). -#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if target.type == 'bigquery' -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name if custom_schema_name else target.schema }}
    {%- endif -%}
{%- endmacro %}
