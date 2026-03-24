#!/usr/bin/env python3
"""
Bill discussion and debate engine for CongressFish.

Orchestrates governmental flow: user proposes a bill → LLM + Neo4j context
generates member responses → debate unfolds → outcomes tracked.

Supports full government simulation (all branches) or filtered (House, Senate, Executive, Judicial).
"""

import json
import logging
from typing import Dict, List, Any, Optional
from enum import Enum
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


class GovernmentBranch(Enum):
    """Government branches that can participate in debate."""
    HOUSE = "house"
    SENATE = "senate"
    EXECUTIVE = "executive"
    JUDICIAL = "judicial"


@dataclass
class Bill:
    """Bill proposal in the system."""
    id: str
    title: str
    description: str
    sponsor_bioguide: Optional[str]  # Who introduced it
    primary_chamber: GovernmentBranch  # House or Senate
    summary: str
    key_provisions: List[str]
    estimated_cost: Optional[float] = None
    affected_agencies: List[str] = None
    related_bills: List[str] = None


@dataclass
class MemberPosition:
    """A member's stance on a bill."""
    bioguide_id: str
    full_name: str
    chamber: str
    party: str
    position: str  # "yes", "no", "abstain", "undecided"
    reasoning: str  # Why they hold this position
    confidence: float  # 0.0-1.0 certainty
    willingness_to_negotiate: bool
    key_concerns: List[str]


@dataclass
class DebateRound:
    """Single round of debate."""
    round_number: int
    speaker_bioguide: str
    statement: str
    directed_to: Optional[str]  # None = general, or target bioguide
    tone: str  # "formal", "persuasive", "hostile", "collaborative"


