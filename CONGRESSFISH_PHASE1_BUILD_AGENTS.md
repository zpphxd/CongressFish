# Claude Code Prompt: CongressFish Phase 1 — Build Persistent Government Agent Profiles

## What This Is

We are forking MiroFish-Offline (already running locally with Neo4j + Ollama) into **CongressFish** — a US government simulation engine. This prompt covers **Phase 1 only**: building persistent, locally-stored agent profiles for every member of Congress, Supreme Court justice, the President/VP, and key influence organizations.

These agents are NOT generated fresh each simulation. They are **built once from a deep data pull, saved locally as persistent entities in Neo4j and as JSON profile files, and then lightly refreshed on each startup** with a quick sweep for new votes, trades, and disclosures.

The simulation engine (Phase 2) will consume these pre-built agents. This phase is purely about data ingestion, profile generation, and local persistence.

---

## Critical Context

- **ProPublica Congress API is DEAD.** No new API keys are being issued. Do NOT use it.
- **GovTrack's bulk data/API is ending.** Use it for historical reference but don't depend on it long-term.
- **Primary data source is the official Congress.gov API** (Library of Congress) — free, well-maintained, has members, votes, bills, committees, cosponsors.
- **Financial trades (STOCK Act disclosures) are critical.** Members' stock trades reveal their true financial interests and potential conflicts. This data must be part of every agent profile.
- **Donor data is critical.** Who funds a member shapes how they vote. OpenFEC + OpenSecrets are the sources.
- **All agent data is stored locally** — Neo4j for the relationship graph, JSON files for full profiles, Ollama-generated persona narratives saved to disk.

---

## Project Setup

```bash
# Fork from existing MiroFish-Offline
cp -r ~/MiroFish-Offline ~/congressfish
cd ~/congressfish

# Create new directories
mkdir -p backend/agents/apis
mkdir -p backend/agents/profiles
mkdir -p backend/agents/storage
mkdir -p backend/agents/cache          # Raw API response caching
mkdir -p backend/agents/personas       # Generated persona JSON files
mkdir -p backend/agents/templates      # Prompt templates for persona generation
mkdir -p backend/agents/trades         # Financial disclosure data
mkdir -p backend/agents/donors         # Campaign finance data

# Install additional dependencies
pip install requests aiohttp tenacity pydantic python-dotenv neo4j beautifulsoup4 lxml
```

Add to `.env`:
```
# Congress.gov API (free — get key at https://api.data.gov/signup/)
CONGRESS_GOV_API_KEY=your_key

# OpenFEC (free — get key at https://api.open.fec.gov/developers/)
OPENFEC_API_KEY=your_key

# OpenSecrets — API is DEAD (discontinued April 2025)
# Use bulk data downloads instead: https://www.opensecrets.org/bulk-data
# Register for educational access to get CSV dumps of all campaign finance + lobbying data
# No API key needed — download CSVs and process locally

# Quiver Quantitative (for congressional stock trades — check https://www.quiverquant.com/api/)
QUIVER_API_KEY=your_key

# Neo4j (existing from MiroFish-Offline)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=mirofish

# Ollama (existing from MiroFish-Offline)
LLM_API_KEY=ollama
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL_NAME=qwen2.5:32b
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_BASE_URL=http://localhost:11434
```

---

## Data Source Matrix

Every agent needs data from multiple sources. Here's what we pull from where:

| Data | Source | API | Free? | Notes |
|------|--------|-----|-------|-------|
| Member list, bio, party, state, district | Congress.gov API | `api.congress.gov/v3/member` | Yes (key required) | Official LOC source, replaces ProPublica |
| Voting records (roll call) | Congress.gov API | `api.congress.gov/v3/vote` | Yes | House votes added 2025, Senate available |
| Bills sponsored/cosponsored | Congress.gov API | `api.congress.gov/v3/bill` | Yes | Full bill data 1973-present |
| Committee assignments | Congress.gov API | `api.congress.gov/v3/committee` | Yes | Current and historical |
| Amendments | Congress.gov API | `api.congress.gov/v3/amendment` | Yes | Amendment sponsorship data |
| DW-NOMINATE ideology scores | VoteView | CSV download from voteview.com | Yes, no key | Best ideology positioning data |
| Campaign finance — donors | OpenFEC | `api.open.fec.gov/v1/` | Yes (key required) | Donor lists, PAC money, industry breakdown |
| Campaign finance — totals | OpenFEC | `api.open.fec.gov/v1/` | Yes | Total raised, spent, cash on hand |
| Lobbying data | OpenSecrets | `opensecrets.org/api/` | Yes (limited) | Top industries, PAC contributions, scorecards |
| Stock trades (STOCK Act) | Quiver Quantitative | `quiverquant.com/api/` | Free tier available | Congressional stock/options trades |
| Stock trades (backup) | Capitol Trades | Scrape `capitoltrades.com` | Free to view | Backup if Quiver is limited |
| Stock trades (official) | House/Senate clerk | `efdsearch.senate.gov`, `disclosures-clerk.house.gov` | Yes | Official STOCK Act filings, PDF parsing needed |
| SCOTUS justice data | Oyez Project | `api.oyez.org` | Yes, no key | Justice profiles, case history |
| SCOTUS voting patterns | Supreme Court Database | `scdb.wustl.edu` | Yes, CSV download | Case-level voting data by justice |
| Executive orders | Federal Register | `federalregister.gov/api/v1/` | Yes, no key | Presidential actions |
| congress-legislators (GitHub) | unitedstates project | GitHub YAML bulk data | Yes | Best source for biographical data, social media, IDs |
| LegiScan | LegiScan API | `api.legiscan.com` | Free tier (30k/mo) | Bill tracking, search, supplements Congress.gov |

---

## API Client Modules

### 1. Congress.gov API Client
`backend/agents/apis/congress_gov.py`

This is the PRIMARY data source. It replaces ProPublica for all legislative data.

