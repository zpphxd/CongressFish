#!/usr/bin/env python3
"""
Enrich all Congress member profiles with committee assignments.

Uses unitedstates-project YAML data which has complete committee membership data.
This enriches both Senate and House profiles with their committee assignments.
"""

import os
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from collections import defaultdict

import sys
sys.path.insert(0, os.path.dirname(__file__))

from backend.agents.config import AgentsConfig
from backend.agents.apis.unitedstates_project import UnitedStatesProjectClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CommitteeEnricher:
    """Enriches all Congress member profiles with committee assignments."""

    def __init__(self):
        """Initialize the enricher."""
        self.us_client = UnitedStatesProjectClient(
            cache_dir=os.path.join(AgentsConfig.CACHE_DIR, 'unitedstates'),
        )

        self.senate_dir = Path(AgentsConfig.CONGRESS_SENATE_PERSONAS_DIR)
        self.house_dir = Path(AgentsConfig.CONGRESS_HOUSE_PERSONAS_DIR)

        if not self.senate_dir.exists():
            raise ValueError(f'Senate personas directory not found: {self.senate_dir}')
        if not self.house_dir.exists():
            raise ValueError(f'House personas directory not found: {self.house_dir}')

        logger.info(f'Senate profiles directory: {self.senate_dir}')
        logger.info(f'House profiles directory: {self.house_dir}')

    async def enrich_all(self) -> Dict:
        """Enrich all Congress member profiles with committee assignments."""

        # Download committee memberships from unitedstates
        logger.info('Fetching committee memberships from unitedstates-project...')
        try:
            memberships = await self.us_client.get_committee_memberships()
        except Exception as e:
            logger.error(f'Failed to fetch committee memberships: {e}')
            return {
                'total': 0,
                'senate': {'success': 0, 'failed': 0},
                'house': {'success': 0, 'failed': 0},
            }

        logger.info(f'Retrieved {len(memberships)} committees')

        # Build bioguide -> committees mapping
        bioguide_to_committees = defaultdict(list)
        for committee_code, members in memberships.items():
            if not isinstance(members, list):
                continue

            for member in members:
                bioguide_id = member.get('bioguide')
                if not bioguide_id:
                    continue

                # Normalize committee assignment
                assignment = {
                    'code': committee_code,
                    'title': member.get('title', 'Member'),
                    'rank': member.get('rank'),
                    'party': member.get('party'),  # 'majority' or 'minority'
                }
                bioguide_to_committees[bioguide_id].append(assignment)

        logger.info(f'Built committee mapping for {len(bioguide_to_committees)} members')

        # Enrich Senate profiles
        logger.info('Enriching Senate profiles...')
        senate_stats = await self._enrich_chamber(
            self.senate_dir, bioguide_to_committees, 'senate'
        )

        # Enrich House profiles
        logger.info('Enriching House profiles...')
        house_stats = await self._enrich_chamber(
            self.house_dir, bioguide_to_committees, 'house'
        )

        return {
            'total': senate_stats['success'] + house_stats['success'],
            'senate': senate_stats,
            'house': house_stats,
            'total_committees_assigned': sum(
                len(v) for v in bioguide_to_committees.values()
            ),
            'unique_committees': len(memberships),
        }

    async def _enrich_chamber(self, chamber_dir: Path, bioguide_to_committees: Dict,
                              chamber_name: str) -> Dict:
        """Enrich all profiles in a chamber directory."""

        profile_files = list(chamber_dir.glob('*.json'))
        logger.info(f'Found {len(profile_files)} {chamber_name} profiles')

        stats = {'success': 0, 'failed': 0, 'enriched_with_committees': 0}

        for profile_path in profile_files:
            try:
                with open(profile_path, 'r') as f:
                    profile = json.load(f)

                bioguide_id = profile.get('bioguide_id')
                if not bioguide_id:
                    logger.warning(f'No bioguide_id in {profile_path.name}')
                    stats['failed'] += 1
                    continue

                # Get committees for this member
                committees = bioguide_to_committees.get(bioguide_id, [])

                # Update profile
                profile['committee_assignments'] = committees
                profile['updated_at'] = datetime.utcnow().isoformat()

                # Save back
                with open(profile_path, 'w') as f:
                    json.dump(profile, f, indent=2)

                if committees:
                    logger.debug(f'{profile.get("full_name")} ({bioguide_id}): {len(committees)} committees')
                    stats['enriched_with_committees'] += 1

                stats['success'] += 1

            except Exception as e:
                logger.warning(f'Failed to enrich {profile_path.name}: {e}')
                stats['failed'] += 1

        logger.info(f'{chamber_name.upper()}: {stats["success"]} processed, '
                   f'{stats["enriched_with_committees"]} with committees, '
                   f'{stats["failed"]} failed')

        return stats


async def main():
    """Main entry point."""
    logger.info('='*70)
    logger.info('COMMITTEE ENRICHMENT')
    logger.info('='*70)
    logger.info('')

    try:
        enricher = CommitteeEnricher()
        results = await enricher.enrich_all()

        logger.info('')
        logger.info('='*70)
        logger.info('ENRICHMENT COMPLETE')
        logger.info('='*70)
        logger.info(f'Total members enriched: {results["total"]}')
        logger.info(f'Senate: {results["senate"]["success"]} success, {results["senate"]["failed"]} failed')
        logger.info(f'House: {results["house"]["success"]} success, {results["house"]["failed"]} failed')
        logger.info(f'Total committee assignments: {results.get("total_committees_assigned", 0)}')
        logger.info(f'Unique committees: {results.get("unique_committees", 0)}')
        logger.info('='*70)

        return results['total'] > 0

    except Exception as e:
        logger.error(f'Fatal error: {e}', exc_info=True)
        return False


if __name__ == '__main__':
    success = asyncio.run(main())
    exit(0 if success else 1)
