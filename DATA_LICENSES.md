# Data sources and licences

FinFacts code is MIT-licensed. The data it processes comes from the sources below. Nothing private, proprietary or employer-related is used.

| Source | URL | Terms | Used for | First downloaded |
|---|---|---|---|---|
| SEC EDGAR XBRL company facts (bulk) | https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip | Public US government data. Use must follow the [SEC fair-access policy](https://www.sec.gov/os/accessing-edgar-data): declared User-Agent, ≤ 10 requests/second | Financial facts (bronze → silver → gold) | 2026-10-20 (snapshot 2026-10-20) |
| SEC EDGAR submissions (bulk) | https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip | As above | Filing metadata, accession numbers, fiscal year end | 2026-10-20 (snapshot 2026-10-20) |
| SEC company tickers | https://www.sec.gov/files/company_tickers.json | As above | Validating CIKs in the universe | 2026-10-20 |
| S&P 500 constituents (datasets/s-and-p-500-companies) | https://github.com/datasets/s-and-p-500-companies | [ODC-PDDL 1.0](http://opendatacommons.org/licenses/pddl/) (public domain dedication) | Company universe snapshot in `config/universe/` | 2026-10-20 |

Planned (added when first used): `data.sec.gov` submissions / companyfacts / frames APIs (Week 2) and 10-K HTML documents from `sec.gov/Archives` (Week 6), both under the SEC terms above.

"S&P 500" is a trademark of S&P Dow Jones Indices LLC. FinFacts only uses the public list of constituent companies and is not affiliated with or endorsed by S&P.