```python
"""
Congress.gov API v3 Client
Docs: https://api.congress.gov/
GitHub: https://github.com/LibraryOfCongress/api.congress.gov

Key endpoints:
  GET /v3/member
    - List all members, filter by congress number, state, district
    - Returns: bioguideId, name, party, state, district, terms, depiction (photo)
  GET /v3/member/{bioguideId}
    - Full member detail
  GET /v3/member/{bioguideId}/sponsored-legislation
    - Bills this member has sponsored
  GET /v3/member/{bioguideId}/cosponsored-legislation
    - Bills this member has cosponsored
  GET /v3/bill/{congress}/{billType}/{billNumber}
    - Bill detail with actions, text, summaries
  GET /v3/bill/{congress}/{billType}/{billNumber}/cosponsors
    - Cosponsor list for a bill
  GET /v3/committee/{chamber}/{committeeCode}
    - Committee detail and membership
  GET /v3/vote (BETA - House roll call votes added May 2025)
    - Roll call vote data with per-member positions

Rate limit: ~5000/hour (generous)
Auth: ?api_key={key} query parameter
Response: JSON (default) or XML
Pagination: offset-based, 20 results default, max 250

Build an async client with caching (save raw JSON responses to cache/) and retry logic (tenacity, exponential backoff). Every API response should be cached to disk so we never re-pull the same data during development.
"""
```

### 2. congress-legislators GitHub Data
`backend/agents/apis/unitedstates_project.py`

The `unitedstates/congress-legislators` GitHub repo has the BEST biographical and cross-reference data. Pull the YAML files directly.

```python
"""
Source: https://github.com/unitedstates/congress-legislators
Files:
  - legislators-current.yaml: All current members with:
    - Full name, birthday, gender
    - bioguide, thomas, govtrack, opensecrets (CRP), votesmart, fec IDs
    - Official website, social media accounts
    - Terms of service (chamber, state, district, party, start/end dates)
  - legislators-historical.yaml: Former members (same schema)
  - committees-current.yaml: Committee names, jurisdictions
  - committee-membership-current.yaml: Who sits on what

Download these as raw YAML and parse locally.
This gives us the ID cross-reference table needed to join data across
Congress.gov, OpenFEC, OpenSecrets, VoteView, etc.
"""
```

### 3. VoteView / DW-NOMINATE
`backend/agents/apis/voteview.py`

```python
"""
Source: https://voteview.com/data
Download: members.csv for the current congress

Key fields:
  - bioguide_id (join key)
  - nominate_dim1: Liberal-conservative score (-1 to +1)
  - nominate_dim2: Second dimension (historically: race/region, now less clear)
  - party_code
  - congress

This is the gold standard for ideological positioning.
Also download rollcall votes CSV for detailed vote-by-vote data.
No API key needed — direct CSV download.
"""
```

### 4. OpenFEC Client (Campaign Finance)
`backend/agents/apis/openfec.py`

```python
"""
OpenFEC API
Docs: https://api.open.fec.gov/developers/
Auth: api_key query parameter

Key endpoints:
  GET /v1/candidates/
    - Search candidates by name, state, office
  GET /v1/candidates/{candidate_id}/totals/
    - Fundraising totals by cycle
  GET /v1/schedules/schedule_a/
    - Individual contributions (donors)
    - Filter by committee_id, contributor_name
    - Get top donors per member
  GET /v1/schedules/schedule_b/
    - Disbursements (where money goes)
  GET /v1/committee/{committee_id}/
    - PAC and committee details
  GET /v1/candidates/{candidate_id}/totals/
    - Total receipts, disbursements, cash on hand, debt

Build per-member financial profile:
  - Total raised this cycle
  - % from individuals vs PACs vs party
  - Top 20 individual donors (name, employer, amount)
  - Top 20 organizational/PAC donors
  - Industry breakdown of donations
  - Self-funding amount

Rate limit: 1000 requests/hour
Use the FEC ID from congress-legislators YAML to join.
"""
```

### 5. Stock Trades (STOCK Act Disclosures)
`backend/agents/apis/stock_trades.py`

This is the "follow their money" layer. Critical for understanding financial conflicts of interest.

```python
"""
Congressional stock trade data sources:

PRIMARY: Quiver Quantitative API
  - https://www.quiverquant.com/sources/congresstrading
  - Provides parsed STOCK Act disclosures
  - Fields: representative, transaction_date, ticker, asset_description,
    type (purchase/sale), amount_range, district, party

BACKUP: Capitol Trades (capitoltrades.com)
  - Scrape if Quiver is rate-limited
  - Similar data structure

OFFICIAL (if needed for depth):
  - Senate: https://efdsearch.senate.gov/search/
  - House: https://disclosures-clerk.house.gov/FinancialDisclosure
  - These are the raw STOCK Act filings (often PDFs)
  - Parse with BeautifulSoup for the search index, then PDF parsing for details

For each member, build a financial interests profile:
  - All stock trades in the last 2 years
  - Current estimated holdings by sector/industry
  - Largest positions
  - Most active trading sectors
  - Trades that coincide with committee activity (potential conflicts)
  - Aggregate: net buyer or seller? Which sectors?

This data is GOLD for the simulation because:
  - A member who owns $500K in defense stocks and sits on Armed Services
    has a financial incentive to support defense spending
  - A member actively buying pharma stocks before a healthcare vote
    reveals their true expectations
  - Stock trades are often more honest than public statements
"""
```

### 6. OpenSecrets Bulk Data Processor (API is DEAD — use CSV downloads)
`backend/agents/apis/opensecrets_bulk.py`

