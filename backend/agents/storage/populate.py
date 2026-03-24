"""
Neo4j Graph Population
======================
Populates graph with CongressFish agent nodes and relationships.

CLI usage:
    python populate.py --full              # Build entire graph (Congress, SCOTUS, Executive, Orgs)
    python populate.py --senate-only       # Build Senate members only (test mode)
    python populate.py --data-only         # Load data, no persona generation
    python populate.py --personas-only     # Generate personas for existing profiles
    python populate.py --refresh           # Update only changed agents
"""

import os
import json
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class GraphPopulator:
    """Populates Neo4j graph from CongressFish profiles."""

    def __init__(self, graph_client, profiles_dir: str):
        """
        Args:
            graph_client: CongressGraphClient instance
            profiles_dir: Directory containing profile JSON files
        """
        self.graph_client = graph_client
        self.profiles_dir = profiles_dir

    def populate_congress_members(
        self,
        chamber: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> int:
        """
        Load Congress member profiles and populate graph.

        Args:
            chamber: 'house' or 'senate', None for both
            limit: Maximum members to load

        Returns:
            Number of members loaded
        """
        members_dir = os.path.join(self.profiles_dir, 'congress')
        if chamber:
            members_dir = os.path.join(members_dir, chamber)

        if not os.path.exists(members_dir):
            logger.warning(f'Members directory not found: {members_dir}')
            return 0

        count = 0
        for json_file in Path(members_dir).glob('*.json'):
            try:
                with open(json_file, 'r') as f:
                    profile = json.load(f)

                # Create Member node
                self.graph_client.create_member(profile)

                # Create party relationship
                self.graph_client.create_member_party_relationship(
                    profile['bioguide_id'],
                    profile['party']
                )

                # Create committee relationships
                for committee in profile.get('committee_assignments', []):
                    self.graph_client.create_committee(
                        {
                            'code': committee.get('committee_code'),
                            'name': committee.get('committee_name'),
                            'chamber': committee.get('chamber'),
                        }
                    )
                    self.graph_client.create_committee_service(
                        profile['bioguide_id'],
                        committee.get('committee_code'),
                        rank=committee.get('rank'),
                        is_chair=committee.get('is_chair', False),
                    )

                count += 1
                if limit and count >= limit:
                    break

                if count % 50 == 0:
                    logger.info(f'Loaded {count} members...')

            except Exception as e:
                logger.warning(f'Failed to load {json_file}: {e}')

        logger.info(f'Total members loaded: {count}')
        return count

    def populate_justices(self) -> int:
        """Load SCOTUS justice profiles and populate graph."""
        justices_dir = os.path.join(self.profiles_dir, 'scotus')

        if not os.path.exists(justices_dir):
            logger.warning(f'Justices directory not found: {justices_dir}')
            return 0

        count = 0
        for json_file in Path(justices_dir).glob('*.json'):
            try:
                with open(json_file, 'r') as f:
                    profile = json.load(f)

                self.graph_client.create_justice(profile)
                count += 1

            except Exception as e:
                logger.warning(f'Failed to load {json_file}: {e}')

        logger.info(f'Total justices loaded: {count}')
        return count

    def populate_influence_orgs(self) -> int:
        """Load influence organization profiles and populate graph."""
        orgs_dir = os.path.join(self.profiles_dir, 'influence')

        if not os.path.exists(orgs_dir):
            logger.info(f'Influence orgs directory not found: {orgs_dir}')
            return 0

        count = 0
        for json_file in Path(orgs_dir).glob('*.json'):
            try:
                with open(json_file, 'r') as f:
                    profile = json.load(f)

                self.graph_client.create_organization(profile)
                count += 1

            except Exception as e:
                logger.warning(f'Failed to load {json_file}: {e}')

        logger.info(f'Total organizations loaded: {count}')
        return count

    def build_cosponsorship_network(self) -> int:
        """Build cosponsorship relationships from Congress member profiles."""
        logger.info('Building cosponsorship network...')

        members_dir = os.path.join(self.profiles_dir, 'congress')
        count = 0

        member_profiles = {}
        for chamber in ['house', 'senate']:
            chamber_dir = os.path.join(members_dir, chamber)
            for json_file in Path(chamber_dir).glob('*.json'):
                try:
                    with open(json_file, 'r') as f:
                        profile = json.load(f)
                        bioguide_id = profile['bioguide_id']
                        member_profiles[bioguide_id] = profile
                except Exception as e:
                    logger.warning(f'Failed to load {json_file}: {e}')

        # Build cosponsorship relationships
        # This would require bill/cosponsorship data from Congress.gov
        # For now, just log that this is pending actual bill data
        logger.info(f'Cosponsorship network building requires bill-level data (pending)')

        return count

    def build_voting_alignment_network(self, chamber: Optional[str] = None) -> int:
        """Build voting alignment relationships from VoteView data."""
        logger.info(f'Building voting alignment network (chamber={chamber})...')

        members_dir = os.path.join(self.profiles_dir, 'congress')
        count = 0

        # Load profiles and extract voting alignment data
        if chamber:
            search_dir = os.path.join(members_dir, chamber)
        else:
            search_dir = members_dir

        for json_file in Path(search_dir).rglob('*.json'):
            try:
                with open(json_file, 'r') as f:
                    profile = json.load(f)
                    bioguide_id = profile['bioguide_id']

                    # Create voting alignment relationships from profile data
                    for other_id, agreement_pct in profile.get('voting_alignment_with_others', {}).items():
                        self.graph_client.create_voting_alignment(
                            bioguide_id,
                            other_id,
                            agreement_pct,
                        )
                        count += 1

            except Exception as e:
                logger.warning(f'Failed to process {json_file}: {e}')

        logger.info(f'Total voting alignment relationships created: {count}')
        return count

    def verify_graph_integrity(self) -> Dict:
        """Check graph statistics and report integrity."""
        stats = {
            'member_count': self.graph_client.get_member_count(),
            'justice_count': self.graph_client.get_justice_count(),
            'serves_on_count': self.graph_client.get_relationship_count('SERVES_ON'),
            'votes_with_count': self.graph_client.get_relationship_count('VOTES_WITH'),
            'party_member_count': self.graph_client.get_relationship_count('PARTY_MEMBER'),
        }

        logger.info(f'\n=== Graph Integrity Report ===')
        logger.info(f'Members: {stats["member_count"]}')
        logger.info(f'Justices: {stats["justice_count"]}')
        logger.info(f'SERVES_ON relationships: {stats["serves_on_count"]}')
        logger.info(f'VOTES_WITH relationships: {stats["votes_with_count"]}')
        logger.info(f'PARTY_MEMBER relationships: {stats["party_member_count"]}')

        return stats


def main():
    """CLI for graph population."""
    parser = argparse.ArgumentParser(
        description='Populate Neo4j graph with CongressFish profiles'
    )
    parser.add_argument(
        '--full',
        action='store_true',
        help='Build entire graph (Congress, SCOTUS, Executive, Orgs)',
    )
    parser.add_argument(
        '--senate-only',
        action='store_true',
        help='Build Senate members only (test mode)',
    )
    parser.add_argument(
        '--house-only',
        action='store_true',
        help='Build House members only',
    )
    parser.add_argument(
        '--data-only',
        action='store_true',
        help='Load data, no persona generation',
    )
    parser.add_argument(
        '--personas-only',
        action='store_true',
        help='Generate personas for existing profiles',
    )
    parser.add_argument(
        '--refresh',
        action='store_true',
        help='Update only changed agents',
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Maximum members to load',
    )

    args = parser.parse_args()

    # Initialize Neo4j client
    from neo4j import GraphDatabase
    from backend.agents.config import AgentsConfig
    from .graph import CongressGraphClient

    driver = GraphDatabase.driver(
        AgentsConfig.NEO4J_URI,
        auth=(AgentsConfig.NEO4J_USER, AgentsConfig.NEO4J_PASSWORD),
    )

    graph_client = CongressGraphClient(driver)

    # Ensure schema exists
    logger.info('Creating graph schema...')
    graph_client.ensure_schema()

    # Determine profiles directory
    profiles_dir = os.path.join(
        os.path.dirname(__file__), '../../..', 'backend', 'agents', 'personas'
    )

    populator = GraphPopulator(graph_client, profiles_dir)

    # Execute based on flags
    if args.full:
        logger.info('=== Full Graph Population ===')
        members = populator.populate_congress_members()
        justices = populator.populate_justices()
        orgs = populator.populate_influence_orgs()
        populator.build_voting_alignment_network()
        populator.verify_graph_integrity()

    elif args.senate_only:
        logger.info('=== Senate-Only Population (Test Mode) ===')
        members = populator.populate_congress_members(chamber='senate', limit=args.limit)
        populator.build_voting_alignment_network(chamber='senate')
        populator.verify_graph_integrity()

    elif args.house_only:
        logger.info('=== House-Only Population ===')
        members = populator.populate_congress_members(chamber='house', limit=args.limit)
        populator.build_voting_alignment_network(chamber='house')
        populator.verify_graph_integrity()

    else:
        logger.info('Specify --full, --senate-only, --house-only, --data-only, --personas-only, or --refresh')

    driver.close()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
