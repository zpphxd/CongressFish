"""
Congress.gov API v3 Client
===========================
Official Library of Congress API for accessing comprehensive Congressional data.

Docs: https://api.congress.gov/
Replaced ProPublica Congress API (which is dead/discontinued).

Key endpoints:
  /v3/member — List all members with party, state, district, committees
  /v3/member/{bioguideId} — Full member detail
  /v3/member/{bioguideId}/sponsored-legislation — Bills sponsored
  /v3/member/{bioguideId}/cosponsored-legislation — Bills cosponsored
  /v3/bill — Bills with summaries, status, votes
  /v3/bill/{congress}/{billType}/{billNumber} — Bill detail
  /v3/committee — Committees with jurisdiction
  /v3/vote (BETA, House votes added May 2025) — Roll call votes with per-member positions

Rate limit: ~5000 requests/hour
Auth: api_key query parameter

All responses cached to disk to avoid re-pulling during development.
"""

import os
import json
import aiohttp
import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import time

logger = logging.getLogger(__name__)


class CongressGovClient:
    """Async HTTP client for Congress.gov API v3."""

    BASE_URL = 'https://api.congress.gov/v3'
    REQUEST_TIMEOUT = 30
    RATE_LIMIT_REQUESTS = 5000
    RATE_LIMIT_WINDOW = 3600  # 1 hour
    CONCURRENCY_LIMIT = 10

    def __init__(self, api_key: str, cache_dir: str):
        """
        Args:
            api_key: Congress.gov API key
            cache_dir: Directory to cache API responses
        """
        if not api_key:
            raise ValueError('Congress.gov API key is required')

        self.api_key = api_key
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

        # Rate limiting
        self.request_times = []  # For simple rate limit tracking
        self._request_lock = asyncio.Lock()

    def _get_cache_path(self, endpoint: str, params: Dict) -> str:
        """Generate a cache file path for an endpoint + params combination."""
        # Create a cache key from endpoint and params
        param_str = '_'.join(f'{k}={v}' for k, v in sorted(params.items()))
        cache_key = f'{endpoint}_{param_str}' if param_str else endpoint
        # Sanitize for filesystem
        cache_key = cache_key.replace('/', '_').replace('{', '').replace('}', '')
        return os.path.join(self.cache_dir, f'{cache_key}.json')

    def _load_from_cache(self, cache_path: str) -> Optional[Dict]:
        """Load response from cache if it exists and is recent (< 7 days old)."""
        if not os.path.exists(cache_path):
            return None

        file_age_seconds = time.time() - os.path.getmtime(cache_path)
        if file_age_seconds > 7 * 24 * 3600:  # 7 days
            logger.debug(f'Cache expired for {cache_path}')
            return None

        try:
            with open(cache_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f'Failed to load cache {cache_path}: {e}')
            return None

    def _save_to_cache(self, cache_path: str, data: Dict) -> None:
        """Save response to cache."""
        try:
            with open(cache_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f'Failed to save cache {cache_path}: {e}')

    async def _check_rate_limit(self) -> None:
        """Check and enforce rate limit."""
        async with self._request_lock:
            now = time.time()
            # Remove old requests outside the window
            self.request_times = [t for t in self.request_times if now - t < self.RATE_LIMIT_WINDOW]

            if len(self.request_times) >= self.RATE_LIMIT_REQUESTS:
                sleep_time = self.RATE_LIMIT_WINDOW - (now - self.request_times[0])
                if sleep_time > 0:
                    logger.warning(f'Rate limit approaching, sleeping {sleep_time:.1f}s')
                    await asyncio.sleep(sleep_time)
                    self.request_times = []

            self.request_times.append(now)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=10),
        retry=retry_if_exception_type(aiohttp.ClientError),
    )
    async def _request(
        self,
        endpoint: str,
        params: Dict = None,
        cache: bool = True,
    ) -> Dict:
        """
        Make an HTTP GET request with caching and retries.

        Args:
            endpoint: API endpoint path (e.g., '/v3/member')
            params: Query parameters
            cache: Whether to cache the response

        Returns:
            Parsed JSON response
        """
        if params is None:
            params = {}

        # Add API key
        params['api_key'] = self.api_key
        params['limit'] = params.get('limit', 250)  # Max results per page

        # Check cache
        cache_path = self._get_cache_path(endpoint, {k: v for k, v in params.items() if k != 'api_key'})
        if cache:
            cached = self._load_from_cache(cache_path)
            if cached:
                logger.debug(f'Cache hit: {endpoint}')
                return cached

        # Rate limit
        await self._check_rate_limit()

        # Make request
        url = f'{self.BASE_URL}{endpoint}'
        logger.debug(f'GET {url}')

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=self.REQUEST_TIMEOUT),
            ) as resp:
                if resp.status != 200:
                    raise aiohttp.ClientError(f'{resp.status} {resp.reason}')

                data = await resp.json()

                # Cache successful response
                if cache:
                    self._save_to_cache(cache_path, data)

                return data

    async def get_members(self, congress: int = 119, chamber: Optional[str] = None) -> List[Dict]:
        """
        Get all members of Congress.

        Args:
            congress: Congress number (e.g., 119)
            chamber: Optional filter by 'Senate' or 'House'

        Returns:
            List of member records
        """
        logger.info(f'Fetching members for Congress {congress}, chamber={chamber}')

        all_members = []
        offset = 0
        limit = 250

        while True:
            params = {
                'offset': offset,
                'limit': limit,
                'congress': congress,
            }
            if chamber:
                params['chamber'] = chamber.lower()

            # API endpoint for all members
            data = await self._request('/member', params=params)

            members = data.get('members', [])
            if not members:
                break

            all_members.extend(members)
            logger.info(f'Fetched {len(all_members)} members so far')

            # Check if there are more pages
            pagination = data.get('pagination', {})
            if not pagination.get('next'):
                break

            offset += limit

        logger.info(f'Total members: {len(all_members)}')
        return all_members

    async def get_member(self, bioguide_id: str) -> Optional[Dict]:
        """Get full details for a single member."""
        try:
            data = await self._request(f'/v3/member/{bioguide_id}')
            return data.get('member')
        except Exception as e:
            logger.warning(f'Failed to fetch member {bioguide_id}: {e}')
            return None

    async def get_member_sponsored_bills(
        self,
        bioguide_id: str,
        congress: int = 119,
        limit: int = 100,
    ) -> List[Dict]:
        """Get bills sponsored by a member."""
        try:
            params = {'limit': limit}
            data = await self._request(
                f'/v3/member/{bioguide_id}/sponsored-legislation',
                params=params,
            )
            return data.get('sponsoredLegislation', [])
        except Exception as e:
            logger.warning(f'Failed to fetch sponsored bills for {bioguide_id}: {e}')
            return []

    async def get_member_cosponsored_bills(
        self,
        bioguide_id: str,
        congress: int = 119,
        limit: int = 100,
    ) -> List[Dict]:
        """Get bills cosponsored by a member."""
        try:
            params = {'limit': limit}
            data = await self._request(
                f'/v3/member/{bioguide_id}/cosponsored-legislation',
                params=params,
            )
            return data.get('cosponsoredLegislation', [])
        except Exception as e:
            logger.warning(f'Failed to fetch cosponsored bills for {bioguide_id}: {e}')
            return []

    async def get_committees(self, chamber: Optional[str] = None) -> List[Dict]:
        """Get all committees."""
        logger.info(f'Fetching committees, chamber={chamber}')

        all_committees = []
        offset = 0
        limit = 250

        while True:
            params = {'offset': offset, 'limit': limit}
            if chamber:
                params['chamber'] = chamber

            data = await self._request('/committee', params=params)

            committees = data.get('committees', [])
            if not committees:
                break

            all_committees.extend(committees)
            logger.info(f'Fetched {len(all_committees)} committees so far')

            # Check for more pages
            if not data.get('pagination', {}).get('next'):
                break

            offset += limit

        logger.info(f'Total committees: {len(all_committees)}')
        return all_committees

    async def get_committee(self, committee_code: str) -> Optional[Dict]:
        """Get details for a specific committee."""
        try:
            data = await self._request(f'/v3/committee/{committee_code}')
            return data.get('committee')
        except Exception as e:
            logger.warning(f'Failed to fetch committee {committee_code}: {e}')
            return None

    async def get_bill(
        self,
        congress: int,
        bill_type: str,
        bill_number: int,
    ) -> Optional[Dict]:
        """Get details for a specific bill."""
        try:
            data = await self._request(f'/v3/bill/{congress}/{bill_type.lower()}/{bill_number}')
            return data.get('bill')
        except Exception as e:
            logger.warning(f'Failed to fetch bill {congress}/{bill_type}/{bill_number}: {e}')
            return None


async def main():
    """Test the client."""
    import sys
    sys.path.insert(0, os.path.dirname(__file__))

    # Try to import from config, fallback for standalone testing
    api_key = os.getenv('CONGRESS_GOV_API_KEY')
    if not api_key:
        print('ERROR: CONGRESS_GOV_API_KEY not set in .env')
        return

    cache_dir = os.path.join(
        os.path.dirname(__file__), '../../..', 'backend', 'agents', 'cache', 'congress_gov'
    )
    client = CongressGovClient(api_key, cache_dir)

    # Test: get members
    print('\\n=== Testing Congress.gov API ===')
    members = await client.get_members(congress=119)
    print(f'\\nTotal members: {len(members)}')

    # Sample member
    if members:
        sample = members[0]
        print(f'\\nSample member:')
        print(f'  Name: {sample.get("firstName")} {sample.get("lastName")}')
        print(f'  Bioguide: {sample.get("bioguideId")}')
        print(f'  Party: {sample.get("party")}')
        print(f'  State: {sample.get("state")}')

    # Test: get committees
    committees = await client.get_committees()
    print(f'\\nTotal committees: {len(committees)}')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
