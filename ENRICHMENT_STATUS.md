# CongressFish Agent Enrichment Status

## Summary
As of March 24, 2026: **631 government agents enriched and ready for simulation**

## Breakdown by Branch

### 📋 Congress Members (614 total)
- **✅ Affiliations**: 614/614 (100%) - Party, committees, chamber
- **✅ Ideology**: 613/614 (99.8%) - DW-NOMINATE scores from Voteview
- **✅ Committee Assignments**: 533/614 (87%) - Committee codes and ranks
- **⏳ Biography**: 0/614 (0%) - Ballotpedia scraper in progress

#### Ideology Spectrum
- Scores range from **-0.94** (most liberal) to **+0.93** (most conservative)
- Primary dimension (dim1): Left-right ideological positioning
- Secondary dimension (dim2): Pro/anti-government economic positioning
- Example: Pete Aguilar (D-CA) = -0.326 (center-left)

### ⚖️ SCOTUS Justices (9 total)
- **✅ Affiliations**: 9/9 (100%) - Institution, position (Chief/Associate)
- **📊 Profiles**: All 9 current justices as of March 2026

### 🏛️ Executive Branch (8 total)
- **✅ Affiliations**: 8/8 (100%) - Executive branch, title, role
- **📊 Officials**:
  - President: Donald Trump
  - Vice President: J.D. Vance
  - 6 Cabinet members (State, Treasury, Defense, AG, Interior, DHS)

## Data Sources

| Source | Data Type | Status | Coverage |
|--------|-----------|--------|----------|
| Congress.gov API | Member directory, committees | ✅ | All 614 members |
| Voteview | DW-NOMINATE ideology scores | ✅ | 613/614 members |
| Ballotpedia | Biography (birth, education, occupation) | ⏳ | 0% (scraper running) |
| OpenFEC | Campaign finance | 🔴 | Blocked (requires FEC ID mapping) |
| Oyez | SCOTUS voting patterns | 📅 | Future enhancement |

## Technical Details

### Files Generated
- Congress profiles: `backend/agents/personas/congress/{senate,house}/*.json` (614 files)
- SCOTUS profiles: `backend/agents/personas/scotus/*.json` (9 files)
- Executive profiles: `backend/agents/personas/executive/*.json` (8 files)

### Profile Schema
Each agent profile includes:
```json
{
  "bioguide_id": "A000371",
  "full_name": "Aguilar, Pete",
  "chamber": "house",
  "state": "CALIFORNIA",
  "party": "D",
  "affiliations": ["Party: Democratic Party", "Committee: HSAP", ...],
  "committee_assignments": [{...}],
  "ideology": {
    "primary_dimension": -0.326,
    "secondary_dimension": 0.142,
    "source": "Voteview",
    "year": 2026
  },
  "biography": {
    "birth_date": null,
    "education": null,
    "wikipedia_summary": null
  },
  ...
}
```

## Next Steps

### Immediate (Ready Now)
1. **Build Neo4j graph** - Load all 631 enriched agents into graph
2. **Start simulations** - Use agents for legislative pipeline simulation
3. **Visualizations** - Render ideology spectrum, committee networks

### Medium-term (High Priority)
1. **Complete biography enrichment** - Finish Ballotpedia scraper
2. **Add campaign finance** - Map FEC IDs and pull OpenFEC data
3. **Generate AI personas** - Use Ollama to create behavioral profiles

### Long-term (Phase 2)
1. **Influence organizations** - Build PACs, advocacy groups, lobbying orgs
2. **Vote alignment networks** - Calculate agreement rates between members
3. **Enhanced SCOTUS data** - Pull voting patterns from Oyez API

## API Keys & Configuration

Required for full enrichment:
- ✅ `OPENFEC_API_KEY` - Added to `.env`
- 📥 Voteview CSV - Downloaded and cached
- 📅 Oyez API - Available but not yet integrated
- 📥 Ballotpedia - Web scraper (no key needed)

## Performance Notes

- **Ideology enrichment**: ~1 second for all 614 members
- **Affiliation extraction**: ~0.5 seconds for all 631 agents
- **Ballotpedia biography scraping**: ~5-10 minutes for all members (network-bound)
- **Profile file I/O**: ~614 JSON read/write operations per enrichment pass

## Known Issues

1. **Ballotpedia infobox parsing**: Needs improvement for better extraction rates
2. **FEC ID mapping**: No existing mapping between bioguide_id and fec_id (would need cross-reference build)
3. **SCOTUS Oyez API**: Not yet integrated (low priority - could use hardcoded data)

---

*Last updated: March 24, 2026*
*Next review: When biography enrichment completes*
