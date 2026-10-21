# Concept mapping: from XBRL tags to certified metrics

FinFacts publishes **21 certified metrics**. Each is defined once in [`dbt/seeds/metrics.csv`](../dbt/seeds/metrics.csv). The XBRL concepts it accepts, in priority order with a reason for each, are in [`dbt/seeds/concept_map.csv`](../dbt/seeds/concept_map.csv). In the warehouse, `gold.dim_concept` lists every metric with its definition and accepted concepts.

## The rules

1. **One concept per company, metric and fiscal period.** FinFacts uses the highest-priority concept the company ever reported for that period and records it in `source_concept`. It never sums or blends tags.
2. **Totals before subsets.** A total tag (`Revenues`, utilities' `RegulatedAndUnregulatedOperatingRevenue`) ranks above the ASC 606 `RevenueFromContractWithCustomer…` tags, which leave out non-contract revenue such as leases, derivatives and alternative revenue programmes.
3. **Reported beats derived.** A derived value only fills a gap. It is never used when the company tagged the number itself.
4. **Derivations are point-in-time.** A derived value gets a new version whenever one of its inputs is restated, and it exists only while its inputs are known ([`macros/derive.sql`](../dbt/macros/derive.sql)).
5. **No number is better than a wrong number.** Metrics that don't apply (operating income for most banks, gross profit for insurers that tag no cost of revenue) stay empty.

## Derivations

| Derived value | Rule | When it is used |
|---|---|---|
| Quarterly flows (Q2, Q3, Q4) | `Q2 = H1 − Q1`, `Q3 = 9M − H1`, `Q4 = FY − 9M` | Companies file Q4 only as part of the year, and cash-flow statements only as year-to-date. **Only when both inputs use the same XBRL concept**: subtracting a subset tag from a total (e.g. FY `Revenues` − 9M contract revenue) produced 909 wrong quarters, 18 of them negative revenue. Such quarters are left empty. Not used for EPS or share counts, which can't be subtracted. |
| Net income | `ProfitLoss − net income attributable to NCI` | Companies that never tag `NetIncomeLoss` (e.g. Illinois Tool Works). This raised net-income coverage from 89.5% to 97.7%. |
| Bank revenue | net interest income + non-interest income | Banks with no total-revenue tag. |
| Gross profit | revenue − cost of revenue | When `GrossProfit` isn't tagged. |
| Equity incl. NCI (helper) | parent equity + NCI | When not tagged, or when the tagged value fails validation (below). |
| Total liabilities | liabilities-and-equity − equity incl. NCI − temporary equity | About 28% of companies never tag `Liabilities`. |
| Long-term debt | non-current + current portion | When no total long-term-debt tag exists. |
| Free cash flow | operating cash flow − capex | Always derived. |
| Margins | gross profit, operating income or net income ÷ revenue | Always derived; null when revenue is 0. |

**Input validation.** A reported "equity including NCI" below 99% of parent equity *from the same filing* is rejected as a tagging error. Example: Agilent tags −$305M against $5,898M of parent equity.

## Decisions worth knowing

| Decision | Why |
|---|---|
| `net_income` is attributable to the parent | That's what EPS uses and what analysts quote. `ProfitLoss` (includes NCI) and `NetIncomeLossAvailableToCommonStockholdersBasic` (after preferred dividends) are rejected as primary tags. |
| `long_term_debt`, not "total debt" | There is no reliable total-debt tag. Building one from short-term borrowings + commercial paper + current debt double-counts for many companies. The metric is long-term debt including current maturities, and its name says so. |
| `cash_and_equivalents` excludes restricted cash | The balance-sheet tag comes first. The cash-flow total (which includes restricted cash) is only a fallback. |
| Cost of revenue excludes "…ExcludingDepreciation…" tags | Their different definition would overstate gross profit. |
| Fiscal year is named by the calendar year it ends in | Apple's year ending Sep 2025 is FY2025; Walmart's ending Jan 2026 is FY2026 (Walmart also calls it fiscal 2026; Target would call such a year "2025"). |
| Year ends in the first week of a month mean the previous month end | J&J's fiscal year end is listed by SEC as `0103` because one 52/53-week year ended on 3 January. Without this rule every J&J year was labelled one year late. The golden-value test caught it. |

## How the mapping is verified

| Check | Result (2026-10-21) |
|---|---|
| 30 golden values read from 10-K statements (10 companies × revenue, net income, total assets), checked **as known the day after filing** | 30 / 30 |
| Coverage of revenue / net income / total assets over company fiscal years | 97.9% / 97.7% / 98.0% (gate: 95%) |
| Balance sheet identity, assets = liabilities + equity incl. NCI + temporary equity (0.5% tolerance) | 1.96% of 18,788 company-periods fail (gate: 2.5%) |
| Gross-profit identity, gross profit = revenue − cost of revenue (1% tolerance) | 5.1% of 12,596 fail (gate: 6%) |
| Free cash flow = operating cash flow − capex | exact |

The failing identity rows are kept in `quality.identity_checks`. Most balance-sheet failures are company tagging errors. Most gross-profit failures are businesses where gross profit isn't revenue − cost of revenue. Examples are Altria (excise taxes sit between them), Caterpillar (financial-products revenue) and Centene (insurer). The gates were set just above the measured rates (an approved plan change), so any regression fails the build.

## Known limitations

- **Successor issuers.** 12 companies re-registered under a new CIK (e.g. ExxonMobil 2026, Disney 2019, Broadcom 2018, BlackRock 2024). [`config/universe/predecessors.csv`](../config/universe/predecessors.csv) maps each old CIK to the new one, with a cutoff at the successor's 8-K12B succession filing, because some old CIKs keep filing as subsidiaries. Every pair was checked against SEC's own records; one remembered CIK (Evergy's) was wrong and was corrected. Paramount Skydance is left out because it is unclear which company is the accounting predecessor. Remaining gaps: APA has tagged revenue only with its own extension concept since 2021, and BlackRock's old CIK has no FY2015 total-revenue fact.
- **Concept switching.** A company can move between tags over the years, for example Apple: `SalesRevenueNet` → `Revenues` → ASC 606. Values stay comparable in practice, and `source_concept` shows every switch.
- **Recast years.** When a company recasts its full year (e.g. discontinued operations) but not the 9-month figure, FY − 9M is genuinely negative. 13 revenue quarters are affected (e.g. AIG 2022 Q4, Exelon 2020 Q4). They are kept as calculated and flagged by `is_derived`.
- **Banks and insurers.** Revenue follows the bank-revenue rule above. Insurers' revenue uses `Revenues`. Gross profit and operating income are mostly empty by design.
