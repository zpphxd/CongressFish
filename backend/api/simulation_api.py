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
from backend.simulation.congress_simulator import CongressSimulator
from backend.simulation.bill_discussion_engine import (
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

    simulator = CongressSimulator()
    logger.info("✓ Simulator initialized with Congress member personas")


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

        logger.info(f"✓ Created simulation {simulation_id} - now in active_simulations: {simulation_id in active_simulations}")

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
    logger.info(f"Status check for {simulation_id} - exists: {simulation_id in active_simulations}, all_sims: {list(active_simulations.keys())}")
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


@app.get("/api/simulation/{simulation_id}/graph")
async def get_simulation_graph(simulation_id: str) -> Dict[str, Any]:
    """
    Get graph data (nodes and edges) for relevant Congress members.

    Args:
        simulation_id: Simulation ID

    Returns:
        Graph nodes (members) and edges (relationships) for selected branches
    """
    if simulation_id not in active_simulations:
        raise HTTPException(status_code=404, detail="Simulation not found")

    if not neo4j_client:
        raise HTTPException(status_code=503, detail="Database unavailable")

    sim = active_simulations[simulation_id]
    branches = sim.get("branches", [])

    # Map GovernmentBranch enum to chamber names for Neo4j query
    chamber_map = {
        "HOUSE": "House",
        "SENATE": "Senate",
        "EXECUTIVE": "Executive",
        "JUDICIAL": "Judicial"
    }

    chambers = [chamber_map.get(b.name, b.name) if b else None for b in branches if b]

    # Get members for selected chambers
    nodes = []
    edges = []

    if neo4j_client:
        # Query members by chamber
        if chambers:
            for chamber in chambers:
                members = neo4j_client.get_members_by_chamber(chamber)
                for member in members:
                    nodes.append({
                        "id": member.get("bioguide_id", member.get("id")),
                        "label": member.get("full_name", "Unknown"),
                        "type": "member",
                        "chamber": chamber,
                        "party": member.get("party", "Independent"),
                        "ideology": member.get("ideology_score", 0)
                    })

        # Get committees as secondary nodes
        if nodes:
            committees = neo4j_client.session.run(
                "MATCH (m:CongressMember)-[r:SERVES_ON]->(c:Committee) "
                "WHERE m.bioguide_id IN $bioguides "
                "RETURN DISTINCT c.id as id, c.name as name",
                bioguides=[n["id"] for n in nodes]
            ).data()

            for committee in committees:
                nodes.append({
                    "id": committee["id"],
                    "label": committee["name"],
                    "type": "committee"
                })

                # Add edges from members to committees
                member_committee_edges = neo4j_client.session.run(
                    "MATCH (m:CongressMember)-[r:SERVES_ON]->(c:Committee {id: $committee_id}) "
                    "WHERE m.bioguide_id IN $bioguides "
                    "RETURN m.bioguide_id as member_id",
                    committee_id=committee["id"],
                    bioguides=[n["id"] for n in nodes if n["type"] == "member"]
                ).data()

                for edge in member_committee_edges:
                    edges.append({
                        "source": edge["member_id"],
                        "target": committee["id"],
                        "type": "serves_on"
                    })

    return {
        "simulation_id": simulation_id,
        "nodes": nodes if nodes else [],
        "edges": edges if edges else [],
        "chambers": [b.name if b else "ALL" for b in branches]
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

    raw_results = sim.get("results", {})

    # Transform raw results into frontend-friendly format
    # Aggregate votes from all stages
    total_yes = sum(s.get("yes_votes", 0) for s in raw_results.get("stage_results", []))
    total_no = sum(s.get("no_votes", 0) for s in raw_results.get("stage_results", []))
    total_abstain = sum(s.get("abstain_votes", 0) for s in raw_results.get("stage_results", []))

    total_votes = total_yes + total_no + total_abstain
    percentage_yes = (total_yes / total_votes * 100) if total_votes > 0 else 0

    return {
        "bill_title": raw_results.get("bill_title", ""),
        "bill_description": raw_results.get("bill_description", ""),
        "final_status": raw_results.get("final_status", "unknown"),
        "passed": raw_results.get("passed", False),
        "chambers": raw_results.get("chambers", []),
        "stage_results": raw_results.get("stage_results", []),
        "vote_results": {
            "yes": total_yes,
            "no": total_no,
            "abstain": total_abstain,
            "passes": raw_results.get("passed", False),
            "margin": total_yes - total_no,
            "percentage_yes": percentage_yes / 100
        },
        "member_positions": {},  # Placeholder - would need to extract from debate feed if needed
        "duration_seconds": raw_results.get("duration_seconds", 0)
    }


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
    """Run simulation in background using OASIS pipeline stages."""
    try:
        if not simulator:
            logger.error("Simulator not initialized")
            active_simulations[simulation_id]["status"] = "error"
            return

        active_simulations[simulation_id]["progress"] = 10
        logger.info(f"Running simulation {simulation_id}...")

        # Run simulation using the CongressSimulator
        # (which uses the prebuilt personas)
        results = simulator.run_simulation(
            bill_title=bill.title,
            bill_description=bill.description,
            chambers=_branches_to_chambers(branches)
        )

        active_simulations[simulation_id]["progress"] = 100
        active_simulations[simulation_id]["status"] = "complete"
        active_simulations[simulation_id]["results"] = results

        logger.info(f"✓ Simulation {simulation_id} complete")

    except Exception as e:
        logger.error(f"Simulation error: {e}", exc_info=True)
        active_simulations[simulation_id]["status"] = "error"
        active_simulations[simulation_id]["error"] = str(e)


def _branches_to_chambers(branches: Optional[List[GovernmentBranch]]) -> Optional[List[str]]:
    """Convert GovernmentBranch enums to chamber names."""
    if not branches:
        return None

    chamber_names = []
    for branch in branches:
        if branch == GovernmentBranch.HOUSE:
            chamber_names.append("House")
        elif branch == GovernmentBranch.SENATE:
            chamber_names.append("Senate")
        elif branch == GovernmentBranch.EXECUTIVE:
            chamber_names.append("Executive")
        elif branch == GovernmentBranch.JUDICIAL:
            chamber_names.append("Judicial")

    return chamber_names if chamber_names else None


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