```python
"""
OpenSecrets API was discontinued April 2025.
Bulk data downloads are still available for educational use.
Register at: https://www.opensecrets.org/bulk-data

SETUP:
1. Register for bulk data access (educational use)
2. Download these CSV tables:
   - CandsCRP: Candidate information with CRP IDs
   - PACs: PAC-to-candidate contributions
   - Indivs: Individual contributions (largest file, ~1.5GB)
   - Lobby: Lobbying registrations
   - Lobs: Individual lobbyist records
   - LobbyIndustry: Industry lobbying totals
   - LobbyAgency: Agencies lobbied
   - LobbyIssue: Issues lobbied on
   - LobbyBill: Specific bills lobbied
3. Store in backend/agents/cache/opensecrets/
4. Load into DuckDB for fast local querying

DuckDB is preferred over SQLite for this because:
- Handles 1.5GB CSV files without breaking a sweat
- Column-oriented storage is perfect for analytical queries
- Can query CSVs directly without importing

pip install duckdb

USAGE:
  db = duckdb.connect('backend/agents/cache/opensecrets/opensecrets.duckdb')
  
  # Import CSVs on first run
  db.execute("CREATE TABLE IF NOT EXISTS pacs AS SELECT * FROM read_csv_auto('PACs.csv')")
  db.execute("CREATE TABLE IF NOT EXISTS indivs AS SELECT * FROM read_csv_auto('Indivs.csv')")
  db.execute("CREATE TABLE IF NOT EXISTS lobby AS SELECT * FROM read_csv_auto('Lobby.csv')")
  # etc.
  
  # Query: Top PAC donors to a specific candidate
  db.execute('''
    SELECT Orgname, Total
    FROM pacs 
    WHERE CID = ? AND Cycle = '2024'
    ORDER BY Total DESC LIMIT 20
  ''', [crp_id])
  
  # Query: Industry breakdown for a candidate
  db.execute('''
    SELECT RealCode, SUM(Amount) as total
    FROM indivs
    WHERE RecipID = ? AND Cycle = '2024'
    GROUP BY RealCode
    ORDER BY total DESC
  ''', [crp_id])
  
  # Query: Lobbying on bills in a specific committee's jurisdiction
  db.execute('''
    SELECT lb.BillID, l.Client, l.Amount
    FROM lobby_bill lb
    JOIN lobby l ON lb.UniqID = l.UniqID
    WHERE lb.BillID LIKE 'h119%'
    ORDER BY l.Amount DESC
  ''')

Cross-reference CRP IDs to bioguide IDs via congress-legislators YAML.
The YAML includes opensecrets_id (CRP ID) for most members.
"""
```

### 7. Supreme Court Data
`backend/agents/apis/scotus.py`

```python
"""
Sources:
  Oyez API: https://api.oyez.org/
    - GET /justices → all justices with bios
    - GET /justices/{id} → detail including opinions
    - GET /cases → case list with outcomes
    - No key needed

  Supreme Court Database (SCDB):
    - http://scdb.wustl.edu/data.php
    - Download case-centered data CSV
    - Fields: case name, docket, decision date, issue area,
      direction (conservative/liberal), vote margin,
      per-justice vote (majority/dissent/concurrence)

  Build per-justice profile:
    - Appointing president and confirmation vote margin
    - Ideological lean from SCDB voting patterns
    - Issue area breakdown (1st amendment, due process, economic, etc.)
    - Agreement rate with every other current justice
    - Dissent frequency and patterns
    - Opinion writing tendencies
"""
```

### 8. Executive Branch
`backend/agents/apis/executive.py`

```python
"""
Executive branch agents are fewer and more manually curated.

  President:
    - Policy positions from official White House statements
    - Executive orders from Federal Register API:
      GET https://www.federalregister.gov/api/v1/documents.json
        ?presidential_document_type=executive_order
        &president=donald-trump  (or current president)
    - Signing statements and vetoes from Congress.gov
    - Approval rating (scrape from 538 or RCP)

  Vice President:
    - Role as Senate tie-breaker (critical for 50-50 votes)
    - Policy positions and public statements

  Key Cabinet (manually maintained):
    - Relevant secretaries based on simulation topic
    - E.g., Treasury Secretary for financial regulation bills,
      Defense Secretary for military spending bills

Federal Register API needs no key.
"""
```

---

## Agent Profile Schema

`backend/agents/profiles/models.py`

Every agent is persisted locally as a JSON file AND as a Neo4j node. The JSON is the complete profile; Neo4j stores the relational data.

