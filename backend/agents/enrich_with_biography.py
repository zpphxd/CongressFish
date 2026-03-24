#!/usr/bin/env python3
"""
Enrich Congress member profiles with biographical data from Wikipedia and Ballotpedia.

This script:
1. For each of 614 Congress members, fetch Wikipedia biography (via full_name search)
2. Parse Wikipedia extract, birth date, birth place, education, occupation
3. Enrich profile biography fields with fetched data
4. Cache results to avoid re-scraping

Usage:
  python backend/agents/enrich_with_biography.py
"""

import os
import json
import logging
import asyncio
from pathlib import Path
from typing import Dict, Optional, List
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from backend.agents.apis.wikipedia import WikipediaClient
from backend.agents.apis.ballotpedia import BallotpediaClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('enrichment_biography.log')
    ]
)
logger = logging.getLogger(__name__)


class BiographyEnricher:
    """Enriches Congress member profiles with biographical data."""

    def __init__(self, project_root: str):
        """Initialize paths and API clients."""
        self.project_root = project_root
        self.congress_dir = os.path.join(project_root, 'backend', 'agents', 'personas', 'congress')

        # Cache directories for API clients
        wiki_cache = os.path.join(project_root, 'backend', 'agents', 'cache', 'wikipedia')
        ballotpedia_cache = os.path.join(project_root, 'backend', 'agents', 'cache', 'ballotpedia')

        self.wikipedia_client = WikipediaClient(wiki_cache)
        self.ballotpedia_cache = ballotpedia_cache
        os.makedirs(self.ballotpedia_cache, exist_ok=True)

    async def fetch_biography(self, full_name: str, state: str, chamber: str) -> Optional[Dict]:
        """
        Fetch biographical data from Wikipedia.

        Args:
            full_name: Full name (e.g., "Robert B. Aderholt")
            state: State name (e.g., "ALABAMA")
            chamber: Chamber (e.g., "house" or "senate")

        Returns:
            Dict with biography fields or None if not found
        """
        try:
            # Try Wikipedia first with full name as the search term
            # Wikipedia typically uses "FirstName_LastName" format
            wiki_search = full_name.replace(' ', '_')

            bio_data = await self.wikipedia_client.get_biography(wiki_search)

            if not bio_data:
                logger.debug(f'{full_name}: Wikipedia article not found')
                return None

            # Extract relevant fields for BiographicalData
            return {
                'birth_date': bio_data.get('birth_date'),
                'birth_place': bio_data.get('birth_place'),
                'education': bio_data.get('education'),
                'occupation': bio_data.get('occupation'),
                'wikipedia_summary': bio_data.get('extract'),
                'wikipedia_full_text': bio_data.get('full_text'),
            }

        except Exception as e:
            logger.warning(f'{full_name}: Error fetching biography: {e}')
            return None

    async def enrich_profile(self, profile: Dict) -> Optional[Dict]:
        """
        Enrich a single Congress member profile with biographical data.

        Args:
            profile: Congress member profile dict

        Returns:
            Updated profile or None if enrichment failed
        """
        full_name = profile.get('full_name')
        state = profile.get('state')
        chamber = profile.get('chamber')
        bioguide_id = profile.get('bioguide_id')

        if not full_name or not state or not chamber:
            logger.warning(f'{bioguide_id}: Missing required fields, skipping')
            return None

        # Fetch biography data
        bio_data = await self.fetch_biography(full_name, state, chamber)

        if not bio_data:
            logger.debug(f'{bioguide_id} ({full_name}): No biography data found')
            return None

        # Merge into profile
        if not profile.get('biography'):
            profile['biography'] = {}

        for key, value in bio_data.items():
            if value:  # Only set non-None values
                profile['biography'][key] = value

        return profile

    async def enrich_all(self, max_concurrent: int = 3):
        """
        Enrich all Congress member profiles with biographical data.

        Args:
            max_concurrent: Maximum concurrent Wikipedia requests (be respectful)
        """
        logger.info('Starting biography enrichment pipeline')

        # Find all Congress member profile files
        profiles_to_enrich = []
        for chamber_dir in [
            os.path.join(self.congress_dir, 'house'),
            os.path.join(self.congress_dir, 'senate')
        ]:
            if os.path.exists(chamber_dir):
                profiles_to_enrich.extend(Path(chamber_dir).glob('*.json'))

        logger.info(f'Found {len(profiles_to_enrich)} Congress member profiles')

        # Enrich with concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)
        profiles_updated = 0
        profiles_not_found = 0

        async def bounded_enrich(profile_path):
            async with semaphore:
                try:
                    with open(profile_path, 'r') as f:
                        profile = json.load(f)

                    bioguide = profile.get('bioguide_id')
                    updated_profile = await self.enrich_profile(profile)

                    if updated_profile:
                        # Save updated profile
                        with open(profile_path, 'w') as f:
                            json.dump(updated_profile, f, indent=2)
                        return (True, bioguide)
                    else:
                        return (False, bioguide)

                except Exception as e:
                    logger.error(f'Error processing {profile_path}: {e}')
                    return (False, None)

        # Process all profiles concurrently
        tasks = [bounded_enrich(p) for p in profiles_to_enrich]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.error(f'Batch processing error: {result}')
                continue

            success, bioguide = result
            if success:
                profiles_updated += 1
            else:
                profiles_not_found += 1

            if (profiles_updated + profiles_not_found) % 50 == 0:
                logger.info(f'Processed {profiles_updated + profiles_not_found} profiles...')

        logger.info(f'Enrichment complete: {profiles_updated} updated, {profiles_not_found} not found')
        return profiles_updated, profiles_not_found


async def main():
    """Main entry point."""
    enricher = BiographyEnricher(project_root)
    updated, not_found = await enricher.enrich_all(max_concurrent=3)

    if updated == 0:
        logger.warning('No profiles were updated. Wikipedia data may not be available.')
    else:
        logger.info(f'Success: {updated} Congress member profiles enriched with biographical data')


if __name__ == '__main__':
    asyncio.run(main())
