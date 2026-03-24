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
        agents = []

        # TODO: Query Neo4j for:
        # - Members with SERVES_ON relationship to relevant committee
        # - Committee chair (is_chair=True)
        # - Party whips (if available)
        # - Lobbyists targeting this committee (LOBBIES relationship)

        return agents

    def evaluate_gate_check(self, bill: Bill, agents: dict, oasis_output: str, vote_signals: dict) -> bool:
        """
        Gate check: Committee vote.

        Passes if: yes_votes > no_votes
        """
        yes_votes = sum(1 for v in vote_signals.values() if v == 'YES')
        no_votes = sum(1 for v in vote_signals.values() if v == 'NO')

        # Committee passes if simple majority YES
        return yes_votes > no_votes
