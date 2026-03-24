"""
Base Stage Executor
===================
Abstract base class for pipeline stages.

Each stage:
1. Selects relevant agents (subset of all agents)
2. Loads their profiles + persona narratives
3. Runs OASIS mini-simulation (5-10 rounds)
4. Parses vote signals from agent posts
5. Evaluates gate check
6. Returns outcome with cross-stage memory
"""

import logging
import subprocess
import json
import tempfile
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from pathlib import Path

from backend.simulation.pipeline import Bill, StageOutcome, StageType

logger = logging.getLogger(__name__)


class StageExecutor(ABC):
    """Base class for stage executors."""

    def __init__(self, neo4j_client, personas_dir: str):
        """
        Args:
            neo4j_client: CongressGraphClient for querying agents
            personas_dir: Path to personas/ directory with JSON profiles
        """
        self.neo4j_client = neo4j_client
        self.personas_dir = personas_dir

    @abstractmethod
    def select_agents(self, bill: Bill) -> List[str]:
        """
        Select bioguide_ids of agents relevant to this stage.

        Returns:
            List of bioguide_ids
        """
        pass

    def load_agent_profiles(self, agent_ids: List[str]) -> Dict[str, Dict]:
        """
        Load JSON profiles for agents.

        Args:
            agent_ids: List of bioguide_ids

        Returns:
            {bioguide_id: profile_dict, ...}
        """
        profiles = {}

        for agent_id in agent_ids:
            # Find profile file
            profile_path = self._find_profile_path(agent_id)
            if not profile_path:
                logger.warning(f'Profile not found for {agent_id}')
                continue

            try:
                with open(profile_path, 'r') as f:
                    profile = json.load(f)
                    profiles[agent_id] = profile
            except Exception as e:
                logger.warning(f'Failed to load profile {profile_path}: {e}')

        return profiles

    def _find_profile_path(self, agent_id: str) -> Optional[str]:
        """Find JSON profile file for agent."""
        # Search congress subdirectories
        for chamber in ['house', 'senate']:
            path = Path(self.personas_dir) / 'congress' / chamber / f'{agent_id}.json'
            if path.exists():
                return str(path)

        # Search other directories
        for subdir in ['scotus', 'executive', 'influence']:
            path = Path(self.personas_dir) / subdir / f'{agent_id}.json'
            if path.exists():
                return str(path)

        return None

    def run_oasis_simulation(
        self,
        agents: Dict[str, Dict],
        stage_context: str,
        num_rounds: int = 5,
    ) -> str:
        """
        Run OASIS mini-simulation for this stage.

        Args:
            agents: {agent_id: profile, ...}
            stage_context: Stage description (e.g., "Committee Markup")
            num_rounds: Number of simulation rounds

        Returns:
            Raw OASIS output (social media posts)
        """
        logger.info(f'Running OASIS simulation with {len(agents)} agents, {num_rounds} rounds')

        # This would call the existing OASIS subprocess
        # For now, return placeholder
        # Full implementation:
        # 1. Write agent profiles to temp CSV
        # 2. Call backend/scripts/run_oasis_simulation.py
        # 3. Parse output, return posts

        return f"OASIS simulation output for {len(agents)} agents"

    @abstractmethod
    def evaluate_gate_check(
        self,
        bill: Bill,
        agents: Dict[str, Dict],
        oasis_output: str,
        vote_signals: Dict[str, str],
    ) -> bool:
        """
        Evaluate gate check: does the bill advance?

        Args:
            bill: Bill being simulated
            agents: {agent_id: profile, ...}
            oasis_output: Raw OASIS agent posts
            vote_signals: {agent_id: 'YES'|'NO'|'ABSTAIN'|'UNKNOWN'}

        Returns:
            True if bill passes, False if it fails
        """
        pass

    def parse_vote_signals(self, oasis_output: str) -> Dict[str, str]:
        """
        Extract vote signals from OASIS output.

        Looks for explicit YES/NO/PRESENT statements in agent posts.

        Args:
            oasis_output: Raw OASIS agent posts

        Returns:
            {agent_id: 'YES'|'NO'|'ABSTAIN'|'UNKNOWN'}
        """
        vote_signals = {}

        # Simple pattern matching for "I vote YES" / "I vote NO" / "PRESENT"
        # Full implementation would parse actual OASIS output format

        return vote_signals

    def extract_key_commitments(self, oasis_output: str) -> List[str]:
        """
        Extract cross-stage memory: key commitments from agent posts.

        Examples:
        - "I'm on record supporting this bill"
        - "My donors are watching — must oppose"
        - "Leadership told us to vote NO"

        Args:
            oasis_output: Raw OASIS agent posts

        Returns:
            List of commitment strings for next stage
        """
        return []

    def execute(
        self,
        bill: Bill,
        cross_stage_memory: List[str],
    ) -> StageOutcome:
        """
        Execute this stage.

        Args:
            bill: Bill being simulated
            cross_stage_memory: Commitments from prior stages

        Returns:
            StageOutcome with results
        """
        try:
            # Select relevant agents
            agent_ids = self.select_agents(bill)
            logger.info(f'Selected {len(agent_ids)} agents for this stage')

            # Load profiles
            agents = self.load_agent_profiles(agent_ids)
            if not agents:
                logger.warning('No agent profiles loaded')
                return StageOutcome(
                    stage=self.stage_type,
                    status=bill.status,
                    passed=False,
                )

            # Build stage context from bill + cross-stage memory
            stage_context = self._build_context(bill, cross_stage_memory)

            # Run OASIS
            oasis_output = self.run_oasis_simulation(agents, stage_context)

            # Parse vote signals
            vote_signals = self.parse_vote_signals(oasis_output)

            # Evaluate gate check
            passed = self.evaluate_gate_check(bill, agents, oasis_output, vote_signals)

            # Extract cross-stage memory
            key_commitments = self.extract_key_commitments(oasis_output)

            # Count votes
            yes_count = sum(1 for v in vote_signals.values() if v == 'YES')
            no_count = sum(1 for v in vote_signals.values() if v == 'NO')
            abstain_count = sum(1 for v in vote_signals.values() if v == 'ABSTAIN')

            return StageOutcome(
                stage=self.stage_type,
                status=bill.status,
                passed=passed,
                vote_yes=yes_count,
                vote_no=no_count,
                vote_abstain=abstain_count,
                agents_supporting=[aid for aid, vote in vote_signals.items() if vote == 'YES'],
                agents_opposing=[aid for aid, vote in vote_signals.items() if vote == 'NO'],
                key_commitments=key_commitments,
                oasis_feed=oasis_output,
            )

        except Exception as e:
            logger.error(f'Stage execution failed: {e}', exc_info=True)
            return StageOutcome(
                stage=self.stage_type,
                status=bill.status,
                passed=False,
            )

    def _build_context(self, bill: Bill, cross_stage_memory: List[str]) -> str:
        """Build stage context prompt."""
        context = f"""
Bill: {bill.title}
Summary: {bill.summary}

Your role as an agent: Discuss this bill, express your position, and signal your vote.

Prior commitments:
{chr(10).join(f"- {m}" for m in cross_stage_memory) if cross_stage_memory else "- None yet"}

Discuss the bill's merits, your party position, donor pressure, and how you plan to vote.
End your post with an explicit vote signal: "I vote YES", "I vote NO", or "I will be PRESENT".
"""
        return context

    @property
    @abstractmethod
    def stage_type(self) -> StageType:
        """Return this stage's type."""
        pass
