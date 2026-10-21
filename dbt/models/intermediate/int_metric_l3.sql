-- Layer 3 (on layer 2):
--   gross profit = revenue - cost of revenue
--   equity incl. NCI = parent equity + NCI (NCI optional)
with derived as (
    {{ derive(ref('int_metric_l2'),
              period_rules('gross_profit', 'revenue', 'cost_of_revenue',
                           ['Q1', 'Q2', 'Q3', 'Q4', 'Q2_YTD', 'Q3_YTD', 'FY']),
              'a - b') }}
    union all
    {{ derive(ref('int_metric_l2'),
              period_rules('equity_incl_nci', 'total_equity', 'minority_interest',
                           ['Q1', 'Q2', 'Q3', 'Q4', 'FY']),
              'a + coalesce(b, 0)', b_optional=true) }}
)

{{ fill_missing(ref('int_metric_l2'), 'derived') }}
