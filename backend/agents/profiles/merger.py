"""
Profile Merger
==============
Merges data from all API sources into unified Pydantic profiles.

Takes output from all Phase 2 API clients (Congress.gov, Wikipedia, VoteView,
OpenFEC, Oyez, unitedstates YAML) and combines into CongressMemberProfile,
JusticeProfile, ExecutiveProfile, InfluenceOrgProfile.

No random generation—only explicit profiles from actual data.
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from .models import (
    CongressMemberProfile, JusticeProfile, ExecutiveProfile, InfluenceOrgProfile,
    Chamber, Party, IDCrossReference, BiographicalData, IdeologyScore,
    CampaignFinance, CommitteeAssignment, Scorecard, StockTrade,
)

logger = logging.getLogger(__name__)


class ProfileMerger:
    """Merges data from all API sources into unified profiles."""

    def __init__(self):
        """Initialize merger."""
        pass

    def merge_congress_member(
        self,
        unitedstates_record: Dict,  # From unitedstates_project.py
        congress_gov_member: Dict,  # From congress_gov.py get_member()
        congress_gov_detail: Dict,  # From congress_gov.py get_member() detailed endpoint
        wikipedia_bio: Optional[Dict],  # From wikipedia.py get_biography()
        voteview_member: Optional[Dict],  # From voteview.py get_members_119th_congress()
        openfec_totals: Optional[Dict],  # From openfec.py get_candidate_totals()
        openfec_top_donors: Optional[Dict],  # From openfec.py get_top_donors_individual()
        openfec_top_pacs: Optional[Dict],  # From openfec.py get_top_donors_pac()
        stock_trades: Optional[List[Dict]] = None,  # From stock_trades.py (future)
        scorecards: Optional[List[Dict]] = None,  # From scorecards.py (future)
        voting_alignment: Optional[Dict[str, float]] = None,  # From voteview or congress voting records
    ) -> Optional[CongressMemberProfile]:
        """
        Merge all data sources for a Congress member into unified profile.

        Args:
            All dictionaries from respective API clients

        Returns:
            CongressMemberProfile or None if critical data missing
        """
        try:
            # Extract from Congress.gov
            bioguide_id = congress_gov_member.get('bioguideId')
            if not bioguide_id:
                logger.warning('Missing bioguideId in Congress.gov data')
                return None

            # Get current term from Congress.gov
            terms = congress_gov_member.get('terms', {})
            term_items = terms.get('item', [])
            if not term_items:
                logger.warning(f'No terms found for {bioguide_id}')
                return None

            current_term = term_items[-1]  # Last term is current
            chamber_str = current_term.get('chamber', '').lower()
            if 'senate' in chamber_str:
                chamber = Chamber.SENATE
                district = None
            else:
                chamber = Chamber.HOUSE
                district = current_term.get('district')

            # Parse basic info
            full_name = congress_gov_member.get('name', '')
            name_parts = full_name.split(', ')
            if len(name_parts) == 2:
                last_name, first_name = name_parts
            else:
                first_name = full_name.split()[0] if full_name else ''
                last_name = ' '.join(full_name.split()[1:]) if len(full_name.split()) > 1 else ''

            state = congress_gov_member.get('state', '')
            party_str = congress_gov_member.get('partyName', '').upper()
            party = self._parse_party(party_str)

            # Build ID cross-reference from unitedstates record
            ids = self._build_id_cross_reference(bioguide_id, unitedstates_record)

            # Extract biography from Wikipedia
            biography = self._extract_biography(wikipedia_bio)

            # Extract ideology scores
            ideology = self._extract_ideology(voteview_member)

            # Extract social media
            twitter = None
            facebook = None
            youtube = None
            contact_form = congress_gov_detail.get('contact_form') if congress_gov_detail else None
            official_website = congress_gov_detail.get('url') if congress_gov_detail else None

            # Extract campaign finance
            campaign_finance = None
            if openfec_totals:
                campaign_finance = CampaignFinance(
                    cycle=openfec_totals.get('cycle', 2024),
                    receipts=float(openfec_totals.get('receipts', 0)),
                    disbursements=float(openfec_totals.get('disbursements', 0)),
                    cash_on_hand=float(openfec_totals.get('cash_on_hand', 0)),
                    loans=float(openfec_totals.get('loans_received', 0)),
                    candidate_contribution=float(openfec_totals.get('candidate_contribution', 0)),
                    top_individual_donors=openfec_top_donors or [],
                    top_pac_donors=openfec_top_pacs or [],
                )

            # Extract stock trades
            stock_trades_list = []
            if stock_trades:
                stock_trades_list = [
                    StockTrade(**trade) for trade in stock_trades
                ]

            # Extract scorecards
            scorecards_list = []
            if scorecards:
                scorecards_list = [
                    Scorecard(**scorecard) for scorecard in scorecards
                ]

            # Extract committee assignments from Congress.gov detail
            committee_assignments = []
            if congress_gov_detail:
                committees = congress_gov_detail.get('committees', [])
                for committee in committees:
                    try:
                        assignment = CommitteeAssignment(
                            committee_code=committee.get('code', ''),
                            committee_name=committee.get('name', ''),
                            chamber=committee.get('chamber', '').lower(),
                            rank=committee.get('rank'),
                            is_chair=committee.get('isChair', False),
                            is_ranking_member=committee.get('isRankingMember', False),
                        )
                        committee_assignments.append(assignment)
                    except Exception as e:
                        logger.warning(f'Failed to parse committee {committee}: {e}')

            # Build final profile
            data_sources = ['congress_gov', 'unitedstates']
            if wikipedia_bio:
                data_sources.append('wikipedia')
            if voteview_member:
                data_sources.append('voteview')
            if openfec_totals:
                data_sources.append('openfec')
            if stock_trades:
                data_sources.append('stock_trades')
            if scorecards:
                data_sources.append('scorecards')

            profile = CongressMemberProfile(
                bioguide_id=bioguide_id,
                full_name=full_name,
                first_name=first_name,
                last_name=last_name,
                chamber=chamber,
                state=state,
                district=int(district) if district and district.isdigit() else None,
                party=party,
                ids=ids,
                biography=biography,
                ideology=ideology,
                twitter=twitter,
                facebook=facebook,
                youtube=youtube,
                contact_form=contact_form,
                official_website=official_website,
                committee_assignments=committee_assignments,
                campaign_finance=campaign_finance,
                stock_trades=stock_trades_list,
                scorecards=scorecards_list,
                voting_alignment_with_others=voting_alignment or {},
                data_sources=data_sources,
            )

            return profile

        except Exception as e:
            logger.error(f'Failed to merge congress member profile: {e}')
            return None

    def merge_justice(
        self,
        oyez_justice: Dict,  # From oyez.py get_justice_detail()
        oyez_votes: Optional[List[Dict]],  # From oyez.py get_justice_votes()
        wikipedia_bio: Optional[Dict],  # From wikipedia.py
        voting_alignment: Optional[Dict[str, float]] = None,  # Justice-to-justice agreement
    ) -> Optional[JusticeProfile]:
        """
        Merge all data sources for a Supreme Court justice.

        Args:
            All dictionaries from respective API clients

        Returns:
            JusticeProfile or None if critical data missing
        """
        try:
            oyez_id = oyez_justice.get('id')
            if not oyez_id:
                logger.warning('Missing oyez ID in justice data')
                return None

            name = oyez_justice.get('name', '')
            biography = self._extract_biography(wikipedia_bio)
            ideology = self._extract_ideology_from_votes(oyez_votes) if oyez_votes else IdeologyScore()

            # Parse opinion counts from votes
            total_opinions = len(oyez_votes) if oyez_votes else 0
            majority_count = sum(1 for v in (oyez_votes or []) if v.get('opinion_type') == 'majority')
            concurring_count = sum(1 for v in (oyez_votes or []) if v.get('opinion_type') == 'concurring')
            dissenting_count = sum(1 for v in (oyez_votes or []) if v.get('opinion_type') == 'dissenting')

            profile = JusticeProfile(
                name=name,
                oyez_id=oyez_id,
                biography=biography,
                birth_date=oyez_justice.get('birth_date'),
                death_date=oyez_justice.get('death_date'),
                appointed_by=oyez_justice.get('appointed_by'),
                appointment_date=oyez_justice.get('appointment_date'),
                term_start=oyez_justice.get('term_start'),
                term_end=oyez_justice.get('term_end'),
                ideology=ideology,
                total_opinions=total_opinions,
                majority_opinions=majority_count,
                concurring_opinions=concurring_count,
                dissenting_opinions=dissenting_count,
                voting_alignment_with_others=voting_alignment or {},
                data_sources=['oyez', 'wikipedia'],
            )

            return profile

        except Exception as e:
            logger.error(f'Failed to merge justice profile: {e}')
            return None

    def merge_executive(
        self,
        name: str,
        role: str,  # "President", "Vice President", "Secretary of State", etc.
        wikipedia_bio: Optional[Dict] = None,
        policy_positions: Optional[Dict[str, str]] = None,
    ) -> Optional[ExecutiveProfile]:
        """
        Merge data for Executive branch official.

        Args:
            name: Full name
            role: Official role/title
            wikipedia_bio: Wikipedia biography data
            policy_positions: Manually defined policy positions

        Returns:
            ExecutiveProfile or None if critical data missing
        """
        try:
            if not name or not role:
                logger.warning('Missing name or role for executive profile')
                return None

            biography = self._extract_biography(wikipedia_bio) if wikipedia_bio else BiographicalData()

            profile = ExecutiveProfile(
                full_name=name,
                role=role,
                biography=biography,
                policy_positions=policy_positions or {},
                data_sources=['manual', 'wikipedia'] if wikipedia_bio else ['manual'],
            )

            return profile

        except Exception as e:
            logger.error(f'Failed to merge executive profile: {e}')
            return None

    def merge_influence_org(
        self,
        name: str,
        org_type: str,  # "PAC", "advocacy_group", etc.
        total_raised: Optional[float] = None,
        total_spent: Optional[float] = None,
        top_recipients: Optional[List[Dict]] = None,
        positions_on_issues: Optional[Dict[str, str]] = None,
    ) -> Optional[InfluenceOrgProfile]:
        """
        Merge data for influence organization.

        Args:
            name: Organization name
            org_type: Type of organization
            total_raised: Total funds raised
            total_spent: Total funds spent
            top_recipients: List of top donation recipients
            positions_on_issues: Position statements on issues

        Returns:
            InfluenceOrgProfile or None if critical data missing
        """
        try:
            if not name or not org_type:
                logger.warning('Missing name or org_type for influence org profile')
                return None

            profile = InfluenceOrgProfile(
                name=name,
                org_type=org_type,
                total_raised=total_raised,
                total_spent=total_spent,
                top_recipients=top_recipients or [],
                positions_on_issues=positions_on_issues or {},
                data_sources=['openfec', 'opensecrets'],
            )

            return profile

        except Exception as e:
            logger.error(f'Failed to merge influence org profile: {e}')
            return None

    # Private helper methods

    def _parse_party(self, party_str: str) -> Party:
        """Parse party string to Party enum."""
        party_str = party_str.upper().strip()
        if party_str.startswith('R'):
            return Party.REPUBLICAN
        elif party_str.startswith('D'):
            return Party.DEMOCRAT
        elif party_str.startswith('I'):
            return Party.INDEPENDENT
        else:
            return Party.OTHER

    def _build_id_cross_reference(self, bioguide_id: str, unitedstates_record: Dict) -> IDCrossReference:
        """Build ID cross-reference from unitedstates data."""
        ids_data = unitedstates_record.get('ids', {}) if unitedstates_record else {}

        return IDCrossReference(
            bioguide_id=bioguide_id,
            fec_id=ids_data.get('fec_id'),
            opensecrets_id=ids_data.get('opensecrets_id'),
            govtrack_id=ids_data.get('govtrack_id'),
            votesmart_id=ids_data.get('votesmart_id'),
            ballotpedia_id=ids_data.get('ballotpedia_id'),
            wikipedia_id=ids_data.get('wikipedia_id'),
            wikidata_id=ids_data.get('wikidata_id'),
            thomas_id=ids_data.get('thomas_id'),
        )

    def _extract_biography(self, wikipedia_bio: Optional[Dict]) -> BiographicalData:
        """Extract biography from Wikipedia data."""
        if not wikipedia_bio:
            return BiographicalData()

        return BiographicalData(
            birth_date=wikipedia_bio.get('birth_date'),
            birth_place=wikipedia_bio.get('birth_place'),
            death_date=None,  # Wikipedia doesn't provide in our scraper
            education=wikipedia_bio.get('education'),
            occupation=wikipedia_bio.get('occupation'),
            wikipedia_summary=wikipedia_bio.get('extract'),
            wikipedia_full_text=wikipedia_bio.get('full_text'),
        )

    def _extract_ideology(self, voteview_member: Optional[Dict]) -> IdeologyScore:
        """Extract ideology scores from VoteView data."""
        if not voteview_member:
            return IdeologyScore()

        return IdeologyScore(
            primary_dimension=voteview_member.get('dw_nominate_dim1'),
            secondary_dimension=voteview_member.get('dw_nominate_dim2'),
            source='voteview',
            year=2024,  # Latest Congress
        )

    def _extract_ideology_from_votes(self, oyez_votes: List[Dict]) -> IdeologyScore:
        """Estimate ideology from Supreme Court voting patterns."""
        # Simplified: count dissents vs majority votes
        # More dissents = more likely to be ideological outlier
        if not oyez_votes:
            return IdeologyScore()

        dissents = sum(1 for v in oyez_votes if v.get('opinion_type') == 'dissenting')
        total = len(oyez_votes)

        if total == 0:
            return IdeologyScore()

        # Map dissent rate to ideological dimension (-1 to 1)
        dissent_rate = dissents / total
        ideology_score = (dissent_rate * 2) - 1  # Range: -1 to 1

        return IdeologyScore(
            primary_dimension=ideology_score,
            secondary_dimension=None,
            source='oyez_voting_patterns',
            year=2024,
        )


async def main():
    """Test the merger."""
    merger = ProfileMerger()

    # Example: merge a congress member
    # This would use real data from API clients in production
    print('\n=== Testing Profile Merger ===')
    print('Merger ready to combine data from all API sources')
    print('See backend/agents/build.py for orchestration of full merge process')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    import asyncio
    asyncio.run(main())
