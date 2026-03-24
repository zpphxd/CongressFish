"""
Congressional Data API Clients
==============================
Async HTTP clients for pulling data from various government and external APIs.

Modules:
  - unitedstates_project: Cross-reference ID mapper from GitHub YAML
  - congress_gov: Congress.gov API v3 client (primary legislative data)
  - voteview: VoteView CSV download and DW-NOMINATE score extraction
  - openfec: OpenFEC API client for campaign finance data
  - stock_trades: Quiver Quantitative + Capitol Trades for STOCK Act disclosures
  - scotus: Oyez API + SCDB CSV for Supreme Court justice data
  - executive: Federal Register + manual data for President/VP/Cabinet
  - scorecards: Web scraping for organizational congressional scorecards

All clients include:
  - Response caching to disk (no re-pulls during development)
  - Retry logic via tenacity (exponential backoff)
  - Rate limit respect
"""

__all__ = [
    'unitedstates_project',
    'congress_gov',
    'voteview',
    'openfec',
    'stock_trades',
    'scotus',
    'executive',
    'scorecards',
]
