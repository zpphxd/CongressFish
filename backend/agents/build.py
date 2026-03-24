#!/usr/bin/env python3
"""
CongressFish Agent Build Orchestrator
======================================
Master script to download data, merge profiles, generate personas, and populate Neo4j.

CLI usage:
    python backend/agents/build.py --full              # Full Congress + SCOTUS + Executive + Orgs
    python backend/agents/build.py --senate-only       # Senate members only (test)
    python backend/agents/build.py --house-only        # House members only
    python backend/agents/build.py --data-only         # Download data, no persona generation
    python backend/agents/build.py --personas-only     # Generate personas for existing profiles
    python backend/agents/build.py --refresh           # Update changed agents only (fast)
    python backend/agents/build.py --limit 10          # Limit members processed (for testing)
    python backend/agents/build.py --force-personas    # Regenerate all personas (slow)
"""

import os
import sys
import json
import time
import logging
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from backend.agents.config import AgentsConfig
from backend.agents.apis.unitedstates_project import UnitedStatesProjectClient
from backend.agents.apis.congress_gov import CongressGovClient
from backend.agents.apis.voteview import VoteViewClient
from backend.agents.apis.openfec import OpenFECClient
from backend.agents.apis.wikipedia import WikipediaClient
from backend.agents.apis.oyez import OyezClient
from backend.agents.profiles.merger import ProfileMerger
from backend.agents.profiles.generator import PersonaGenerator
from backend.agents.storage.populate import GraphPopulator
from backend.agents.storage.graph import CongressGraphClient
from backend.app.utils.llm_client import LLMClient

logger = logging.getLogger(__name__)


