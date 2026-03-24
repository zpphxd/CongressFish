"""
Oyez Supreme Court API Client
==============================
Fetches Supreme Court justice data including:
- Justice profiles (biography, judicial philosophy)
- Opinion data (voting records per case)
- Judicial voting patterns and alignment

Source: https://api.oyez.org/
This is the canonical source for SCOTUS data and voting records.
"""

import os
import json
import aiohttp
import asyncio
import logging
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class JusticeProfile:
    """Complete profile for a Supreme Court justice."""
    id: str
    name: str
    birth_date: Optional[str]
    death_date: Optional[str]
    term_start: Optional[str]
    term_end: Optional[str]
    court_id: str  # Court era ID (e.g., '2023-06-30')
    wikipedia_id: Optional[str]
    ideology_score: Optional[float] = None
    voting_record: Optional[Dict] = None  # Summary of voting patterns


@dataclass
class CaseVote:
    """A justice's vote in a specific case."""
    case_id: str
    case_name: str
    decision_date: str
    justice_id: str
    justice_name: str
    vote: str  # 'majority', 'concur', 'dissent', 'concur_in_part', etc.
    opinion_type: Optional[str]  # 'majority', 'concurring', 'dissenting', 'concur_in_part'


class OyezClient:
    """Async HTTP client for Oyez Supreme Court API."""

    BASE_URL = 'https://api.oyez.org'
    REQUEST_TIMEOUT = 30
    MIN_REQUEST_INTERVAL = 0.5  # Seconds between requests

    def __init__(self, cache_dir: str):
        """
        Args:
            cache_dir: Directory to cache API responses
        """
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.last_request_time = 0

    def _get_cache_path(self, endpoint: str, params: Dict = None) -> str:
        """Generate a cache file path for an endpoint."""
        param_str = '_'.join(f'{k}={v}' for k, v in sorted(params.items())) if params else ''
        cache_key = f'{endpoint}_{param_str}' if param_str else endpoint
        cache_key = cache_key.replace('/', '_').replace('{', '').replace('}', '')
        return os.path.join(self.cache_dir, f'{cache_key}.json')

    def _load_from_cache(self, cache_path: str) -> Optional[Dict]:
        """Load response from cache if it exists and is recent (< 30 days old)."""
        if not os.path.exists(cache_path):
            return None

        file_age_seconds = time.time() - os.path.getmtime(cache_path)
        if file_age_seconds > 30 * 24 * 3600:  # 30 days
            logger.debug(f'Cache expired for {cache_path}')
            return None

        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f'Failed to load cache {cache_path}: {e}')
            return None

    def _save_to_cache(self, cache_path: str, data: Dict) -> None:
        """Save response to cache."""
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f'Failed to save cache {cache_path}: {e}')

    async def _rate_limit(self) -> None:
        """Enforce minimum interval between requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.MIN_REQUEST_INTERVAL:
            await asyncio.sleep(self.MIN_REQUEST_INTERVAL - elapsed)
        self.last_request_time = time.time()

    async def _request(self, endpoint: str, params: Dict = None) -> Dict:
        """
        Make an HTTP GET request to Oyez API with caching.

        Args:
            endpoint: API endpoint path (e.g., '/api/rest/v3/justices')
            params: Optional query parameters

        Returns:
            Parsed JSON response
        """
        if params is None:
            params = {}

        # Check cache
        cache_path = self._get_cache_path(endpoint, params)
        cached = self._load_from_cache(cache_path)
        if cached:
            logger.debug(f'Cache hit: {endpoint}')
            return cached

        # Rate limit
        await self._rate_limit()

        url = f'{self.BASE_URL}{endpoint}'
        logger.debug(f'GET {url}')

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=self.REQUEST_TIMEOUT),
                headers={'User-Agent': 'CongressFish/1.0'},
            ) as resp:
                if resp.status != 200:
                    raise aiohttp.ClientError(f'{resp.status} {resp.reason}')

                data = await resp.json()

                # Cache successful response
                self._save_to_cache(cache_path, data)

                return data

    async def get_justices(self, current_only: bool = True) -> List[JusticeProfile]:
        """
        Get all justices (optionally current only).

        Args:
            current_only: If True, only get current justices

        Returns:
            List of JusticeProfile objects
        """
        logger.info(f'Fetching justices (current_only={current_only})')

        # Get all justices
        data = await self._request('/api/rest/v3/justices')

        justices = []
        for justice_data in data.get('results', []):
            # Parse profile
            profile = JusticeProfile(
                id=justice_data.get('id'),
                name=justice_data.get('name'),
                birth_date=justice_data.get('birth_date'),
                death_date=justice_data.get('death_date'),
                term_start=justice_data.get('term_start'),
                term_end=justice_data.get('term_end'),
                court_id=justice_data.get('href', '').split('/')[-1] if justice_data.get('href') else '',
                wikipedia_id=None,  # Oyez doesn't provide Wikipedia IDs directly
            )

            # Skip if filtering by current only
            if current_only and justice_data.get('term_end'):
                continue

            justices.append(profile)

        logger.info(f'Fetched {len(justices)} justices')
        return justices

    async def get_justice_votes(self, justice_id: str, limit: int = 500) -> List[CaseVote]:
        """
        Get voting record for a specific justice.

        Args:
            justice_id: Justice ID from Oyez
            limit: Maximum number of cases to fetch

        Returns:
            List of CaseVote objects
        """
        logger.info(f'Fetching votes for justice {justice_id}')

        votes = []
        offset = 0

        while len(votes) < limit:
            # Fetch opinions per justice
            data = await self._request(f'/api/rest/v3/justices/{justice_id}/opinions', {
                'limit': min(50, limit - len(votes)),
                'offset': offset,
            })

            opinions = data.get('results', [])
            if not opinions:
                break

            # Parse votes from opinions
            for opinion in opinions:
                case = opinion.get('case', {})
                case_votes = opinion.get('votes', [])

                for vote_data in case_votes:
                    if vote_data.get('member_id') == justice_id:
                        vote = CaseVote(
                            case_id=case.get('id'),
                            case_name=case.get('name', ''),
                            decision_date=case.get('decision_date', ''),
                            justice_id=justice_id,
                            justice_name=vote_data.get('member', {}).get('name', ''),
                            vote=vote_data.get('vote', ''),
                            opinion_type=opinion.get('type'),
                        )
                        votes.append(vote)

            # Check if more pages
            if not data.get('next'):
                break

            offset += 50

        logger.info(f'Fetched {len(votes)} votes for justice {justice_id}')
        return votes

    async def get_justice_detail(self, justice_id: str) -> Optional[Dict]:
        """
        Get detailed profile for a justice including biography.

        Args:
            justice_id: Justice ID from Oyez

        Returns:
            Dict with detailed justice information
        """
        try:
            data = await self._request(f'/api/rest/v3/justices/{justice_id}')
            return data
        except Exception as e:
            logger.warning(f'Failed to fetch justice detail {justice_id}: {e}')
            return None

    async def compute_voting_alignment(
        self,
        justice_votes_map: Dict[str, List[CaseVote]]
    ) -> Dict[str, Dict[str, float]]:
        """
        Compute pairwise voting alignment between justices.

        Args:
            justice_votes_map: Dict mapping justice_id → list of CaseVote

        Returns:
            Dict mapping justice_id → dict of {other_justice_id → agreement_pct}
        """
        logger.info('Computing justice voting alignment...')

        alignment = {}

        justice_ids = list(justice_votes_map.keys())

        for j1_id in justice_ids:
            alignment[j1_id] = {}

            j1_votes = justice_votes_map[j1_id]
            j1_case_votes = {v.case_id: v.vote for v in j1_votes}

            for j2_id in justice_ids:
                if j1_id == j2_id:
                    continue

                j2_votes = justice_votes_map[j2_id]
                j2_case_votes = {v.case_id: v.vote for v in j2_votes}

                # Find common cases
                common_cases = set(j1_case_votes.keys()) & set(j2_case_votes.keys())
                if not common_cases:
                    alignment[j1_id][j2_id] = 0.0
                    continue

                # Count agreements
                agreements = sum(
                    1 for case_id in common_cases
                    if j1_case_votes[case_id] == j2_case_votes[case_id]
                )

                alignment[j1_id][j2_id] = round(agreements / len(common_cases) * 100, 1)

        return alignment

    async def get_all_justices_with_votes(self) -> Dict[str, Dict]:
        """
        Get all current justices with their voting records and alignment.

        Returns:
            Dict mapping justice_id → {profile, votes, alignment_with_others}
        """
        logger.info('Fetching all justices with voting records...')

        # Get justice list
        justices = await self.get_justices(current_only=True)

        # Fetch votes for each justice
        justice_votes_map = {}
        justice_data_map = {}

        for justice in justices:
            try:
                votes = await self.get_justice_votes(justice.id, limit=200)
                justice_votes_map[justice.id] = votes

                detail = await self.get_justice_detail(justice.id)
                justice_data_map[justice.id] = {
                    'profile': justice,
                    'detail': detail,
                    'votes': votes,
                }
            except Exception as e:
                logger.warning(f'Failed to fetch votes for {justice.name}: {e}')

        # Compute alignment
        alignment = await self.compute_voting_alignment(justice_votes_map)

        # Merge alignment into results
        result = {}
        for j_id, data in justice_data_map.items():
            result[j_id] = {
                'profile': {
                    'id': data['profile'].id,
                    'name': data['profile'].name,
                    'birth_date': data['profile'].birth_date,
                    'term_start': data['profile'].term_start,
                    'term_end': data['profile'].term_end,
                },
                'detail': data['detail'],
                'vote_count': len(data['votes']),
                'alignment_with_others': alignment.get(j_id, {}),
            }

        logger.info(f'Fetched {len(result)} justices with voting records')
        return result


async def main():
    """Test the client."""
    cache_dir = os.path.join(
        os.path.dirname(__file__), '../../..', 'backend', 'agents', 'cache', 'oyez'
    )
    client = OyezClient(cache_dir)

    print('\n=== Testing Oyez Client ===')

    # Get justices
    justices = await client.get_justices(current_only=True)
    print(f'\nCurrent justices: {len(justices)}')
    for justice in justices[:3]:
        print(f'  {justice.name} (b. {justice.birth_date})')

    # Get votes for first justice
    if justices:
        j = justices[0]
        votes = await client.get_justice_votes(j.id, limit=50)
        print(f'\nVotes for {j.name}: {len(votes)}')
        if votes:
            print(f'  Sample: {votes[0].case_name} → {votes[0].vote}')

    # Get full data with alignment
    print('\nFetching all justices with votes and alignment...')
    all_justices = await client.get_all_justices_with_votes()
    print(f'Total justices: {len(all_justices)}')

    for j_id, data in list(all_justices.items())[:1]:
        print(f'\n{data["profile"]["name"]}:')
        print(f'  Votes: {data["vote_count"]}')
        alignment = data['alignment_with_others']
        if alignment:
            top_aligned = max(alignment.items(), key=lambda x: x[1])
            print(f'  Most aligned with: {top_aligned[0]} ({top_aligned[1]}%)')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
