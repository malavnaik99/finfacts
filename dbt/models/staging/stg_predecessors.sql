-- Companies that re-registered under a new CIK (holding-company reorganisations,
-- redomiciles). Facts and filings of the predecessor CIK that SEC accepted before the
-- succession (cutoff_date = the successor's 8-K12B) are attributed to the successor;
-- later ones are dropped, because some predecessors keep filing as subsidiaries.
select
    cast(successor_cik as bigint) as successor_cik,
    cast(predecessor_cik as bigint) as predecessor_cik,
    cast(cutoff_date as date) as cutoff_date
from {{ source('config', 'predecessors') }}
