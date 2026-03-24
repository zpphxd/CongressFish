"""
CongressFish Agents Configuration
==================================
Loads API keys and configuration from .env file.
"""

import os
from dotenv import load_dotenv

# Load .env from project root
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_env_path = os.path.join(_project_root, '.env')
if os.path.exists(_env_path):
    load_dotenv(_env_path)


class AgentsConfig:
    """Configuration for data ingest and agent building."""

    # Congress.gov API
    CONGRESS_GOV_API_KEY = os.getenv('CONGRESS_GOV_API_KEY', '')
    CONGRESS_GOV_BASE_URL = 'https://api.congress.gov/v3'
    CONGRESS_GOV_RATE_LIMIT = 5000  # Requests per hour
    CONGRESS_GOV_CONCURRENCY = 10   # Concurrent requests

    # OpenFEC API
    OPENFEC_API_KEY = os.getenv('OPENFEC_API_KEY', '')
    OPENFEC_BASE_URL = 'https://api.open.fec.gov/v1'
    OPENFEC_RATE_LIMIT = 1000       # Requests per hour

    # Quiver Quantitative
    QUIVER_API_KEY = os.getenv('QUIVER_API_KEY', '')
    QUIVER_BASE_URL = 'https://www.quiverquant.com/api/v1'

    # Neo4j
    NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
    NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'password')

    # Ollama (for persona generation)
    LLM_API_KEY = os.getenv('LLM_API_KEY', 'ollama')
    LLM_BASE_URL = os.getenv('LLM_BASE_URL', 'http://localhost:11434/v1')
    LLM_MODEL_NAME = os.getenv('LLM_MODEL_NAME', 'qwen2.5:32b')

    # Cache & storage
    PROJECT_ROOT = _project_root
    CACHE_DIR = os.path.join(PROJECT_ROOT, 'backend', 'agents', 'cache')
    PERSONAS_DIR = os.path.join(PROJECT_ROOT, 'backend', 'agents', 'personas')

    # Directories
    CONGRESS_PERSONAS_DIR = os.path.join(PERSONAS_DIR, 'congress')
    CONGRESS_HOUSE_PERSONAS_DIR = os.path.join(CONGRESS_PERSONAS_DIR, 'house')
    CONGRESS_SENATE_PERSONAS_DIR = os.path.join(CONGRESS_PERSONAS_DIR, 'senate')
    SCOTUS_PERSONAS_DIR = os.path.join(PERSONAS_DIR, 'scotus')
    EXECUTIVE_PERSONAS_DIR = os.path.join(PERSONAS_DIR, 'executive')
    INFLUENCE_PERSONAS_DIR = os.path.join(PERSONAS_DIR, 'influence')

    # Data sources
    CONGRESS_CONGRESS_NUMBER = 119  # 119th Congress (2025-2027)

    # Persona generation
    PERSONA_TEMPERATURE = 0.7
    PERSONA_MAX_TOKENS = 1200

    @classmethod
    def ensure_directories_exist(cls):
        """Create all necessary directories if they don't exist."""
        for d in [
            cls.CACHE_DIR,
            cls.CONGRESS_HOUSE_PERSONAS_DIR,
            cls.CONGRESS_SENATE_PERSONAS_DIR,
            cls.SCOTUS_PERSONAS_DIR,
            cls.EXECUTIVE_PERSONAS_DIR,
            cls.INFLUENCE_PERSONAS_DIR,
        ]:
            os.makedirs(d, exist_ok=True)
