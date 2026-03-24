"""
Agent Profile Generation
========================
Pydantic models for all agent types and LLM-based persona generation.

Modules:
  - models: Pydantic schemas for CongressMemberProfile, JusticeProfile, etc.
  - generator: Ollama-based persona narrative generation
  - merger: Merges data from all APIs into unified profile objects
"""

__all__ = [
    'models',
    'generator',
    'merger',
]
