#!/usr/bin/env python3
"""
Master agent builder orchestrator.

Builds and enriches all agent profiles:
- 614 Congress members (112 Senate + 502 House)
- 9 Supreme Court justices
- 6 Executive branch officials

Usage:
  python backend/agents/orchestrator.py --all
  python backend/agents/orchestrator.py --congress --scotus --executive
  python backend/agents/orchestrator.py --enrich-congress
"""

import os
import sys
import subprocess
import logging
from pathlib import Path
import argparse
from typing import Dict

sys.path.insert(0, os.path.dirname(__file__))

from backend.agents.config import AgentsConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AgentBuildOrchestrator:
    """Orchestrates building and enriching all agent profiles."""

    def __init__(self):
        """Initialize orchestrator."""
        self.script_dir = Path(__file__).parent
        AgentsConfig.ensure_directories_exist()

    def run_script(self, script_name: str, args: list = None) -> bool:
        """Run a Python script and return success status."""
        if args is None:
            args = []

        script_path = self.script_dir / script_name
        if not script_path.exists():
            logger.error(f'Script not found: {script_path}')
            return False

        logger.info(f'Running: python {script_name} {" ".join(args)}')
        try:
            result = subprocess.run(
                [sys.executable, str(script_path)] + args,
                check=True,
                cwd=str(self.script_dir.parent.parent.parent),
            )
            return result.returncode == 0
        except subprocess.CalledProcessError as e:
            logger.error(f'Script failed: {script_name} (exit code {e.returncode})')
            return False
        except Exception as e:
            logger.error(f'Error running script: {e}')
            return False

    def build_congress(self) -> bool:
        """Build Congress member profiles."""
        logger.info('='*70)
        logger.info('BUILDING CONGRESS MEMBERS')
        logger.info('='*70)

        success = self.run_script('build_smart.py', ['--chamber', 'senate'])
        success = self.run_script('build_smart.py', ['--chamber', 'house']) and success
        return success

    def enrich_congress(self) -> bool:
        """Enrich Congress member profiles with external data."""
        logger.info('='*70)
        logger.info('ENRICHING CONGRESS MEMBERS')
        logger.info('='*70)

        success = self.run_script('enrich_all_committees.py', [])
        success = self.run_script('enrich_congress_members.py', ['--all']) and success
        return success

    def build_scotus(self) -> bool:
        """Build SCOTUS justice profiles."""
        logger.info('='*70)
        logger.info('BUILDING SCOTUS PROFILES')
        logger.info('='*70)

        return self.run_script('build_scotus.py', [])

    def build_executive(self) -> bool:
        """Build executive branch profiles."""
        logger.info('='*70)
        logger.info('BUILDING EXECUTIVE PROFILES')
        logger.info('='*70)

        return self.run_script('build_executive.py', [])

    def build_all(self) -> bool:
        """Build all agent profiles."""
        success = True

        logger.info('')
        logger.info('START: BUILDING ALL AGENTS')
        logger.info('')

        success = self.build_congress() and success
        success = self.enrich_congress() and success
        success = self.build_scotus() and success
        success = self.build_executive() and success

        return success

    def verify_builds(self) -> Dict:
        """Verify that all profiles were built successfully."""
        logger.info('='*70)
        logger.info('VERIFYING BUILDS')
        logger.info('='*70)

        results = {
            'congress_senate': len(list(Path(AgentsConfig.CONGRESS_SENATE_PERSONAS_DIR).glob('*.json'))),
            'congress_house': len(list(Path(AgentsConfig.CONGRESS_HOUSE_PERSONAS_DIR).glob('*.json'))),
            'scotus': len(list(Path(AgentsConfig.CONGRESS_SCOTUS_PERSONAS_DIR).glob('*.json'))),
            'executive': len(list(Path(AgentsConfig.CONGRESS_EXECUTIVE_PERSONAS_DIR).glob('*.json'))),
        }

        logger.info(f'Congress Senate: {results["congress_senate"]} profiles')
        logger.info(f'Congress House: {results["congress_house"]} profiles')
        logger.info(f'SCOTUS: {results["scotus"]} profiles')
        logger.info(f'Executive: {results["executive"]} profiles')
        logger.info(f'TOTAL: {sum(results.values())} profiles')

        return results


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Build and enrich agent profiles')
    parser.add_argument('--all', action='store_true', help='Build all agents')
    parser.add_argument('--congress', action='store_true', help='Build Congress members')
    parser.add_argument('--enrich-congress', action='store_true', help='Enrich Congress members')
    parser.add_argument('--scotus', action='store_true', help='Build SCOTUS justices')
    parser.add_argument('--executive', action='store_true', help='Build executive branch')
    parser.add_argument('--verify', action='store_true', help='Verify all builds')

    args = parser.parse_args()

    if not any([args.all, args.congress, args.enrich_congress, args.scotus, args.executive, args.verify]):
        args.all = True

    orchestrator = AgentBuildOrchestrator()

    success = True
    if args.all:
        success = orchestrator.build_all()
    else:
        if args.congress:
            success = orchestrator.build_congress() and success
        if args.enrich_congress:
            success = orchestrator.enrich_congress() and success
        if args.scotus:
            success = orchestrator.build_scotus() and success
        if args.executive:
            success = orchestrator.build_executive() and success

    if args.verify or args.all:
        results = orchestrator.verify_builds()

    logger.info('')
    logger.info('='*70)
    logger.info('BUILD COMPLETE')
    logger.info('='*70)

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
