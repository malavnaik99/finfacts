-- depends_on: {{ ref('metrics') }}
-- Layer 1: reported values + quarters companies never file as 3-month figures:
--   Q2 = Q2_YTD - Q1, Q3 = Q3_YTD - Q2_YTD, Q4 = FY - Q3_YTD  (flow metrics only)
-- Both inputs must use the same XBRL concept; otherwise a total minus a subset tag
-- (e.g. FY Revenues minus 9M contract revenue) gives a wrong, even negative, quarter.
{%- set flow_metrics = [] -%}
{%- if execute -%}
    {%- set flow_metrics = run_query(
        "select metric_id from " ~ ref('metrics') ~ " where quarter_derivable order by metric_id"
    ).columns[0].values() -%}
{%- endif %}

with base as (
    -- explicit columns: int_metric_reported also carries its incremental cik_bucket
    select cik, metric_id, fiscal_year, fiscal_period, value, valid_from, valid_to,
           source_concept, accession_number, is_derived
    from {{ ref('int_metric_reported') }}
),

derived as (
    {{ derive(ref('int_metric_reported'), quarter_rules(flow_metrics), 'a - b', same_source=true) }}
)

{{ fill_missing('base', 'derived') }}
