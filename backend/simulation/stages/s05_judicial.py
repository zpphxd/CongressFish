"""Stage 5: Judicial Review (SCOTUS risk assessment)"""

from backend.simulation.pipeline import Bill, StageType, BillStatus
from backend.simulation.stages.base import StageExecutor


class JudicialStage(StageExecutor):
    """Judicial Review stage.

    Agents:
    - 9 Supreme Court justices

    Output: Constitutional risk assessment (not a hard pass/fail).
    Bill is enacted regardless, but analysis informs future litigation risk.
    """

    @property
    def stage_type(self) -> StageType:
        return StageType.JUDICIAL

    def select_agents(self, bill: Bill) -> list:
        """Select all 9 SCOTUS justices."""
        # Simple hardcoded agent selection from loaded personas
        from backend.simulation.persona_loader import PersonaLoader

        try:
            personas = PersonaLoader()
            members = personas.get_personas_by_chamber('house')
            # Use members 20-29 as judicial representatives
            agents = [m.get('bioguide_id') for m in members[20:29] if m.get('bioguide_id')]
            return agents
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to load personas: {e}")
            return []

    def evaluate_gate_check(self, bill: Bill, agents: dict, oasis_output: str, vote_signals: dict) -> bool:
        """
        Gate check: Judicial review is advisory only.

        This stage always passes (bill is already enacted).
        Output is constitutional risk assessment for future litigation.

        Returns:
            Always True (Supreme Court cannot veto enacted laws)
        """
        # Log judicial analysis if any votes were cast
        if vote_signals:
            yes_count = sum(1 for v in vote_signals.values() if v == 'YES')
            no_count = sum(1 for v in vote_signals.values() if v == 'NO')
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f'Judicial Review: {yes_count} justices found constitution compliant, {no_count} found concerns')

        return True