class AgentBuildOrchestrator:
    """Orchestrates the full agent build pipeline."""

    def __init__(self, chamber: Optional[str] = None, limit: Optional[int] = None, force_personas: bool = False):
        """
        Args:
            chamber: 'house', 'senate', or None for both
            limit: Maximum agents to process (for testing)
            force_personas: Regenerate personas even if they exist
        """
        self.chamber = chamber
        self.limit = limit
        self.force_personas = force_personas
        self.start_time = time.time()

        # Initialize API clients
        logger.info('Initializing API clients...')
        self.us_api = UnitedStatesProjectClient()
        self.congress_api = CongressGovClient()
        self.voteview_api = VoteViewClient()
        self.openfec_api = OpenFECClient()
        self.wikipedia_api = WikipediaClient()
        self.oyez_api = OyezClient()

        # Initialize LLM for persona generation
        self.llm_client = LLMClient(
            base_url=AgentsConfig.LLM_BASE_URL,
            api_key=AgentsConfig.LLM_API_KEY,
            model_name=AgentsConfig.LLM_MODEL_NAME,
        )
        self.persona_generator = PersonaGenerator(self.llm_client)

        # Initialize Neo4j
        from neo4j import GraphDatabase
        self.driver = GraphDatabase.driver(
            AgentsConfig.NEO4J_URI,
            auth=(AgentsConfig.NEO4J_USER, AgentsConfig.NEO4J_PASSWORD),
        )
        self.graph_client = CongressGraphClient(self.driver)

        # Initialize merger
        self.merger = ProfileMerger(
            us_api=self.us_api,
            congress_api=self.congress_api,
            voteview_api=self.voteview_api,
            openfec_api=self.openfec_api,
            wikipedia_api=self.wikipedia_api,
        )

    def build_congress_members(self, data_only: bool = False) -> int:
        """
        Download, merge, and save Congress member profiles.

        Args:
            data_only: If True, skip persona generation

        Returns:
            Number of members processed
        """
        logger.info('=== Building Congress Member Profiles ===')

        # Get member list from Congress.gov
        members_list = self.congress_api.get_members_list(chamber=self.chamber)
        if not members_list:
            logger.error('Failed to fetch members list')
            return 0

        if self.limit:
            members_list = members_list[:self.limit]

        logger.info(f'Processing {len(members_list)} members...')

        count = 0
        for member_data in members_list:
            try:
                bioguide_id = member_data.get('bioguide_id')
                full_name = member_data.get('name')

                logger.debug(f'Processing {full_name} ({bioguide_id})...')

                # Merge data from all sources
                profile = self.merger.merge_congress_member(bioguide_id)
                if not profile:
                    logger.warning(f'Failed to merge profile for {full_name}')
                    continue

                # Generate persona if not data_only
                if not data_only:
                    persona_text = self.persona_generator.generate_congress_member_persona(
                        profile,
                        force=self.force_personas,
                    )
                    if persona_text:
                        profile.persona_narrative = persona_text

                # Save profile JSON
                self._save_profile(profile, 'congress')

                count += 1
                if count % 10 == 0:
                    elapsed = time.time() - self.start_time
                    logger.info(f'Processed {count}/{len(members_list)} members ({elapsed:.1f}s)')

            except Exception as e:
                logger.warning(f'Failed to process {full_name}: {e}')

        logger.info(f'Total Congress members processed: {count}')
        return count

    def build_scotus_justices(self, data_only: bool = False) -> int:
        """Build SCOTUS justice profiles."""
        logger.info('=== Building SCOTUS Justice Profiles ===')

        try:
            justices = self.oyez_api.get_justices()
            if not justices:
                logger.warning('No justices fetched')
                return 0

            count = 0
            for justice_data in justices:
                try:
                    name = justice_data.get('name')
                    logger.debug(f'Processing Justice {name}...')

                    # Merge data
                    profile = self.merger.merge_justice(justice_data)
                    if not profile:
                        logger.warning(f'Failed to merge profile for {name}')
                        continue

                    # Generate persona
                    if not data_only:
                        persona_text = self.persona_generator.generate_justice_persona(
                            profile,
                            force=self.force_personas,
                        )
                        if persona_text:
                            profile.persona_narrative = persona_text

                    # Save
                    self._save_profile(profile, 'scotus')
                    count += 1

                except Exception as e:
                    logger.warning(f'Failed to process justice {name}: {e}')

            logger.info(f'Total justices processed: {count}')
            return count

        except Exception as e:
            logger.error(f'Failed to build SCOTUS justices: {e}')
            return 0

    def build_executive_officials(self, data_only: bool = False) -> int:
        """Build Executive branch official profiles."""
        logger.info('=== Building Executive Official Profiles ===')

        # For now, just load from manual data if available
        # Full integration would require Federal Register API
        logger.info('Executive profiles require manual data input (Federal Register API pending)')
        return 0

    def build_influence_organizations(self, data_only: bool = False) -> int:
        """Build influence organization profiles."""
        logger.info('=== Building Influence Organization Profiles ===')

        # For now, just load from OpenFEC PAC data if available
        # Full integration would require comprehensive lobbying data scraping
        logger.info('Influence org profiles require OpenFEC PAC data integration (pending)')
        return 0

    def populate_graph(self) -> bool:
        """Populate Neo4j graph with all profiles."""
        logger.info('=== Populating Neo4j Graph ===')

        try:
            # Ensure schema
            self.graph_client.ensure_schema()

            # Create populator
            populator = GraphPopulator(self.graph_client, AgentsConfig.PERSONAS_BASE_DIR)

            # Populate
            member_count = populator.populate_congress_members(
                chamber=self.chamber,
                limit=self.limit,
            )
            justice_count = populator.populate_justices()

            # Build relationships
            populator.build_voting_alignment_network(chamber=self.chamber)
            populator.build_cosponsorship_network()

            # Verify
            stats = populator.verify_graph_integrity()

            logger.info(f'Graph population complete: {member_count} members, {justice_count} justices')
            return True

        except Exception as e:
            logger.error(f'Failed to populate graph: {e}')
            return False

    def _save_profile(self, profile, profile_type: str):
        """Save profile as JSON."""
        try:
            if profile_type == 'congress':
                # Determine chamber directory
                chamber_dir = AgentsConfig.CONGRESS_HOUSE_PERSONAS_DIR
                if hasattr(profile, 'chamber'):
                    if profile.chamber.value == 'senate':
                        chamber_dir = AgentsConfig.CONGRESS_SENATE_PERSONAS_DIR

                output_path = os.path.join(chamber_dir, f'{profile.bioguide_id}.json')

            elif profile_type == 'scotus':
                output_path = os.path.join(AgentsConfig.SCOTUS_PERSONAS_DIR, f'{profile.oyez_id}.json')

            elif profile_type == 'executive':
                output_path = os.path.join(AgentsConfig.EXECUTIVE_PERSONAS_DIR, f'{profile.full_name.replace(" ", "_")}.json')

            elif profile_type == 'influence':
                output_path = os.path.join(AgentsConfig.INFLUENCE_PERSONAS_DIR, f'{profile.name.replace(" ", "_")}.json')

            else:
                logger.warning(f'Unknown profile type: {profile_type}')
                return

            # Ensure directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            # Convert to dict and save
            profile_dict = profile.dict()
            with open(output_path, 'w') as f:
                json.dump(profile_dict, f, indent=2, default=str)

            logger.debug(f'Saved profile to {output_path}')

        except Exception as e:
            logger.warning(f'Failed to save profile: {e}')

    def run(self, full: bool = False, data_only: bool = False, personas_only: bool = False, refresh: bool = False):
        """Execute build process."""
        try:
            if refresh:
                logger.info('=== Refresh Mode ===')
                self._refresh_changed_agents()

            elif personas_only:
                logger.info('=== Persona Generation Only ===')
                self._generate_personas_for_existing_profiles()

            elif data_only:
                logger.info('=== Data Download Only (No Persona Generation) ===')
                self.build_congress_members(data_only=True)
                self.build_scotus_justices(data_only=True)

            elif full:
                logger.info('=== Full Build ===')
                self.build_congress_members()
                self.build_scotus_justices()
                self.build_executive_officials()
                self.build_influence_organizations()
                self.populate_graph()

            else:
                logger.info('=== Default: Congress Members Only ===')
                self.build_congress_members()
                self.populate_graph()

            elapsed = time.time() - self.start_time
            logger.info(f'\nBuild complete in {elapsed:.1f}s')

        except Exception as e:
            logger.error(f'Build failed: {e}', exc_info=True)

        finally:
            self.driver.close()

    def _refresh_changed_agents(self):
        """Update only changed agents (fast)."""
        logger.info('Checking for changed agents...')
        # Load last refresh timestamp
        refresh_state_path = os.path.join(AgentsConfig.CACHE_BASE_DIR, '.refresh_state.json')
        if os.path.exists(refresh_state_path):
            with open(refresh_state_path, 'r') as f:
                state = json.load(f)
                last_refresh = state.get('last_refresh_at')
                logger.info(f'Last refresh: {last_refresh}')
        else:
            logger.info('No prior refresh found, will scan all agents')

        # For now, just rebuild all
        # Full implementation would check for new votes, trades, etc.
        self.build_congress_members(data_only=True)

        # Update state
        os.makedirs(os.path.dirname(refresh_state_path), exist_ok=True)
        with open(refresh_state_path, 'w') as f:
            json.dump({'last_refresh_at': datetime.utcnow().isoformat()}, f)

    def _generate_personas_for_existing_profiles(self):
        """Generate personas for all existing profile JSONs."""
        logger.info('Generating personas for existing profiles...')

        count = 0
        for chamber in ['house', 'senate']:
            chamber_dir = (
                AgentsConfig.CONGRESS_HOUSE_PERSONAS_DIR
                if chamber == 'house'
                else AgentsConfig.CONGRESS_SENATE_PERSONAS_DIR
            )

            if not os.path.exists(chamber_dir):
                logger.warning(f'Directory not found: {chamber_dir}')
                continue

            for json_file in Path(chamber_dir).glob('*.json'):
                try:
                    with open(json_file, 'r') as f:
                        profile_dict = json.load(f)

                    # Import profile model
                    from backend.agents.profiles.models import CongressMemberProfile
                    profile = CongressMemberProfile(**profile_dict)

                    # Generate persona
                    persona_text = self.persona_generator.generate_congress_member_persona(
                        profile,
                        force=True,
                    )

                    if persona_text:
                        profile.persona_narrative = persona_text
                        self._save_profile(profile, 'congress')
                        count += 1

                except Exception as e:
                    logger.warning(f'Failed to process {json_file}: {e}')

        logger.info(f'Generated personas for {count} profiles')


