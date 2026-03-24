"""Stage 3: Floor Vote (with Senate filibuster check)"""

from backend.simulation.pipeline import Bill, StageType, BillStatus
from backend.simulation.stages.base import StageExecutor


class FloorStage(StageExecutor):
    """Floor Vote stage with Senate filibuster logic.

    House:
    - All 435 members
    - Passes if: yes_votes > no_votes

    Senate:
    - All 100 senators
    - Filibuster check: if opposed, needs 60 votes to pass cloture
    - Passes if: yes_votes >= 50 (VP tiebreaker) AND cloture achieved
    """

    @property
    def stage_type(self) -> StageType:
        return StageType.FLOOR

    def select_agents(self, bill: Bill) -> list:
        """Select all members of relevant chamber."""
        # TODO: Query Neo4j for all members with matching chamber
        # - If House: all members with chamber='house'
        # - If Senate: all members with chamber='senate'
        return []

    def evaluate_gate_check(self, bill: Bill, agents: dict, oasis_output: str, vote_signals: dict) -> bool:
        """
        Gate check: Floor vote with chamber-specific rules.

        House: Simple majority (yes > no)
        Senate: 50 votes (+ VP tiebreaker) AND 60-vote cloture (if filibustered)
        """
        yes_votes = sum(1 for v in vote_signals.values() if v == 'YES')
        no_votes = sum(1 for v in vote_signals.values() if v == 'NO')
        total = yes_votes + no_votes

        if bill.chamber == 'house':
            # House: simple majority
            return yes_votes > no_votes

        elif bill.chamber == 'senate':
            # Senate: 50 votes + cloture (60-vote threshold)
            has_fifty = yes_votes >= 50

            # Check if filibustered: majority opposes?
            if no_votes > yes_votes:
                # Filibuster invoked, need 60 to break cloture
                return yes_votes >= 60

            return has_fifty

        return False
