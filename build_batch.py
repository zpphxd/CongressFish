#!/usr/bin/env python3
"""
Simple batch builder: Download data from APIs and save as JSON profiles.
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

async def build_congress_batch(chamber: str, limit: int = None):
    """Download members from Congress.gov and save profiles."""
    logger.info(f'Building {chamber.upper()} member profiles...\n')

    # Ensure directories exist
    AgentsConfig.ensure_directories_exist()

    # Initialize client
    congress_client = CongressGovClient(
        api_key=AgentsConfig.CONGRESS_GOV_API_KEY,
        cache_dir=AgentsConfig.CACHE_DIR,
    )

    # Fetch members
    logger.info(f'Fetching {chamber} members from Congress.gov...')
    try:
        members = await congress_client.get_members(congress=119, chamber=chamber)
    except Exception as e:
        logger.error(f'Failed to fetch members: {e}')
        return 0

    if not members:
        logger.error('No members returned')
        return 0

    if limit:
        members = members[:limit]

    logger.info(f'Got {len(members)} members\n')

    # Map chamber and party
    chamber_enum = Chamber.SENATE if chamber == 'senate' else Chamber.HOUSE

    # Save each as a basic profile
    # The API returns mixed historical data. Just filter by chamber.
    # The congress=119 parameter was for the API, but it returns all members.
    current_members = []
    for m in members:
        terms = m.get('terms', {}).get('item', [])
        if terms:
            last_term = terms[-1]
            # Check last term's chamber
            last_chamber = last_term.get('chamber', '').lower()
            requested = chamber.lower()

            if (requested == 'senate' and 'senate' in last_chamber) or \
               (requested == 'house' and 'house' in last_chamber):
                current_members.append(m)

    logger.info(f'Found {len(current_members)} {chamber.upper()} members (all-time, API limitation)\n')

    count = 0
    for member in current_members:
        try:
            bioguide_id = member.get('bioguideId')

            # Parse name from "Last, First" format
            full_name = member.get('name', '')
            if ',' in full_name:
                parts = full_name.split(',')
                last_name = parts[0].strip()
                first_name = parts[1].strip() if len(parts) > 1 else ''
            else:
                first_name = ''
                last_name = full_name

            state = member.get('state', '').upper()

            # Parse party from partyName
            party_name = member.get('partyName', 'Independent')
            if 'Republican' in party_name:
                party = Party.REPUBLICAN
            elif 'Democratic' in party_name or 'Democrat' in party_name:
                party = Party.DEMOCRAT
            elif 'Independent' in party_name:
                party = Party.INDEPENDENT
            else:
                party = Party.OTHER

            # Get district and verify this member is in current Congress
            district = None
            terms_data = member.get('terms', {})
            terms_list = terms_data.get('item', []) if isinstance(terms_data, dict) else terms_data

            # Get district if available (for House members)
            if chamber == 'house' and terms_list:
                # Most recent term
                most_recent = terms_list[-1] if isinstance(terms_list, list) else None
                if most_recent and 'district' in most_recent:
                    try:
                        district = int(most_recent['district'])
                    except:
                        pass

            # Create minimal profile (API data only, no merging)
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
            )

            # Determine output directory
            if chamber == 'senate':
                output_dir = AgentsConfig.CONGRESS_SENATE_PERSONAS_DIR
            else:
                output_dir = AgentsConfig.CONGRESS_HOUSE_PERSONAS_DIR

            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, f'{bioguide_id}.json')

            # Save
            profile_dict = profile.__dict__
            # Convert enums to strings
            profile_dict['chamber'] = profile.chamber.value
            profile_dict['party'] = profile.party.value
            # Convert nested dataclass
            if hasattr(profile_dict['ids'], '__dict__'):
                profile_dict['ids'] = profile_dict['ids'].__dict__

            with open(output_path, 'w') as f:
                json.dump(profile_dict, f, indent=2, default=str)

            logger.info(f'✓ {full_name} ({bioguide_id})')
            count += 1

        except Exception as e:
            logger.warning(f'✗ Error processing member: {e}')

    logger.info(f'\n✓ Saved {count}/{len(current_members)} profiles to {output_dir}')
    return count

if __name__ == '__main__':
    import asyncio
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--chamber', choices=['senate', 'house'], default='senate')
    parser.add_argument('--limit', type=int, help='Limit number of members')
    args = parser.parse_args()

    count = asyncio.run(build_congress_batch(args.chamber, args.limit))
    sys.exit(0 if count > 0 else 1)