```python
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class StockTrade(BaseModel):
    date: datetime
    ticker: str
    asset_description: str
    transaction_type: str  # purchase, sale, exchange
    amount_range: str  # "$1,001 - $15,000", "$50,001 - $100,000", etc.
    amount_low: int  # parsed lower bound
    amount_high: int  # parsed upper bound

class DonorRecord(BaseModel):
    name: str
    organization: Optional[str]
    industry: Optional[str]
    total_amount: float
    cycle: str

class ScorecardRating(BaseModel):
    organization: str
    score: str  # "A+", "92%", "F", etc.
    year: int
    issue_area: str  # "guns", "environment", "labor", etc.

class CongressMemberProfile(BaseModel):
    """Complete locally-persisted profile for a Congress member agent."""

    # Identity
    bioguide_id: str  # Primary key across all systems
    full_name: str
    first_name: str
    last_name: str
    party: str
    chamber: str  # "senate" or "house"
    state: str
    district: Optional[str]  # None for senators
    date_of_birth: Optional[str]
    gender: Optional[str]
    photo_url: Optional[str]

    # Cross-reference IDs (for joining across data sources)
    fec_id: Optional[str]
    opensecrets_id: Optional[str]  # CRP ID
    govtrack_id: Optional[str]
    votesmart_id: Optional[str]
    thomas_id: Optional[str]

    # Legislative record
    terms_served: int
    current_term_start: str
    next_election: str
    leadership_role: Optional[str]  # "Speaker", "Majority Whip", etc.
    committees: list[dict]  # [{name, code, chamber, rank, is_chair, subcommittees}]
    caucuses: list[str]
    bills_sponsored: list[dict]  # [{bill_id, title, status, issue_area}]
    bills_cosponsored: list[dict]
    recent_votes: list[dict]  # [{vote_id, bill, date, position, party_vote}]

    # Ideology & loyalty
    dw_nominate_dim1: Optional[float]  # -1 (liberal) to +1 (conservative)
    dw_nominate_dim2: Optional[float]
    party_loyalty_pct: Optional[float]  # % votes with party
    bipartisan_index: Optional[float]  # from GovTrack or Lugar Center

    # FINANCIAL — FOLLOW THE MONEY
    # Campaign finance
    total_raised_current_cycle: Optional[float]
    pct_from_individuals: Optional[float]
    pct_from_pacs: Optional[float]
    pct_self_funded: Optional[float]
    cash_on_hand: Optional[float]
    top_donors: list[DonorRecord]  # Top 20 donors
    top_industries: list[dict]  # [{industry, amount, pct}]
    top_pac_donors: list[DonorRecord]

    # Stock trades (STOCK Act)
    stock_trades: list[StockTrade]  # All trades last 2 years
    top_sectors_traded: list[dict]  # [{sector, net_buy_sell, total_volume}]
    potential_conflicts: list[dict]  # [{trade, committee_overlap, description}]
    estimated_portfolio_sectors: list[dict]  # Best estimate of holdings by sector

    # Influence & pressure points
    scorecard_ratings: list[ScorecardRating]
    vulnerability_score: Optional[float]  # How competitive is their seat? (0-1)
    margin_last_election: Optional[float]
    district_lean: Optional[str]  # "R+12", "D+3", "EVEN", etc.

    # Social & communication
    official_website: Optional[str]
    twitter_handle: Optional[str]
    facebook: Optional[str]
    youtube: Optional[str]

    # Generated content
    persona_narrative: Optional[str]  # Ollama-generated behavioral description
    persona_generated_at: Optional[datetime]

    # Metadata
    data_pulled_at: datetime
    data_sources: list[str]  # Which APIs contributed to this profile
    last_refresh_at: Optional[datetime]


class JusticeProfile(BaseModel):
    """Persistent profile for a Supreme Court justice agent."""
    name: str
    appointed_by: str
    confirmation_vote: Optional[str]  # "78-22"
    appointment_year: int
    ideology_score: Optional[float]
    liberal_vote_pct: Optional[float]
    conservative_vote_pct: Optional[float]
    issue_area_breakdown: dict  # {issue: {liberal_pct, conservative_pct, total_cases}}
    agreement_rates: dict  # {other_justice_name: pct}
    notable_opinions: list[dict]
    dissent_rate: Optional[float]
    persona_narrative: Optional[str]
    persona_generated_at: Optional[datetime]
    data_pulled_at: datetime


class ExecutiveProfile(BaseModel):
    """Persistent profile for President/VP."""
    name: str
    role: str  # "president" or "vice_president"
    party: str
    approval_rating: Optional[float]
    policy_positions: list[dict]  # [{issue, position, strength}]
    executive_orders: list[dict]  # [{title, date, summary, issue_area}]
    vetoes: list[dict]
    signing_statements: list[dict]
    persona_narrative: Optional[str]
    data_pulled_at: datetime


class InfluenceOrgProfile(BaseModel):
    """Persistent profile for lobby orgs, PACs, advocacy groups."""
    name: str
    org_type: str  # "lobby", "pac", "advocacy", "think_tank"
    ideology: Optional[str]  # "conservative", "liberal", "nonpartisan"
    key_issues: list[str]
    annual_lobbying_spend: Optional[float]
    top_recipients: list[dict]  # [{member_bioguide, amount, cycle}]
    congressional_scorecard: Optional[dict]  # {bioguide_id: score}
    persona_narrative: Optional[str]
    data_pulled_at: datetime
```

---

## Persona Generation

`backend/agents/profiles/generator.py`

For each agent, use Ollama to generate a behavioral persona narrative. This is the text that gets injected into the agent's system prompt during simulation.

**This runs ONCE during initial build, then only re-runs when significant new data arrives.**

### Congressional Member Persona Prompt Template
`backend/agents/templates/congress_member_prompt.txt`

```
You are generating a behavioral persona for a political simulation agent.
This agent represents a real US Congress member. Based on the following
REAL DATA, write a detailed behavioral description (500-800 words) that
captures HOW this person would behave in legislative negotiations.

Do NOT just list facts. Describe BEHAVIORAL PATTERNS:
- What are they willing to trade in a negotiation? What's untouchable?
- When do they break from their party? What triggers it?
- How do their donors and financial interests influence their votes?
- What's their reelection calculus? Are they in a safe seat or fighting for survival?
- How do they interact with colleagues? Coalition builder or lone wolf?
- What committee expertise gives them leverage?
- What are their STOCK trades telling us about their real interests vs public statements?
  (e.g., if they publicly oppose Big Pharma but their portfolio is heavy pharma stocks,
   note the contradiction and how it might affect their behavior)
- Who has leverage over them? (donors, party leadership, voters, media)
- What's their negotiation style? (dealmaker, ideologue, grandstander, workhorse)

REAL DATA FOR THIS MEMBER:
=========================
Name: {full_name}
Party: {party} | Chamber: {chamber} | State: {state} {district}
Terms served: {terms_served} | Next election: {next_election}
Leadership role: {leadership_role}
Ideology (DW-NOMINATE): {dw_nominate_dim1} (scale: -1 liberal to +1 conservative)
Party loyalty: {party_loyalty_pct}%
Margin last election: {margin_last_election} | District lean: {district_lean}

COMMITTEES: {committees_formatted}
CAUCUSES: {caucuses_formatted}

TOP BILLS SPONSORED: {bills_sponsored_formatted}
RECENT KEY VOTES: {recent_votes_formatted}

FINANCIAL PROFILE:
  Total raised: ${total_raised_current_cycle}
  From individuals: {pct_from_individuals}% | From PACs: {pct_from_pacs}%
  Top donors: {top_donors_formatted}
  Top industries: {top_industries_formatted}

STOCK TRADES (STOCK Act disclosures):
{stock_trades_formatted}
  Top sectors traded: {top_sectors_traded_formatted}
  Potential conflicts of interest: {potential_conflicts_formatted}

SCORECARD RATINGS:
{scorecard_ratings_formatted}

Write the behavioral persona now. Be specific and predictive.
```

### Generation Process

```python
async def generate_persona(profile: CongressMemberProfile, ollama_url: str, model: str):
    """
    Generate and save a behavioral persona narrative.
    Saves to both the profile JSON and as a standalone file.

    IMPORTANT:
    - Use temperature 0.7 for creative but grounded output
    - Cache the result — only regenerate if underlying data changes significantly
    - Log generation time (expect 30-90 seconds per agent at 32b)
    - For initial build of all 535+, consider batching overnight
    - For faster iteration, use qwen2.5:14b (less nuanced but 3x faster)
    """
    pass
```

---

## Local Persistence Strategy

### File-Based Persistence
Every agent profile is saved as a JSON file at a predictable path:

