# Data sources and licences

FinFacts code is MIT-licensed. The data it processes comes from the sources below. Nothing private, proprietary or employer-related is used.

| Source | URL | Terms | Used for | First downloaded |
|---|---|---|---|---|
| SEC EDGAR XBRL company facts (bulk) | https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip | Public US government data. Use must follow the [SEC fair-access policy](https://www.sec.gov/os/accessing-edgar-data): declared User-Agent, ≤ 10 requests/second | Financial facts (bronze → silver → gold) | 2026-10-20 (snapshot 2026-10-20) |
| SEC EDGAR submissions (bulk) | https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip | As above | Filing metadata, accession numbers, fiscal year end | 2026-10-20 (snapshot 2026-10-20) |
| SEC company tickers | https://www.sec.gov/files/company_tickers.json | As above | Validating CIKs in the universe | 2026-10-20 |
| SEC EDGAR APIs: submissions and companyfacts | https://data.sec.gov/submissions/, https://data.sec.gov/api/xbrl/companyfacts/ | As above | Daily incremental load | 2026-10-20 |
| SEC EDGAR 10-K documents (Item 1A and Item 7 text) | https://www.sec.gov/Archives/edgar/data/ | As above | Retrieval chunks and embeddings | 2026-10-24 |
| S&P 500 constituents (datasets/s-and-p-500-companies) | https://github.com/datasets/s-and-p-500-companies | [ODC-PDDL 1.0](http://opendatacommons.org/licenses/pddl/) (public domain dedication) | Company universe snapshot in `config/universe/` | 2026-10-20 |

`tests/fixtures/bronze/` holds a trimmed copy of eight companies' SEC data (public) for offline CI.

"S&P 500" is a trademark of S&P Dow Jones Indices LLC. FinFacts only uses the public list of constituent companies and is not affiliated with or endorsed by S&P.

## Outputs published by FinFacts

The Hugging Face dataset [`Malavnaik/finfacts`](https://huggingface.co/datasets/Malavnaik/finfacts) (eval questions, gold SQL and answers, certified tables, 10-K chunks with embeddings) is released under **CC BY 4.0**. It is derived from the SEC sources above; the embedding model `BAAI/bge-small-en-v1.5` is MIT-licensed.
