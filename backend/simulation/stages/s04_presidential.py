"""Stage 4: Presidential Action (sign/veto)"""

from backend.simulation.pipeline import Bill, StageType, BillStatus
from backend.simulation.stages.base import StageExecutor


class PresidentialStage(StageExecutor):
    """Presidential Action stage.

    Agents:
    - President
    - VP (for tie-breaking if Senate)
    - Congressional leadership (pressure)
    - Key Cabinet on relevant policy
    """

    @property
    def stage_type(self) -> StageType:
        return StageType.PRESIDENTIAL

    def select_agents(self, bill: Bill) -> list:
        """Select President, VP, congressional leadership."""
        # Simple hardcoded agent selection from loaded personas
        from backend.simulation.persona_loader import PersonaLoader

        try:
            personas = PersonaLoader()
            members = personas.get_personas_by_chamber('house')
            # Use first 3 House members as executive representatives
            agents = [m.get('bioguide_id') for m in members[:3] if m.get('bioguide_id')]
            return agents
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to load personas: {e}")
            return []

    def evaluate_gate_check(self, bill: Bill, agents: dict, oasis_output: str, vote_signals: dict) -> bool:
        """
        Gate check: Presidential signature.

        Passes if: President signals YES (vote to sign)
        Fails if: President signals NO (veto)

        If no agents (presidential branch is simplified), assume sign.
        """
        # If no agents selected, assume bill is signed (simplified flow)
        if not agents:
            return True

        # Find President's vote (should be the only/first agent)
        if vote_signals:
            first_vote = list(vote_signals.values())[0]
            return first_vote != 'NO'

        # If no votes, assume sign (passive approval)
        return True