```
backend/agents/personas/
├── congress/
│   ├── house/
│   │   ├── A000370.json  # Alma Adams (bioguide ID)
│   │   ├── A000379.json  # etc.
│   │   └── ...
│   └── senate/
│       ├── B001230.json
│       └── ...
├── scotus/
│   ├── john_roberts.json
│   ├── clarence_thomas.json
│   └── ...
├── executive/
│   ├── president.json
│   └── vice_president.json
└── influence/
    ├── nra.json
    ├── chamber_of_commerce.json
    ├── afl_cio.json
    └── ...
```

### Neo4j Graph Persistence
`backend/agents/storage/graph.py`

The relational data lives in Neo4j. The JSON files have the full detail; Neo4j has the connections.

Every Member node MUST include a `party` property. All graph visualizations, relationship trees, and frontend components must color-code by party: **Republican = Red, Democrat = Blue, Independent = Gray.** This is not a nice-to-have — it's the core visual identity of CongressFish. The judiciary (SCOTUS) should use purple. Influence orgs use green. Executive branch uses gold.

```cypher
// Node schema
CREATE CONSTRAINT FOR (m:Member) REQUIRE m.bioguide_id IS UNIQUE;
CREATE CONSTRAINT FOR (j:Justice) REQUIRE j.name IS UNIQUE;
CREATE CONSTRAINT FOR (c:Committee) REQUIRE c.code IS UNIQUE;
CREATE CONSTRAINT FOR (o:Organization) REQUIRE o.name IS UNIQUE;
CREATE CONSTRAINT FOR (b:Bill) REQUIRE b.bill_id IS UNIQUE;

// Relationship types
(m:Member)-[:SERVES_ON {rank: int, is_chair: bool, is_ranking: bool}]->(c:Committee)
(m:Member)-[:MEMBER_OF]->(caucus:Caucus)
(m:Member)-[:PARTY_MEMBER]->(p:Party)
(m:Member)-[:REPRESENTS]->(s:State)
(m:Member)-[:SPONSORED]->(b:Bill)
(m:Member)-[:COSPONSORED]->(b:Bill)
(m:Member)-[:COSPONSORS_WITH {count: int, pct: float}]->(m2:Member)
(m:Member)-[:VOTES_WITH {agreement_pct: float}]->(m2:Member)
(m:Member)-[:STATE_COLLEAGUE]->(m2:Member)
(m:Member)-[:FUNDED_BY {amount: float, cycle: str}]->(o:Organization)
(m:Member)-[:TRADED {ticker: str, type: str, amount_range: str, date: str}]->(sector:Sector)
(m:Member)-[:SCORED_BY {score: str, year: int}]->(o:Organization)
(j:Justice)-[:AGREES_WITH {pct: float}]->(j2:Justice)
(j:Justice)-[:APPOINTED_BY]->(pres:Executive)
(o:Organization)-[:LOBBIES {spending: float, issues: list}]->(c:Committee)
```

---

## Agent Loading & Startup Behavior

**After the initial build, agents are ALREADY on disk and in Neo4j.** Starting CongressFish should NOT rebuild anything. The startup path should be:

1. **Check if agents exist** — look for JSON files in `backend/agents/personas/congress/`. If they exist, agents are built. Load them from disk into memory. This should take seconds, not minutes.
2. **Quick refresh sweep** (< 5 minutes) — hit the APIs for new votes, new stock trades, and member changes since the last refresh timestamp. Update only the affected agent profiles. Do NOT regenerate personas unless explicitly asked.
3. **Ready for simulation** — the simulation engine can immediately pull any agent from the in-memory store or query Neo4j for relationship data.

The key insight: **the expensive build happens once. Every subsequent startup is just a fast load + light delta refresh.** If no internet is available, skip the refresh entirely and use cached data. The system should work fully offline after initial build.

### Startup Refresh Sweep
`backend/agents/refresh.py`

Runs automatically on startup. Should complete in under 5 minutes.

- Check for new roll call votes since `last_refresh_at` (Congress.gov API). Update affected members' vote arrays.
- Check for new STOCK Act trade disclosures (Quiver/Capitol Trades). Add to affected members' trade arrays. Flag new potential conflicts.
- Check for new FEC filings (quarterly — only pull during filing season).
- Check for member changes — resignations, special elections, party switches, committee reassignments.
- Do NOT re-generate persona narratives on refresh. Only flag members with significant data changes for optional manual persona regeneration.
- Save `last_refresh_at` timestamp to a state file.
---

## Build Orchestrator

`backend/agents/build.py`

The master script that does the full initial build. Run this ONCE, then use refresh for ongoing updates.

```bash
# Full initial build (expect 2-4 hours for data pull + 8-12 hours for persona generation)
python backend/agents/build.py --full

# Just pull data, skip persona generation (for testing)
python backend/agents/build.py --data-only

# Just generate personas from existing data
python backend/agents/build.py --personas-only

# Build only Senate (100 members) for fast testing
python backend/agents/build.py --senate-only

# Regenerate personas for specific members
python backend/agents/build.py --regenerate A000370 B001230

# Refresh (quick startup sweep)
python backend/agents/build.py --refresh
```

```python
"""
Build Orchestrator
==================
Execution order:

1. Pull congress-legislators YAML (ID cross-reference table)
2. Pull Congress.gov member list for 119th Congress
3. Cross-reference IDs between sources
4. For each member:
   a. Pull Congress.gov detail (votes, bills, committees)
   b. Pull VoteView ideology scores
   c. Pull OpenFEC campaign finance
   d. Pull stock trades from Quiver/Capitol Trades
   e. Pull OpenSecrets lobbying/scorecard data
   f. Merge all data into CongressMemberProfile
   g. Save JSON to disk
   h. Write to Neo4j
5. Build cosponsorship network from bill data
   - For every pair of members who cosponsored the same bill,
     increment their COSPONSORS_WITH relationship weight
6. Build voting alignment network
   - For every pair of members, calculate % agreement on roll call votes
   - Create VOTES_WITH relationships for pairs with >50% overlap
7. Pull SCOTUS data and build justice profiles
8. Build executive profiles
9. Pull top 50 lobbying orgs and build influence profiles
10. Generate persona narratives via Ollama (slowest step)
11. Verify graph integrity (all nodes connected, no orphans)
12. Print summary stats

Estimated totals:
  - 435 House members
  - 100 Senators
  - 6 non-voting delegates
  - 9 Supreme Court justices
  - 2 Executive (President, VP)
  - ~50-100 influence organizations
  = ~600-650 agent profiles
"""
```

