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
        # TODO: Query Neo4j for:
        # - Current President (Executive node)
        # - VP
        # - Speaker/Majority Leader
        # - Relevant Cabinet member(s)
        return []

    def evaluate_gate_check(self, bill: Bill, agents: dict, oasis_output: str, vote_signals: dict) -> bool:
        """
        Gate check: Presidential signature.

        Passes if: President signals YES (vote to sign)
        Fails if: President signals NO (veto)

        Vetoed bills continue to veto override attempt (not implemented here).
        """
        # Find President's vote
        for agent_id, vote in vote_signals.items():
            if agent_id == 'PRESIDENT':
                return vote == 'YES'

        # If President didn't signal, assume signs (passive approval)
        return True
