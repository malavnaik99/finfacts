-- Layer 4 (on layer 3):
--   liabilities + temporary equity (helper) = liabilities-and-equity - equity incl. NCI
--   long-term debt = non-current + current portion (current optional)
{%- set periods = ['Q1', 'Q2', 'Q3', 'Q4', 'FY'] %}

with derived as (
    {{ derive(ref('int_metric_l3'),
              period_rules('liabilities_plus_temp_equity', 'liabilities_and_equity',
                           'equity_incl_nci', periods),
              'a - b') }}
    union all
    {{ derive(ref('int_metric_l3'),
              period_rules('long_term_debt', 'long_term_debt_noncurrent',
                           'long_term_debt_current', periods),
              'a + coalesce(b, 0)', b_optional=true) }}
)

{{ fill_missing(ref('int_metric_l3'), 'derived') }}