---

## File Structure

```
congressfish/
├── backend/
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── build.py              # Master build orchestrator
│   │   ├── refresh.py            # Startup refresh sweep
│   │   ├── apis/
│   │   │   ├── __init__.py
│   │   │   ├── congress_gov.py   # Congress.gov API v3
│   │   │   ├── unitedstates_project.py  # GitHub YAML data
│   │   │   ├── voteview.py       # DW-NOMINATE scores
│   │   │   ├── openfec.py        # Campaign finance
│   │   │   ├── opensecrets.py    # Lobbying & scorecards
│   │   │   ├── stock_trades.py   # STOCK Act disclosures
│   │   │   ├── scotus.py         # Supreme Court data
│   │   │   ├── executive.py      # President/VP/Cabinet
│   │   │   └── legiscan.py       # Supplemental bill tracking
│   │   ├── profiles/
│   │   │   ├── __init__.py
│   │   │   ├── models.py         # Pydantic schemas (above)
│   │   │   └── generator.py      # Ollama persona generation
│   │   ├── templates/
│   │   │   ├── congress_member_prompt.txt
│   │   │   ├── justice_prompt.txt
│   │   │   ├── executive_prompt.txt
│   │   │   └── influence_org_prompt.txt
│   │   ├── storage/
│   │   │   ├── __init__.py
│   │   │   ├── graph.py          # Neo4j schema & CRUD
│   │   │   └── file_store.py     # JSON file persistence
│   │   ├── cache/                # Raw API response cache
│   │   │   ├── congress_gov/
│   │   │   ├── openfec/
│   │   │   ├── voteview/
│   │   │   ├── opensecrets/
│   │   │   └── stock_trades/
│   │   ├── personas/             # Generated agent JSON files
│   │   │   ├── congress/
│   │   │   │   ├── house/
│   │   │   │   └── senate/
│   │   │   ├── scotus/
│   │   │   ├── executive/
│   │   │   └── influence/
│   │   └── .refresh_state.json   # Last refresh timestamp
│   └── ... (existing MiroFish backend)
├── .env.example
├── requirements-agents.txt
└── ... (existing MiroFish files)
```

---

## Execution Order for Claude Code

1. Set up directory structure and install dependencies
2. Build the `congress-legislators` YAML downloader and ID cross-reference table FIRST — everything else joins through bioguide_id
3. Build the Congress.gov API client — this is the backbone
4. Build the VoteView CSV downloader — quick win, gives ideology scores
5. Build the OpenFEC client — donor data
6. Build the stock trades client — financial interest data
7. Build the OpenSecrets client — lobbying and scorecards
8. Build the Pydantic models and profile merger that combines all sources
9. Build the Neo4j schema and population logic
10. Build the file persistence layer
11. **TEST**: Pull data for 5 senators, merge, save to JSON + Neo4j, verify
12. Build the Ollama persona generator
13. **TEST**: Generate personas for those 5 senators, review quality
14. Build the full orchestrator
15. Build the startup refresh sweep
16. **RUN**: Full build for Senate only (100 members) as proof of concept
17. **RUN**: Full build for all members

---

## Key Reminders

- **Cache everything.** Raw API responses go to `cache/` as JSON. Never re-pull the same data during development.
- **Idempotent writes.** Neo4j operations should use MERGE not CREATE. JSON files overwrite by bioguide_id.
- **Persona generation is SLOW.** At qwen2.5:32b, expect 30-90 seconds per agent. 650 agents = 8-16 hours. Use 14b for iteration, 32b for final build. Consider running overnight.
- **The cosponsorship network is the most important relationship.** It determines who influences who in the simulation. Invest time getting the weights right.
- **Stock trades + committee assignments = conflict detection.** Cross-reference trades against committee jurisdictions. If a member on the Energy Committee is trading oil stocks, that's a behavioral signal.
- **Donor data + vote history = loyalty prediction.** If a member's top donors are pharma companies and they've never voted against pharma, that's a high-confidence behavioral pattern.

---

## ADDENDUM: Critical Data Gaps & How to Fill Them

### A. COMPLETE VOTING HISTORY (Not Just Recent Votes)

Every agent needs their FULL voting record, not just the last 20 votes. This is what makes
behavioral prediction accurate — patterns across hundreds of votes over multiple terms.

**Congress.gov API** provides roll call vote data but the House vote endpoints are relatively
new (beta, added May 2025). For comprehensive historical voting data:

```python
"""
VOTING HISTORY STRATEGY (multi-source):

1. Congress.gov API — Primary for current congress
   GET /v3/member/{bioguideId}
   - Returns sponsored/cosponsored legislation
   GET /v3/vote/{congress}/{chamber}/{rollCallNumber}
   - Returns per-member vote positions
   - Paginate through all votes in the 119th Congress
   - Also pull 118th and 117th for recent history

2. VoteView (voteview.com) — GOLD for full historical record
   - Download rollcall votes CSV: contains EVERY roll call vote
     with per-member positions going back to the 1st Congress
   - Fields: congress, chamber, rollnumber, icpsr (member ID),
     cast_code (1=yea, 6=nay, 7-9=absent/abstain), date
   - Cross-reference icpsr to bioguide via their members CSV
   - This gives you the complete lifetime voting record

3. Clerk of the House / Secretary of the Senate — Official source
   - House: https://clerk.house.gov/Votes
   - Senate: https://www.senate.gov/legislative/votes.htm
   - XML/structured data for every roll call vote
   - Scrape if needed for the most current votes not yet in Congress.gov

For each member, compute from their full vote history:
  - Total votes cast vs missed (attendance rate)
  - Party loyalty percentage (overall and by issue area)
  - Bipartisan voting frequency
  - Vote agreement % with every other current member
  - Issue area voting breakdown (defense, healthcare, environment, etc.)
  - Vote consistency over time (have they shifted left/right?)
  - Key "break" votes — times they went against party on high-profile bills
  - Whip compliance — do they follow party leadership on close votes?
"""
```

