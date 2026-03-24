# CongressFish System Setup & Architecture

Complete government simulation system with enriched Congress member profiles, Neo4j knowledge graph, Ollama personas, and bill debate engine.

## System Architecture

```
User Interface (React Frontend)
           ↓
   REST API (FastAPI)
           ↓
┌──────────────────────────────────────┐
│   Simulation Engine                  │
│ • Bill Discussion Engine             │
│ • Vote Prediction (Claude/Ollama)    │
│ • Debate Generation                  │
└──────────────────────────────────────┘
           ↓
    Neo4j Graph Database
┌──────────────────────────────────────┐
│ Nodes: Congress Members, Committees,  │
│        Parties, States, Bills         │
│ Relationships: MEMBER_OF, FROM_STATE, │
│               COSPONSORED_WITH, etc.  │
└──────────────────────────────────────┘
           ↓
   Enriched Agent Profiles
   (Biographical, Financial,
    Ideology, Committee data)
```

## Components

### 1. Data Layer

**Files:**
- `backend/agents/personas/congress/{house,senate}/*.json` — 614 enriched member profiles
- `backend/agents/apis/grok.py` — Grok API client (removed after enrichment)
- `backend/agents/enrich_with_biography.py` — Biography enrichment script (removed after enrichment)

**Profile Structure:**
```json
{
  "bioguide_id": "A000055",
  "full_name": "Robert B. Aderholt",
  "party": "R",
  "state": "ALABAMA",
  "chamber": "house",
  "ids": {"fec_id": "H6AL04098"},
  "biography": {
    "birth_date": "1965-07-22",
    "birth_place": "Haleyville, Alabama",
    "education": "Birmingham-Southern College, Samford University",
    "occupation": "Attorney",
    "wikipedia_summary": "...",
    "full_biography": "..."
  },
  "campaign_finance": {
    "receipts": 627403.31,
    "disbursements": 532579.79,
    "cash_on_hand": 1061719.86
  },
  "ideology": {
    "primary_dimension": 0.65,
    "secondary_dimension": -0.1
  },
  "committee_assignments": [
    {"code": "HSAP", "title": "Appropriations", "rank": 5}
  ]
}
```

### 2. Graph Database Layer

**Neo4j Installation:**

```bash
# Option 1: Docker (recommended)
docker run -d \
  -p 7687:7687 \
  -p 7474:7474 \
  -e NEO4J_AUTH=neo4j/password \
  neo4j:latest

# Option 2: Local installation
# https://neo4j.com/download/
# Default connection: bolt://localhost:7687
# Default credentials: neo4j/password
```

**Files:**
- `backend/graph/neo4j_client.py` — Connection & query client
- `backend/graph/neo4j_schema.py` — Schema definition
- `backend/graph/load_graph.py` — Loader script

**Load Graph:**

```bash
python backend/graph/load_graph.py \
  --neo4j-uri bolt://localhost:7687 \
  --neo4j-user neo4j \
  --neo4j-password password
```

**Graph Nodes:**
- `CongressMember` — 614 members with all biographical data
- `Party` — Democratic, Republican, Independent, Libertarian
- `Committee` — 50+ standing committees
- `State` — All 50 states + DC

**Graph Relationships:**
- `PARTY_MEMBER` — Member → Party
- `FROM_STATE` — Member → State
- `MEMBER_OF` — Member → Committee
- `COSPONSORED_WITH` — Member ↔ Member (committees in common)
- `IDEOLOGICALLY_ALIGNED` — Member ↔ Member (similar ideology scores)

**Query Examples:**

```cypher
# Get all Democrats
MATCH (m:CongressMember)-[:PARTY_MEMBER]->(p:Party {code: "D"})
RETURN m ORDER BY m.full_name

# Get members on Appropriations Committee
MATCH (m:CongressMember)-[:MEMBER_OF]->(c:Committee {code: "HSAP"})
RETURN m ORDER BY m.full_name

# Get ideology spectrum
MATCH (m:CongressMember)
RETURN m ORDER BY m.ideology_primary
```

### 3. Persona Generation Layer

**Ollama Installation:**

