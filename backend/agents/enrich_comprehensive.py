#!/usr/bin/env python3
"""
Comprehensive Congress member enrichment using multiple data sources.

Enriches Congress member profiles with:
1. VoteView ideology scores (DW-NOMINATE)
2. OpenFEC campaign finance data
3. Ballotpedia biographical data (birth, education, occupation)

Usage:
  python backend/agents/enrich_comprehensive.py --all
  python backend/agents/enrich_comprehensive.py --ideology
  python backend/agents/enrich_comprehensive.py --finance
  python backend/agents/enrich_comprehensive.py --biography
"""

import os
import json
import asyncio
import logging
from pathlib import Path
from typing import Dict, Optional
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from backend.agents.config import AgentsConfig
from backend.agents.apis.voteview import VoteViewClient
from backend.agents.apis.openfec import OpenFECClient
from backend.agents.apis.ballotpedia import BallotpediaClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ComprehensiveEnricher:
    """Orchestrates comprehensive Congress member enrichment."""

    def __init__(self):
        """Initialize with all API clients."""
        self.senate_dir = Path(AgentsConfig.CONGRESS_SENATE_PERSONAS_DIR)
        self.house_dir = Path(AgentsConfig.CONGRESS_HOUSE_PERSONAS_DIR)

        self.voteview_client = VoteViewClient(
            cache_dir=os.path.join(AgentsConfig.CACHE_DIR, 'voteview')
        )
        self.openfec_client = OpenFECClient(
            api_key=AgentsConfig.OPENFEC_API_KEY,
            cache_dir=os.path.join(AgentsConfig.CACHE_DIR, 'openfec')
        )
        self.ballotpedia_client = BallotpediaClient(
            cache_dir=os.path.join(AgentsConfig.CACHE_DIR, 'ballotpedia')
        )

    def get_all_profiles(self) -> Dict[str, Path]:
        """Get all Senate and House member profiles."""
        profiles = {}
        for profile_file in self.senate_dir.glob('*.json'):
            profiles[profile_file.stem] = profile_file
        for profile_file in self.house_dir.glob('*.json'):
            profiles[profile_file.stem] = profile_file
        return profiles

    async def enrich_ideology(self) -> Dict:
        """Enrich profiles with VoteView ideology scores."""
        logger.info('='*70)
        logger.info('ENRICHING WITH VOTEVIEW IDEOLOGY SCORES')
        logger.info('='*70)

        profiles = self.get_all_profiles()
        stats = {'success': 0, 'failed': 0}

        # Download VoteView data
        logger.info('Downloading VoteView ideology scores...')
        ideology_data = await self.voteview_client.get_members_119th_congress()

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

    async def enrich_biography(self) -> Dict:
        """Enrich profiles with Ballotpedia biographical data."""
        logger.info('='*70)
        logger.info('ENRICHING WITH BALLOTPEDIA BIOGRAPHICAL DATA')
        logger.info('='*70)

        profiles = self.get_all_profiles()
        stats = {'success': 0, 'failed': 0, 'skipped': 0}

        async with BallotpediaClient(
            cache_dir=os.path.join(AgentsConfig.CACHE_DIR, 'ballotpedia')
        ) as client:
            for i, (bioguide_id, profile_path) in enumerate(profiles.items(), 1):
                try:
                    with open(profile_path, 'r') as f:
                        profile = json.load(f)

                    name = profile.get('full_name')
                    state = profile.get('state')
                    chamber = profile.get('chamber')

                    if not name or not state or not chamber:
                        stats['skipped'] += 1
                        continue

                    # Fetch from Ballotpedia
                    bio_data = await client.get_member_profile(name, state, chamber)
                    if bio_data:
                        # Update biography section
                        if 'biography' not in profile:
                            profile['biography'] = {}

                        profile['biography'].update({
                            'birth_date': bio_data.get('birth_date'),
                            'birthplace': bio_data.get('birthplace'),
                            'education': bio_data.get('education'),
                            'occupation': bio_data.get('occupation'),
                            'religion': bio_data.get('religion'),
                        })

                        # Save updated profile
                        with open(profile_path, 'w') as f:
                            json.dump(profile, f, indent=2)
                        stats['success'] += 1

                        if i % 50 == 0:
                            logger.info(f'  ({i}/{len(profiles)}) Processed biographical data')
                    else:
                        stats['failed'] += 1

                except Exception as e:
                    logger.warning(f'Failed to enrich {bioguide_id} with biography: {e}')
                    stats['failed'] += 1

        logger.info(f'Biography enrichment: {stats["success"]} success, {stats["failed"]} failed, {stats["skipped"]} skipped')
        return stats

    async def enrich_all(self) -> Dict:
        """Enrich all profiles with all available data."""
        results = {
            'ideology': await self.enrich_ideology(),
            'campaign_finance': await self.enrich_campaign_finance(),
            'biography': await self.enrich_biography(),
        }
        return results


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Enrich Congress member profiles comprehensively')
    parser.add_argument('--all', action='store_true', help='Enrich with all data sources')
    parser.add_argument('--ideology', action='store_true', help='Enrich with ideology scores')
    parser.add_argument('--finance', action='store_true', help='Enrich with campaign finance')
    parser.add_argument('--biography', action='store_true', help='Enrich with biographical data')

    args = parser.parse_args()

    if not any([args.all, args.ideology, args.finance, args.biography]):
        args.all = True

    enricher = ComprehensiveEnricher()

    if args.all:
        results = await enricher.enrich_all()
    else:
        results = {}
        if args.ideology:
            results['ideology'] = await enricher.enrich_ideology()
        if args.finance:
            results['campaign_finance'] = await enricher.enrich_campaign_finance()
        if args.biography:
            results['biography'] = await enricher.enrich_biography()

    logger.info('')
    logger.info('='*70)
    logger.info('ENRICHMENT COMPLETE')
    logger.info('='*70)
    for source, stats in results.items():
        logger.info(f'{source}: {stats}')


if __name__ == '__main__':
    asyncio.run(main())
