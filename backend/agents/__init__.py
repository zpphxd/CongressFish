"""
CongressFish Agents Module
==========================
Data ingest, profile generation, and Neo4j graph population for
US government simulation agents.

Submodules:
  - apis: Data collection clients (Congress.gov, OpenFEC, VoteView, etc.)
  - profiles: Pydantic models and persona generation
  - storage: Neo4j schema and graph population
  - build: Master orchestrator and refresh logic
"""

__version__ = "0.1.0"
