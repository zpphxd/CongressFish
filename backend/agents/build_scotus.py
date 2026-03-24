#!/usr/bin/env python3
"""
Build Supreme Court justice profiles from Oyez API.

Creates individual JSON profiles for all 9 current justices with:
- Basic information (name, appointment date, ideology)
- Biographical data
- Voting patterns and judicial alignment
- Cross-reference IDs

Usage:
  python backend/agents/build_scotus.py
"""

import os
import json
import asyncio
import logging
from pathlib import Path
from typing import Dict, List
import sys

sys.path.insert(0, os.path.dirname(__file__))

from backend.agents.config import AgentsConfig
from backend.agents.apis.oyez import OyezClient
from backend.agents.apis.wikipedia import WikipediaClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SCOTUSBuilder:
    """Builds Supreme Court justice profiles."""

    def __init__(self):
        """Initialize builder with API clients."""
        self.oyez_client = OyezClient(
            cache_dir=os.path.join(AgentsConfig.CACHE_DIR, 'oyez')
        )
        self.wikipedia_client = WikipediaClient(
            cache_dir=os.path.join(AgentsConfig.CACHE_DIR, 'wikipedia')
        )
        self.output_dir = Path(AgentsConfig.CONGRESS_SCOTUS_PERSONAS_DIR)
        os.makedirs(self.output_dir, exist_ok=True)

    async def build_all_justices(self) -> int:
        """Build profiles for all current justices."""
        logger.info('='*70)
        logger.info('BUILDING SCOTUS JUSTICE PROFILES')
        logger.info('='*70)

        # Get current justices
        logger.info('Fetching current justice list from Oyez...')
        justices = await self.oyez_client.get_current_justices()

        if not justices:
            logger.error('Failed to fetch justice list')
            return 0

        logger.info(f'Found {len(justices)} current justices\n')

        count = 0
        for i, justice_data in enumerate(justices, 1):
            try:
                justice_id = justice_data.get('id')
                name = justice_data.get('name', '')

                logger.info(f'  ({i}/{len(justices)}) Building profile for {name}...')

                # Fetch detailed justice information
                detail = await self.oyez_client.get_justice(justice_id)
                if not detail:
                    logger.warning(f'  ({i}/{len(justices)}) ✗ {name} - no detail found')
                    continue

                # Fetch voting patterns
                voting = await self.oyez_client.get_justice_voting_patterns(justice_id)

                # Fetch Wikipedia data if available
                wiki_summary = None
                wiki_id = detail.get('wikipedia_id')
                if wiki_id:
                    wiki_data = await self.wikipedia_client.get_article_summary(wiki_id)
                    if wiki_data:
                        wiki_summary = wiki_data.get('summary')

                # Create profile
                profile = {
                    'scotus_id': justice_id,
                    'full_name': name,
                    'first_name': name.split()[0] if ' ' in name else '',
                    'last_name': ' '.join(name.split()[1:]) if ' ' in name else name,
                    'title': 'Associate Justice' if name != 'Chief Justice John G. Roberts, Jr.' else 'Chief Justice',
                    'appointed_by': detail.get('appointed_by'),
                    'appointed_year': detail.get('appointed_year'),
                    'birth_year': detail.get('birth_year'),
                    'birth_place': detail.get('birth_place'),
                    'education': detail.get('education'),
                    'biography': {
                        'wikipedia_summary': wiki_summary,
                        'judicial_philosophy': detail.get('judicial_philosophy'),
                    },
                    'ideology': {
                        'primary_dimension': voting.get('avg_position') if voting else None,
                        'source': 'Oyez Voting Patterns',
                        'year': 2026,
                    },
                    'voting_patterns': voting,
                    'ids': {
                        'oyez_id': justice_id,
                        'wikipedia_id': wiki_id,
                    },
                }

                # Save profile
                output_path = self.output_dir / f'{justice_id}.json'
                with open(output_path, 'w') as f:
                    json.dump(profile, f, indent=2)

                logger.info(f'  ({i}/{len(justices)}) ✓ {name}')
                count += 1

            except Exception as e:
                logger.warning(f'  ({i}/{len(justices)}) ✗ Error: {e}')

        logger.info(f'\n✓ Built {count}/{len(justices)} justice profiles')
        return count


async def main():
    """Main entry point."""
    builder = SCOTUSBuilder()
    count = await builder.build_all_justices()

    logger.info('')
    logger.info('='*70)
    logger.info('SCOTUS BUILD COMPLETE')
    logger.info('='*70)
    logger.info(f'Total profiles: {count}')
    logger.info(f'Location: {builder.output_dir}')


if __name__ == '__main__':
    asyncio.run(main())
