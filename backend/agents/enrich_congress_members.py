#!/usr/bin/env python3
"""
Comprehensive Congress member enrichment orchestrator.

Enriches all 614 Congress member profiles with:
1. Wikipedia biographical data
2. VoteView ideology scores (DW-NOMINATE)
3. OpenFEC campaign finance data
4. Oyez data (if available)

Usage:
  python backend/agents/enrich_congress_members.py --all
  python backend/agents/enrich_congress_members.py --wikipedia
  python backend/agents/enrich_congress_members.py --ideology
  python backend/agents/enrich_congress_members.py --finance
"""

import os
import json
import asyncio
import logging
from pathlib import Path
from typing import Dict, Optional
import sys

sys.path.insert(0, os.path.dirname(__file__))

from backend.agents.config import AgentsConfig
from backend.agents.apis.wikipedia import WikipediaClient
from backend.agents.apis.voteview import VoteViewClient
from backend.agents.apis.openfec import OpenFecClient
from backend.agents.apis.unitedstates_project import UnitedStatesProjectClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CongressMemberEnricher:
    """Orchestrates enrichment of Congress member profiles."""

    def __init__(self):
        """Initialize enricher with all API clients."""
        self.senate_dir = Path(AgentsConfig.CONGRESS_SENATE_PERSONAS_DIR)
        self.house_dir = Path(AgentsConfig.CONGRESS_HOUSE_PERSONAS_DIR)

        self.wikipedia_client = WikipediaClient(
            cache_dir=os.path.join(AgentsConfig.CACHE_DIR, 'wikipedia')
        )
        self.voteview_client = VoteViewClient(
            cache_dir=os.path.join(AgentsConfig.CACHE_DIR, 'voteview')
        )
        self.openfec_client = OpenFecClient(
            api_key=AgentsConfig.OPENFEC_API_KEY,
            cache_dir=os.path.join(AgentsConfig.CACHE_DIR, 'openfec')
        )
        self.us_client = UnitedStatesProjectClient(
            cache_dir=os.path.join(AgentsConfig.CACHE_DIR, 'unitedstates')
        )

    def get_all_profiles(self) -> Dict[str, Path]:
        """Get all Senate and House member profiles."""
        profiles = {}
        for profile_file in self.senate_dir.glob('*.json'):
            profiles[profile_file.stem] = profile_file
        for profile_file in self.house_dir.glob('*.json'):
            profiles[profile_file.stem] = profile_file
        return profiles

    async def enrich_wikipedia(self) -> Dict:
        """Enrich profiles with Wikipedia biographical data."""
        logger.info('='*70)
        logger.info('ENRICHING WITH WIKIPEDIA')
        logger.info('='*70)

        profiles = self.get_all_profiles()
        stats = {'success': 0, 'failed': 0, 'skipped': 0}

        # Get Wikipedia ID mapping
        logger.info('Fetching Wikipedia ID mappings...')
        wiki_mapping = await self.us_client.get_wikipedia_ids()

        for i, (bioguide_id, profile_path) in enumerate(profiles.items(), 1):
            try:
                with open(profile_path, 'r') as f:
                    profile = json.load(f)

                wiki_id = wiki_mapping.get(bioguide_id)
                if not wiki_id:
                    stats['skipped'] += 1
                    continue

                # Fetch Wikipedia data
                wiki_data = await self.wikipedia_client.get_article_summary(wiki_id)
                if wiki_data:
                    if 'biography' not in profile:
                        profile['biography'] = {}
                    profile['biography']['wikipedia_summary'] = wiki_data.get('summary')
                    profile['biography']['wikipedia_full_text'] = wiki_data.get('full_text')
                    profile['ids']['wikipedia_id'] = wiki_id

                    # Save updated profile
                    with open(profile_path, 'w') as f:
                        json.dump(profile, f, indent=2)
                    stats['success'] += 1

                    if i % 50 == 0:
                        logger.info(f'  ({i}/{len(profiles)}) Processed Wikipedia data')
                else:
                    stats['failed'] += 1

            except Exception as e:
                logger.warning(f'Failed to enrich {bioguide_id} with Wikipedia: {e}')
                stats['failed'] += 1

        logger.info(f'Wikipedia enrichment: {stats["success"]} success, {stats["failed"]} failed, {stats["skipped"]} skipped')
        return stats

    async def enrich_ideology(self) -> Dict:
        """Enrich profiles with VoteView ideology scores."""
        logger.info('='*70)
        logger.info('ENRICHING WITH VOTEVIEW IDEOLOGY SCORES')
        logger.info('='*70)

        profiles = self.get_all_profiles()
        stats = {'success': 0, 'failed': 0}

        # Download VoteView data
        logger.info('Downloading VoteView ideology scores...')
        ideology_data = await self.voteview_client.get_members()

        if not ideology_data:
            logger.error('Failed to fetch VoteView data')
            return stats

        ideology_by_bioguide = {m.bioguide_id: m for m in ideology_data}

        for i, (bioguide_id, profile_path) in enumerate(profiles.items(), 1):
            try:
                with open(profile_path, 'r') as f:
                    profile = json.load(f)

                ideology = ideology_by_bioguide.get(bioguide_id)
                if ideology:
                    profile['ideology'] = {
                        'primary_dimension': ideology.dw_nominate_dim1,
                        'secondary_dimension': ideology.dw_nominate_dim2,
                        'source': 'VoteView',
                        'year': 2026
                    }

                    # Save updated profile
                    with open(profile_path, 'w') as f:
                        json.dump(profile, f, indent=2)
                    stats['success'] += 1

                    if i % 100 == 0:
                        logger.info(f'  ({i}/{len(profiles)}) Processed ideology scores')
                else:
                    stats['failed'] += 1

            except Exception as e:
                logger.warning(f'Failed to enrich {bioguide_id} with ideology: {e}')
                stats['failed'] += 1

        logger.info(f'Ideology enrichment: {stats["success"]} success, {stats["failed"]} failed')
        return stats

    async def enrich_campaign_finance(self) -> Dict:
        """Enrich profiles with OpenFEC campaign finance data."""
        logger.info('='*70)
        logger.info('ENRICHING WITH OPENFEC CAMPAIGN FINANCE')
        logger.info('='*70)

        if not AgentsConfig.OPENFEC_API_KEY:
            logger.warning('OPENFEC_API_KEY not set, skipping finance enrichment')
            return {'success': 0, 'failed': 0, 'skipped': 614}

        profiles = self.get_all_profiles()
        stats = {'success': 0, 'failed': 0, 'skipped': 0}

        for i, (bioguide_id, profile_path) in enumerate(profiles.items(), 1):
            try:
                with open(profile_path, 'r') as f:
                    profile = json.load(f)

                # Get FEC ID from cross-reference
                fec_id = profile.get('ids', {}).get('fec_id')
                if not fec_id:
                    # Try to fetch from OpenFEC
                    name = profile.get('full_name')
                    chamber = 'H' if profile.get('chamber') == 'house' else 'S'
                    state = profile.get('state')

                    candidate_info = await self.openfec_client.search_candidate(
                        name, chamber, state
                    )
                    if candidate_info:
                        fec_id = candidate_info.get('candidate_id')
                        profile['ids']['fec_id'] = fec_id

                if fec_id:
                    # Fetch candidate totals
                    totals = await self.openfec_client.get_candidate_totals(fec_id)
                    if totals:
                        profile['campaign_finance'] = {
                            'fec_id': fec_id,
                            'totals': {
                                'receipts': totals.get('receipts', 0),
                                'disbursements': totals.get('disbursements', 0),
                                'cash_on_hand': totals.get('cash_on_hand', 0),
                            }
                        }

                        # Fetch top donors
                        top_donors = await self.openfec_client.get_top_donors(fec_id, limit=10)
                        if top_donors:
                            profile['campaign_finance']['top_donors'] = top_donors

                        # Save updated profile
                        with open(profile_path, 'w') as f:
                            json.dump(profile, f, indent=2)
                        stats['success'] += 1
                    else:
                        stats['failed'] += 1
                else:
                    stats['skipped'] += 1

                if i % 100 == 0:
                    logger.info(f'  ({i}/{len(profiles)}) Processed campaign finance')

            except Exception as e:
                logger.warning(f'Failed to enrich {bioguide_id} with campaign finance: {e}')
                stats['failed'] += 1

        logger.info(f'Campaign finance enrichment: {stats["success"]} success, {stats["failed"]} failed, {stats["skipped"]} skipped')
        return stats

    async def enrich_all(self) -> Dict:
        """Enrich all profiles with all available data."""
        results = {
            'wikipedia': await self.enrich_wikipedia(),
            'ideology': await self.enrich_ideology(),
            'campaign_finance': await self.enrich_campaign_finance(),
        }
        return results


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Enrich Congress member profiles')
    parser.add_argument('--all', action='store_true', help='Enrich with all data sources')
    parser.add_argument('--wikipedia', action='store_true', help='Enrich with Wikipedia')
    parser.add_argument('--ideology', action='store_true', help='Enrich with ideology scores')
    parser.add_argument('--finance', action='store_true', help='Enrich with campaign finance')

    args = parser.parse_args()

    if not any([args.all, args.wikipedia, args.ideology, args.finance]):
        args.all = True

    enricher = CongressMemberEnricher()

    if args.all:
        results = await enricher.enrich_all()
    else:
        results = {}
        if args.wikipedia:
            results['wikipedia'] = await enricher.enrich_wikipedia()
        if args.ideology:
            results['ideology'] = await enricher.enrich_ideology()
        if args.finance:
            results['campaign_finance'] = await enricher.enrich_campaign_finance()

    logger.info('')
    logger.info('='*70)
    logger.info('ENRICHMENT COMPLETE')
    logger.info('='*70)
    for source, stats in results.items():
        logger.info(f'{source}: {stats}')


if __name__ == '__main__':
    asyncio.run(main())
