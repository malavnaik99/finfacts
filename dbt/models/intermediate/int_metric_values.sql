-- depends_on: {{ ref('metrics') }}
-- All metric versions (certified + helpers): reported values, then derived values that fill
-- only the gaps reported values leave. Each layer builds on the previous one, and every
-- derivation is point-in-time (see macros/derive.sql).
--   1. quarters:   Q2 = Q2_YTD - Q1, Q3 = Q3_YTD - Q2_YTD, Q4 = FY - Q3_YTD  (flow metrics)
--   2. net income = ProfitLoss - NCI share (companies that never tag NetIncomeLoss, e.g. ITW)
--      bank revenue = net interest income + non-interest income
--   3. gross profit = revenue - cost of revenue
--   4. equity incl. NCI = parent equity + NCI (NCI optional)
--   5. total liabilities = liabilities-and-equity - equity incl. NCI - temporary equity
--   6. long-term debt = non-current + current portion (current optional)
{%- set flow_metrics = [] -%}
{%- if execute -%}
    {%- set flow_metrics = run_query(
        "select metric_id from " ~ ref('metrics') ~ " where quarter_derivable order by metric_id"
    ).columns[0].values() -%}
{%- endif -%}
{%- set duration_periods = ['Q1', 'Q2', 'Q3', 'Q4', 'Q2_YTD', 'Q3_YTD', 'FY'] -%}
{%- set instant_periods = ['Q1', 'Q2', 'Q3', 'Q4', 'FY'] %}

with reported_raw as (
    select * from {{ ref('int_metric_reported') }}
),

-- Input validation: total equity incl. NCI cannot be far below parent equity from the same
-- filing (e.g. CIK 1090872 tags -305m against 5,898m parent equity). Such values are
-- dropped so equity incl. NCI is derived as parent equity + NCI instead.
reported as (
    select r.*
    from reported_raw as r
    where not (
        r.metric_id = 'equity_incl_nci'
        and exists (
            select 1 from reported_raw as e
            where e.metric_id = 'total_equity' and e.cik = r.cik
                and e.fiscal_year = r.fiscal_year and e.fiscal_period = r.fiscal_period
                and e.accession_number = r.accession_number
                and e.value > 0 and r.value < e.value * 0.99
        )
    )
),

quarters as (
    {%- for m in flow_metrics %}
    {{ derive('reported', {'metric': m, 'period': 'Q2'}, {'metric': m, 'period': 'Q2_YTD'},
              {'metric': m, 'period': 'Q1'}, 'a - b') }}
    union all
    {{ derive('reported', {'metric': m, 'period': 'Q3'}, {'metric': m, 'period': 'Q3_YTD'},
              {'metric': m, 'period': 'Q2_YTD'}, 'a - b') }}
    union all
    {{ derive('reported', {'metric': m, 'period': 'Q4'}, {'metric': m, 'period': 'FY'},
              {'metric': m, 'period': 'Q3_YTD'}, 'a - b') }}
    {%- if not loop.last %} union all {% endif -%}
    {%- endfor %}
),

l1 as ({{ fill_missing('reported', 'quarters') }}),
net_income as (
    {{ per_period('l1', duration_periods, 'net_income', 'profit_loss', 'net_income_nci',
                  'a - coalesce(b, 0)', b_optional=true) }}
),

l1b as ({{ fill_missing('l1', 'net_income') }}),
bank_revenue as (
    {{ per_period('l1b', duration_periods, 'revenue', 'net_interest_income', 'noninterest_income', 'a + b') }}
),

l2 as ({{ fill_missing('l1b', 'bank_revenue') }}),
gross_profit as (
    {{ per_period('l2', duration_periods, 'gross_profit', 'revenue', 'cost_of_revenue', 'a - b') }}
),

l3 as ({{ fill_missing('l2', 'gross_profit') }}),
equity_incl_nci as (
    {{ per_period('l3', instant_periods, 'equity_incl_nci', 'total_equity', 'minority_interest',
                  'a + coalesce(b, 0)', b_optional=true) }}
),

l4 as ({{ fill_missing('l3', 'equity_incl_nci') }}),
liabilities_plus_temp as (
    {{ per_period('l4', instant_periods, 'liabilities_plus_temp_equity', 'liabilities_and_equity',
                  'equity_incl_nci', 'a - b') }}
),

l5 as (select * from l4 union all select * from liabilities_plus_temp),
total_liabilities as (
    {{ per_period('l5', instant_periods, 'total_liabilities', 'liabilities_plus_temp_equity',
                  'temporary_equity', 'a - coalesce(b, 0)', b_optional=true) }}
),

l6 as ({{ fill_missing('l4', 'total_liabilities') }}),
long_term_debt as (
    {{ per_period('l6', instant_periods, 'long_term_debt', 'long_term_debt_noncurrent',
                  'long_term_debt_current', 'a + coalesce(b, 0)', b_optional=true) }}
)

{{ fill_missing('l6', 'long_term_debt') }}
