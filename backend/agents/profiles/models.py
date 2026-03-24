"""
CongressFish Agent Profile Models
==================================
Pydantic models for all agent types: Congress members, SCOTUS justices,
Executive branch officials, and Influence organizations.

These are unified representations after merging data from all API sources.
No random generation—only explicit profiles from real data sources.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum


class Chamber(str, Enum):
    """Legislative chamber."""
    HOUSE = "house"
    SENATE = "senate"


class Party(str, Enum):
    """Political party."""
    REPUBLICAN = "R"
    DEMOCRAT = "D"
    INDEPENDENT = "I"
    OTHER = "O"


@dataclass
class IDCrossReference:
    """Cross-reference IDs across all systems for a single person."""
    bioguide_id: str
    fec_id: Optional[str] = None
    opensecrets_id: Optional[str] = None
    govtrack_id: Optional[str] = None
    votesmart_id: Optional[str] = None
    ballotpedia_id: Optional[str] = None
    wikipedia_id: Optional[str] = None
    wikidata_id: Optional[str] = None
    thomas_id: Optional[str] = None


@dataclass
class BiographicalData:
    """Biographical background extracted from Wikipedia and other sources."""
    birth_date: Optional[str] = None
    birth_place: Optional[str] = None
    death_date: Optional[str] = None
    education: Optional[str] = None
    occupation: Optional[str] = None
    wikipedia_summary: Optional[str] = None
    wikipedia_full_text: Optional[str] = None


@dataclass
class IdeologyScore:
    """Ideology positioning (DW-NOMINATE or similar)."""
    primary_dimension: Optional[float] = None  # dim1: left-right
    secondary_dimension: Optional[float] = None  # dim2: expansion
    source: Optional[str] = None  # "voteview", "manifesto", etc.
    year: Optional[int] = None


@dataclass
class StockTrade:
    """STOCK Act disclosure."""
    trade_date: str
    stock_symbol: str
    issuer: str
    transaction_type: str  # "buy", "sell", "exchange"
    amount_range: str  # "$1,001 - $15,000", etc.
    committee: Optional[str] = None  # Committee assignment context


@dataclass
class CampaignFinance:
    """Campaign finance data for an election cycle."""
    cycle: int
    receipts: float
    disbursements: float
    cash_on_hand: float
    loans: float
    candidate_contribution: float
    top_individual_donors: List[Dict[str, Any]] = field(default_factory=list)
    top_pac_donors: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class Scorecard:
    """Voting scorecard from an advocacy organization."""
    organization: str
    score: float  # Usually 0-100
    year: int
    issue_area: Optional[str] = None


@dataclass
class CommitteeAssignment:
    """Committee membership for a Congress member."""
    committee_code: str
    committee_name: str
    chamber: str
    rank: Optional[int] = None  # Seniority rank on committee
    is_chair: bool = False
    is_ranking_member: bool = False
    subcommittees: List[Dict] = field(default_factory=list)


@dataclass
class CongressMemberProfile:
    """
    Complete profile for a United States Congress member.

    No random generation—only explicit profiles built from real data sources:
    - Congress.gov API
    - unitedstates/congress-legislators YAML
    - Wikipedia biographies
    - VoteView ideology scores
    - OpenFEC campaign finance
    - STOCK Act disclosures
    - Advocacy organization scorecards
    """
    # Identity
    bioguide_id: str
    full_name: str
    first_name: str
    last_name: str

    # Current term
    chamber: Chamber
    state: str
    district: Optional[int] = None  # None for senators
    party: Party

    # IDs across all systems
    ids: IDCrossReference = field(default_factory=lambda: IDCrossReference(""))

    # Biographical data
    biography: BiographicalData = field(default_factory=BiographicalData)

    # Ideology positioning
    ideology: IdeologyScore = field(default_factory=IdeologyScore)

    # Social media
    twitter: Optional[str] = None
    facebook: Optional[str] = None
    youtube: Optional[str] = None
    contact_form: Optional[str] = None
    official_website: Optional[str] = None

    # Legislative activity
    sponsored_bills: List[Dict[str, Any]] = field(default_factory=list)
    cosponsored_bills: List[Dict[str, Any]] = field(default_factory=list)
    committee_assignments: List[CommitteeAssignment] = field(default_factory=list)

    # Campaign finance (most recent cycle)
    campaign_finance: Optional[CampaignFinance] = None

    # Stock trades (STOCK Act disclosures)
    stock_trades: List[StockTrade] = field(default_factory=list)

    # Voting scorecards
    scorecards: List[Scorecard] = field(default_factory=list)

    # Voting patterns & alignment
    voting_alignment_with_others: Dict[str, float] = field(default_factory=dict)  # bioguide_id → agreement %

    # Generated persona (only if --force or first generation)
    persona_narrative: Optional[str] = None

    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    data_sources: List[str] = field(default_factory=list)  # ["congress_gov", "voteview", "wikipedia", ...]


@dataclass
class JusticeProfile:
    """
    Complete profile for a Supreme Court justice.

    Data sources:
    - Oyez API (justice profiles, voting records)
    - Wikipedia biographies
    - Judicial voting alignment
    """
    # Identity
    name: str
    oyez_id: str

    # Biographical data
    biography: BiographicalData = field(default_factory=BiographicalData)

    # Current/former Court status
    birth_date: Optional[str] = None
    death_date: Optional[str] = None
    appointed_by: Optional[str] = None  # President name
    appointment_date: Optional[str] = None
    term_start: Optional[str] = None
    term_end: Optional[str] = None

    # Ideology positioning (from voting patterns)
    ideology: IdeologyScore = field(default_factory=IdeologyScore)

    # Voting record & alignment
    total_opinions: int = 0
    majority_opinions: int = 0
    concurring_opinions: int = 0
    dissenting_opinions: int = 0
    voting_alignment_with_others: Dict[str, float] = field(default_factory=dict)  # justice_name → agreement %

    # Opinion topics/issue areas
    issue_area_votes: Dict[str, int] = field(default_factory=dict)  # "criminal_procedure" → count

    # Generated persona
    persona_narrative: Optional[str] = None

    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    data_sources: List[str] = field(default_factory=list)


@dataclass
class ExecutiveProfile:
    """
    Profile for Executive branch official (President, VP, Cabinet, etc.).

    Data sources:
    - Federal Register API
    - Manual biographical data
    - Policy position documents
    """
    # Identity
    full_name: str
    role: str  # "President", "Vice President", "Secretary of State", etc.

    # Biographical data
    biography: BiographicalData = field(default_factory=BiographicalData)

    # Current term
    term_start: Optional[str] = None
    term_end: Optional[str] = None
    appointed_by: Optional[str] = None  # President name (for Cabinet)

    # Policy positions (manually defined per role)
    policy_positions: Dict[str, str] = field(default_factory=dict)  # "healthcare" → "position text"

    # Notable executive orders / actions
    major_actions: List[Dict[str, Any]] = field(default_factory=list)

    # Social media
    twitter: Optional[str] = None
    official_website: Optional[str] = None

    # Generated persona
    persona_narrative: Optional[str] = None

    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    data_sources: List[str] = field(default_factory=list)


@dataclass
class InfluenceOrgProfile:
    """
    Profile for influence organization (PAC, advocacy group, lobbying firm, etc.).

    Data sources:
    - OpenFEC PAC records
    - OpenSecrets lobbying data (future)
    - Scorecard organization data
    """
    # Identity
    name: str
    org_type: str  # "PAC", "advocacy_group", "lobbying_firm", "industry_association", etc.

    # Financial data
    total_raised: Optional[float] = None
    total_spent: Optional[float] = None
    cash_on_hand: Optional[float] = None

    # Lobbying activity
    top_lobbying_issues: List[Dict[str, Any]] = field(default_factory=list)  # {issue, amount, year}
    members_lobbied: List[Dict[str, Any]] = field(default_factory=list)  # {member_bioguide, amount, date}
    committees_targeted: List[Dict[str, Any]] = field(default_factory=list)

    # Funding & donations
    top_recipients: List[Dict[str, Any]] = field(default_factory=list)  # {member, amount}
    primary_funding_sources: List[Dict[str, Any]] = field(default_factory=list)

    # Issue positions & scorecards (if org is advocacy)
    positions_on_issues: Dict[str, str] = field(default_factory=dict)  # "climate" → "position text"

    # Social media & contact
    website: Optional[str] = None
    twitter: Optional[str] = None
    email: Optional[str] = None

    # Generated persona
    persona_narrative: Optional[str] = None

    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    data_sources: List[str] = field(default_factory=list)


# Utility functions for serialization
def congress_member_to_dict(profile: CongressMemberProfile) -> Dict:
    """Convert CongressMemberProfile to dict for JSON serialization."""
    return asdict(profile)


def justice_to_dict(profile: JusticeProfile) -> Dict:
    """Convert JusticeProfile to dict for JSON serialization."""
    return asdict(profile)


def executive_to_dict(profile: ExecutiveProfile) -> Dict:
    """Convert ExecutiveProfile to dict for JSON serialization."""
    return asdict(profile)


def influence_org_to_dict(profile: InfluenceOrgProfile) -> Dict:
    """Convert InfluenceOrgProfile to dict for JSON serialization."""
    return asdict(profile)
