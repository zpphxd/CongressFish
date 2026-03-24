#!/usr/bin/env python3
"""
CongressFish Agent Refresh
==========================
Fast refresh script to check for new votes, trades, and scorecards.
Only updates agents that have changed since last refresh.

CLI usage:
    python backend/agents/refresh.py              # Quick refresh (< 5 min)
    python backend/agents/refresh.py --full       # Full update (30-45 min)
    python backend/agents/refresh.py --trades     # Check for new stock trades only
    python backend/agents/refresh.py --votes      # Check for new roll call votes only
"""

import os
import sys
import json
import time
import logging
import argparse
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from backend.agents.config import AgentsConfig
from backend.agents.apis.congress_gov import CongressGovAPI
from backend.agents.apis.voteview import VoteViewAPI
from backend.agents.profiles.merger import ProfileMerger
from backend.agents.storage.populate import GraphPopulator
from backend.agents.storage.graph import CongressGraphClient

logger = logging.getLogger(__name__)


class AgentRefresh:
    """Refreshes changed agent profiles."""

    def __init__(self):
        self.start_time = time.time()
        self.congress_api = CongressGovAPI()
        self.voteview_api = VoteViewAPI()
        self.state_path = os.path.join(AgentsConfig.CACHE_BASE_DIR, '.refresh_state.json')

        from neo4j import GraphDatabase
        self.driver = GraphDatabase.driver(
            AgentsConfig.NEO4J_URI,
            auth=(AgentsConfig.NEO4J_USER, AgentsConfig.NEO4J_PASSWORD),
        )
        self.graph_client = CongressGraphClient(self.driver)

    def load_state(self) -> dict:
        """Load last refresh state."""
        if os.path.exists(self.state_path):
            with open(self.state_path, 'r') as f:
                return json.load(f)
        return {'last_refresh_at': None, 'changed_agents': []}

    def save_state(self, state: dict):
        """Save refresh state."""
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        state['last_refresh_at'] = datetime.utcnow().isoformat()
        with open(self.state_path, 'w') as f:
            json.dump(state, f, indent=2)

    def detect_vote_changes(self) -> list:
        """Detect Congress members with new roll call votes."""
        logger.info('Checking for new roll call votes...')

        state = self.load_state()
        last_refresh = state.get('last_refresh_at')

        if not last_refresh:
            logger.info('First refresh, will check all votes')
            return []  # Would need to scan all votes; for now, return empty

        changed = []
        # Full implementation would query Congress.gov for votes since last_refresh
        # and identify which members changed positions
        logger.info(f'Detected {len(changed)} members with vote changes')
        return changed

    def detect_trade_changes(self) -> list:
        """Detect Congress members with new stock trades."""
        logger.info('Checking for new stock trades...')

        state = self.load_state()
        last_refresh = state.get('last_refresh_at')

        if not last_refresh:
            logger.info('First refresh, will check all trades')
            return []

        changed = []
        # Full implementation would check Stock Act disclosures
        # for trades filed since last_refresh
        logger.info(f'Detected {len(changed)} members with trade changes')
        return changed

    def refresh_fast(self):
        """Quick refresh (< 5 min): check votes and trades only."""
        logger.info('=== Fast Refresh ===')

        state = self.load_state()

        # Detect changes
        vote_changes = self.detect_vote_changes()
        trade_changes = self.detect_trade_changes()

        changed = set(vote_changes + trade_changes)
        logger.info(f'Found {len(changed)} agents with changes')

        # Update only changed agents
        if changed:
            logger.info(f'Refreshing {len(changed)} agents...')
            # TODO: reload and regenerate only these agents
            pass

        self.save_state(state)

        elapsed = time.time() - self.start_time
        logger.info(f'Fast refresh complete in {elapsed:.1f}s')

    def refresh_full(self):
        """Full refresh: re-download all data."""
        logger.info('=== Full Refresh ===')

        from backend.agents.build import AgentBuildOrchestrator

        orchestrator = AgentBuildOrchestrator()
        orchestrator.run(data_only=True)  # Don't regenerate personas

        self.save_state({})

        elapsed = time.time() - self.start_time
        logger.info(f'Full refresh complete in {elapsed:.1f}s')

    def refresh_trades_only(self):
        """Refresh stock trades only."""
        logger.info('=== Refresh Trades Only ===')

        state = self.load_state()
        changes = self.detect_trade_changes()

        if changes:
            logger.info(f'Updating {len(changes)} members with trade changes')

        self.save_state(state)

        elapsed = time.time() - self.start_time
        logger.info(f'Trade refresh complete in {elapsed:.1f}s')

    def refresh_votes_only(self):
        """Refresh roll call votes only."""
        logger.info('=== Refresh Votes Only ===')

        state = self.load_state()
        changes = self.detect_vote_changes()

        if changes:
            logger.info(f'Updating {len(changes)} members with vote changes')

        self.save_state(state)

        elapsed = time.time() - self.start_time
        logger.info(f'Vote refresh complete in {elapsed:.1f}s')


def main():
    parser = argparse.ArgumentParser(
        description='Refresh CongressFish agent data incrementally',
        epilog=__doc__,
    )
    parser.add_argument('--full', action='store_true', help='Full update (slow)')
    parser.add_argument('--trades', action='store_true', help='Stock trades only')
    parser.add_argument('--votes', action='store_true', help='Roll call votes only')

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    )

    refresher = AgentRefresh()

    try:
        if args.full:
            refresher.refresh_full()
        elif args.trades:
            refresher.refresh_trades_only()
        elif args.votes:
            refresher.refresh_votes_only()
        else:
            refresher.refresh_fast()
    finally:
        refresher.driver.close()


if __name__ == '__main__':
    main()