def main():
    parser = argparse.ArgumentParser(
        description='Build CongressFish agent profiles and populate Neo4j graph',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument('--full', action='store_true', help='Full build (Congress, SCOTUS, Executive, Orgs)')
    parser.add_argument('--senate-only', action='store_true', help='Senate members only (test mode)')
    parser.add_argument('--house-only', action='store_true', help='House members only')
    parser.add_argument('--data-only', action='store_true', help='Download data, no persona generation')
    parser.add_argument('--personas-only', action='store_true', help='Generate personas for existing profiles')
    parser.add_argument('--refresh', action='store_true', help='Update changed agents only')
    parser.add_argument('--limit', type=int, help='Limit number of agents processed')
    parser.add_argument('--force-personas', action='store_true', help='Regenerate all personas')

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    )

    # Determine chamber
    chamber = None
    if args.senate_only:
        chamber = 'senate'
    elif args.house_only:
        chamber = 'house'

    # Create orchestrator
    orchestrator = AgentBuildOrchestrator(
        chamber=chamber,
        limit=args.limit,
        force_personas=args.force_personas,
    )

    # Run
    orchestrator.run(
        full=args.full,
        data_only=args.data_only,
        personas_only=args.personas_only,
        refresh=args.refresh,
    )


if __name__ == '__main__':
    main()
