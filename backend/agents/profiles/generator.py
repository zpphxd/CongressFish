"""
Persona Generator
=================
Generates persona narratives for all agent types via Ollama LLM.

Uses prompt templates + profile data to generate behavioral profiles.
Results cached in profile JSON—only regenerate with --force flag.

No random generation—personas built from actual voting records, biographical data, etc.
"""

import os
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)


class PersonaGenerator:
    """Generates persona narratives for agents via LLM."""

    def __init__(self, llm_client):
        """
        Args:
            llm_client: LLM client (Ollama wrapper from backend/app/utils/llm_client.py)
        """
        self.llm_client = llm_client
        self.template_dir = os.path.join(
            os.path.dirname(__file__), '..', 'templates'
        )

    def _load_template(self, template_name: str) -> str:
        """Load prompt template from file."""
        template_path = os.path.join(self.template_dir, f'{template_name}.txt')
        try:
            with open(template_path, 'r') as f:
                return f.read()
        except FileNotFoundError:
            logger.error(f'Template not found: {template_path}')
            return ''

    def generate_congress_member_persona(
        self,
        profile,  # CongressMemberProfile
        force: bool = False,
    ) -> Optional[str]:
        """
        Generate persona narrative for a Congress member.

        Args:
            profile: CongressMemberProfile object
            force: If True, regenerate even if persona_narrative exists

        Returns:
            Generated persona text, or existing if not force and already generated
        """
        # Return existing if not forcing regeneration
        if profile.persona_narrative and not force:
            logger.debug(f'Using cached persona for {profile.full_name}')
            return profile.persona_narrative

        logger.info(f'Generating persona for {profile.full_name}...')

        template = self._load_template('congress_member_prompt')
        if not template:
            return None

        # Build committee list
        committee_names = ', '.join([c.committee_name for c in profile.committee_assignments[:3]])
        committee_chairs = ', '.join([c.committee_name for c in profile.committee_assignments if c.is_chair])

        # Build public positions from scorecards
        public_positions_text = ''
        if profile.scorecards:
            for scorecard in profile.scorecards[:3]:
                public_positions_text += f'- {scorecard.organization} Score ({scorecard.year}): {scorecard.score}\n'

        # Extract prior career from biography
        prior_career = profile.biography.occupation or 'Not available'

        # Build prompt
        prompt = template.format(
            name=profile.full_name,
            state=profile.state,
            chamber=profile.chamber.value,
            party=profile.party.value,
            district=profile.district or 'At-large',
            sponsored_bill_count=len(profile.sponsored_bills),
            cosponsored_bill_count=len(profile.cosponsored_bills),
            committees=committee_names or 'None',
            committee_chairs=committee_chairs or 'None',
            ideology_primary=round(profile.ideology.primary_dimension, 2) if profile.ideology.primary_dimension else 0,
            ideology_secondary=round(profile.ideology.secondary_dimension, 2) if profile.ideology.secondary_dimension else 0,
            party_loyalty_pct='Unknown',  # Would need to compute
            party_agreement_pct='Unknown',
            receipts=profile.campaign_finance.receipts if profile.campaign_finance else 0,
            disbursements=profile.campaign_finance.disbursements if profile.campaign_finance else 0,
            top_individual_donor='Unknown',  # Would extract from donors list
            top_pac_donor='Unknown',
            funding_vulnerability='Moderate',  # Would compute from finance data
            education=profile.biography.education or 'Not available',
            prior_career=prior_career,
            hometown=profile.biography.birth_place or 'Not available',
            years_service='Unknown',  # Would compute from terms
            previous_offices='Not available',  # Would pull from bio
            public_positions=public_positions_text or 'Not available',
        )

        # Call LLM
        try:
            persona_text = self.llm_client.generate(
                prompt=prompt,
                temperature=0.7,
                max_tokens=1200,
            )
            logger.info(f'Generated persona for {profile.full_name}')
            return persona_text
        except Exception as e:
            logger.error(f'Failed to generate persona for {profile.full_name}: {e}')
            return None

    def generate_justice_persona(
        self,
        profile,  # JusticeProfile
        force: bool = False,
    ) -> Optional[str]:
        """Generate persona narrative for a Supreme Court justice."""
        if profile.persona_narrative and not force:
            logger.debug(f'Using cached persona for {profile.name}')
            return profile.persona_narrative

        logger.info(f'Generating persona for Justice {profile.name}...')

        template = self._load_template('justice_prompt')
        if not template:
            return None

        # Build issue area breakdown
        issue_breakdown = ''
        for issue, count in list(profile.issue_area_votes.items())[:5]:
            issue_breakdown += f'- {issue}: {count} opinions\n'

        # Build voting alignment text
        allies = ', '.join(
            sorted(profile.voting_alignment_with_others.items(), key=lambda x: x[1], reverse=True)[:3]
        )

        prompt = template.format(
            name=profile.name,
            appointed_by=profile.appointed_by or 'Unknown',
            appointment_year=profile.appointment_date[:4] if profile.appointment_date else 'Unknown',
            years_on_court='Unknown',  # Would compute from term dates
            status='Current' if not profile.term_end else 'Retired',
            total_opinions=profile.total_opinions,
            majority_opinions=profile.majority_opinions,
            concurring_opinions=profile.concurring_opinions,
            dissenting_opinions=profile.dissenting_opinions,
            dissent_rate=round((profile.dissenting_opinions / profile.total_opinions * 100), 1) if profile.total_opinions else 0,
            strongest_allies=allies or 'Not computed',
            frequent_dissenters='Not computed',
            ideological_position='Center-left to center-right',  # Would infer from votes
            issue_area_breakdown=issue_breakdown or 'Not available',
            education=profile.biography.education or 'Not available',
            prior_career=profile.biography.occupation or 'Not available',
            hometown=profile.biography.birth_place or 'Not available',
            notable_cases_below='Not available',
            major_decisions='Not available',
        )

        try:
            persona_text = self.llm_client.generate(
                prompt=prompt,
                temperature=0.7,
                max_tokens=1200,
            )
            logger.info(f'Generated persona for Justice {profile.name}')
            return persona_text
        except Exception as e:
            logger.error(f'Failed to generate persona for Justice {profile.name}: {e}')
            return None

    def generate_executive_persona(
        self,
        profile,  # ExecutiveProfile
        force: bool = False,
    ) -> Optional[str]:
        """Generate persona narrative for an Executive branch official."""
        if profile.persona_narrative and not force:
            logger.debug(f'Using cached persona for {profile.full_name}')
            return profile.persona_narrative

        logger.info(f'Generating persona for {profile.full_name}...')

        template = self._load_template('executive_prompt')
        if not template:
            return None

        # Build policy positions text
        policy_text = ''
        for issue, position in list(profile.policy_positions.items())[:3]:
            policy_text += f'- {issue}: {position}\n'

        prompt = template.format(
            name=profile.full_name,
            title=profile.role,
            term_years='Current' if not profile.term_end else profile.term_end,
            appointed_by=profile.appointed_by or 'Not applicable',
            prior_role='Not available',
            education=profile.biography.education or 'Not available',
            career_path=profile.biography.occupation or 'Not available',
            expertise='Not available',
            government_service='Not available',
            key_initiatives='Not available',
            policy_areas=', '.join(profile.policy_positions.keys()) if profile.policy_positions else 'Not available',
            controversy_level='Low to moderate',
            media_presence='Active',
            reports_to='The President' if profile.role != 'President' else 'Electorate',
            congressional_allies='Not available',
            known_tensions='Not available',
            documented_positions=policy_text or 'Not available',
        )

        try:
            persona_text = self.llm_client.generate(
                prompt=prompt,
                temperature=0.7,
                max_tokens=1200,
            )
            logger.info(f'Generated persona for {profile.full_name}')
            return persona_text
        except Exception as e:
            logger.error(f'Failed to generate persona for {profile.full_name}: {e}')
            return None

    def generate_influence_org_persona(
        self,
        profile,  # InfluenceOrgProfile
        force: bool = False,
    ) -> Optional[str]:
        """Generate persona narrative for an influence organization."""
        if profile.persona_narrative and not force:
            logger.debug(f'Using cached persona for {profile.name}')
            return profile.persona_narrative

        logger.info(f'Generating persona for {profile.name}...')

        template = self._load_template('influence_org_prompt')
        if not template:
            return None

        # Build positions text
        positions_text = ''
        for issue, position in list(profile.positions_on_issues.items())[:3]:
            positions_text += f'- {issue}: {position}\n'

        prompt = template.format(
            name=profile.name,
            org_type=profile.org_type,
            founded_year='Not available',
            mission='Not available',
            total_raised=profile.total_raised or 0,
            total_spent=profile.total_spent or 0,
            cash_on_hand=profile.cash_on_hand or 0,
            funding_sources='Not available',
            top_recipients=', '.join([r.get('member') for r in profile.top_recipients[:3]]) if profile.top_recipients else 'Not available',
            committee_targets='Not available',
            lobbying_issues='Multiple',
            lobbying_spend=0,
            partisan_lean='Not determined',
            issue_areas=', '.join(profile.positions_on_issues.keys()) if profile.positions_on_issues else 'Not available',
            geographic_focus='National',
            allied_orgs='Not available',
            opposing_orgs='Not available',
            public_positions=positions_text or 'Not available',
        )

        try:
            persona_text = self.llm_client.generate(
                prompt=prompt,
                temperature=0.7,
                max_tokens=1200,
            )
            logger.info(f'Generated persona for {profile.name}')
            return persona_text
        except Exception as e:
            logger.error(f'Failed to generate persona for {profile.name}: {e}')
            return None