class BillDiscussionEngine:
    """Orchestrates bill discussion and debate flow."""

    def __init__(self, neo4j_client, llm_client):
        """
        Initialize discussion engine.

        Args:
            neo4j_client: Neo4j client for member/committee context
            llm_client: LLM client (Claude or Ollama) for generating responses
        """
        self.neo4j = neo4j_client
        self.llm = llm_client
        self.active_bills: Dict[str, Bill] = {}
        self.member_positions: Dict[str, MemberPosition] = {}
        self.debate_rounds: List[DebateRound] = []

    def create_bill(
        self,
        bill_id: str,
        title: str,
        description: str,
        primary_chamber: GovernmentBranch = GovernmentBranch.HOUSE,
        sponsor_bioguide: Optional[str] = None,
        key_provisions: Optional[List[str]] = None,
        estimated_cost: Optional[float] = None
    ) -> Bill:
        """
        Create a new bill for discussion.

        Args:
            bill_id: Unique bill identifier
            title: Bill title
            description: Full description/text
            primary_chamber: Which chamber introduces it
            sponsor_bioguide: Sponsoring member (optional)
            key_provisions: Main provisions of the bill
            estimated_cost: Estimated fiscal impact

        Returns:
            Bill object
        """
        bill = Bill(
            id=bill_id,
            title=title,
            description=description,
            sponsor_bioguide=sponsor_bioguide,
            primary_chamber=primary_chamber,
            summary=self._summarize_bill(description),
            key_provisions=key_provisions or [],
            estimated_cost=estimated_cost
        )

        self.active_bills[bill_id] = bill
        self.member_positions[bill_id] = {}
        self.debate_rounds[bill_id] = []

        logger.info(f"Created bill {bill_id}: {title}")
        return bill

    def get_relevant_members(
        self,
        bill: Bill,
        branches: Optional[List[GovernmentBranch]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get members relevant to a bill.

        Priority order:
        1. Sponsor (if present)
        2. Members of relevant committees
        3. Party leadership
        4. Ideological spectrum diversity

        Args:
            bill: Bill object
            branches: Branches to include (default all)

        Returns:
            List of member profiles with relevance scores
        """
        if branches is None:
            branches = [GovernmentBranch.HOUSE, GovernmentBranch.SENATE]

        # Extract relevant committees from bill keywords
        committees = self._identify_relevant_committees(bill.description)

        relevant_members = []

        # Get members from relevant committees
        for committee in committees:
            members = self.neo4j.get_members_by_committee(committee)
            for member in members:
                member["relevance_score"] = 1.0
                member["reason"] = f"Member of {committee}"
                relevant_members.append(member)

        # Add party leaders (by ideology extremes)
        for party_code in ["D", "R"]:
            members = self.neo4j.get_members_by_party(party_code)
            # Add leftmost (D) and rightmost (R) members for leadership
            if party_code == "D":
                leader = min(members, key=lambda m: m.get("ideology_primary", 0))
            else:
                leader = max(members, key=lambda m: m.get("ideology_primary", 0))
            leader["relevance_score"] = 0.9
            leader["reason"] = f"{party_code} leadership/"
            relevant_members.append(leader)

        # Add ideological diversity (pick from spectrum)
        spectrum = self.neo4j.get_ideological_spectrum()
        for member in [spectrum[0], spectrum[len(spectrum)//2], spectrum[-1]]:
            member["relevance_score"] = 0.7
            member["reason"] = "Ideological diversity"
            relevant_members.append(member)

        # Filter by branch
        filtered = [
            m for m in relevant_members
            if m.get("chamber").lower() in [b.value for b in branches]
        ]

        return sorted(filtered, key=lambda m: m.get("relevance_score", 0), reverse=True)

    def predict_member_position(
        self,
        bill: Bill,
        member_bioguide: str
    ) -> MemberPosition:
        """
        Predict a member's position on a bill using LLM.

        Uses Neo4j context (committees, ideology, allies) + member persona.

        Args:
            bill: Bill object
            member_bioguide: Target member

        Returns:
            MemberPosition with predicted stance
        """
        # Get member context from Neo4j
        context = self.neo4j.get_bill_prediction_context(member_bioguide)

        member = context["member"]
        committees = context["committees"]
        allies = context["allies"]
        party = context["party"]

        # Build LLM prompt
        prompt = f"""Analyze this member's likely position on the bill based on their profile.

MEMBER: {member.get('full_name')}
PARTY: {party.get('name', 'Unknown')}
IDEOLOGY: {member.get('ideology_primary', 0):.2f} ([-1 far left, +1 far right])

COMMITTEES: {', '.join([c.get('title', c.get('code')) for c in committees])}

BIOGRAPHY:
{member.get('full_biography', 'Not available')[:300]}

PERSONA:
{member.get('persona_narrative', 'Standard legislative behavior')[:300]}

BILL:
Title: {bill.title}
Summary: {bill.summary}
Key Provisions: {', '.join(bill.key_provisions)}

Predict:
1. Will this member vote YES, NO, or ABSTAIN?
2. How confident are you (0.0-1.0)?
3. What are their key concerns or motivations?
4. Would they be willing to negotiate or compromise?
5. In 2-3 sentences, explain their likely reasoning.

Format as JSON with: position (yes/no/abstain), confidence (0.0-1.0), reasoning, key_concerns (list), willing_to_negotiate (boolean)"""

        # Call LLM
        response = self.llm.generate(prompt, max_tokens=500)

        # Parse response into MemberPosition
        try:
            import json
            position_data = json.loads(response)
        except:
            # Fallback if LLM doesn't return valid JSON
            position_data = {
                "position": "undecided",
                "confidence": 0.5,
                "reasoning": response,
                "key_concerns": [],
                "willing_to_negotiate": True
            }

        return MemberPosition(
            bioguide_id=member_bioguide,
            full_name=member.get("full_name"),
            chamber=member.get("chamber"),
            party=member.get("party"),
            position=position_data.get("position", "undecided"),
            reasoning=position_data.get("reasoning", ""),
            confidence=float(position_data.get("confidence", 0.5)),
            willingness_to_negotiate=position_data.get("willing_to_negotiate", True),
            key_concerns=position_data.get("key_concerns", [])
        )

    def run_debate_round(
        self,
        bill: Bill,
        round_number: int
    ) -> List[DebateRound]:
        """
        Run one round of debate on a bill.

        Members respond to previous speakers or make opening statements.

        Args:
            bill: Bill object
            round_number: Current round

        Returns:
            List of statements made in this round
        """
        statements = []

        # Get all members with positions
        members_with_positions = [
            self.member_positions[bill.id].get(bioguide_id)
            for bioguide_id in self.member_positions[bill.id].keys()
        ]

        # Pick speakers for this round (rotate between parties and positions)
        speakers = self._select_speakers_for_round(members_with_positions, round_number)

        for speaker in speakers:
            # Generate statement
            statement = self._generate_debate_statement(bill, speaker, statements)

            debate_round = DebateRound(
                round_number=round_number,
                speaker_bioguide=speaker.bioguide_id,
                statement=statement,
                directed_to=None,  # Could target specific opponents
                tone="formal"
            )

            statements.append(debate_round)
            self.debate_rounds.append(debate_round)

        return statements

    def tally_votes(self, bill: Bill) -> Dict[str, Any]:
        """
        Tally votes and determine bill outcome.

        Args:
            bill: Bill object

        Returns:
            Dict with vote counts and outcome
        """
        positions = self.member_positions[bill.id]

        yes_votes = len([p for p in positions.values() if p.position == "yes"])
        no_votes = len([p for p in positions.values() if p.position == "no"])
        abstain_votes = len([p for p in positions.values() if p.position == "abstain"])

        total_votes = yes_votes + no_votes + abstain_votes

        return {
            "yes": yes_votes,
            "no": no_votes,
            "abstain": abstain_votes,
            "total": total_votes,
            "passes": yes_votes > no_votes,
            "margin": abs(yes_votes - no_votes),
            "percentage_yes": yes_votes / total_votes if total_votes > 0 else 0
        }

    # Helper methods
    def _summarize_bill(self, description: str) -> str:
        """Create brief summary of bill."""
        return description[:200] + "..." if len(description) > 200 else description

    def _identify_relevant_committees(self, bill_text: str) -> List[str]:
        """Extract relevant committee codes from bill text."""
        # Simplified: would use Neo4j to query committees by keywords
        return ["HSAP", "HSWM"]  # Placeholder

    def _select_speakers_for_round(self, members: List[MemberPosition], round_num: int) -> List[MemberPosition]:
        """Select which members speak in this round."""
        # Rotate: start with sponsors/key committees, then party leaders, then opposition
        return members[:5]  # Simplified

    def _generate_debate_statement(
        self,
        bill: Bill,
        speaker: MemberPosition,
        previous_statements: List[DebateRound]
    ) -> str:
        """Generate a debate statement from a member using LLM."""
        # Would call LLM with speaker's persona + bill context
        return f"{speaker.full_name}: {speaker.reasoning}"


class GovernmentSimulator:
    """High-level orchestrator for full government simulation."""

    def __init__(self, neo4j_client, llm_client):
        """Initialize simulator."""
        self.discussion_engine = BillDiscussionEngine(neo4j_client, llm_client)
        self.neo4j = neo4j_client
        self.llm = llm_client

    def run_full_simulation(
        self,
        bill: Bill,
        max_debate_rounds: int = 5,
        branches: Optional[List[GovernmentBranch]] = None
    ) -> Dict[str, Any]:
        """
        Run full governmental debate on a bill.

        Args:
            bill: Bill object
            max_debate_rounds: Max rounds of debate
            branches: Which branches participate (default all)

        Returns:
            Complete simulation results
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"Starting simulation: {bill.title}")
        logger.info(f"Branches: {[b.value for b in (branches or [GovernmentBranch.HOUSE, GovernmentBranch.SENATE])]}")
        logger.info(f"{'='*60}\n")

        # Get relevant members
        members = self.discussion_engine.get_relevant_members(bill, branches)

        # Predict positions
        for member in members:
            position = self.discussion_engine.predict_member_position(bill, member["bioguide_id"])
            self.discussion_engine.member_positions[bill.id][member["bioguide_id"]] = position

        # Run debate rounds
        for round_num in range(max_debate_rounds):
            logger.info(f"--- Debate Round {round_num + 1} ---")
            statements = self.discussion_engine.run_debate_round(bill, round_num)
            # Could re-predict positions based on statements
            # For now, simplified

        # Tally votes
        results = self.discussion_engine.tally_votes(bill)

        return {
            "bill": asdict(bill),
            "member_count": len(members),
            "member_positions": {
                bid: asdict(pos)
                for bid, pos in self.discussion_engine.member_positions[bill.id].items()
            },
            "debate_rounds": [asdict(r) for r in self.discussion_engine.debate_rounds],
            "vote_results": results
        }
