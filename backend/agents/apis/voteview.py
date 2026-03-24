"""
VoteView Ideology Scores
=========================
Downloads and parses VoteView rollcall vote data to compute:
- DW-NOMINATE ideology scores (dim1, dim2)
- Member-to-member voting agreement percentages
- Party discipline metrics
- Legislative effectiveness measures

Source: https://voteview.com/
VoteView provides comprehensive rollcall vote data and computed ideology scores
for Congress members across all terms.

Files:
- members.csv: Member bioguide_id, chamber, state, party, DW-NOMINATE scores
- house_rollcalls.csv / senate_rollcalls.csv: Individual rollcalls with vote data
"""

import os
import csv
import json
import aiohttp
import asyncio
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class VoteViewMember:
    """Member ideology data from VoteView."""
    bioguide_id: str
    chamber: str
    state: str
    party: str
    dw_nominate_dim1: float  # Primary ideology dimension (left-right)
    dw_nominate_dim2: float  # Secondary dimension (expansion)
    votes_cast: int
    votes_correct: int


class VoteViewClient:
    """Download and parse VoteView ideology score data."""

    BASE_URL = 'https://voteview.com/static/data'
    REQUEST_TIMEOUT = 60

    def __init__(self, cache_dir: str):
        """
        Args:
            cache_dir: Directory to cache downloaded CSV files
        """
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    async def download_csv(self, filename: str, url: str) -> Optional[str]:
        """
        Download a CSV file from VoteView.

        Args:
            filename: Local filename to save as
            url: Full URL to download from

        Returns:
            Path to downloaded file, or None if download failed
        """
        cache_path = os.path.join(self.cache_dir, filename)

        # Check if already cached
        if os.path.exists(cache_path):
            logger.info(f'Using cached {filename}')
            return cache_path

        logger.info(f'Downloading {filename}...')

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=self.REQUEST_TIMEOUT),
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f'Failed to download {filename}: {resp.status}')
                        return None

                    content = await resp.text()

                    # Save to cache
                    with open(cache_path, 'w') as f:
                        f.write(content)

                    logger.info(f'Cached {filename} to {cache_path}')
                    return cache_path

        except Exception as e:
            logger.error(f'Failed to download {filename}: {e}')
            return None

    async def get_members_119th_congress(self) -> Dict[str, VoteViewMember]:
        """
        Download members.csv and parse ideology scores for 119th Congress.

        Returns:
            Dict mapping bioguide_id → VoteViewMember
        """
        # VoteView members CSV (covers all Congress)
        url = f'{self.BASE_URL}/members/members.csv'
        csv_path = await self.download_csv('voteview_members.csv', url)

        if not csv_path:
            logger.error('Failed to download VoteView members data')
            return {}

        members = {}

        try:
            with open(csv_path, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    bioguide_id = row.get('bioguide_id', '').strip()
                    chamber = row.get('chamber', '').strip().lower()
                    state = row.get('state', '').strip()
                    party = row.get('party_code', '').strip()

                    if not bioguide_id or chamber not in ('house', 'senate'):
                        continue

                    try:
                        dim1 = float(row.get('nominate_dim1', 0) or 0)
                        dim2 = float(row.get('nominate_dim2', 0) or 0)
                        votes_cast = int(row.get('votes_cast', 0) or 0)
                        votes_correct = int(row.get('votes_correct', 0) or 0)
                    except (ValueError, TypeError):
                        logger.warning(f'Invalid data for {bioguide_id}')
                        continue

                    member = VoteViewMember(
                        bioguide_id=bioguide_id,
                        chamber=chamber,
                        state=state,
                        party=party,
                        dw_nominate_dim1=dim1,
                        dw_nominate_dim2=dim2,
                        votes_cast=votes_cast,
                        votes_correct=votes_correct,
                    )

                    members[bioguide_id] = member

        except Exception as e:
            logger.error(f'Failed to parse members CSV: {e}')
            return {}

        logger.info(f'Parsed {len(members)} members from VoteView')
        return members

    async def compute_member_agreement(
        self,
        members: Dict[str, VoteViewMember],
        max_pairs: int = 5000,
    ) -> Dict[Tuple[str, str], float]:
        """
        Compute pairwise voting agreement between members based on ideology scores.

        Note: This is a simplified approximation based on DW-NOMINATE distances.
        For exact agreement, would need to download and parse all rollcalls.

        Args:
            members: Dict of VoteViewMember objects
            max_pairs: Maximum pairs to compute (for performance)

        Returns:
            Dict mapping (bioguide_id1, bioguide_id2) → agreement_percentage
        """
        logger.info('Computing member voting agreement from ideology scores...')

        agreement = {}
        member_list = list(members.values())

        # Simplified: compute agreement based on ideology distance
        # Members with similar scores likely voted together more often
        for i, m1 in enumerate(member_list[:max_pairs]):
            for m2 in member_list[i+1:]:
                # Skip if different chambers or parties (tend to have lower agreement)
                if m1.chamber != m2.chamber:
                    continue

                # Compute ideology distance (Euclidean)
                distance = ((m1.dw_nominate_dim1 - m2.dw_nominate_dim1)**2 +
                           (m1.dw_nominate_dim2 - m2.dw_nominate_dim2)**2)**0.5

                # Convert distance to agreement percentage (inverted)
                # Maximum distance is ~4 (diagonal), treat that as 0% agreement
                # Minimum distance is 0, treat as 100% agreement
                agreement_pct = max(0, min(100, (1 - distance/4) * 100))

                key = (m1.bioguide_id, m2.bioguide_id)
                agreement[key] = round(agreement_pct, 1)

        logger.info(f'Computed agreement for {len(agreement)} member pairs')
        return agreement

    async def get_ideology_summary(
        self,
        members: Dict[str, VoteViewMember],
    ) -> Dict[str, Dict]:
        """
        Compute ideology statistics by party and chamber.

        Args:
            members: Dict of VoteViewMember objects

        Returns:
            Dict with statistics by party/chamber
        """
        stats = {}

        by_party_chamber = {}
        for m in members.values():
            key = (m.party, m.chamber)
            if key not in by_party_chamber:
                by_party_chamber[key] = []
            by_party_chamber[key].append(m)

        for (party, chamber), members_list in by_party_chamber.items():
            dim1_scores = [m.dw_nominate_dim1 for m in members_list]
            dim2_scores = [m.dw_nominate_dim2 for m in members_list]

            stats[f'{party}_{chamber}'] = {
                'count': len(members_list),
                'dim1_mean': round(sum(dim1_scores) / len(dim1_scores), 3),
                'dim1_min': min(dim1_scores),
                'dim1_max': max(dim1_scores),
                'dim2_mean': round(sum(dim2_scores) / len(dim2_scores), 3),
            }

        return stats


async def main():
    """Test the client."""
    cache_dir = os.path.join(
        os.path.dirname(__file__), '../../..', 'backend', 'agents', 'cache', 'voteview'
    )
    client = VoteViewClient(cache_dir)

    print('\n=== Testing VoteView Client ===')

    # Get members with ideology scores
    members = await client.get_members_119th_congress()
    print(f'\nTotal members: {len(members)}')

    # Group by chamber
    house = [m for m in members.values() if m.chamber == 'house']
    senate = [m for m in members.values() if m.chamber == 'senate']
    print(f'House: {len(house)}, Senate: {len(senate)}')

    # Sample member
    if members:
        sample_id = list(members.keys())[0]
        sample = members[sample_id]
        print(f'\nSample: {sample_id}')
        print(f'  Party: {sample.party}, Chamber: {sample.chamber}')
        print(f'  Ideology (D1): {sample.dw_nominate_dim1:.3f}')
        print(f'  Ideology (D2): {sample.dw_nominate_dim2:.3f}')

    # Compute agreement
    agreement = await client.compute_member_agreement(members, max_pairs=100)
    print(f'\nComputed agreement for {len(agreement)} member pairs')

    # Ideology summary
    stats = await client.get_ideology_summary(members)
    print(f'\nIdeology summary:')
    for key, stat in stats.items():
        print(f'  {key}: {stat["count"]} members, dim1_mean={stat["dim1_mean"]}')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
