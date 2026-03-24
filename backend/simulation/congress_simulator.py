"""Congress bill debate simulator using existing persona profiles."""

import json
import logging
from typing import Dict, List, Optional, Any
from dataclasses import asdict

from backend.simulation.persona_loader import PersonaLoader


logger = logging.getLogger(__name__)


class CongressSimulator:
    """Simulate Congress debate on bills using member personas."""

    def __init__(self):
        """Initialize simulator with persona loader."""
        self.personas = PersonaLoader()
        logger.info(f"✓ Loaded {self.personas.total_personas} Congress member personas")

    def get_relevant_members(
        self,
        bill_description: str,
        chambers: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get relevant Congress members for a bill.

        Args:
            bill_description: Natural language description of the bill
            chambers: List of chambers to include (House, Senate, Executive, Judicial)

        Returns:
            List of relevant member personas
        """
        if not chambers:
            chambers = ["House", "Senate"]

        members = []
        for chamber in chambers:
            if chamber in ["House", "Senate"]:
                chamber_members = self.personas.get_personas_by_chamber(chamber)
                members.extend(chamber_members)

        return members

    def predict_position(
        self,
        member: Dict[str, Any],
        bill_description: str
    ) -> Dict[str, Any]:
        """
        Predict a member's position on a bill based on their profile.

        Args:
            member: Member persona dict
            bill_description: Bill description

        Returns:
            Position prediction with yes/no/abstain and confidence
        """
        # Use ideology score and party affiliation as simple heuristics
        ideology = member.get("ideology_score", 0)  # -1 (far left) to +1 (far right)
        party = member.get("party", "I")

        # Simple heuristic: check keywords in bill
        bill_lower = bill_description.lower()

        # Healthcare bills - Democrats support, Republicans oppose
        if any(word in bill_lower for word in ["healthcare", "medicaid", "medicare", "public option"]):
            if party == "D":
                position = "yes"
                confidence = 0.75 + (abs(ideology) * 0.1)
            elif party == "R":
                position = "no"
                confidence = 0.70 + (abs(ideology) * 0.1)
            else:
                position = "abstain"
                confidence = 0.5
        # Tax bills - generally split by party
        elif any(word in bill_lower for word in ["tax", "revenue", "deficit"]):
            if party == "R":
                position = "no"
                confidence = 0.65
            elif party == "D":
                position = "yes"
                confidence = 0.60
            else:
                position = "abstain"
                confidence = 0.5
        # Environmental bills
        elif any(word in bill_lower for word in ["environment", "climate", "carbon", "emission"]):
            if party == "D":
                position = "yes"
                confidence = 0.70
            elif party == "R":
                position = "no"
                confidence = 0.60
            else:
                position = "abstain"
                confidence = 0.5
        # Default: use ideology
        else:
            if ideology > 0.2:  # Conservative
                position = "no"
            elif ideology < -0.2:  # Liberal
                position = "yes"
            else:  # Moderate
                position = "abstain"
            confidence = 0.5

        # Clamp confidence
        confidence = min(1.0, max(0.0, confidence))

        return {
            "bioguide_id": member.get("bioguide_id"),
            "full_name": member.get("full_name"),
            "position": position,
            "confidence": confidence,
            "reasoning": f"Based on {party} party affiliation and {member.get('ideology_score', 0):.2f} ideology score"
        }

    def tally_votes(
        self,
        members: List[Dict[str, Any]],
        positions: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Tally votes across members.

        Args:
            members: List of member personas
            positions: Dict of bioguide_id -> position prediction

        Returns:
            Vote tally with yes/no/abstain counts
        """
        yes_votes = 0
        no_votes = 0
        abstain_votes = 0

        for member in members:
            bioguide_id = member.get("bioguide_id")
            position_data = positions.get(bioguide_id, {})
            position = position_data.get("position", "abstain")

            if position == "yes":
                yes_votes += 1
            elif position == "no":
                no_votes += 1
            else:
                abstain_votes += 1

        total_votes = yes_votes + no_votes + abstain_votes
        passed = yes_votes > (no_votes + abstain_votes) / 2 if total_votes > 0 else False

        return {
            "yes_votes": yes_votes,
            "no_votes": no_votes,
            "abstain_votes": abstain_votes,
            "total_votes": total_votes,
            "passed": passed,
            "passing_threshold": (total_votes // 2) + 1
        }

    def run_simulation(
        self,
        bill_title: str,
        bill_description: str,
        chambers: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Run a full simulation.

        Args:
            bill_title: Bill title
            bill_description: Bill description
            chambers: Chambers to include (House, Senate, Executive, Judicial)

        Returns:
            Simulation results with votes and member positions
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"Bill: {bill_title}")
        logger.info(f"Chambers: {chambers or ['House', 'Senate']}")
        logger.info(f"{'='*60}")

        # Get relevant members
        members = self.get_relevant_members(bill_description, chambers)
        logger.info(f"Found {len(members)} relevant members")

        # Predict positions
        positions = {}
        for member in members:
            prediction = self.predict_position(member, bill_description)
            positions[member["bioguide_id"]] = prediction

        # Tally votes
        vote_results = self.tally_votes(members, positions)

        logger.info(f"Results: {vote_results['yes_votes']} yes, {vote_results['no_votes']} no")
        logger.info(f"Bill {'PASSED' if vote_results['passed'] else 'FAILED'}")

        return {
            "bill_title": bill_title,
            "bill_description": bill_description,
            "chambers": chambers or ["House", "Senate"],
            "member_count": len(members),
            "member_positions": positions,
            "vote_results": vote_results
        }
