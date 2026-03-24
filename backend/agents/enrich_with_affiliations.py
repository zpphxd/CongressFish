#!/usr/bin/env python3
"""
Enrich government agent profiles with group affiliations.

Adds group affiliations (committees, caucuses, party) to all government agents:
- Congress members
- SCOTUS justices
- Executive branch officials

This is a simplified version that uses profile data to infer affiliations.

Usage:
  python backend/agents/enrich_with_affiliations.py --all
  python backend/agents/enrich_with_affiliations.py --congress
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from backend.agents.config import AgentsConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AffiliationEnricher:
    """Enriches government agents with group affiliations."""

    @staticmethod
    def enrich_congress_profile(profile: Dict) -> Dict:
        """Enrich a Congress member profile with group affiliations."""
        if 'affiliations' not in profile:
            profile['affiliations'] = []

        # Add party affiliation
        party_map = {'R': 'Republican Party', 'D': 'Democratic Party', 'I': 'Independent'}
        party = profile.get('party')
        if party:
            party_name = party_map.get(party, party)
            profile['affiliations'].append(f"Party: {party_name}")

        # Add committees from committee_assignments
        committees = profile.get('committee_assignments', [])
        for committee in committees:
            code = committee.get('code')
            title = committee.get('title')
            if code:
                # Add committee affiliation
                affil = f"Committee: {code}"
                if title and title != 'Member':
                    affil += f" ({title})"
                if affil not in profile['affiliations']:
                    profile['affiliations'].append(affil)

        # Add chamber affiliation
        chamber = profile.get('chamber')
        if chamber == 'senate':
            profile['affiliations'].append("Chamber: United States Senate")
        elif chamber == 'house':
            profile['affiliations'].append("Chamber: House of Representatives")

        return profile

    @staticmethod
    def enrich_scotus_profile(profile: Dict) -> Dict:
        """Enrich a SCOTUS justice profile with group affiliations."""
        if 'affiliations' not in profile:
            profile['affiliations'] = []

        # Add SCOTUS affiliation
        profile['affiliations'].append("Institution: Supreme Court of the United States")

        # Add title as affiliation
        title = profile.get('title')
        if title:
            profile['affiliations'].append(f"Position: {title}")

        return profile

    @staticmethod
    def enrich_executive_profile(profile: Dict) -> Dict:
        """Enrich an executive profile with group affiliations."""
        if 'affiliations' not in profile:
            profile['affiliations'] = []

        # Add executive branch affiliation
        profile['affiliations'].append("Branch: Executive Branch")

        # Add role affiliation
        role = profile.get('role')
        title = profile.get('title')
        if role:
            profile['affiliations'].append(f"Role: {title or role}")

        return profile

    def enrich_congress(self) -> Dict:
        """Enrich all Congress member profiles with affiliations."""
        logger.info('='*70)
        logger.info('ENRICHING CONGRESS WITH AFFILIATIONS')
        logger.info('='*70)

        senate_dir = Path(AgentsConfig.CONGRESS_SENATE_PERSONAS_DIR)
        house_dir = Path(AgentsConfig.CONGRESS_HOUSE_PERSONAS_DIR)

        stats = {'senate': 0, 'house': 0, 'failed': 0}

        # Senate
        logger.info('Enriching Senate...')
        for profile_file in senate_dir.glob('*.json'):
            try:
                with open(profile_file, 'r') as f:
                    profile = json.load(f)

                profile = self.enrich_congress_profile(profile)

                with open(profile_file, 'w') as f:
                    json.dump(profile, f, indent=2)

                stats['senate'] += 1
            except Exception as e:
                logger.warning(f'Failed to enrich {profile_file.name}: {e}')
                stats['failed'] += 1

        # House
        logger.info('Enriching House...')
        for profile_file in house_dir.glob('*.json'):
            try:
                with open(profile_file, 'r') as f:
                    profile = json.load(f)

                profile = self.enrich_congress_profile(profile)

                with open(profile_file, 'w') as f:
                    json.dump(profile, f, indent=2)

                stats['house'] += 1
            except Exception as e:
                logger.warning(f'Failed to enrich {profile_file.name}: {e}')
                stats['failed'] += 1

        logger.info(f'Congress: {stats["senate"] + stats["house"]} enriched, {stats["failed"]} failed')
        return stats

    def enrich_scotus(self) -> Dict:
        """Enrich all SCOTUS justice profiles with affiliations."""
        logger.info('='*70)
        logger.info('ENRICHING SCOTUS WITH AFFILIATIONS')
        logger.info('='*70)

        scotus_dir = Path(AgentsConfig.CONGRESS_SCOTUS_PERSONAS_DIR)
        stats = {'success': 0, 'failed': 0}

        for profile_file in scotus_dir.glob('*.json'):
            try:
                with open(profile_file, 'r') as f:
                    profile = json.load(f)

                profile = self.enrich_scotus_profile(profile)

                with open(profile_file, 'w') as f:
                    json.dump(profile, f, indent=2)

                stats['success'] += 1
            except Exception as e:
                logger.warning(f'Failed to enrich {profile_file.name}: {e}')
                stats['failed'] += 1

        logger.info(f'SCOTUS: {stats["success"]} enriched, {stats["failed"]} failed')
        return stats

    def enrich_executive(self) -> Dict:
        """Enrich all executive branch profiles with affiliations."""
        logger.info('='*70)
        logger.info('ENRICHING EXECUTIVE WITH AFFILIATIONS')
        logger.info('='*70)

        exec_dir = Path(AgentsConfig.CONGRESS_EXECUTIVE_PERSONAS_DIR)
        stats = {'success': 0, 'failed': 0}

        for profile_file in exec_dir.glob('*.json'):
            try:
                with open(profile_file, 'r') as f:
                    profile = json.load(f)

                profile = self.enrich_executive_profile(profile)

                with open(profile_file, 'w') as f:
                    json.dump(profile, f, indent=2)

                stats['success'] += 1
            except Exception as e:
                logger.warning(f'Failed to enrich {profile_file.name}: {e}')
                stats['failed'] += 1

        logger.info(f'Executive: {stats["success"]} enriched, {stats["failed"]} failed')
        return stats

    def enrich_all(self) -> Dict:
        """Enrich all government agents with affiliations."""
        congress_stats = self.enrich_congress()
        scotus_stats = self.enrich_scotus()
        exec_stats = self.enrich_executive()

        return {
            'congress': congress_stats,
            'scotus': scotus_stats,
            'executive': exec_stats,
        }


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Enrich government agents with affiliations')
    parser.add_argument('--all', action='store_true', help='Enrich all branches')
    parser.add_argument('--congress', action='store_true', help='Enrich Congress')
    parser.add_argument('--scotus', action='store_true', help='Enrich SCOTUS')
    parser.add_argument('--executive', action='store_true', help='Enrich executive')

    args = parser.parse_args()

    if not any([args.all, args.congress, args.scotus, args.executive]):
        args.all = True

    enricher = AffiliationEnricher()

    if args.all:
        results = enricher.enrich_all()
    else:
        results = {}
        if args.congress:
            results['congress'] = enricher.enrich_congress()
        if args.scotus:
            results['scotus'] = enricher.enrich_scotus()
        if args.executive:
            results['executive'] = enricher.enrich_executive()

    logger.info('')
    logger.info('='*70)
    logger.info('AFFILIATION ENRICHMENT COMPLETE')
    logger.info('='*70)
    for branch, stats in results.items():
        if isinstance(stats, dict):
            for key, val in stats.items():
                if isinstance(val, int):
                    continue
                logger.info(f'{branch}: {val}')


if __name__ == '__main__':
    main()
