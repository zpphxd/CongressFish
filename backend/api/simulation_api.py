#!/usr/bin/env python3
"""
REST API for CongressFish bill simulation system.

Endpoints for:
- Document/bill upload
- Query submission
- Simulation control (full flow, filtered branches)
- Results retrieval
"""

from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import json
import uuid
import logging

from backend.graph.neo4j_client import Neo4jClient
from backend.simulation.bill_discussion_engine import (
    BillDiscussionEngine,
    GovernmentSimulator,
    Bill,
    GovernmentBranch
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="CongressFish Simulation API",
    description="US Government bill debate simulation",
    version="1.0.0"
)

# Global state
neo4j_client = None
simulator = None
active_simulations: Dict[str, Dict[str, Any]] = {}


@app.on_event("startup")
async def startup():
    """Initialize connections on startup."""
    global neo4j_client, simulator

    neo4j_client = Neo4jClient()
    if neo4j_client.connect():
        logger.info("✓ Connected to Neo4j")
    else:
        logger.error("✗ Failed to connect to Neo4j")

    # Would initialize LLM client here
    # simulator = GovernmentSimulator(neo4j_client, llm_client)


@app.on_event("shutdown")
async def shutdown():
    """Clean up on shutdown."""
    if neo4j_client:
        neo4j_client.close()


# Pydantic models

class BillInput(BaseModel):
    """Bill proposal input."""
    title: str
    description: str
    primary_chamber: str = "house"  # house or senate
    sponsor_bioguide: Optional[str] = None
    key_provisions: List[str] = []
    estimated_cost: Optional[float] = None


class SimulationConfig(BaseModel):
    """Configuration for simulation run."""
    bill: BillInput
    branches: List[str] = ["house", "senate"]  # house, senate, executive, judicial
    max_debate_rounds: int = 5
    include_media_response: bool = False
    include_polling: bool = False


class SimulationRequest(BaseModel):
    """Request to start a simulation."""
    query: str  # Natural language description of bill
    scope: str = "all"  # all, house, senate, executive, judicial


# Endpoints

