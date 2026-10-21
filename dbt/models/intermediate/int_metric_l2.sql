-- Layer 2 (on layer 1):
--   net income = ProfitLoss - NCI share   (companies that never tag NetIncomeLoss, e.g. ITW)
--   bank revenue = net interest income + non-interest income
--   free cash flow = operating cash flow - capex
{%- set periods = ['Q1', 'Q2', 'Q3', 'Q4', 'Q2_YTD', 'Q3_YTD', 'FY'] %}

with derived as (
    {{ derive(ref('int_metric_l1_quarters'),
              period_rules('net_income', 'profit_loss', 'net_income_nci', periods),
              'a - coalesce(b, 0)', b_optional=true) }}
    union all
    {{ derive(ref('int_metric_l1_quarters'),
              period_rules('revenue', 'net_interest_income', 'noninterest_income', periods),
              'a + b') }}
    union all
    {{ derive(ref('int_metric_l1_quarters'),
              period_rules('free_cash_flow', 'operating_cash_flow', 'capex', periods),
              'a - b') }}
)

{{ fill_missing(ref('int_metric_l1_quarters'), 'derived') }}
