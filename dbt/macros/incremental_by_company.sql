{#-
  Incremental by company. A new filing only changes data for its own company, and every
  silver model is computed per company (all windows partition by CIK or by keys containing
  it), so a daily run rebuilds only companies whose files changed.

  Companies are grouped into 1,000 buckets (CIK mod 1000). `finfacts load-bq` compares the
  files it loads with those of the last successful build and passes three vars to dbt:
    changed_buckets  buckets with at least one changed company
    scope_ciks       every universe company in those buckets (successor CIKs)
    scope_raw_ciks   scope_ciks plus their predecessor CIKs (as they appear in raw tables)
  Without these vars (local builds, CI, first run, full refresh) everything is rebuilt.

  BigQuery: integer-range partitions on cik_bucket, insert_overwrite (dynamic) replaces only
  the buckets the run produced. DuckDB: delete+insert on cik_bucket.
-#}

{% macro cik_bucket(col='cik') -%}
    mod(cast({{ col }} as {{ dbt.type_bigint() }}), 1000)
{%- endmacro %}

{% macro company_incremental_config() -%}
    {%- if target.type == 'bigquery' -%}
        {%- set cfg = {
            'materialized': 'incremental',
            'incremental_strategy': 'insert_overwrite',
            'partition_by': {'field': 'cik_bucket', 'data_type': 'int64',
                             'range': {'start': 0, 'end': 1000, 'interval': 1}},
            'cluster_by': ['cik'],
            'on_schema_change': 'fail',
        } -%}
    {%- else -%}
        {%- set cfg = {
            'materialized': 'incremental',
            'incremental_strategy': 'delete+insert',
            'unique_key': 'cik_bucket',
            'on_schema_change': 'fail',
        } -%}
    {%- endif -%}
    {{ return(cfg) }}
{%- endmacro %}

{#- Row filter on a model's input during an incremental run; `true` otherwise.
    kind='raw' filters raw tables (predecessor CIKs not yet mapped); kind='bucket' filters a
    bucketed silver table on cik_bucket, which guarantees partition pruning on BigQuery. -#}
{% macro company_scope(col, kind='mapped') -%}
    {#- unit tests have no target table (this is none), so is_incremental() must not run -#}
    {%- if var('changed_buckets', none) is not none and this is not none and is_incremental() -%}
        {%- if kind == 'bucket' -%}
            {%- set values = var('changed_buckets') -%}
        {%- else -%}
            {%- set values = var('scope_raw_ciks') if kind == 'raw' else var('scope_ciks') -%}
        {%- endif -%}
        {{ col }} in ({{ values | join(', ') if values else '-1' }})
    {%- else -%}
        true
    {%- endif -%}
{%- endmacro %}

{#- Same scope for tests on bucketed tables: unchanged buckets were tested when built and
    have not been touched since. -#}
{% macro bucket_test_scope(col='cik_bucket') -%}
    {%- set buckets = var('changed_buckets', none) -%}
    {%- if buckets is not none -%}
        {{ col }} in ({{ buckets | join(', ') if buckets else '-1' }})
    {%- else -%}
        1 = 1
    {%- endif -%}
{%- endmacro %}