### B. OPENSECRETS BULK DATA (API is Dead, Bulk Downloads Still Work)

OpenSecrets discontinued their API in April 2025, but their bulk data downloads
are still available for educational use. Register at https://www.opensecrets.org/bulk-data

```python
"""
OPENSECRETS BULK DATA STRATEGY:

Available CSV tables to download:
  - Candidates: CRP IDs, party, office, district, cycle
  - PACs to Candidates: PAC contributions to candidates with amounts
  - PACs to PACs: Inter-PAC transfers
  - Individual Contributions: Individual donors with employer, amount, date
  - Expenditures: How campaigns spend money
  - Lobbying: Lobbying registrations with amounts
  - Lobbyists: Individual lobbyist records
  - Industry Lobbying: Lobbying spending by industry
  - Agencies Lobbied: Which government agencies are being lobbied
  - Lobbying Issues: What issues are being lobbied on
  - Bills Lobbied: Which specific bills lobbyists are targeting

PROCESS:
1. Download all relevant CSV files (total ~2-3 GB compressed)
2. Store in backend/agents/cache/opensecrets/
3. Build a local SQLite or DuckDB database from the CSVs
4. Query locally — no API needed, no rate limits, complete data
5. Cross-reference CRP IDs to bioguide IDs via congress-legislators YAML

KEY QUERIES TO BUILD PER MEMBER:
  - Top 20 PAC contributors (from PACs_to_Candidates)
  - Top 20 individual donors with employers (from Individual_Contributions)
  - Industry breakdown of all contributions
  - Total lobbying spend targeting committees they sit on
  - Which specific bills affecting their committee had active lobbyists
  - Which lobbying firms are most active with their office

This is actually BETTER than the old API because you get the complete
dataset locally and can do arbitrary queries without rate limits.
"""
```

### C. CLAUDE CODE RESEARCH LAYER — Filling Gaps No API Covers

This is where the build process gets uniquely powerful. For data that no API or
bulk download provides, Claude Code should use web search and web scraping to
research each member and fill in qualitative data.

```python
"""
CLAUDE CODE RESEARCH TASKS:
============================

During the agent build process, after all API/bulk data has been pulled
and merged, Claude Code should do a research pass for each member to
fill in data that only exists in unstructured sources.

FOR EACH MEMBER, RESEARCH AND DOCUMENT:

1. CONGRESSIONAL SCORECARDS (no single API — scrape from each org)
   - NRA grade: https://www.nrapvf.org/grades/
   - League of Conservation Voters: https://scorecard.lcv.org/
   - AFL-CIO: https://aflcio.org/scorecard
   - Heritage Action: https://heritageaction.com/scorecard
   - ACLU: https://www.aclu.org/scorecard
   - NumbersUSA (immigration): https://www.numbersusa.com/content/my/congress/report-cards
   - Planned Parenthood Action Fund
   - FreedomWorks (if still publishing)
   - Chamber of Commerce: https://www.uschamber.com/how-they-voted
   - Club for Growth
   - Susan B. Anthony Pro-Life America
   - Human Rights Campaign (LGBTQ+): https://www.hrc.org/resources/congressional-scorecard
   
   Each publishes a letter grade or percentage score for every member.
   Scrape the current scorecard for each org and store as structured data.
   These are incredibly valuable behavioral signals — they compress an
   org's entire evaluation of a member into a single score.

2. CAUCUS MEMBERSHIPS (not comprehensively available via API)
   - Congressional Black Caucus
   - Congressional Hispanic Caucus
   - Congressional Progressive Caucus
   - Republican Study Committee
   - House Freedom Caucus
   - New Democrat Coalition
   - Blue Dog Coalition
   - Problem Solvers Caucus
   - Congressional Asian Pacific American Caucus
   - Other issue-specific caucuses
   
   These are usually listed on the caucus's website or the member's
   official site. Caucus membership is a strong signal of voting behavior.

3. PUBLIC STATEMENTS & POLICY POSITIONS
   - Search for each member's recent public statements on key issues
   - Check their official website's "issues" page
   - Recent press releases (many available via member websites)
   - Floor speeches on major legislation (Congressional Record)
   - Op-eds and media appearances
   
   Summarize into structured policy positions:
   {issue: str, position: str, strength: "strong"/"moderate"/"weak", source: str}

4. BIOGRAPHICAL & BACKGROUND CONTEXT
   - Previous career (lawyer, doctor, military, business, etc.)
   - Military service (strong influence on defense votes)
   - Education
   - Notable personal connections (spouse's employer, family businesses)
   - Any current ethics investigations or controversies
   - Previous offices held (state legislature, governor, etc.)

5. DISTRICT/STATE DEMOGRAPHICS & POLITICAL CONTEXT
   - District PVI (Cook Partisan Voting Index)
   - Key industries in their district/state
   - Major employers in their district
   - Recent demographic shifts
   - Redistricting changes affecting their seat
   - Primary challenge history (have they been primaried?)

6. RECENT NEWS & CONTEXT (last 6 months)
   - Any recent controversies or scandals
   - Major policy fights they've been involved in
   - Leadership challenges or power plays
   - Committee assignment changes
   - Notable floor speeches or media moments

Claude Code should do this research using web search, then save the
results as structured JSON alongside the API-sourced data. The
persona generator will use ALL of this when generating the
behavioral narrative.

IMPORTANT: Cache all research results. This is the most time-intensive
part of the build but it only needs to happen once per member.
On refresh, only re-research members flagged for significant changes.
"""
```

### D. LOBBYING DATA DEEP DIVE

Since we can't use OpenSecrets' API anymore, and their bulk data gives us the raw
lobbying records, we need to build our own lobbying analysis layer.

