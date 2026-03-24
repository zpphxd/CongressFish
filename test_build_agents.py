#!/usr/bin/env python3
"""
Quick test: build 5 Senate agents to verify pipeline works.
"""

import os
import sys
import json
import logging
from pathlib import Path

# Setup path
sys.path.insert(0, os.path.dirname(__file__))

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

from backend.agents.config import AgentsConfig
from backend.agents.apis.congress_gov import CongressGovClient
from backend.agents.apis.unitedstates_project import UnitedStatesProjectClient
from backend.agents.apis.wikipedia import WikipediaClient
from backend.agents.apis.voteview import VoteViewClient
from backend.agents.apis.openfec import OpenFECClient
from backend.agents.apis.oyez import OyezClient
from backend.agents.profiles.merger import ProfileMerger
from backend.agents.profiles.models import CongressMemberProfile
from backend.agents.profiles.generator import PersonaGenerator
from backend.app.utils.llm_client import LLMClient

async def test_build():
    logger.info('Testing agent build pipeline with 5 Senate members...\n')

    # Ensure directories exist
    AgentsConfig.ensure_directories_exist()

    # Initialize clients
    logger.info('Step 1: Initialize API clients')
    congress_client = CongressGovClient(
        api_key=AgentsConfig.CONGRESS_GOV_API_KEY,
        cache_dir=AgentsConfig.CACHE_DIR,
    )
    us_client = UnitedStatesProjectClient(cache_dir=AgentsConfig.CACHE_DIR)
    wiki_client = WikipediaClient(cache_dir=AgentsConfig.CACHE_DIR)
    voteview_client = VoteViewClient(cache_dir=AgentsConfig.CACHE_DIR)
    openfec_client = OpenFECClient(api_key=AgentsConfig.OPENFEC_API_KEY, cache_dir=AgentsConfig.CACHE_DIR)
    oyez_client = OyezClient(cache_dir=AgentsConfig.CACHE_DIR)

    # Get 5 Senate members
    logger.info('Step 2: Fetch Senate members from Congress.gov')
    members = await congress_client.get_members(congress=119, chamber='senate')
    if not members:
        logger.error('Failed to fetch Senate members')
        return False

    test_members = members[:5]
    logger.info(f'  Found {len(members)} Senate members, testing with first 5')
    for m in test_members:
        logger.info(f'    - {m.get("name")} ({m.get("bioguide_id")})')

    # Build merger
    logger.info('\nStep 3: Initialize merger')
    merger = ProfileMerger(
        us_api=us_client,
        congress_api=congress_client,
        voteview_api=voteview_client,
        openfec_api=openfec_client,
        wikipedia_api=wiki_client,
    )

    # Initialize persona generator
    logger.info('Step 4: Initialize persona generator')
    llm_client = LLMClient(
        base_url=AgentsConfig.LLM_BASE_URL,
        api_key=AgentsConfig.LLM_API_KEY,
        model=AgentsConfig.LLM_MODEL_NAME,
    )
    generator = PersonaGenerator(llm_client)

    # Merge and save each member
    logger.info('\nStep 5: Merge profiles and generate personas')
    count = 0
    for member in test_members:
        bioguide_id = member.get('bioguide_id')
        name = member.get('name')

        try:
            logger.info(f'  Processing {name}...')

            # Merge profile
            profile = merger.merge_congress_member(bioguide_id)
            if not profile:
                logger.warning(f'    Failed to merge {name}')
                continue

            # Generate persona
            persona = generator.generate_congress_member_persona(profile, force=False)
            if persona:
                profile.persona_narrative = persona
                logger.info(f'    Generated persona ({len(persona)} chars)')

            # Save to JSON
            output_dir = AgentsConfig.CONGRESS_SENATE_PERSONAS_DIR
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, f'{bioguide_id}.json')

            profile_dict = profile.dict()
            with open(output_path, 'w') as f:
                json.dump(profile_dict, f, indent=2, default=str)

            logger.info(f'    Saved to {output_path}')
            count += 1

        except Exception as e:
            logger.warning(f'    Error: {e}')

    logger.info(f'\n✓ Built {count}/{len(test_members)} profiles')
    return count > 0


if __name__ == '__main__':
    import asyncio
    success = asyncio.run(test_build())
    sys.exit(0 if success else 1)
