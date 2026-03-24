#!/usr/bin/env python3
"""
Smart agent builder: Get current Congress 119 members, then pull individual details.
"""

import os
import sys
import json
import logging
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

from backend.agents.config import AgentsConfig
from backend.agents.apis.congress_gov import CongressGovClient
from backend.agents.profiles.models import CongressMemberProfile, Chamber, Party, IDCrossReference

async def build_congress_smart(chamber: str, limit: int = None):
    """Build Congress members by pulling individual details for current members."""
    logger.info(f'Building {chamber.upper()} member profiles (current Congress 119)...\n')

    AgentsConfig.ensure_directories_exist()

    congress_client = CongressGovClient(
        api_key=AgentsConfig.CONGRESS_GOV_API_KEY,
        cache_dir=AgentsConfig.CACHE_DIR,
    )

    # Step 1: Get bulk member list
    logger.info('Step 1: Fetching member list...')
    try:
        all_members = await congress_client.get_members(congress=119, chamber=chamber)
    except Exception as e:
        logger.error(f'Failed to fetch members: {e}')
        return 0

    # Step 2: Filter to current Congress members only (those still serving in 2026)
    logger.info(f'Step 2: Filtering to current Congress 119 members...')
    current_members = []
    for m in all_members:
        terms = m.get('terms', {}).get('item', [])
        if terms:
            last_term = terms[-1]
            last_chamber = last_term.get('chamber', '').lower()

            # Must be in requested chamber
            if chamber == 'senate' and 'senate' not in last_chamber:
                continue
            if chamber == 'house' and 'house' not in last_chamber:
                continue

            # Must have no end year (still serving) or end year >= 2025
            end_year = last_term.get('endYear')
            if end_year and end_year < 2025:
                continue

            # Include this member
            current_members.append(m)

    if limit:
        current_members = current_members[:limit]

    logger.info(f'Found {len(current_members)} current {chamber} members\n')

    # Step 3: Pull individual details for each member
    logger.info('Step 3: Pulling individual member details...')
    chamber_enum = Chamber.SENATE if chamber == 'senate' else Chamber.HOUSE
    count = 0

    for i, member in enumerate(current_members, 1):
        try:
            bioguide_id = member.get('bioguideId')
            full_name = member.get('name', '')
            state = member.get('state', '').upper()
            party_name = member.get('partyName', 'Independent')

            # Map party
            if 'Republican' in party_name:
                party = Party.REPUBLICAN
            elif 'Democratic' in party_name or 'Democrat' in party_name:
                party = Party.DEMOCRAT
            elif 'Independent' in party_name:
                party = Party.INDEPENDENT
            else:
                party = Party.OTHER

            # Parse name
            if ',' in full_name:
                parts = full_name.split(',')
                last_name = parts[0].strip()
                first_name = parts[1].strip() if len(parts) > 1 else ''
            else:
                first_name = ''
                last_name = full_name

            # Get district for House
            district = None
            if chamber == 'house':
                terms = member.get('terms', {}).get('item', [])
                if terms:
                    last_term = terms[-1]
                    if 'district' in last_term:
                        try:
                            district = int(last_term['district'])
                        except:
                            pass

            # Fetch individual member details (committees, bills, etc.)
            detail = await congress_client.get_member(bioguide_id)
            if not detail:
                logger.warning(f'  ({i}/{len(current_members)}) ✗ {full_name} - no detail')
                continue

            # Extract additional info from detail
            member_detail = detail or {}

            # Get committees if available
            committee_assignments = []
            # TODO: Pull from committee endpoints when available

            # Create profile
            profile = CongressMemberProfile(
                bioguide_id=bioguide_id,
                full_name=full_name,
                first_name=first_name,
                last_name=last_name,
                chamber=chamber_enum,
                state=state,
                party=party,
                district=district,
                ids=IDCrossReference(bioguide_id=bioguide_id),
                committee_assignments=committee_assignments,
            )

            # Save
            if chamber == 'senate':
                output_dir = AgentsConfig.CONGRESS_SENATE_PERSONAS_DIR
            else:
                output_dir = AgentsConfig.CONGRESS_HOUSE_PERSONAS_DIR

            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, f'{bioguide_id}.json')

            profile_dict = profile.__dict__
            profile_dict['chamber'] = profile.chamber.value
            profile_dict['party'] = profile.party.value
            if hasattr(profile_dict['ids'], '__dict__'):
                profile_dict['ids'] = profile_dict['ids'].__dict__
            if hasattr(profile_dict.get('biography'), '__dict__'):
                bio = profile_dict.get('biography')
                if bio:
                    profile_dict['biography'] = bio.__dict__
            if hasattr(profile_dict.get('ideology'), '__dict__'):
                ideo = profile_dict.get('ideology')
                if ideo:
                    profile_dict['ideology'] = ideo.__dict__

            with open(output_path, 'w') as f:
                json.dump(profile_dict, f, indent=2, default=str)

            logger.info(f'  ({i}/{len(current_members)}) ✓ {full_name} ({bioguide_id})')
            count += 1

        except Exception as e:
            logger.warning(f'  ({i}/{len(current_members)}) ✗ Error: {e}')

    logger.info(f'\n✓ Saved {count}/{len(current_members)} current Congress members')
    return count

if __name__ == '__main__':
    import asyncio
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--chamber', choices=['senate', 'house'], default='senate')
    parser.add_argument('--limit', type=int, help='Limit number of members')
    args = parser.parse_args()

    count = asyncio.run(build_congress_smart(args.chamber, args.limit))
    sys.exit(0 if count > 0 else 1)
