"""
United States Congress Legislators GitHub Data
===============================================
Download and parse the unitedstates/congress-legislators YAML files.
This provides the canonical cross-reference mapping between different
ID systems (bioguide, FEC, OpenSecrets, GovTrack, VoteSmart, Thomas).

Source: https://github.com/unitedstates/congress-legislators

Files used:
  - legislators-current.yaml: All current members with full ID cross-reference
  - committees-current.yaml: Committee names and jurisdiction codes
  - committee-membership-current.yaml: Current committee assignments
"""

import os
import yaml
import aiohttp
import asyncio
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class IDCrossReference:
    """Complete ID mapping for a Congress member across all systems."""
    bioguide_id: str
    thomas_id: Optional[str] = None
    fec_id: Optional[str] = None
    opensecrets_id: Optional[str] = None  # CRP ID
    govtrack_id: Optional[str] = None
    votesmart_id: Optional[str] = None
    ballotpedia_id: Optional[str] = None
    wikipedia_id: Optional[str] = None
    wikidata_id: Optional[str] = None

    def to_dict(self) -> Dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class LegislatorTerms:
    """Term information for a member."""
    chamber: str  # 'senate' or 'house'
    state: str
    party: str  # 'R', 'D', 'I', etc.
    start: str  # YYYY-MM-DD
    end: str    # YYYY-MM-DD
    district: Optional[str] = None  # None for senators


@dataclass
class LegislatorRecord:
    """Complete record for a current Congress member from unitedstates data."""
    bioguide_id: str
    first_name: str
    last_name: str
    full_name: str
    date_of_birth: Optional[str]
    gender: Optional[str]
    ids: IDCrossReference
    terms: List[LegislatorTerms]

    # Social media
    twitter: Optional[str] = None
    facebook: Optional[str] = None
    youtube: Optional[str] = None
    contact_form: Optional[str] = None
    official_website: Optional[str] = None


