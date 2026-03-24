"""Congress bill debate simulator using OASIS pipeline + LLM agents."""

import logging
from typing import Dict, List, Optional, Any

from backend.simulation.persona_loader import PersonaLoader
from backend.simulation.pipeline import Bill, Pipeline, StageType, BillStatus
from backend.simulation.stages.s01_introduction import IntroductionStage
from backend.simulation.stages.s02_committee import CommitteeStage
from backend.simulation.stages.s03_floor import FloorStage
from backend.simulation.stages.s04_presidential import PresidentialStage
from backend.simulation.stages.s05_judicial import JudicialStage

logger = logging.getLogger(__name__)


class CongressSimulator:
    """Simulate Congress debate on bills using prebuilt member personas + OASIS pipeline.

    This orchestrates the 5-stage pipeline:
    1. Introduction & Referral
    2. Committee Markup & Vote
    3. Floor Vote
    4. Presidential Review
    5. Judicial Review

    Each stage runs an LLM-powered debate with selected agents, extracting vote signals.
    """

    def __init__(self, personas_dir: str = None):
        """Initialize simulator with persona loader and OASIS pipeline.

        Args:
            personas_dir: Path to personas directory (defaults to standard location)
        """
        self.personas = PersonaLoader()
        logger.info(f"✓ Loaded {self.personas.total_personas} Congress member personas")

        # Initialize pipeline with stage executors
        self.pipeline = Pipeline()

        # For now, use a simple agent selector that pulls from loaded personas
        # Real implementation would query Neo4j for committee memberships, etc.
        self.personas_dir = personas_dir or "backend/agents/personas"

        # Register stage executors
        self._register_stages()

    def _register_stages(self):
        """Register stage executors with pipeline."""
        # Register stages with persona-based agent selection
        stages_config = [
            (StageType.INTRODUCTION, IntroductionStage),
            (StageType.COMMITTEE, CommitteeStage),
            (StageType.FLOOR, FloorStage),
            (StageType.PRESIDENTIAL, PresidentialStage),
            (StageType.JUDICIAL, JudicialStage),
        ]

        for stage_type, stage_class in stages_config:
            try:
                # Create executor (neo4j_client can be None for persona-based selection)
                executor = stage_class(neo4j_client=None, personas_dir=self.personas_dir)

                # Override select_agents to use persona-based selection
                original_select = executor.select_agents
                stage_type_captured = stage_type  # Capture for closure
                executor.select_agents = lambda bill: self._select_agents_for_stage(bill, stage_type_captured)

                self.pipeline.register_stage(stage_type, executor)
                logger.info(f'✓ Registered {stage_type.value} stage')
            except Exception as e:
                logger.error(f'Failed to register {stage_type.value} stage: {e}', exc_info=True)

    def _select_agents_for_stage(self, bill: Bill, stage_type: StageType) -> List[str]:
        """Select agents for a stage based on personas."""
        # For initial implementation: select by chamber
        # - Introduction: leadership only (Speaker, Majority Leaders) — simplified: 10 members
        # - Committee: committee members — simplified: 30 members
        # - Floor: all members of initiating chamber
        # - Presidential: executive branch (simplified to SCOTUS for now)
        # - Judicial: judicial branch (SCOTUS)

        logger.info(f"Selecting agents for {stage_type.value} stage")

        if stage_type == StageType.INTRODUCTION:
            # Just top party leaders: ~10 members
            # Simplified: pull first 10 from chamber
            chamber = bill.chamber.lower() if hasattr(bill, 'chamber') else 'house'
            members = self.personas.get_personas_by_chamber(chamber)[:10]

        elif stage_type == StageType.COMMITTEE:
            # Committee members (~30 for relevant committee)
            chamber = bill.chamber.lower() if hasattr(bill, 'chamber') else 'house'
            members = self.personas.get_personas_by_chamber(chamber)[:30]

        elif stage_type == StageType.FLOOR:
            # All members of the chamber
            chamber = bill.chamber.lower() if hasattr(bill, 'chamber') else 'house'
            members = self.personas.get_personas_by_chamber(chamber)

        elif stage_type == StageType.PRESIDENTIAL:
            # Executive branch — simplified: return empty (will be skipped)
            members = []

        elif stage_type == StageType.JUDICIAL:
            # Judicial branch (SCOTUS) — simplified: return empty (will be skipped)
            members = []
        else:
            members = []

        agent_ids = [m.get('bioguide_id') for m in members if m.get('bioguide_id')]
        logger.info(f"Selected {len(agent_ids)} agents for {stage_type.value}")
        return agent_ids

    def run_simulation(
        self,
        bill_title: str,
        bill_description: str,
        chambers: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Run a full multi-stage simulation.

        Args:
            bill_title: Bill title
            bill_description: Bill description
            chambers: Chambers to process (House, Senate, Executive, Judicial)

        Returns:
            Simulation results with stage outcomes and final tally
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"Bill: {bill_title}")
        logger.info(f"Chambers: {chambers or ['House', 'Senate']}")
        logger.info(f"{'='*60}")

        # Create bill object
        # Map chamber string to format expected by pipeline
        primary_chamber = 'house'
        if chambers and len(chambers) == 1:
            primary_chamber = chambers[0].lower()

        bill = Bill(
            bill_id="sim_" + bill_title[:20].replace(' ', '_'),
            title=bill_title,
            summary=bill_description,
            chamber=primary_chamber,
            sponsor_bioguide=None,
            status=BillStatus.INTRODUCED
        )

        # Run pipeline
        try:
            pipeline_state = self.pipeline.execute(bill)
            logger.info(f"✓ Simulation complete. Final status: {pipeline_state.final_status.value}")

            # Compile results
            return {
                "bill_title": bill_title,
                "bill_description": bill_description,
                "chambers": chambers or ["House", "Senate"],
                "final_status": pipeline_state.final_status.value,
                "passed": pipeline_state.final_status in [BillStatus.SIGNED, BillStatus.ENACTED],
                "stage_results": [
                    {
                        "stage": s.stage.value,
                        "passed": s.passed,
                        "yes_votes": s.vote_yes,
                        "no_votes": s.vote_no,
                        "abstain_votes": s.vote_abstain,
                        "debate_feed": s.oasis_feed[:500] if s.oasis_feed else "",  # First 500 chars
                    }
                    for s in pipeline_state.stage_history
                ],
                "total_stages": len(pipeline_state.stage_history),
                "duration_seconds": pipeline_state.summary()['duration_seconds'],
            }

        except Exception as e:
            logger.error(f"Simulation failed: {e}", exc_info=True)
            return {
                "bill_title": bill_title,
                "bill_description": bill_description,
                "error": str(e),
                "final_status": "error",
                "passed": False
            }
