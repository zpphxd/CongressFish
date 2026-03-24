# CongressFish Implementation Roadmap

US Government Simulation Engine — Multi-stage legislative pipeline with persistent ~650 agent profiles (Congress, SCOTUS, Executive, Influence Orgs).

---

## Completed ✓

### Phase 1: Fork & Project Setup
- [x] Fork MiroFish-Offline → CongressFish
- [x] Initialize git with remote tracking
- [x] Create directory skeleton
- [x] Add requirements-agents.txt with data ingest dependencies
- [x] Update .env.example with API keys (Congress.gov, OpenFEC)

### Phase 2A: ID Cross-Reference
- [x] Implement `backend/agents/apis/unitedstates_project.py`
  - Downloads legislators-current.yaml from unitedstates/congress-legislators
  - Builds canonical ID mapping: bioguide_id → {fec_id, opensecrets_id, govtrack_id, votesmart_id, wikipedia_id, ...}
  - Returns LegislatorRecord objects with full term history
  - Caches YAML for 7 days

### Phase 2B: Congress.gov API
- [x] Implement `backend/agents/apis/congress_gov.py`
  - Async client with aiohttp + tenacity retries
  - Rate limiting (5000 req/hour) + exponential backoff
  - Response caching (7-day TTL)
  - Methods: get_members(), get_member_detail(), get_member_sponsored_bills(), get_member_cosponsored_bills(), get_committees()
  - Tested: API endpoint verified working

### Phase 2C: Wikipedia Biographical Data
- [x] Implement `backend/agents/apis/wikipedia.py`
  - Scrapes Wikipedia biographies for all government figures
  - Respects rate limiting (1-2 req/sec)
  - Extracts: birth_date, birth_place, occupation, education, full_text
  - Caches responses (30-day TTL)
  - Async batch fetching with semaphore

### Phase 2D: Oyez Supreme Court API
- [x] Implement `backend/agents/apis/oyez.py`
  - Fetches justice profiles and voting records from official SCOTUS API
  - Computes pairwise justice voting alignment percentages
  - Returns case votes, opinion types, decision dates
  - Caches all responses (30-day TTL)

### Phase 2E: VoteView Ideology Scores
- [x] Implement `backend/agents/apis/voteview.py`
  - Downloads members.csv and parses DW-NOMINATE ideology scores (dim1, dim2)
  - Computes member-to-member voting agreement percentages
  - Generates ideology statistics by party/chamber
  - No network calls required (local CSV parsing)

### Phase 2F: OpenFEC Campaign Finance
- [x] Implement `backend/agents/apis/openfec.py`
  - Fetches candidate totals (receipts, disbursements, cash on hand)
  - Gets top individual donors (name, state, occupation, amount)
  - Gets top PAC donors
  - Implements rate limiting (1000 req/hour) + caching (7-day TTL)

---

## In Progress 🚧

### Phase 3: Pydantic Models & Profile Merger
- [ ] Implement `backend/agents/profiles/models.py`
  - Define CongressMemberProfile, JusticeProfile, ExecutiveProfile, InfluenceOrgProfile Pydantic models
  - Include all fields from data ingest pipeline (trades, donors, scorecard, biography, ideology)
  - Add conflict detection (stock trades vs committee jurisdiction)

- [ ] Implement `backend/agents/profiles/merger.py`
  - Merges data from all API clients into unified Pydantic models
  - Handles missing fields gracefully
  - Cross-validates data across sources

### Phase 4: Persona Generation
- [ ] Implement `backend/agents/profiles/generator.py`
  - Use existing `backend/app/utils/llm_client.py` (Ollama wrapper)
  - 4 prompt templates: congress_member_prompt.txt, justice_prompt.txt, executive_prompt.txt, influence_org_prompt.txt
  - Temperature 0.7, ~500-800 words per persona
  - Cache result in profile JSON (regenerate with --force flag)
  - Expected: 30-90s per agent at qwen2.5:32b

