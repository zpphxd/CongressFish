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
        # TODO: Query Neo4j for all Justice nodes
        return []

    def evaluate_gate_check(self, bill: Bill, agents: dict, oasis_output: str, vote_signals: dict) -> bool:
        """
        Gate check: Judicial review is advisory only.

        This stage always passes (bill is already enacted).
        Output is risk assessment for future litigation.

        Returns:
            Always True (no veto power)
        """
        return True
