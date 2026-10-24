-- Headline numbers for the page.
select
    (select count(distinct cik) from gold.fct_financials_latest) as companies,
    (select count(distinct metric_id) from gold.fct_financials_latest) as metrics,
    (select count(*) from gold.fct_financials) as fact_versions,
    (select countif(is_restatement) from gold.fct_financials) as restatements,
    (select min(fiscal_year) from gold.fct_financials_latest) as first_fiscal_year,
    (select max(fiscal_year) from gold.fct_financials_latest) as last_fiscal_year