```python
"""
LOBBYING DATA STRATEGY:

1. OpenSecrets Bulk Data (primary)
   - Download Lobbying, Lobbyists, Industry_Lobbying, Agencies_Lobbied,
     Lobbying_Issues, Bills_Lobbied CSVs
   - Load into local DuckDB/SQLite
   - Query: For each committee, what industries are lobbying it?
   - Query: For each member, what lobbyists are registered to their office?
   - Query: For each active bill, which orgs are lobbying on it?

2. Senate Lobbying Disclosure Database (official source)
   - https://lda.senate.gov/filings/public/filing/search/
   - Searchable database of all lobbying registrations and quarterly reports
   - Scrape for specific members/committees as needed

3. House Lobbying Disclosure
   - https://lobbyingdisclosure.house.gov/
   - Same data, different interface

4. FEC Independent Expenditures (OpenFEC API)
   - GET /v1/schedules/schedule_e/
   - Independent expenditures FOR or AGAINST each candidate
   - This shows which outside groups are spending money to help/hurt them

BUILD PER-MEMBER LOBBYING PROFILE:
  - Top 10 industries lobbying their committees
  - Top lobbying firms registered to contact their office
  - Dollar volume of lobbying on bills they've sponsored
  - Independent expenditures for/against them
  - Revolving door connections (former staffers now lobbying)
"""
```

### E. FINANCIAL DISCLOSURE DEEP DIVE (Beyond Stock Trades)

Stock trades are just one piece. STOCK Act and EIGA filings include broader
financial interests.

```python
"""
FINANCIAL DISCLOSURE SOURCES:

1. Stock Trades (already covered — Quiver, Capitol Trades, clerk sites)

2. Annual Financial Disclosures (EIGA filings)
   - Senate: https://efdsearch.senate.gov/search/
   - House: https://disclosures-clerk.house.gov/FinancialDisclosure
   - These include:
     - Asset holdings (not just trades — what they OWN)
     - Income sources (speaking fees, book royalties, rental income)
     - Liabilities (mortgages, loans — who do they owe money to?)
     - Positions held (corporate boards, nonprofit boards)
     - Agreements (consulting, employment, severance)
     - Gifts received
     - Travel reimbursements
   
   These are mostly PDFs. For initial build, Claude Code should research
   the most recent annual filing for each member and extract key data points.
   For the full 535+ members, this is a manual-research task best done
   by Claude Code during the build process, not via API.

3. Personal Net Worth Estimates
   - OpenSecrets publishes net worth estimates based on EIGA filings
   - These are still on their website even though the API is dead
   - Scrape the member pages on opensecrets.org for net worth data
   
4. Outside Earned Income
   - Some members have significant outside income (law firms, medical
     practices, book deals, speaking fees)
   - This creates additional financial interest vectors beyond stocks
"""
```

### F. UPDATED DATA SOURCE MATRIX (Corrected)

| Data | Source | Method | Free? | Status |
|------|--------|--------|-------|--------|
| Member list, bio, roles | Congress.gov API | API (key required) | Yes | Active |
| Cross-reference IDs | unitedstates/congress-legislators | GitHub YAML | Yes | Active |
| Roll call votes (current) | Congress.gov API | API | Yes | Active (House beta) |
| Full voting history | VoteView | CSV download | Yes | Active |
| Bills, cosponsors, actions | Congress.gov API | API | Yes | Active |
| Committees & membership | Congress.gov API | API | Yes | Active |
| Bill tracking & search | LegiScan | API (30k/mo free) | Yes | Active |
| Campaign finance (FEC) | OpenFEC | API (key required) | Yes | Active |
| Industry/PAC contributions | OpenSecrets Bulk Data | CSV download | Yes (edu) | Active |
| Lobbying records | OpenSecrets Bulk Data | CSV download | Yes (edu) | Active |
| Lobbying (official) | Senate LDA / House LD | Scrape | Yes | Active |
| Stock trades (STOCK Act) | Quiver Quantitative | API | Free tier | Active |
| Stock trades (backup) | Capitol Trades | Scrape | Yes | Active |
| Stock trades (official) | House/Senate clerk | Scrape + PDF parse | Yes | Active |
| Financial disclosures | eFD Search (Senate/House) | Scrape + PDF parse | Yes | Active |
| DW-NOMINATE ideology | VoteView | CSV download | Yes | Active |
| Congressional scorecards | Individual org websites | Scrape | Yes | Active |
| SCOTUS data | Oyez + SCDB | API + CSV | Yes | Active |
| Executive orders | Federal Register | API (no key) | Yes | Active |
| Biographical/qualitative | Web research (Claude Code) | Search + scrape | Yes | N/A |
| District demographics | Cook PVI, Census | Research | Yes | Active |
| **ProPublica Congress API** | **DEAD** | **—** | **—** | **Discontinued** |
| **OpenSecrets API** | **DEAD** | **—** | **—** | **Discontinued April 2025** |
| **GovTrack API** | **ENDING** | **—** | **—** | **Shutting down summer 2026** |

---

## Updated Execution Order for Claude Code

1. Set up directory structure and install dependencies
2. Download `congress-legislators` YAML — build the ID cross-reference table FIRST
3. Build Congress.gov API client — pull all 119th Congress members, committees, recent bills
4. Download VoteView CSVs — full voting history + ideology scores for all members
5. Build OpenFEC client — pull campaign finance for all members
6. Download OpenSecrets bulk CSVs — load into local DuckDB for lobbying + industry queries
7. Build stock trades client (Quiver + Capitol Trades) — pull all STOCK Act disclosures
8. Build the Pydantic profile merger — combine all structured data per member
9. **Claude Code research pass** — for each member, fill in:
   - Congressional scorecards (scrape each org's website)
   - Caucus memberships
   - Policy positions from official websites
   - District PVI and key local industries
   - Financial disclosure highlights (net worth, major assets, outside income)
   - Recent news context
10. Save all merged profiles as JSON to `backend/agents/personas/`
11. Build Neo4j schema and populate graph with all nodes and relationships
12. Build cosponsorship network from bill data (relationship weights)
13. Build voting alignment network from VoteView data
14. **TEST**: Review 5 senator profiles for completeness and accuracy
15. Generate Ollama persona narratives for all agents
16. **TEST**: Review persona quality for 5 senators
17. Build SCOTUS justice profiles (Oyez + SCDB)
18. Build executive profiles (Federal Register + research)
19. Build influence organization profiles (lobbying data + scorecards)
20. Build startup refresh sweep
21. **RUN**: Full build for Senate only (100 members) as proof of concept
22. **RUN**: Full build for all members + justices + executive + influence orgs
