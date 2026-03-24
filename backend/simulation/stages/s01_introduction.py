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
        agents = []

        # TODO: Query Neo4j for:
        # - Bill sponsor
        # - Speaker (if House) or Majority Leader (if Senate)
        # - Committee chair(s) for relevant jurisdiction

        return agents

    def evaluate_gate_check(self, bill: Bill, agents: dict, oasis_output: str, vote_signals: dict) -> bool:
        """
        Gate check: Is bill formally introduced and referred?

        In real Congress: automatic if sponsor is valid.
        For simulation: check Speaker/Leader didn't block (rare).
        """
        # In real Congress, this is largely automatic
        # Simulation: assume success unless explicitly blocked
        return True