### Phase 5: Neo4j Graph Population
- [ ] Implement `backend/agents/storage/graph.py`
  - Define new node labels: Member, Justice, Executive, Committee, Caucus, Party, Organization, Sector
  - Define constraints and indexes
  - Implement CRUD operations (create_member, create_justice, etc.)

- [ ] Implement `backend/agents/storage/populate.py`
  - CLI script to populate graph from merged profile data
  - Supports --full, --senate-only, --data-only, --personas-only, --refresh flags
  - Idempotent MERGE operations
  - Build cosponsorship network (COSPONSORS_WITH edges)
  - Build voting alignment network (VOTES_WITH edges)

---

## Not Started ⏳

### Phase 2G: Stock Trades (STOCK Act)
- [ ] Implement `backend/agents/apis/stock_trades.py`
  - Primary source: Quiver Quantitative API (key pending)
  - Backup: Capitol Trades scraper
  - Parse into StockTrade records
  - Cross-reference with committee assignments for conflict detection

### Phase 2H: Executive Branch Data
- [ ] Implement `backend/agents/apis/executive.py`
  - Federal Register API for executive orders
  - Hardcoded current President/VP/Cabinet with manual policy positions
  - Connect to influence organizations for lobbying ties

### Phase 2I: Congressional Scorecards
- [ ] Implement `backend/agents/apis/scorecards.py`
  - Scrape NRA, LCV, AFL-CIO, ACLU, HRC, Chamber of Commerce, Heritage Action scorecard pages
  - Store as {org, score, year, issue_area} per member

### Phase 6: Build Orchestrator & Refresh
- [ ] Implement `backend/agents/build.py`
  - Master orchestrator: run phases 2-5 in sequence
  - Full build: ~15-30 min for all 650 agents
  - Startup refresh (~5 min): check for new votes, trades, update affected profiles

- [ ] Implement `backend/agents/refresh.py`
  - Scheduled/startup refresh logic
  - Update last_refresh_at timestamp

- [ ] Shell scripts
  - `scripts/build_agents.sh` — run full build
  - `scripts/refresh_data.sh` — run quick refresh
  - `scripts/run_congress_sim.sh` — start pipeline simulation

### Phase 7: Multi-Stage Legislative Pipeline
- [ ] Implement `backend/simulation/pipeline.py` — state machine
- [ ] Implement `backend/simulation/orchestrator.py` — pipeline controller
- [ ] Implement stage base class and 5-stage implementations:
  - `s01_introduction.py` — Sponsor introduces bill + committee assignment
  - `s02_committee_markup.py` — Committee debate and vote
  - `s03_floor_vote.py` — Full chamber vote (with filibuster check for Senate)
  - `s04_presidential_action.py` — President signs/vetoes
  - `s05_judicial_review.py` — Judicial risk assessment

- [ ] Implement `backend/simulation/vote_counter.py` — extract vote signals from OASIS posts
- [ ] Implement `backend/simulation/memory.py` — cross-stage memory injection
- [ ] Implement `backend/simulation/congress_report.py` — final report generation

- [ ] New Flask API endpoints:
  - `POST /api/congress/simulate` — start pipeline simulation
  - `GET /api/congress/simulate/:id` — get pipeline state
  - `GET /api/congress/members` — list all members (filterable)
  - `GET /api/congress/graph/network` — relationship graph data for D3

### Phase 8: Frontend
- [ ] New Views (Vue 3):
  - `CongressDashboard.vue` — landing page with pipeline tracker
  - `MemberExplorer.vue` — searchable member list, party-colored cards
  - `MemberProfile.vue` — full member detail (trades, donors, ideology, persona)
  - `PipelineView.vue` — horizontal stage-by-stage tracker (CI/CD style)
  - `FloorMapView.vue` — 435-seat House map or 100-seat Senate semicircle

- [ ] New Components:
  - `FloorMap.vue` — SVG seat chart, party-colored, interactive
  - `VoteTracker.vue` — running yes/no/undecided tally bar
  - `CoalitionGraph.vue` — D3 force-directed graph (party-colored nodes)
  - `MemberCard.vue` — compact member summary

