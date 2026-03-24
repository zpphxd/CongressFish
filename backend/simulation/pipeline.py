"""
CongressFish Multi-Stage Legislative Pipeline
==============================================
5-stage state machine for bill movement through Congress.

Stages:
  1. Introduction & Committee Referral
  2. Committee Markup & Vote
  3. Floor Vote (with Senate filibuster check)
  4. Presidential Action (sign/veto)
  5. Judicial Review (SCOTUS risk assessment)

Each stage runs a scoped OASIS mini-simulation with relevant agents only.
Cross-stage memory injects prior commitments into subsequent stages.
"""

import logging
from enum import Enum
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


class BillStatus(str, Enum):
    """Bill lifecycle status."""
    INTRODUCED = "introduced"
    IN_COMMITTEE = "in_committee"
    COMMITTEE_PASSED = "committee_passed"
    COMMITTEE_FAILED = "committee_failed"
    FLOOR_DEBATE = "floor_debate"
    FLOOR_PASSED = "floor_passed"
    FLOOR_FAILED = "floor_failed"
    FILIBUSTERED = "filibustered"
    PRESIDENTIAL_REVIEW = "presidential_review"
    SIGNED = "signed"
    VETOED = "vetoed"
    VETO_OVERRIDE_ATTEMPT = "veto_override_attempt"
    VETO_OVERRIDDEN = "veto_overridden"
    JUDICIAL_REVIEW = "judicial_review"
    ENACTED = "enacted"
    DEAD = "dead"


class StageType(str, Enum):
    """Pipeline stage types."""
    INTRODUCTION = "introduction"
    COMMITTEE = "committee"
    FLOOR = "floor"
    PRESIDENTIAL = "presidential"
    JUDICIAL = "judicial"


@dataclass
class Bill:
    """Bill definition."""
    bill_id: str
    title: str
    summary: str
    chamber: str  # 'house' or 'senate'
    sponsor_bioguide: Optional[str] = None
    topic: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    status: BillStatus = BillStatus.INTRODUCED


@dataclass
class StageOutcome:
    """Result of a single stage."""
    stage: StageType
    status: BillStatus
    passed: bool
    vote_yes: int = 0
    vote_no: int = 0
    vote_abstain: int = 0
    agents_supporting: List[str] = field(default_factory=list)
    agents_opposing: List[str] = field(default_factory=list)
    key_commitments: List[str] = field(default_factory=list)  # Cross-stage memory
    key_swaps: Dict[str, str] = field(default_factory=dict)  # {agent: old_vote -> new_vote}
    oasis_feed: str = ""  # Raw OASIS agent outputs (social media posts)
    gate_check_details: Dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0


@dataclass
class PipelineState:
    """Full pipeline execution state."""
    bill: Bill
    current_stage: StageType = StageType.INTRODUCTION
    stage_history: List[StageOutcome] = field(default_factory=list)
    cross_stage_memory: List[str] = field(default_factory=list)  # Commitments from prior stages
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    final_status: BillStatus = BillStatus.INTRODUCED

    def record_stage(self, outcome: StageOutcome):
        """Record completed stage and update memory."""
        self.stage_history.append(outcome)
        self.current_stage = self._next_stage(outcome.stage)
        self.final_status = outcome.status

        # Extract key commitments for next stage
        if outcome.key_commitments:
            self.cross_stage_memory.extend(outcome.key_commitments)

    def _next_stage(self, current: StageType) -> StageType:
        """Determine next stage."""
        order = [
            StageType.INTRODUCTION,
            StageType.COMMITTEE,
            StageType.FLOOR,
            StageType.PRESIDENTIAL,
            StageType.JUDICIAL,
        ]
        try:
            idx = order.index(current)
            return order[idx + 1] if idx + 1 < len(order) else None
        except ValueError:
            return None

    def is_terminal(self) -> bool:
        """Check if bill is in terminal state."""
        terminal_statuses = {
            BillStatus.ENACTED,
            BillStatus.DEAD,
            BillStatus.VETOED,  # Stays vetoed if override fails
        }
        return self.final_status in terminal_statuses

    def summary(self) -> Dict[str, Any]:
        """Get pipeline summary."""
        return {
            'bill': {
                'id': self.bill.bill_id,
                'title': self.bill.title,
                'chamber': self.bill.chamber,
            },
            'final_status': self.final_status.value,
            'stages_completed': len(self.stage_history),
            'stage_outcomes': [
                {
                    'stage': s.stage.value,
                    'passed': s.passed,
                    'votes': {'yes': s.vote_yes, 'no': s.vote_no, 'abstain': s.vote_abstain},
                    'duration_s': s.duration_seconds,
                }
                for s in self.stage_history
            ],
            'duration_seconds': (
                (self.completed_at or datetime.utcnow()) - self.started_at
            ).total_seconds(),
        }


class Pipeline:
    """Base pipeline orchestrator."""

    def __init__(self):
        """Initialize pipeline."""
        self.stages = {}  # {StageType: StageExecutor}

    def register_stage(self, stage_type: StageType, executor):
        """Register a stage executor."""
        self.stages[stage_type] = executor
        logger.info(f'Registered stage: {stage_type.value}')

    def execute(self, bill: Bill) -> PipelineState:
        """
        Execute full pipeline for a bill.

        Returns:
            PipelineState with full history
        """
        state = PipelineState(bill=bill)
        logger.info(f'Starting pipeline for bill: {bill.title}')

        # Stage sequence
        stage_sequence = [
            StageType.INTRODUCTION,
            StageType.COMMITTEE,
            StageType.FLOOR,
            StageType.PRESIDENTIAL,
            StageType.JUDICIAL,
        ]

        for stage_type in stage_sequence:
            # Check for terminal status
            if state.is_terminal():
                logger.info(f'Bill reached terminal status: {state.final_status.value}')
                break

            # Get stage executor
            executor = self.stages.get(stage_type)
            if not executor:
                logger.warning(f'No executor for stage: {stage_type.value}')
                break

            logger.info(f'Executing stage: {stage_type.value}')

            try:
                # Execute stage with cross-stage memory
                outcome = executor.execute(
                    bill=state.bill,
                    cross_stage_memory=state.cross_stage_memory,
                )

                # Record outcome
                state.record_stage(outcome)

                # Check if stage failed (gate check failed)
                if not outcome.passed:
                    logger.info(f'Bill failed at stage: {stage_type.value}')
                    state.final_status = BillStatus.DEAD
                    break

            except Exception as e:
                logger.error(f'Stage execution failed: {e}', exc_info=True)
                state.final_status = BillStatus.DEAD
                break

        # Mark completion
        state.completed_at = datetime.utcnow()
        logger.info(f'Pipeline complete. Final status: {state.final_status.value}')

        return state
