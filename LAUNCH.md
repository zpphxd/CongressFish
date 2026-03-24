# CongressFish Launch Guide

## Quick Start (2 Commands)

### Prerequisites
- Docker & Docker Compose installed

### Launch

```bash
# 1. Start all services (Neo4j + Ollama + FastAPI + React)
docker compose up -d

# 2. Pull the LLM model
docker exec congressfish-ollama ollama pull qwen2.5:32b
```

Then open **http://localhost:3000** and you're ready to simulate bills.

---

## What's Running

| Service | URL | Container |
|---------|-----|-----------|
| **React UI** | http://localhost:3000 | congressfish |
| **FastAPI** | http://localhost:8000 | congressfish |
| **Neo4j Browser** | http://localhost:7474 | congressfish-neo4j |
| **Ollama** | http://localhost:11434 | congressfish-ollama |

---

## How It Works

1. **Browser** → Propose a bill in natural language
2. **React UI** → Sends request to FastAPI backend
3. **FastAPI** → Loads relevant Congress members from Neo4j
4. **LLM (Ollama qwen2.5:32b)** → Uses existing member personas to predict positions and generate debate
5. **Results** → Vote outcomes, member positions, debate transcript

All member profiles already have:
- ✅ Biographical data (Wikipedia + Ballotpedia)
- ✅ Campaign finance (FEC records)
- ✅ Committee assignments
- ✅ Ideology scores (Voteview)

---

## Common Commands

### Check service status
```bash
docker compose ps
```

### View logs
```bash
docker compose logs -f congressfish    # Backend + Frontend
docker compose logs -f congressfish-neo4j
docker compose logs -f congressfish-ollama
```

### Stop all services
```bash
docker compose down
```

### Full reset (remove data)
```bash
docker compose down -v
```

### Enter Neo4j Browser
Open http://localhost:7474, default credentials: `neo4j` / `congressfish`

---

## Manual Setup (No Docker)

If Docker isn't available:

**1. Start Neo4j**
```bash
brew install neo4j
neo4j start
# Or use Docker: docker run -d -p 7687:7687 -p 7474:7474 -e NEO4J_AUTH=neo4j/congressfish neo4j:5.18-community
```

**2. Start Ollama**
```bash
ollama serve
# In another terminal: ollama pull qwen2.5:32b
```

**3. Load Congress data into Neo4j**
```bash
python backend/graph/load_graph.py
```

**4. Start FastAPI backend**
```bash
python -m uvicorn backend.api.simulation_api:app --reload --port 8000
```

**5. Start React frontend**
```bash
cd frontend
npm install
npm run dev
```

---

## Troubleshooting

### "Cannot connect to Docker daemon"
- Install Docker Desktop (macOS/Windows) or Docker Engine (Linux)
- Or use Manual Setup above

### "Port 3000 already in use"
```bash
lsof -i :3000
kill -9 <PID>
# Or change port in docker-compose.yml
```

### Neo4j takes time to start
- Initial startup can take 30-60 seconds
- Check logs: `docker compose logs congressfish-neo4j`
- Wait for "Started" message

### Ollama model not found
```bash
docker exec congressfish-ollama ollama pull qwen2.5:32b
```

### FastAPI can't connect to Neo4j
- Ensure Neo4j container is healthy: `docker compose ps`
- Neo4j password in .env must match docker-compose.yml (congressfish)
- Test connection: `docker exec congressfish python -c "from backend.graph.neo4j_client import Neo4jClient; print(Neo4jClient().connect())"`

---

## System Architecture

```
User Browser (http://localhost:3000)
    ↓
React Frontend (Next.js)
    ↓
FastAPI REST API (http://localhost:8000)
    ↓
┌─────────────────────────────────┐
│  Simulation Engine              │
│ • Load members from Neo4j       │
│ • Predict positions (Ollama)    │
│ • Generate debate               │
│ • Tally votes                   │
└─────────────────────────────────┘
    ↓
Neo4j Graph Database (bolt://localhost:7687)
├─ CongressMembers (614)
├─ Committees (50+)
├─ Parties (4)
└─ States (51)
```

---

## Example: Healthcare Bill

1. Open http://localhost:3000 → "Simulation" page
2. Enter: "Comprehensive healthcare bill with a public option"
3. Click "Start Simulation"
4. Watch progress:
   - Loading members from database
   - Predicting positions
   - Running debate rounds
   - Tallying votes
5. View results:
   - Vote counts (yes/no/abstain)
   - Member breakdown (position, confidence, reasoning)
   - Debate transcript

Expected outcome: Bill likely **passes** in House (Democratic majority), **fails** in Senate (50-50 split).

---

## Next Steps

- **Customize debates** → Edit `backend/simulation/bill_discussion_engine.py`
- **Add features** → Modify `frontend/pages/simulation.tsx`
- **Adjust member profiles** → Edit `backend/agents/personas/congress/{house,senate}/*.json`
- **Change LLM model** → Update `OLLAMA_MODEL` in docker-compose.yml (e.g., `llama2:13b`, `mistral:7b`)

---

## Data Completeness

All 614 Congress members enriched:
- ✅ Full names, parties, states, chambers
- ✅ Committee assignments (50+ committees)
- ✅ Campaign finance (FEC 2024 cycle)
- ✅ Biographical data (Wikipedia + Ballotpedia)
- ✅ Ideology scores (Voteview, -1 to +1 spectrum)

No enrichment scripts needed — data is complete, ready to use.
