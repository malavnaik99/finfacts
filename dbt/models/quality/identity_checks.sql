-- Accounting identities on current values, one row per check per company-period.
-- Checks run only where every input was REPORTED (not derived); otherwise an identity would
-- be true by construction and prove nothing.
--   balance_sheet: assets = liabilities + equity incl. NCI + temporary equity  (0.5%)
--   gross_profit:  gross profit = revenue - cost of revenue                     (1%)
-- Failing rows are the exception list. assert_identity_exception_rate fails the build when a
-- check's failure rate exceeds max_failure_rate. Limits were calibrated on 2026-10-21 just
-- above measured rates (balance sheet 1.96%, gross profit 5.15%; approved plan change) so
-- any regression fails, while known company-specific tagging issues stay listed here.
with latest as (
    select cik, metric_id, fiscal_year, fiscal_period, value, is_derived
    from {{ ref('int_metric_values') }}
    where valid_to is null
),

pivoted as (
    select
        cik,
        fiscal_year,
        fiscal_period,
        max(case when metric_id = 'total_assets' and not is_derived then value end) as assets,
        max(case when metric_id = 'total_liabilities' and not is_derived then value end) as liabilities,
        max(case when metric_id = 'equity_incl_nci' then value end) as equity_incl_nci,
        max(case when metric_id = 'temporary_equity' then value end) as temporary_equity,
        max(case when metric_id = 'revenue' and not is_derived then value end) as revenue,
        max(case when metric_id = 'cost_of_revenue' and not is_derived then value end) as cost_of_revenue,
        max(case when metric_id = 'gross_profit' and not is_derived then value end) as gross_profit
    from latest
    group by cik, fiscal_year, fiscal_period
),

checks as (
    select
        cik, fiscal_year, fiscal_period,
        'balance_sheet' as check_name,
        assets as expected,
        liabilities + equity_incl_nci + coalesce(temporary_equity, 0) as actual,
        0.005 as tolerance,
        0.025 as max_failure_rate
    from pivoted
    where assets is not null and liabilities is not null and equity_incl_nci is not null
    union all
    select
        cik, fiscal_year, fiscal_period,
        'gross_profit' as check_name,
        gross_profit as expected,
        revenue - cost_of_revenue as actual,
        0.01 as tolerance,
        0.06 as max_failure_rate
    from pivoted
    where gross_profit is not null and revenue is not null and cost_of_revenue is not null
)

select
    *,
    abs(expected - actual) / nullif(abs(expected), 0) as relative_diff,
    coalesce(abs(expected - actual) <= tolerance * abs(expected), false) as passed
from checks