@app.post("/api/bill/upload")
async def upload_bill_document(
    file: UploadFile = File(...),
    title: Optional[str] = None
) -> Dict[str, Any]:
    """
    Upload bill document (PDF, text, etc).

    Args:
        file: Bill document file
        title: Optional bill title

    Returns:
        Bill ID and extracted content
    """
    try:
        bill_id = str(uuid.uuid4())[:8]
        content = await file.read()

        # Parse document (simplified - would use PDF parser, etc)
        text = content.decode("utf-8") if isinstance(content, bytes) else str(content)

        return {
            "bill_id": bill_id,
            "filename": file.filename,
            "title": title or file.filename,
            "content_preview": text[:200],
            "status": "uploaded"
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/simulation/start")
async def start_simulation(
    request: SimulationRequest,
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """
    Start a new bill simulation.

    Args:
        request: Simulation request with bill description and scope
        background_tasks: Background task handler

    Returns:
        Simulation ID and initial status
    """
    try:
        simulation_id = str(uuid.uuid4())[:12]

        # Parse the natural language query into a bill
        bill = Bill(
            id=simulation_id,
            title=request.query[:100],
            description=request.query,
            sponsor_bioguide=None,
            primary_chamber="HOUSE",  # Would parse from query
            summary=request.query[:200],
            key_provisions=[]  # Would extract from query
        )

        # Map scope string to GovernmentBranch enum
        branch_map = {
            "house": GovernmentBranch.HOUSE,
            "senate": GovernmentBranch.SENATE,
            "executive": GovernmentBranch.EXECUTIVE,
            "judicial": GovernmentBranch.JUDICIAL,
            "all": None  # None means all branches
        }

        branches = [branch_map[b] for b in request.scope.split(",") if b in branch_map]
        if not branches and request.scope == "all":
            branches = None

        # Initialize simulation tracking
        import datetime
        active_simulations[simulation_id] = {
            "status": "running",
            "bill": bill,
            "branches": branches,
            "progress": 0,
            "results": None,
            "created_at": datetime.datetime.now().isoformat()
        }

        # Run simulation in background
        background_tasks.add_task(
            _run_simulation_background,
            simulation_id,
            bill,
            branches
        )

        return {
            "simulation_id": simulation_id,
            "bill_title": bill.title,
            "scope": request.scope,
            "status": "started",
            "poll_url": f"/api/simulation/{simulation_id}/status"
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/simulation/{simulation_id}/status")
async def get_simulation_status(simulation_id: str) -> Dict[str, Any]:
    """
    Get current simulation status.

    Args:
        simulation_id: Simulation ID

    Returns:
        Current status and progress
    """
    if simulation_id not in active_simulations:
        raise HTTPException(status_code=404, detail="Simulation not found")

    sim = active_simulations[simulation_id]

    return {
        "simulation_id": simulation_id,
        "status": sim["status"],
        "progress": sim["progress"],
        "bill": {
            "title": sim["bill"].title,
            "id": sim["bill"].id
        }
    }


@app.get("/api/simulation/{simulation_id}")
async def get_simulation(simulation_id: str) -> Dict[str, Any]:
    """
    Get simulation details (bill info, config, status).

    Args:
        simulation_id: Simulation ID

    Returns:
        Simulation details
    """
    if simulation_id not in active_simulations:
        raise HTTPException(status_code=404, detail="Simulation not found")

    sim = active_simulations[simulation_id]

    return {
        "simulation_id": simulation_id,
        "bill_title": sim["bill"].title,
        "bill_description": sim["bill"].description,
        "status": sim["status"],
        "progress": sim["progress"],
        "branches": [b.name if b else "ALL" for b in sim.get("branches", [])],
        "created_at": sim.get("created_at", None)
    }


@app.get("/api/simulation/{simulation_id}/config")
async def get_simulation_config(simulation_id: str) -> Dict[str, Any]:
    """
    Get simulation configuration.

    Args:
        simulation_id: Simulation ID

    Returns:
        Simulation config (branches, rounds, etc)
    """
    if simulation_id not in active_simulations:
        raise HTTPException(status_code=404, detail="Simulation not found")

    sim = active_simulations[simulation_id]

    return {
        "simulation_id": simulation_id,
        "branches": [b.name if b else "ALL" for b in sim.get("branches", [])],
        "max_debate_rounds": 5,
        "include_media_response": False,
        "include_polling": False
    }


@app.get("/api/simulation/{simulation_id}/results")
async def get_simulation_results(simulation_id: str) -> Dict[str, Any]:
    """
    Get full simulation results (when complete).

    Args:
        simulation_id: Simulation ID

    Returns:
        Complete debate transcript, votes, outcomes
    """
    if simulation_id not in active_simulations:
        raise HTTPException(status_code=404, detail="Simulation not found")

    sim = active_simulations[simulation_id]

    if sim["status"] == "running":
        raise HTTPException(status_code=202, detail="Simulation still running")

    return sim.get("results", {})


@app.get("/api/members/search")
async def search_members(q: str, party: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Search Congress members.

    Args:
        q: Search query (name)
        party: Filter by party (D/R/I)

    Returns:
        List of matching members
    """
    if not neo4j_client:
        raise HTTPException(status_code=503, detail="Database unavailable")

    members = neo4j_client.search_members(q)

    if party:
        members = [m for m in members if m.get("party") == party]

    return members


@app.get("/api/graph/stats")
async def get_graph_stats() -> Dict[str, int]:
    """Get Neo4j graph statistics."""
    if not neo4j_client:
        raise HTTPException(status_code=503, detail="Database unavailable")

    return neo4j_client.get_graph_stats()


@app.get("/api/members/{bioguide_id}")
async def get_member_detail(bioguide_id: str) -> Dict[str, Any]:
    """Get detailed member profile."""
    if not neo4j_client:
        raise HTTPException(status_code=503, detail="Database unavailable")

    member = neo4j_client.get_member_by_bioguide(bioguide_id)

    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    # Augment with committees and allies
    committees = neo4j_client.get_member_committees(bioguide_id)
    allies = neo4j_client.get_ally_network(bioguide_id)

    return {
        **member,
        "committees": committees,
        "allies": allies
    }


# Background tasks

async def _run_simulation_background(
    simulation_id: str,
    bill: Bill,
    branches: Optional[List[GovernmentBranch]] = None
):
    """Run simulation in background."""
    try:
        if not simulator:
            logger.error("Simulator not initialized")
            active_simulations[simulation_id]["status"] = "error"
            return

        active_simulations[simulation_id]["progress"] = 10

        # Run simulation
        results = simulator.run_full_simulation(
            bill,
            max_debate_rounds=5,
            branches=branches
        )

        active_simulations[simulation_id]["progress"] = 100
        active_simulations[simulation_id]["status"] = "complete"
        active_simulations[simulation_id]["results"] = results

        logger.info(f"✓ Simulation {simulation_id} complete")

    except Exception as e:
        logger.error(f"Simulation error: {e}")
        active_simulations[simulation_id]["status"] = "error"
        active_simulations[simulation_id]["error"] = str(e)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
