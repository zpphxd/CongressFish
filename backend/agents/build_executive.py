#!/usr/bin/env python3
"""
Build executive branch profiles (President, VP, Cabinet).

Creates individual JSON profiles for current executive leadership with:
- Basic information
- Policy positions and ideology
- Biographical data
- Cross-reference IDs

Usage:
  python backend/agents/build_executive.py
"""

import os
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from backend.agents.config import AgentsConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ExecutiveBuilder:
    """Builds executive branch profiles."""

    # Current executive leadership (as of March 2026 - Trump administration)
    CURRENT_EXECUTIVES = [
        {
            'name': 'Donald Trump',
            'title': 'President',
            'role': 'president',
            'wikipedia_id': 'Donald_Trump',
            'ideology': 0.75,  # Strong conservative/populist
            'birth_year': 1946,
        },
        {
            'name': 'J.D. Vance',
            'title': 'Vice President',
            'role': 'vice_president',
            'wikipedia_id': 'J._D._Vance',
            'ideology': 0.70,  # Strong conservative
            'birth_year': 1984,
        },
        {
            'name': 'Marco Rubio',
            'title': 'Secretary of State',
            'role': 'cabinet',
            'wikipedia_id': 'Marco_Rubio',
            'ideology': 0.55,  # Conservative
            'birth_year': 1971,
        },
        {
            'name': 'Scott Bessent',
            'title': 'Secretary of the Treasury',
            'role': 'cabinet',
            'wikipedia_id': 'Scott_Bessent',
            'ideology': 0.50,  # Moderate conservative
            'birth_year': 1964,
        },
        {
            'name': 'Pete Hegseth',
            'title': 'Secretary of Defense',
            'role': 'cabinet',
            'wikipedia_id': 'Pete_Hegseth',
            'ideology': 0.70,  # Strong conservative
            'birth_year': 1983,
        },
        {
            'name': 'Pam Bondi',
            'title': 'Attorney General',
            'role': 'cabinet',
            'wikipedia_id': 'Pam_Bondi',
            'ideology': 0.65,  # Conservative
            'birth_year': 1965,
        },
        {
            'name': 'Doug Burgum',
            'title': 'Secretary of the Interior',
            'role': 'cabinet',
            'wikipedia_id': 'Doug_Burgum',
            'ideology': 0.60,  # Conservative
            'birth_year': 1959,
        },
        {
            'name': 'Markwayne Mullin',
            'title': 'Secretary of Homeland Security',
            'role': 'cabinet',
            'wikipedia_id': 'Markwayne_Mullin',
            'ideology': 0.70,  # Strong conservative
            'birth_year': 1977,
        },
    ]

    def __init__(self):
        """Initialize builder."""
        self.output_dir = Path(AgentsConfig.CONGRESS_EXECUTIVE_PERSONAS_DIR)
        os.makedirs(self.output_dir, exist_ok=True)

    async def build_all_executives(self) -> int:
        """Build profiles for all current executives."""
        logger.info('='*70)
        logger.info('BUILDING EXECUTIVE BRANCH PROFILES')
        logger.info('='*70)

        logger.info(f'Found {len(self.CURRENT_EXECUTIVES)} executive officials\n')

        count = 0
        for i, exec_data in enumerate(self.CURRENT_EXECUTIVES, 1):
            try:
                name = exec_data['name']
                title = exec_data['title']
                wikipedia_id = exec_data.get('wikipedia_id')

                logger.info(f'  ({i}/{len(self.CURRENT_EXECUTIVES)}) Building profile for {name} ({title})...')

                # Create profile
                profile = {
                    'executive_id': name.lower().replace(' ', '_'),
                    'full_name': name,
                    'first_name': name.split()[0] if ' ' in name else '',
                    'last_name': ' '.join(name.split()[1:]) if ' ' in name else name,
                    'title': title,
                    'role': exec_data.get('role'),
                    'birth_year': exec_data.get('birth_year'),
                    'biography': {
                        'wikipedia_summary': None,
                    },
                    'ideology': {
                        'primary_dimension': exec_data.get('ideology'),
                        'source': 'Political Analysis',
                        'year': 2026,
                    },
                    'policy_positions': {
                        'estimated_alignment': exec_data.get('ideology'),
                    },
                    'ids': {
                        'wikipedia_id': wikipedia_id,
                    },
                    'created_at': datetime.utcnow().isoformat(),
                }

                # Save profile
                output_path = self.output_dir / f'{profile["executive_id"]}.json'
                with open(output_path, 'w') as f:
                    json.dump(profile, f, indent=2)

                logger.info(f'  ({i}/{len(self.CURRENT_EXECUTIVES)}) ✓ {name}')
                count += 1

            except Exception as e:
                logger.warning(f'  ({i}/{len(self.CURRENT_EXECUTIVES)}) ✗ Error: {e}')

        logger.info(f'\n✓ Built {count}/{len(self.CURRENT_EXECUTIVES)} executive profiles')
        return count


async def main():
    """Main entry point."""
    builder = ExecutiveBuilder()
    count = await builder.build_all_executives()

    logger.info('')
    logger.info('='*70)
    logger.info('EXECUTIVE BUILD COMPLETE')
    logger.info('='*70)
    logger.info(f'Total profiles: {count}')
    logger.info(f'Location: {builder.output_dir}')


if __name__ == '__main__':
    asyncio.run(main())
