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
import re
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

        Generates debate statements from each agent using LLM (Qwen) + their persona.
        Each agent generates authentic debate statements based on their profile.

        Args:
            agents: {agent_id: profile, ...}
            stage_context: Stage description (e.g., "Committee Markup")
            num_rounds: Number of simulation rounds

        Returns:
            Raw OASIS output (agent debate posts)
        """
        logger.info(f'🎬 Starting LLM-based OASIS debate: {len(agents)} agents, {num_rounds} rounds')

        # Initialize LLM (required)
        from backend.app.utils.llm_client import LLMClient
        try:
            llm = LLMClient()
            logger.info(f'✓ LLM initialized: {llm.model} @ {llm.base_url}')
        except Exception as e:
            logger.error(f'✗ Failed to initialize LLM: {e}', exc_info=True)
            raise RuntimeError(f"LLM initialization failed: {e}")

        all_posts = []

        # Round-robin debate: each agent speaks once per round
        for round_num in range(num_rounds):
            logger.info(f'📢 Round {round_num + 1}/{num_rounds}')

            round_posts = 0
            for agent_id, profile in agents.items():
                try:
                    post = self._generate_agent_statement(
                        llm=llm,
                        agent_id=agent_id,
                        profile=profile,
                        stage_context=stage_context,
                        round_num=round_num,
                        prior_posts=all_posts[-5:] if all_posts else [],
                    )
                    if post:
                        all_posts.append(post)
                        round_posts += 1
                except Exception as e:
                    logger.error(f'  ✗ {agent_id}: {e}', exc_info=True)
                    raise

            logger.info(f'✓ Round {round_num + 1}: {round_posts}/{len(agents)} agents spoke')

        logger.info(f'✓ Debate complete: {len(all_posts)} statements generated')
        return '\n\n'.join(all_posts)

    def _generate_agent_statement(
        self,
        llm,
        agent_id: str,
        profile: Dict,
        stage_context: str,
        round_num: int,
        prior_posts: List[str],
    ) -> str:
        """Generate a single agent statement using LLM."""
        # Build agent persona narrative
        persona = self._build_persona_narrative(agent_id, profile)

        # Build debate context (limit to keep prompt reasonable)
        debate_context = stage_context
        if prior_posts:
            recent = prior_posts[-3:]  # Only last 3 posts for context
            debate_context += f"\n\nRecent debate:\n" + '\n'.join(recent)

        # System prompt
        system_prompt = f"""You are {persona}.

You are in Congress debating a bill. Respond in the voice of this member (100-150 words).
- State your position: support, oppose, or neutral
- Reference your party or ideology if relevant
- End with an explicit vote signal: "I vote YES", "I vote NO", or "I will be PRESENT"

Stay in character and be authentic."""

        # User prompt
        user_prompt = f"""Round {round_num + 1} of debate:

{debate_context}

Make your statement (stay in character, end with explicit vote signal)."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = llm.chat(messages=messages, temperature=0.7, max_tokens=200)
            # Tag with agent ID for vote signal extraction
            return f"[{agent_id}] {response}"
        except Exception as e:
            logger.error(f'LLM call failed for {agent_id}: {e}', exc_info=True)
            return None

    def _build_persona_narrative(self, agent_id: str, profile: Dict) -> str:
        """Build a readable persona narrative from profile."""
        name = profile.get('full_name', agent_id)
        party = profile.get('party', 'I')
        chamber = profile.get('chamber', 'Congress')
        ideology = profile.get('ideology_score', 0)
        state = profile.get('state', '')

        party_name = {'D': 'Democratic', 'R': 'Republican', 'I': 'Independent'}.get(party, 'Independent')

        ideology_desc = 'far-left' if ideology < -0.5 else 'liberal' if ideology < -0.2 else 'moderate-left' if ideology < 0 else 'moderate-right' if ideology < 0.2 else 'conservative' if ideology < 0.5 else 'far-right'

        bio = f"{name}, {party_name} member of {chamber}"
        if state:
            bio += f" from {state}"
        bio += f", {ideology_desc} ideology"

        return bio

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

        # Extract agent ID and find vote signal in their statement
        # Format: [agent_id] ...statement... "I vote YES|NO" or "I will be PRESENT"
        agent_pattern = r'\[([A-Z0-9]+)\]\s+(.*?)(?=\[[A-Z0-9]+\]|$)'

        for match in re.finditer(agent_pattern, oasis_output, re.DOTALL):
            agent_id = match.group(1)
            statement = match.group(2)

            # Look for explicit vote signals
            if re.search(r'i\s+vote\s+yes|i\'ll\s+vote\s+yes|voting\s+yes|support\s+this\s+bill', statement, re.IGNORECASE):
                vote_signals[agent_id] = 'YES'
            elif re.search(r'i\s+vote\s+no|i\'ll\s+vote\s+no|voting\s+no|oppose\s+this\s+bill|cannot\s+support', statement, re.IGNORECASE):
                vote_signals[agent_id] = 'NO'
            elif re.search(r'i\s+(?:will\s+)?be\s+present|abstain|not\s+voting', statement, re.IGNORECASE):
                vote_signals[agent_id] = 'ABSTAIN'
            else:
                vote_signals[agent_id] = 'UNKNOWN'

        logger.info(f'Parsed votes: {sum(1 for v in vote_signals.values() if v == "YES")} YES, {sum(1 for v in vote_signals.values() if v == "NO")} NO')

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