class UnitedStatesProjectClient:
    """
    Downloads and manages unitedstates/congress-legislators YAML data.

    This is the source of truth for ID cross-referencing. All other API clients
    join their data through bioguide_id using this mapping.
    """

    REPO_BASE_URL = 'https://raw.githubusercontent.com/unitedstates/congress-legislators/main'

    # Key files we use
    FILES = {
        'legislators-current': f'{REPO_BASE_URL}/legislators-current.yaml',
        'committees-current': f'{REPO_BASE_URL}/committees-current.yaml',
        'committee-membership-current': f'{REPO_BASE_URL}/committee-membership-current.yaml',
    }

    def __init__(self, cache_dir: str):
        """
        Args:
            cache_dir: Directory to cache downloaded YAML files
        """
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    async def download_file(self, file_key: str) -> Dict:
        """Download and parse a YAML file from GitHub."""
        cache_path = os.path.join(self.cache_dir, f'{file_key}.yaml')

        # Check if cached
        if os.path.exists(cache_path):
            logger.info(f'Loading cached {file_key} from {cache_path}')
            with open(cache_path, 'r') as f:
                return yaml.safe_load(f)

        # Download
        url = self.FILES[file_key]
        logger.info(f'Downloading {file_key} from {url}')

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        raise ValueError(f'Failed to download {file_key}: {resp.status}')

                    content = await resp.text()
                    data = yaml.safe_load(content)

                    # Cache it
                    with open(cache_path, 'w') as f:
                        f.write(content)

                    logger.info(f'Cached {file_key} to {cache_path}')
                    return data

        except Exception as e:
            logger.error(f'Failed to download {file_key}: {e}')
            raise

    async def get_current_members(self) -> Dict[str, LegislatorRecord]:
        """
        Download legislators-current.yaml and parse all members.

        Returns:
            Dict mapping bioguide_id → LegislatorRecord
        """
        data = await self.download_file('legislators-current')

        members = {}
        for member_dict in data:
            # Parse basic info
            bio = member_dict.get('bio', {})
            ids = member_dict.get('id', {})
            terms = member_dict.get('terms', [])

            # Get current term (last one in list)
            if not terms:
                logger.warning(f"Member {bio.get('name')} has no terms, skipping")
                continue

            current_term = terms[-1]
            chamber = current_term.get('type')  # 'sen' or 'rep'

            # Normalize chamber
            if chamber == 'sen':
                chamber = 'senate'
            elif chamber == 'rep':
                chamber = 'house'
            else:
                logger.warning(f"Unknown chamber type: {chamber}")
                continue

            bioguide_id = ids.get('bioguide')
            if not bioguide_id:
                logger.warning(f"Member {bio.get('name')} has no bioguide_id, skipping")
                continue

            # Parse all terms
            parsed_terms = []
            for term in terms:
                parsed_terms.append(LegislatorTerms(
                    chamber='senate' if term.get('type') == 'sen' else 'house',
                    state=term.get('state'),
                    district=term.get('district'),
                    party=term.get('party'),
                    start=term.get('start'),
                    end=term.get('end'),
                ))

            # Build ID cross-reference
            id_cross_ref = IDCrossReference(
                bioguide_id=bioguide_id,
                thomas_id=ids.get('thomas'),
                fec_id=ids.get('fec'),
                opensecrets_id=ids.get('opensecrets'),
                govtrack_id=ids.get('govtrack'),
                votesmart_id=ids.get('votesmart'),
                ballotpedia_id=ids.get('ballotpedia'),
                wikipedia_id=ids.get('wikipedia'),
                wikidata_id=ids.get('wikidata'),
            )

            # Parse social media
            social = member_dict.get('social', [])
            social_dict = {item.get('type'): item.get('id') for item in social}

            # Build record
            name_parts = bio.get('name', '').split()
            record = LegislatorRecord(
                bioguide_id=bioguide_id,
                first_name=bio.get('firstname', ''),
                last_name=bio.get('lastname', ''),
                full_name=bio.get('name', ''),
                date_of_birth=bio.get('birthday'),
                gender=bio.get('gender'),
                ids=id_cross_ref,
                terms=parsed_terms,
                twitter=social_dict.get('Twitter'),
                facebook=social_dict.get('Facebook'),
                youtube=social_dict.get('YouTube'),
                contact_form=member_dict.get('contact_form'),
                official_website=member_dict.get('url'),
            )

            members[bioguide_id] = record

        logger.info(f'Parsed {len(members)} current members')
        return members

    async def get_committees(self) -> Dict[str, Dict]:
        """
        Download committees-current.yaml.

        Returns:
            Dict mapping committee_code → committee_info
        """
        data = await self.download_file('committees-current')

        committees = {}
        for committee_dict in data:
            code = committee_dict.get('thomas_id')
            if not code:
                continue

            committees[code] = {
                'name': committee_dict.get('name'),
                'type': committee_dict.get('type'),  # 'House', 'Senate', 'Joint'
                'jurisdiction': committee_dict.get('jurisdiction'),
                'url': committee_dict.get('url'),
                'jurisdiction_source': committee_dict.get('jurisdiction_source'),
            }

        logger.info(f'Parsed {len(committees)} committees')
        return committees

    async def get_committee_memberships(self) -> List[Dict]:
        """
        Download committee-membership-current.yaml.

        Returns:
            List of membership records with keys:
            {member_bioguide, committee_code, leadership_title, rank}
        """
        data = await self.download_file('committee-membership-current')

        logger.info(f'Parsed {len(data)} committee memberships')
        return data


async def main():
    """Test the client."""
    try:
        from ..config import AgentsConfig
    except ImportError:
        # For standalone testing
        cache_dir = './cache/unitedstates'

    cache_dir = os.path.join(os.path.dirname(__file__), '../../..', 'cache', 'unitedstates')
    client = UnitedStatesProjectClient(cache_dir)

    # Download and print summary
    members = await client.get_current_members()
    print(f'\nTotal members: {len(members)}')

    # Group by chamber
    house = sum(1 for m in members.values() if m.terms[-1].chamber == 'house')
    senate = sum(1 for m in members.values() if m.terms[-1].chamber == 'senate')
    print(f'House: {house}, Senate: {senate}')

    # Sample member
    sample = list(members.values())[0]
    print(f'\nSample member: {sample.full_name}')
    print(f'  Bioguide: {sample.ids.bioguide_id}')
    print(f'  FEC: {sample.ids.fec_id}')
    print(f'  OpenSecrets: {sample.ids.opensecrets_id}')
    print(f'  Twitter: {sample.twitter}')

    # Test committees
    committees = await client.get_committees()
    print(f'\nTotal committees: {len(committees)}')

    # Test memberships
    memberships = await client.get_committee_memberships()
    print(f'Total memberships: {len(memberships)}')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
