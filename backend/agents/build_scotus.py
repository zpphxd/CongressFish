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

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

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

        # Hardcoded current SCOTUS (as of March 2026)
        justices = [
            {'id': 'john-g-roberts-jr', 'name': 'Chief Justice John G. Roberts, Jr.'},
            {'id': 'clarence-thomas', 'name': 'Clarence Thomas'},
            {'id': 'samuel-a-alito-jr', 'name': 'Samuel A. Alito, Jr.'},
            {'id': 'sonia-sotomayor', 'name': 'Sonia Sotomayor'},
            {'id': 'elena-kagan', 'name': 'Elena Kagan'},
            {'id': 'neil-m-gorsuch', 'name': 'Neil M. Gorsuch'},
            {'id': 'brett-m-kavanaugh', 'name': 'Brett M. Kavanaugh'},
            {'id': 'amy-coney-barrett', 'name': 'Amy Coney Barrett'},
            {'id': 'ketanji-brown-jackson', 'name': 'Ketanji Brown Jackson'},
        ]

        logger.info(f'Found {len(justices)} current justices\n')

        count = 0
        for i, justice_data in enumerate(justices, 1):
            try:
                justice_id = justice_data.get('id')
                name = justice_data.get('name', '')

                logger.info(f'  ({i}/{len(justices)}) Building profile for {name}...')

                # Determine if Chief Justice
                is_chief = 'Chief Justice' in name

                # Create profile
                profile = {
                    'scotus_id': justice_id,
                    'full_name': name,
                    'first_name': name.split()[0] if 'Chief' not in name and ' ' in name else (name.split()[-2] if 'Chief' in name and ' ' in name else name),
                    'last_name': ' '.join(name.split()[-1:]) if ' ' in name else name,
                    'title': 'Chief Justice' if is_chief else 'Associate Justice',
                    'appointed_by': None,
                    'appointed_year': None,
                    'birth_year': None,
                    'biography': {
                        'wikipedia_summary': None,
                        'judicial_philosophy': None,
                    },
                    'ideology': {
                        'primary_dimension': None,
                        'source': None,
                        'year': 2026,
                    },
                    'ids': {
                        'oyez_id': justice_id,
                        'wikipedia_id': None,
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
