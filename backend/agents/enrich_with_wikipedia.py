#!/usr/bin/env python3
"""
Enrich all government agent profiles with Wikipedia biographical data.

Pulls Wikipedia data for:
- Congress members (Senate + House)
- SCOTUS justices
- Executive branch officials

Extracts and normalizes biographical information and group affiliations.

Usage:
  python backend/agents/enrich_with_wikipedia.py --all
  python backend/agents/enrich_with_wikipedia.py --congress
  python backend/agents/enrich_with_wikipedia.py --scotus
  python backend/agents/enrich_with_wikipedia.py --executive
"""

import os
import json
import asyncio
import logging
from pathlib import Path
from typing import Dict, Optional, List
import sys
import re

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from backend.agents.config import AgentsConfig
from backend.agents.apis.wikipedia import WikipediaClient
from backend.agents.apis.unitedstates_project import UnitedStatesProjectClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WikipediaEnricher:
    """Enriches government agent profiles with Wikipedia data."""

    def __init__(self):
        """Initialize enricher with API clients."""
        self.wikipedia_client = WikipediaClient(
            cache_dir=os.path.join(AgentsConfig.CACHE_DIR, 'wikipedia')
        )
        self.us_client = UnitedStatesProjectClient(
            cache_dir=os.path.join(AgentsConfig.CACHE_DIR, 'unitedstates')
        )

    def extract_affiliations_from_text(self, text: str) -> List[str]:
        """
        Extract likely group affiliations from Wikipedia text.

        Looks for mentions of:
        - Committees
        - Caucuses
        - Party affiliations
        - Organizations
        """
        affiliations = []

        if not text:
            return affiliations

        # Committee mentions
        committee_pattern = r'(?:Committee|Subcommittee|Chair|Ranking Member)\s+(?:on\s+)?([A-Za-z\s&,]+?)(?:\.|,|;|\band\b)'
        for match in re.finditer(committee_pattern, text, re.IGNORECASE):
            affil = match.group(1).strip()
            if affil and len(affil) > 3:
                affiliations.append(f"Committee: {affil}")

        # Caucus mentions
        caucus_pattern = r'([A-Za-z\s]+?)\s+Caucus'
        for match in re.finditer(caucus_pattern, text, re.IGNORECASE):
            affil = match.group(1).strip()
            if affil and len(affil) > 2:
                affiliations.append(f"Caucus: {affil}")

        # Party mentions
        party_pattern = r'(Democratic|Republican|Independent|Green Party)\s+(?:Party\s+)?(?:member|politician)'
        for match in re.finditer(party_pattern, text, re.IGNORECASE):
            affiliations.append(f"Party: {match.group(1)}")

        return list(set(affiliations))  # Remove duplicates

    async def enrich_congress(self) -> Dict:
        """Enrich Congress member profiles with Wikipedia data."""
        logger.info('='*70)
        logger.info('ENRICHING CONGRESS MEMBERS WITH WIKIPEDIA')
        logger.info('='*70)

        senate_dir = Path(AgentsConfig.CONGRESS_SENATE_PERSONAS_DIR)
        house_dir = Path(AgentsConfig.CONGRESS_HOUSE_PERSONAS_DIR)

        stats = {'senate': {'success': 0, 'failed': 0}, 'house': {'success': 0, 'failed': 0}}

        # Get Wikipedia ID mapping
        logger.info('Fetching Wikipedia ID mappings...')
        try:
            wiki_mapping = await self.us_client.get_wikipedia_ids()
        except:
            logger.warning('Could not fetch Wikipedia ID mapping, will skip Congress enrichment')
            return stats

        # Process Senate
        logger.info('Enriching Senate profiles...')
        for profile_file in senate_dir.glob('*.json'):
            success = await self._enrich_profile(profile_file, wiki_mapping)
            stats['senate']['success' if success else 'failed'] += 1

        # Process House
        logger.info('Enriching House profiles...')
        for profile_file in house_dir.glob('*.json'):
            success = await self._enrich_profile(profile_file, wiki_mapping)
            stats['house']['success' if success else 'failed'] += 1

        return stats

    async def _enrich_profile(self, profile_path: Path, wiki_mapping: Dict) -> bool:
        """Enrich a single profile with Wikipedia data."""
        try:
            with open(profile_path, 'r') as f:
                profile = json.load(f)

            bioguide_id = profile.get('bioguide_id')
            if not bioguide_id:
                return False

            # Get Wikipedia ID
            wiki_id = wiki_mapping.get(bioguide_id)
            if not wiki_id:
                return False

            # Fetch Wikipedia data
            wiki_data = await self.wikipedia_client.get_biography(wiki_id)
            if not wiki_data:
                return False

            # Update profile
            if 'biography' not in profile:
                profile['biography'] = {}

            profile['biography']['wikipedia_summary'] = wiki_data.get('extract')
            profile['biography']['wikipedia_full_text'] = wiki_data.get('full_text')
            profile['ids']['wikipedia_id'] = wiki_id

            # Extract affiliations from Wikipedia text
            full_text = wiki_data.get('full_text', '')
            affiliations = self.extract_affiliations_from_text(full_text)
            if affiliations:
                profile['affiliations'] = affiliations

            # Save updated profile
            with open(profile_path, 'w') as f:
                json.dump(profile, f, indent=2)

            return True

        except Exception as e:
            logger.debug(f'Failed to enrich {profile_path.name}: {e}')
            return False

    async def enrich_scotus(self) -> Dict:
        """Enrich SCOTUS justice profiles with Wikipedia data."""
        logger.info('='*70)
        logger.info('ENRICHING SCOTUS WITH WIKIPEDIA')
        logger.info('='*70)

        scotus_dir = Path(AgentsConfig.CONGRESS_SCOTUS_PERSONAS_DIR)
        stats = {'success': 0, 'failed': 0}

        # SCOTUS Wikipedia IDs (hardcoded mapping)
        scotus_mapping = {
            'john-g-roberts-jr': 'John_G._Roberts,_Jr.',
            'clarence-thomas': 'Clarence_Thomas',
            'samuel-a-alito-jr': 'Samuel_Alito',
            'sonia-sotomayor': 'Sonia_Sotomayor',
            'elena-kagan': 'Elena_Kagan',
            'neil-m-gorsuch': 'Neil_Gorsuch',
            'brett-m-kavanaugh': 'Brett_Kavanaugh',
            'amy-coney-barrett': 'Amy_Coney_Barrett',
            'ketanji-brown-jackson': 'Ketanji_Brown_Jackson',
        }

        for profile_file in scotus_dir.glob('*.json'):
            try:
                with open(profile_file, 'r') as f:
                    profile = json.load(f)

                scotus_id = profile.get('scotus_id')
                wiki_id = scotus_mapping.get(scotus_id)

                if not wiki_id:
                    stats['failed'] += 1
                    continue

                # Fetch Wikipedia data
                wiki_data = await self.wikipedia_client.get_biography(wiki_id)
                if not wiki_data:
                    stats['failed'] += 1
                    continue

                # Update profile
                profile['biography']['wikipedia_summary'] = wiki_data.get('extract')
                profile['ids']['wikipedia_id'] = wiki_id

                # Extract affiliations
                full_text = wiki_data.get('full_text', '')
                affiliations = self.extract_affiliations_from_text(full_text)
                if affiliations:
                    profile['affiliations'] = affiliations

                # Save updated profile
                with open(profile_file, 'w') as f:
                    json.dump(profile, f, indent=2)

                stats['success'] += 1

            except Exception as e:
                logger.debug(f'Failed to enrich {profile_file.name}: {e}')
                stats['failed'] += 1

        return stats

    async def enrich_executive(self) -> Dict:
        """Enrich executive branch profiles with Wikipedia data."""
        logger.info('='*70)
        logger.info('ENRICHING EXECUTIVE WITH WIKIPEDIA')
        logger.info('='*70)

        exec_dir = Path(AgentsConfig.CONGRESS_EXECUTIVE_PERSONAS_DIR)
        stats = {'success': 0, 'failed': 0}

        # Executive Wikipedia IDs mapping
        exec_mapping = {
            'joe_biden': 'Joe_Biden',
            'kamala_harris': 'Kamala_Harris',
            'marco_rubio': 'Marco_Rubio',
            'pete_hegseth': 'Pete_Hegseth',
            'kristi_noem': 'Kristi_Noem',
            'scott_bessent': 'Scott_Bessent',
        }

        for profile_file in exec_dir.glob('*.json'):
            try:
                with open(profile_file, 'r') as f:
                    profile = json.load(f)

                exec_id = profile_file.stem
                wiki_id = exec_mapping.get(exec_id)

                if not wiki_id:
                    stats['failed'] += 1
                    continue

                # Fetch Wikipedia data
                wiki_data = await self.wikipedia_client.get_biography(wiki_id)
                if not wiki_data:
                    stats['failed'] += 1
                    continue

                # Update profile
                profile['biography']['wikipedia_summary'] = wiki_data.get('extract')
                profile['ids']['wikipedia_id'] = wiki_id

                # Extract affiliations
                full_text = wiki_data.get('full_text', '')
                affiliations = self.extract_affiliations_from_text(full_text)
                if affiliations:
                    profile['affiliations'] = affiliations

                # Save updated profile
                with open(profile_file, 'w') as f:
                    json.dump(profile, f, indent=2)

                stats['success'] += 1

            except Exception as e:
                logger.debug(f'Failed to enrich {profile_file.name}: {e}')
                stats['failed'] += 1

        return stats

    async def enrich_all(self) -> Dict:
        """Enrich all government agents with Wikipedia data."""
        results = {
            'congress': await self.enrich_congress(),
            'scotus': await self.enrich_scotus(),
            'executive': await self.enrich_executive(),
        }
        return results


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Enrich government agents with Wikipedia data')
    parser.add_argument('--all', action='store_true', help='Enrich all branches')
    parser.add_argument('--congress', action='store_true', help='Enrich Congress members')
    parser.add_argument('--scotus', action='store_true', help='Enrich SCOTUS justices')
    parser.add_argument('--executive', action='store_true', help='Enrich executive branch')

    args = parser.parse_args()

    if not any([args.all, args.congress, args.scotus, args.executive]):
        args.all = True

    enricher = WikipediaEnricher()

    if args.all:
        results = await enricher.enrich_all()
    else:
        results = {}
        if args.congress:
            results['congress'] = await enricher.enrich_congress()
        if args.scotus:
            results['scotus'] = await enricher.enrich_scotus()
        if args.executive:
            results['executive'] = await enricher.enrich_executive()

    logger.info('')
    logger.info('='*70)
    logger.info('WIKIPEDIA ENRICHMENT COMPLETE')
    logger.info('='*70)
    for branch, stats in results.items():
        if isinstance(stats, dict) and 'success' in stats:
            logger.info(f'{branch}: {stats["success"]} success, {stats["failed"]} failed')
        elif isinstance(stats, dict):
            for key, val in stats.items():
                logger.info(f'{branch}/{key}: {val["success"]} success, {val["failed"]} failed')


if __name__ == '__main__':
    asyncio.run(main())