- [ ] Branding:
  - Update `index.html` title → "CongressFish"
  - Update `Home.vue` heading, add `/congress` route
  - Define party color system (R=#E81B23, D=#0015BC, I=#808080, etc.)

### Phase 9: Data Refresh & Maintenance
- [ ] Transition handling (new Congress seating)
- [ ] Convenience CLI tools
- [ ] Documentation

---

## Success Criteria

**Phase 1 (Setup):** ✓ Done
- Git initialized, remote configured, directory structure created

**Phase 2 (Data Ingest):** In Progress (2/9 complete)
- All 9 API clients implemented and cached
- Can pull full Congress data in < 5 minutes
- ~650 agent profiles built and serialized to JSON

**Phase 3-4 (Models & Personas):** Ready to start
- All Pydantic models validate against real data
- Persona generation completes in < 90 seconds per agent on qwen2.5:32b

**Phase 5 (Neo4j):** Ready to start
- Graph populated with all relationships
- Queries return valid network data (cosponsorship, voting alignment, funding)

**Phase 7 (Pipeline):** Ready to start after phases 3-5
- Submit sample bill through all 5 stages
- Senate bill correctly hits filibuster check (60 vote threshold)
- Failed committee vote terminates pipeline at that stage
- Cross-stage memory correctly carried forward

**Phase 8 (Frontend):** Ready to start after phase 7
- `/congress` route loads without errors
- Floor map renders 435 seats, party-colored
- D3 graph shows member relationships colored by party
- Member card displays photo, party badge, ideology, donors

---

## Timeline Estimate

| Phase | Effort | Status | Start | Target |
|-------|--------|--------|-------|--------|
| 1 | 2h | ✓ | - | ✓ |
| 2A-2F | 16h | 🚧 | - | - |
| 2G-2I | 8h | ⏳ | - | - |
| 3-4 | 6h | ⏳ | - | - |
| 5 | 4h | ⏳ | - | - |
| 6 | 4h | ⏳ | - | - |
| 7 | 12h | ⏳ | - | - |
| 8 | 10h | ⏳ | - | - |
| 9 | 4h | ⏳ | - | - |
| **Total** | **66h** | | | |

---

## Known Constraints

- QUIVER_API_KEY not yet provided (stock trades module built, wired later)
- Oyez has rate limit issues with large concurrent requests (using semaphore)
- VoteView data is read-only (members.csv), no real-time updates
- OpenSecrets skipped for MVP (donor/lobbying via OpenFEC only)
- GovTrack skipped (API ending summer 2026)
- Persona generation at Ollama local speed (30-90s per agent, not parallelizable on single GPU)

---

## Key Decision Log

- **API Keys**: Congress.gov ✓, OpenFEC ✓, Quiver pending
- **Build Scope**: Full Congress (535 members) + SCOTUS (9) + Executive + Influence Orgs from the start
- **Pipeline Stages**: 5-stage MVP (not 11) — Introduction → Committee → Floor Vote → Presidential → Judicial Review
- **Biographical Data**: Include Wikipedia backgrounds for all figures
- **Neo4j Integration**: New node labels alongside existing MiroFish schema (no conflicts)
- **Frontend**: New `/congress` routes alongside existing MiroFish views (no overwrites)

---

## CI/CD & Testing

- Unit tests for each API client (mock responses)
- Integration tests for profile merger (real cached API data)
- E2E test: full pipeline simulation with sample bill
- Lint/type checks via mypy and flake8
- GitHub Actions CI on push to main

---

## References

- **Plan File**: [/Users/zachpowers/.claude/plans/steady-mixing-wozniak.md]
- **Spec Files**: [CONGRESSFISH_PHASE1_BUILD_AGENTS.md], [CLAUDE_CODE_PROMPT_congress_mirofish.md]
- **API Docs**:
  - Congress.gov: https://api.congress.gov/
  - OpenFEC: https://api.open.fec.gov/
  - Oyez: https://api.oyez.org/
  - VoteView: https://voteview.com/
  - unitedstates/congress-legislators: https://github.com/unitedstates/congress-legislators
