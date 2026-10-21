-- All metric versions (certified + helpers). Reported values first; derived values fill only
-- the gaps reported values leave, one stored layer at a time so each layer reads the
-- previous one once (a chain of CTEs would be re-evaluated per reference on BigQuery):
--   int_metric_reported     concept map + input validation
--   int_metric_l1_quarters  Q2/Q3/Q4 from year-to-date figures (same concept only)
--   int_metric_l2           net income from ProfitLoss, bank revenue, free cash flow
--   int_metric_l3           gross profit, equity incl. NCI
--   int_metric_l4           liabilities + temporary equity (helper), long-term debt
--   this model              total liabilities, margins
{%- set duration = ['Q1', 'Q2', 'Q3', 'Q4', 'Q2_YTD', 'Q3_YTD', 'FY'] %}

with derived as (
    {{ derive(ref('int_metric_l4'),
              period_rules('total_liabilities', 'liabilities_plus_temp_equity', 'temporary_equity',
                           ['Q1', 'Q2', 'Q3', 'Q4', 'FY']),
              'a - coalesce(b, 0)', b_optional=true) }}
    union all
    {{ derive(ref('int_metric_l4'), period_rules('gross_margin', 'gross_profit', 'revenue', duration),
              'a / nullif(b, 0)') }}
    union all
    {{ derive(ref('int_metric_l4'), period_rules('operating_margin', 'operating_income', 'revenue', duration),
              'a / nullif(b, 0)') }}
    union all
    {{ derive(ref('int_metric_l4'), period_rules('net_margin', 'net_income', 'revenue', duration),
              'a / nullif(b, 0)') }}
)

{{ fill_missing(ref('int_metric_l4'), 'derived') }}