```bash
# Download and run Ollama
# https://ollama.ai
ollama pull mistral
ollama pull neural-chat
ollama pull llama2

# Or start Ollama server (default: http://localhost:11434)
ollama serve
```

**Files:**
- `backend/agents/generate_personas.py` — Persona generator

**Generate Personas:**

```bash
python backend/agents/generate_personas.py \
  --model mistral \
  --ollama-url http://localhost:11434 \
  --concurrency 2
```

**Output:** Each profile gets `persona` field with:
- `core_values` — Member's main priorities
- `decision_style` — How they vote (ideological/pragmatic)
- `communication_style` — How they debate
- `party_relationship` — Party loyalty/maverick status
- `negotiation_approach` — What persuades them
- `key_interests` — Policy focus areas
- `voting_pattern` — Typical behavior
- `likely_positions` — Where they stand on common issues

### 4. Simulation Engine Layer

**Files:**
- `backend/simulation/bill_discussion_engine.py` — Core simulation logic

**Key Components:**

1. **Bill Creation** — Describe a bill, engine extracts provisions and context
2. **Member Relevance** — Identifies affected members:
   - Committee members (highest relevance)
   - Party leaders (high relevance)
   - Ideology spectrum diversity (medium relevance)
3. **Position Prediction** — Uses LLM to predict vote:
   - Inputs: Member profile + persona + committees + ideology
   - Output: `yes/no/abstain` with confidence & reasoning
4. **Debate Rounds** — Generates statements:
   - Members respond to previous speakers
   - Statements based on persona + bill impact on their interests
5. **Vote Tallying** — Final results:
   - Yes/No/Abstain counts
   - Margin of victory
   - Outcome (passes/fails)

### 5. API Layer

**FastAPI Server:**

```bash
# Install dependencies
pip install fastapi uvicorn

# Run server (default: http://localhost:8000)
python -m uvicorn backend.api.simulation_api:app --reload
```

**Endpoints:**

```
POST   /api/simulation/start          — Start new bill simulation
GET    /api/simulation/{id}/status    — Check progress
GET    /api/simulation/{id}/results   — Get results when complete
POST   /api/bill/upload               — Upload bill document
GET    /api/members/search            — Search members by name
GET    /api/members/{bioguide_id}     — Get member details
GET    /api/graph/stats               — Get graph statistics
```

### 6. Frontend Layer

**React UI:**

**Files:**
- `frontend/pages/simulation.tsx` — Main simulation interface

**Features:**
- Propose bills in natural language
- Select which branches participate (House, Senate, Executive, Judicial, or All)
- Real-time progress indicator
- Vote results visualization
- Member position breakdown
- Debate transcript (future)

**Run Frontend:**

```bash
# Install dependencies
npm install

# Run dev server (default: http://localhost:3000)
npm run dev
```

## Complete Setup Workflow

### 1. Ensure Enrichment is Complete

```bash
# Check all profiles have biography data
grep -c '"wikipedia_summary"' backend/agents/personas/congress/**/*.json
# Should output: 614
```

### 2. Start Neo4j

```bash
# If using Docker
docker run -d \
  --name congressfish-neo4j \
  -p 7687:7687 \
  -p 7474:7474 \
  -e NEO4J_AUTH=neo4j/password \
  neo4j:latest

# Wait 10 seconds for startup
sleep 10

# Test connection
python -c "from backend.graph.neo4j_client import Neo4jClient; c = Neo4jClient(); print('Connected!' if c.connect() else 'Failed')"
```

### 3. Load Congress Data into Neo4j

```bash
python backend/graph/load_graph.py
# Output should show:
# ✓ Created X Party nodes
# ✓ Created 51 State nodes
# ✓ Loaded 614 Congress members
# ✓ Created cosponsorship network
# ✓ Created ideology clusters
```

### 4. Start Ollama (for persona generation)

```bash
# Terminal 1: Start Ollama server
ollama serve

# Terminal 2: Pull models (while server runs)
ollama pull mistral
ollama pull neural-chat
```

### 5. Generate Personas

```bash
python backend/agents/generate_personas.py --model mistral
# Will take 30-60 minutes for 614 members
# Sets --concurrency 2 to avoid overloading Ollama
```

