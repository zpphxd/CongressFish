# CongressFish Local Development Startup

## System Requirements

- Python 3.8+
- Node.js 14+ with npm
- Ollama (for persona generation)
- Neo4j (for knowledge graph)

## Quick Start

### 1. Install Python Dependencies

```bash
# Backend dependencies
pip3 install fastapi uvicorn python-multipart

# Optional: for future enrichment scripts
pip3 install pyyaml requests beautifulsoup4
```

### 2. Install Frontend Dependencies

```bash
cd frontend
npm install
```

### 3. Start Services (in separate terminals)

**Terminal 1: Neo4j**
```bash
# Option A: Using Docker
docker run -d \
  --name congressfish-neo4j \
  -p 7687:7687 \
  -p 7474:7474 \
  -e NEO4J_AUTH=neo4j/mirofish \
  neo4j:latest

# Wait ~10 seconds for startup, then load graph:
python3 backend/graph/load_graph.py

# Option B: Local Neo4j installation
# https://neo4j.com/download/
# Start the service and run: python3 backend/graph/load_graph.py
```

**Terminal 2: FastAPI Backend**
```bash
python3 -m uvicorn backend.api.simulation_api:app --reload --port 8000
```

**Terminal 3: Ollama (optional, for persona generation)**
```bash
ollama serve
# In another shell: ollama pull mistral
```

**Terminal 4: React Frontend**
```bash
cd frontend
npm run dev
```

### 4. Access the System

- **Frontend:** http://localhost:3000
- **API Docs:** http://localhost:8000/docs
- **Neo4j Browser:** http://localhost:7474

## What's Loaded

✓ 614 Congress member profiles (enriched with biography + finance data)
✓ 50+ committees
✓ Party and state data
✓ Ideology scores (Voteview)

## Current Workflow

1. **Upload or describe a bill** in the UI
2. **Select which branches participate** (House, Senate, Executive, Judicial, or All)
3. **Click "Start Simulation"** to:
   - Load relevant members from Neo4j
   - Predict each member's position
   - Generate debate rounds
   - Tally votes
4. **View results:**
   - Vote breakdown (Yes/No/Abstain)
   - Pass/Fail outcome
   - Member-by-member positions (click for details)
   - Confidence levels and reasoning

## Troubleshooting

**Neo4j connection fails:**
```bash
# Check if running on correct port
lsof -i :7687

# Test connection
python3 -c "from backend.graph.neo4j_client import Neo4jClient; c = Neo4jClient(); print('Connected!' if c.connect() else 'Failed')"
```

**API returns 404:**
```bash
# Ensure graph is loaded
python3 backend/graph/load_graph.py --reset

# Check API is running on port 8000
curl http://localhost:8000/api/graph/stats
```

**Frontend doesn't load:**
```bash
# Check npm dependencies
cd frontend && npm install

# Check CORS is enabled in FastAPI (should be by default)
```

## Files Overview

```
backend/
  graph/
    neo4j_client.py       # Connection & queries
    neo4j_schema.py       # Schema definition
    load_graph.py         # Loader script
  agents/
    personas/congress/    # 614 enriched member profiles
    generate_personas.py  # Ollama persona generator
    enrich_with_finance.py # Finance data enrichment
  simulation/
    bill_discussion_engine.py # Core simulation logic
  api/
    simulation_api.py     # FastAPI REST API

frontend/
  pages/
    simulation.tsx        # Main simulation UI
```

## Next Steps

1. **Persona Generation** (optional, for richer simulations):
   ```bash
   python3 backend/agents/generate_personas.py --model mistral
   ```
   (Takes 30-60 minutes for 614 members)

2. **Custom Bill Documents:**
   Upload PDF/TXT files to extract provisions automatically

3. **Advanced Visualizations:**
   Add interactive voting network graphs, ideology spectrum visualization

4. **Extend Simulation:**
   Add amendment proposals, media influence, real-time voting updates
