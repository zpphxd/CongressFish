"""Stage 1: Introduction & Committee Referral"""

from backend.simulation.pipeline import Bill, StageType, BillStatus
from backend.simulation.stages.base import StageExecutor


class IntroductionStage(StageExecutor):
    """Introduction & Committee Referral stage.

    Agents:
    - Sponsor (initiator)
    - Speaker (House) or Leader (Senate)
    - Relevant committee chairs
    """

    @property
    def stage_type(self) -> StageType:
        return StageType.INTRODUCTION

    def select_agents(self, bill: Bill) -> list:
        """Select sponsor, leadership, committee chairs."""
        # Simple hardcoded agent selection from loaded personas
        from backend.simulation.persona_loader import PersonaLoader

        try:
            personas = PersonaLoader()
            chamber = bill.chamber.lower() if hasattr(bill, 'chamber') and bill.chamber else 'house'
            members = personas.get_personas_by_chamber(chamber)
            # Take first 10 for this stage
            agents = [m.get('bioguide_id') for m in members[:10] if m.get('bioguide_id')]
            return agents
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to load personas: {e}")
            return []

    def evaluate_gate_check(self, bill: Bill, agents: dict, oasis_output: str, vote_signals: dict) -> bool:
        """
        Gate check: Is bill formally introduced and referred?

        In real Congress: automatic if sponsor is valid.
        For simulation: check Speaker/Leader didn't block (rare).
        """
        # In real Congress, this is largely automatic
        # Simulation: assume success unless explicitly blocked
        return True