### 6. Start FastAPI Server

```bash
# Terminal: Run API server
python -m uvicorn backend.api.simulation_api:app --reload --port 8000
# Server runs on http://localhost:8000
```

### 7. Start React Frontend

```bash
# Terminal: Run frontend
cd frontend
npm run dev
# Frontend runs on http://localhost:3000
```

### 8. Use the System

1. Open browser to `http://localhost:3000`
2. Navigate to Simulation page
3. Describe a bill (e.g., "Climate action bill with carbon pricing")
4. Choose which branches participate:
   - Select **House only** (quick, 235 members)
   - Select **House + Senate** (medium, 614 members)
   - Select **All** (full simulation with branches)
5. Click "Start Simulation"
6. Watch progress as system:
   - Loads relevant members from Neo4j
   - Predicts positions using Claude API
   - Generates debate statements
   - Tallies votes
7. View results: votes, member positions, margins

## Example: Healthcare Bill Simulation

```
Input: "Comprehensive healthcare bill establishing a public option
        competing with private insurance"

Expected flow:
1. House members loaded: ~235 (especially Ways & Means, Energy & Commerce)
2. Position predictions:
   - Democrats: Mostly YES (align with public option)
   - Republicans: Mixed NO (fiscal concerns)
   - Progressive caucus: Strong YES, detailed reasoning
   - Moderate Democrats: Conditional YES, focus on cost controls
3. Debate rounds: Members address concerns
4. Vote result: Likely PASSES in House (Democratic majority)
```

## Configuration

### Environment Variables

```bash
# .env file
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=mistral

CLAUDE_API_KEY=sk-...  # For vote prediction (optional, can use Ollama)
```

### Scaling

**For larger deployments:**
- Run Neo4j on separate machine
- Use Neo4j causal cluster for HA
- Scale Ollama to multiple GPU servers
- Run FastAPI behind load balancer (Nginx)
- Cache debate generation results

## Testing

```bash
# Test Neo4j connection
python -c "from backend.graph.neo4j_client import Neo4jClient; c = Neo4jClient(); print(c.get_graph_stats())"

# Test Ollama
curl http://localhost:11434/api/generate -d '{"model":"mistral","prompt":"test"}'

# Test API
curl http://localhost:8000/api/graph/stats

# Run a test simulation
curl -X POST http://localhost:8000/api/simulation/start \
  -H "Content-Type: application/json" \
  -d '{"query":"Climate bill","scope":"all"}'
```

## Troubleshooting

**Neo4j connection fails:**
- Check Docker container is running: `docker ps | grep neo4j`
- Check firewall: port 7687 should be open
- Test connection: `telnet localhost 7687`

**Ollama timeout:**
- Check Ollama server: `curl http://localhost:11434/api/tags`
- Reduce concurrency: `--concurrency 1`
- Check GPU availability: `ollama ps`

**API returns 404:**
- Ensure Neo4j graph is loaded: `python backend/graph/load_graph.py`
- Check API server is running on port 8000

**Frontend doesn't show results:**
- Check browser console for errors
- Ensure API is running on port 8000
- Check CORS settings in FastAPI

## Next Steps

1. **Custom bills:** Add bill document upload (PDF → text extraction)
2. **Voting alignment:** Track voting history to refine predictions
3. **Media simulation:** Add public opinion influence on votes
4. **Amendment handling:** Simulate amendment proposals and votes
5. **Visualization:** Interactive network graphs of voting patterns
6. **Export:** Save simulations to JSON/CSV for analysis

## Files Summary

```
backend/
  agents/
    personas/congress/   # 614 enriched member profiles
    generate_personas.py # Ollama persona generator
  graph/
    neo4j_client.py     # Neo4j connection & queries
    neo4j_schema.py     # Schema & loader
    load_graph.py       # Load profiles into Neo4j
  simulation/
    bill_discussion_engine.py  # Core simulation logic
  api/
    simulation_api.py    # FastAPI server

frontend/
  pages/
    simulation.tsx      # Main UI

docs/
  progress.md          # Development progress
  SYSTEM_SETUP.md      # This file
```
