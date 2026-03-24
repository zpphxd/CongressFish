<div align="center">

# CongressFish

**US Government Legislative Simulation Engine — Multi-stage pipeline with 650+ persistent agent profiles**

*Simulate bill movement through Congress, SCOTUS review, Presidential action, and interest group lobbying. All on your hardware.*

[![GitHub](https://img.shields.io/badge/GitHub-zpphxd%2FCongressFish-blue?style=flat-square&logo=github)](https://github.com/zpphxd/CongressFish)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue?style=flat-square)](./LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-green?style=flat-square&logo=python)](https://www.python.org/)
[![Neo4j](https://img.shields.io/badge/Neo4j-5.15%2B-lightblue?style=flat-square&logo=neo4j)](https://neo4j.com/)
[![Ollama](https://img.shields.io/badge/Ollama-Local%20LLM-purple?style=flat-square)](https://ollama.ai/)

</div>

---

## What is CongressFish?

CongressFish is a **legislative simulation engine** that models how bills move through the US government. Built on top of [MiroFish-Offline](https://github.com/nikmcfly/MiroFish-Offline), it adds:

1. **650+ Persistent Agent Profiles** — Every Congress member (535), Supreme Court justice (9), key Executive officials, and influence organizations (PACs, advocacy groups, lobbying firms)
2. **Real Behavioral Data** — Profiles built from:
   - Congress.gov API (bills, voting records, committee assignments)
   - VoteView (DW-NOMINATE ideology scores, member alignment)
   - OpenFEC (campaign finance, donor networks)
   - Wikipedia (biographical backgrounds)
   - Oyez API (SCOTUS justice voting patterns)
   - Stock Act disclosures, advocacy org scorecards
3. **5-Stage Legislative Pipeline** — Introduction → Committee Markup → Floor Vote (with filibuster logic) → Presidential Action → Judicial Review Signal
4. **Coalition Dynamics** — Agents respond to party leadership, donors, committee assignments, and constituent pressure
5. **Multi-Agent Simulation** — Agents interact on simulated social platforms (Twitter/Reddit), forming coalitions, applying lobbying pressure, shifting votes

**No random generation.** Every agent is built from real data. No fictional politicians or organizations.

---

## Quick Start

### Prerequisites

- **Docker & Docker Compose** (easiest), **or**
- Python 3.11+, Node.js 18+, Neo4j 5.15+, Ollama
- Congress.gov API key (free: https://api.congress.gov/)
- OpenFEC API key (free: https://api.open.fec.gov/)

### Option A: Docker (Recommended)

```bash
git clone https://github.com/zpphxd/CongressFish.git
cd CongressFish
cp .env.example .env

# Edit .env to add your API keys:
# CONGRESS_GOV_API_KEY=your_key_here
# OPENFEC_API_KEY=your_key_here

docker compose up -d

# Pull required models
docker exec congressfish-ollama ollama pull qwen2.5:32b
docker exec congressfish-ollama ollama pull nomic-embed-text

# Build the agent graph (first time only, ~30 min)
docker exec congressfish-backend python backend/agents/build.py --full
```

Open `http://localhost:3000` and navigate to **Congress** tab.

### Option B: Manual Setup

**1. Start Neo4j**

```bash
docker run -d --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/congressfish \
  neo4j:5.15-community
```

**2. Start Ollama**

```bash
ollama serve &
ollama pull qwen2.5:32b      # LLM (32b recommended, 14b for less VRAM)
ollama pull nomic-embed-text  # Embeddings
```

**3. Configure & build agents**

```bash
cd CongressFish
cp .env.example .env

# Edit .env with your API keys
# CONGRESS_GOV_API_KEY=...
# OPENFEC_API_KEY=...

pip install -r backend/requirements.txt
python backend/agents/build.py --full  # ~30 minutes
```

**4. Run backend**

```bash
cd backend
python run.py
```

**5. Run frontend**

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

---

## How It Works

### Workflow

```
1. Select a bill (new or from database)
   ↓
2. Enter into Introduction stage
   - Sponsor introduces bill
   - Speaker/Leader assigns to committee
   ↓
3. Committee Markup stage
   - Committee members debate via social simulation
   - Committee votes
   ↓
4. Floor Vote stage
   - Full chamber votes (435 House or 100 Senate)
   - Senate: filibuster check (60-vote threshold)
   ↓
5. Presidential Action stage
   - President decides: sign or veto
   ↓
6. Judicial Review (optional)
   - SCOTUS evaluates constitutional risk
   ↓
7. Final Report
   - Detailed analysis of who voted how and why
   - Coalition dynamics tracked per stage
   - Lobbying pressure impact quantified
```

### Data Sources (No Random Generation)

Each agent is built from **real data only**:

| Agent Type | Data Sources |
|---|---|
| **Congress Members** | Congress.gov API, VoteView, OpenFEC, Wikipedia, Stock Act disclosures, advocacy org scorecards |
| **SCOTUS Justices** | Oyez API (voting records), Wikipedia biographies |
| **Executive Officials** | Federal Register, manual biographical data |
| **Influence Orgs** | OpenFEC PAC records, lobbying activity |

Biographical backgrounds, ideology scores, voting patterns, and campaign finance data are pulled from authoritative sources—no fictional details.

---

## Architecture

CongressFish extends MiroFish with a new agent data ingest pipeline:

```
┌─────────────────────────────────────────────┐
│  Flask API (MiroFish + CongressFish routes) │
│  /api/congress/simulate                     │
│  /api/congress/members                      │
│  /api/congress/graph/network                │
└──────────────┬──────────────────────────────┘
               │
┌──────────────▼──────────────────────────────┐
│      Agent Data Ingest Pipeline             │
│  backend/agents/apis/                       │
│  - congress_gov.py                          │
│  - unitedstates_project.py (ID cross-ref)   │
│  - wikipedia.py (biographies)               │
│  - oyez.py (SCOTUS)                         │
│  - voteview.py (ideology)                   │
│  - openfec.py (campaign finance)            │
└──────────────┬──────────────────────────────┘
               │
┌──────────────▼──────────────────────────────┐
│     Profile Merger & Persona Generation     │
│  backend/agents/profiles/                   │
│  - models.py (Pydantic schemas)             │
│  - merger.py (combine API data)             │
│  - generator.py (LLM persona generation)    │
└──────────────┬──────────────────────────────┘
               │
┌──────────────▼──────────────────────────────┐
│      Neo4j Graph Population                 │
│  backend/agents/storage/                    │
│  - graph.py (schema, CRUD)                  │
│  - populate.py (CLI)                        │
└──────────────┬──────────────────────────────┘
               │
┌──────────────▼──────────────────────────────┐
│  5-Stage Pipeline State Machine             │
│  backend/simulation/                        │
│  - pipeline.py, orchestrator.py             │
│  - stages/s01_*.py through s05_*.py         │
│  - vote_counter.py (extract signals)        │
│  - memory.py (cross-stage state)            │
└──────────────┬──────────────────────────────┘
               │
        ┌──────▼──────┐
        │   Neo4j     │
        │   + Ollama  │
        │   + OASIS   │
        └─────────────┘
```

**Key Features:**

- **Explicit Agent Pool** — Congress members, SCOTUS justices, Executive officials, PACs loaded from real data (no random agents)
- **Profile Caching** — Agent profiles persisted as JSON + Neo4j nodes, regenerated only with `--force`
- **Modular Stages** — Each stage runs a scoped OASIS simulation with relevant agents only
- **Cross-Stage Memory** — Key decisions/commitments injected as context into subsequent stages
- **Vote Signal Extraction** — Parses agent social media posts to count explicit YES/NO votes

---

## Configuration

All settings in `.env`:

```bash
# Congress.gov API
CONGRESS_GOV_API_KEY=your_key_here

# OpenFEC API
OPENFEC_API_KEY=your_key_here

# LLM (Ollama)
LLM_API_KEY=ollama
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL_NAME=qwen2.5:32b

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=congressfish

# Embeddings
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_BASE_URL=http://localhost:11434
```

---

## Agent Building

### Build Full Congress

```bash
python backend/agents/build.py --full
```

Downloads all data from APIs, merges into unified profiles, generates personas via Ollama, populates Neo4j graph.

**Timing:** ~30-60 minutes on typical hardware (qwen2.5:32b)

### Build Test Subset

```bash
# Senate only (100 members)
python backend/agents/build.py --senate-only

# Data only (no persona generation)
python backend/agents/build.py --data-only --senate-only

# Refresh (check for new votes, update affected profiles)
python backend/agents/refresh.py
```

### Profile Structure

Each agent profile includes:

```json
{
  "bioguide_id": "A000001",
  "full_name": "John Smith",
  "chamber": "house",
  "party": "R",
  "state": "CA",

  "biography": {
    "birth_date": "1965-03-15",
    "birth_place": "San Francisco, CA",
    "education": "Stanford University, B.A. Political Science"
  },

  "ideology": {
    "primary_dimension": 0.75,  // DW-NOMINATE (right-leaning)
    "secondary_dimension": -0.2
  },

  "committee_assignments": [
    {
      "committee_code": "HSAP",
      "committee_name": "Committee on Appropriations",
      "rank": 5,
      "is_chair": false
    }
  ],

  "campaign_finance": {
    "cycle": 2024,
    "receipts": 2500000,
    "disbursements": 2400000,
    "cash_on_hand": 100000,
    "top_pac_donors": [...]
  },

  "stock_trades": [...],
  "scorecards": [...],
  "voting_alignment_with_others": {
    "B000001": 0.87,  // 87% agreement with member B000001
    "C000001": 0.45
  },

  "persona_narrative": "Representative Smith is a reliably conservative..."
}
```

---

## Simulation Output

After running a bill through the pipeline:

1. **Stage Outcomes** — Per-stage vote counts, gate check results
2. **Coalition Analysis** — Which members/orgs formed blocs, who switched sides
3. **Lobbying Impact** — Which donors/PACs influenced outcomes
4. **Final Report** — AI analysis of the entire process with quotes from agent posts
5. **Agent Interviews** — Ask any agent why they voted how they did (full memory)

---

## Hardware Requirements

| Tier | RAM | VRAM | Ollama Model | Timeline |
|---|---|---|---|---|
| Minimal | 16 GB | 8 GB | qwen2.5:7b | 2-3 hours (slow) |
| Standard | 32 GB | 12-16 GB | qwen2.5:14b | 45 min - 1 hour |
| Power | 64 GB | 24+ GB | qwen2.5:32b | 30-45 min |

---

## Use Cases

- **Legislative Impact Analysis** — Test draft bills against simulated Congressional response before introducing
- **Lobbying Strategy** — Model which pressure points (donors, committee assignments, party leadership) are most effective
- **Party Discipline** — Analyze likelihood of party members breaking ranks
- **Consensus Building** — Identify pivotal swing members and their pressure points
- **Historical Counterfactuals** — Simulate how actual bills would have passed/failed under different conditions

---

## Project Status

### Completed ✓
- [x] Phase 1: Fork & project setup
- [x] Phase 2: 6 API clients (Congress.gov, Wikipedia, Oyez, VoteView, OpenFEC, unitedstates YAML)
- [x] Phase 3: Pydantic profile models & merger
- [x] Phase 4: Persona generation templates & LLM generation
- [x] Phase 5: Neo4j graph schema & population

### In Progress 🚧
- [ ] Phase 6: Build orchestrator & refresh logic
- [ ] Phase 7: 5-stage pipeline state machine

### Planned 📋
- [ ] Phase 8: Frontend (Congress Dashboard, Member Explorer, Floor Map, Pipeline Tracker)
- [ ] Phase 9: Data refresh & maintenance scripts

See [CONGRESSFISH_ROADMAP.md](./CONGRESSFISH_ROADMAP.md) for detailed timeline and success criteria.

---

## License

AGPL-3.0 — same as [MiroFish](https://github.com/666ghj/MiroFish).

---

## Credits

**CongressFish** extends [MiroFish-Offline](https://github.com/nikmcfly/MiroFish-Offline) with a US government legislative simulation layer. Built with:

- [OASIS](https://github.com/camel-ai/oasis) — Multi-agent social simulation framework
- [Neo4j](https://neo4j.com/) — Graph database
- [Ollama](https://ollama.ai/) — Local LLM engine
- [Congress.gov API](https://api.congress.gov/) — Official Congressional data
- [OpenFEC](https://api.open.fec.gov/) — Campaign finance data
- [Oyez](https://api.oyez.org/) — Supreme Court data

**Original MiroFish** created by [666ghj](https://github.com/666ghj), supported by [Shanda Group](https://www.shanda.com/).
