"""Stage 2: Committee Markup & Vote"""

from backend.simulation.pipeline import Bill, StageType, BillStatus
from backend.simulation.stages.base import StageExecutor


class CommitteeStage(StageExecutor):
    """Committee Markup & Vote stage.

    Agents:
    - Committee members only (10-50 total)
    - Committee chair
    - Relevant party whips
    - Lobbyists targeting committee
    """

    @property
    def stage_type(self) -> StageType:
        return StageType.COMMITTEE

    def select_agents(self, bill: Bill) -> list:
        """Select committee members + chair + whips."""
        # Simple hardcoded agent selection from loaded personas
        from backend.simulation.persona_loader import PersonaLoader

        try:
            personas = PersonaLoader()
            chamber = bill.chamber.lower() if hasattr(bill, 'chamber') and bill.chamber else 'house'
            members = personas.get_personas_by_chamber(chamber)
            # Take members 10-20 for variety
            agents = [m.get('bioguide_id') for m in members[10:20] if m.get('bioguide_id')]
            return agents
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to load personas: {e}")
            return []

    def evaluate_gate_check(self, bill: Bill, agents: dict, oasis_output: str, vote_signals: dict) -> bool:
        """
        Gate check: Committee vote.

        Passes if: yes_votes > no_votes
        """
        yes_votes = sum(1 for v in vote_signals.values() if v == 'YES')
        no_votes = sum(1 for v in vote_signals.values() if v == 'NO')

        # Committee passes if simple majority YES
        return yes_votes > no_votes
