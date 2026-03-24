"""
OpenFEC Campaign Finance API Client
====================================
Fetches campaign finance data for Congress members including:
- Candidate totals (receipts, disbursements)
- Top individual donors
- Top PAC donors
- Industry breakdown
- Committee assignments and spending

Source: https://api.open.fec.gov/
OpenFEC is the official FEC campaign finance API.

Rate limit: 1000 requests/hour
Auth: api_key query parameter
"""

import os
import json
import aiohttp
import asyncio
import logging
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CandidateTotals:
    """Campaign finance totals for a candidate."""
    candidate_id: str
    candidate_name: str
    cycle: int
    office: str  # 'H' for House, 'S' for Senate, 'P' for President
    state: str
    party: Optional[str]
    receipts: float
    disbursements: float
    cash_on_hand: float
    loans: float
    candidate_contribution: float


@dataclass
class DonorInfo:
    """Individual donor information."""
    donor_name: str
    state: str
    occupation: str
    amount: float
    transaction_date: str
    committee_id: str


@dataclass
class PACDonor:
    """PAC donor information."""
    pac_name: str
    pac_id: str
    amount: float
    contribution_date: str


class OpenFECClient:
    """Async HTTP client for OpenFEC API."""

    BASE_URL = 'https://api.open.fec.gov/v1'
    REQUEST_TIMEOUT = 30
    RATE_LIMIT_REQUESTS = 1000
    RATE_LIMIT_WINDOW = 3600  # 1 hour

    def __init__(self, api_key: str, cache_dir: str):
        """
        Args:
            api_key: OpenFEC API key
            cache_dir: Directory to cache API responses
        """
        if not api_key:
            raise ValueError('OpenFEC API key is required')

        self.api_key = api_key
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

        # Rate limiting
        self.request_times = []
        self._request_lock = asyncio.Lock()

    def _get_cache_path(self, endpoint: str, params: Dict) -> str:
        """Generate a cache file path for an endpoint + params combination."""
        param_str = '_'.join(f'{k}={v}' for k, v in sorted(params.items()))
        cache_key = f'{endpoint}_{param_str}' if param_str else endpoint
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

    async def _request(
        self,
        endpoint: str,
        params: Dict = None,
        cache: bool = True,
    ) -> Dict:
        """
        Make an HTTP GET request with caching and rate limiting.

        Args:
            endpoint: API endpoint path (e.g., '/candidates')
            params: Query parameters
            cache: Whether to cache the response

        Returns:
            Parsed JSON response
        """
        if params is None:
            params = {}

        # Add API key
        params['api_key'] = self.api_key
        params['per_page'] = params.get('per_page', 100)

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

    async def get_candidate_by_fec_id(self, fec_id: str, cycle: int = 2024) -> Optional[Dict]:
        """
        Get candidate information by FEC ID.

        Args:
            fec_id: FEC candidate ID
            cycle: Election cycle (2024, 2022, etc.)

        Returns:
            Candidate info dict
        """
        try:
            data = await self._request(f'/candidates/{fec_id}', {'cycle': cycle})
            return data.get('results', [{}])[0] if data.get('results') else None
        except Exception as e:
            logger.warning(f'Failed to fetch candidate {fec_id}: {e}')
            return None

    async def get_candidate_totals(self, fec_id: str, cycle: int = 2024) -> Optional[CandidateTotals]:
        """
        Get campaign finance totals for a candidate.

        Args:
            fec_id: FEC candidate ID
            cycle: Election cycle

        Returns:
            CandidateTotals object
        """
        try:
            data = await self._request(f'/candidate/{fec_id}/totals', {'cycle': cycle})
            results = data.get('results', [])
            if not results:
                return None

            r = results[0]
            return CandidateTotals(
                candidate_id=fec_id,
                candidate_name=r.get('candidate_name', ''),
                cycle=r.get('cycle', cycle),
                office=r.get('office', ''),
                state=r.get('state', ''),
                party=r.get('party', ''),
                receipts=float(r.get('receipts', 0)),
                disbursements=float(r.get('disbursements', 0)),
                cash_on_hand=float(r.get('cash_on_hand', 0)),
                loans=float(r.get('loans_received', 0)),
                candidate_contribution=float(r.get('candidate_contribution', 0)),
            )
        except Exception as e:
            logger.warning(f'Failed to fetch totals for {fec_id}: {e}')
            return None

    async def get_top_donors_individual(
        self,
        fec_id: str,
        cycle: int = 2024,
        limit: int = 20,
    ) -> List[Dict]:
        """
        Get top individual donors to a candidate.

        Args:
            fec_id: FEC candidate ID
            cycle: Election cycle
            limit: Maximum donors to return

        Returns:
            List of donor dicts (name, state, occupation, amount)
        """
        try:
            data = await self._request(
                f'/schedules/schedule_a',
                {
                    'recipient_id': fec_id,
                    'cycle': cycle,
                    'sort': '-contribution_receipt_amount',
                    'per_page': limit,
                },
            )
            return data.get('results', [])
        except Exception as e:
            logger.warning(f'Failed to fetch top donors for {fec_id}: {e}')
            return []

    async def get_top_donors_pac(
        self,
        fec_id: str,
        cycle: int = 2024,
        limit: int = 20,
    ) -> List[Dict]:
        """
        Get top PAC donors to a candidate.

        Args:
            fec_id: FEC candidate ID
            cycle: Election cycle
            limit: Maximum PACs to return

        Returns:
            List of PAC donor dicts
        """
        try:
            data = await self._request(
                f'/schedules/schedule_b',
                {
                    'recipient_id': fec_id,
                    'cycle': cycle,
                    'sort': '-contribution_receipt_amount',
                    'per_page': limit,
                },
            )
            return data.get('results', [])
        except Exception as e:
            logger.warning(f'Failed to fetch PAC donors for {fec_id}: {e}')
            return []

    async def get_candidate_committees(self, fec_id: str, cycle: int = 2024) -> List[Dict]:
        """
        Get committees associated with a candidate.

        Args:
            fec_id: FEC candidate ID
            cycle: Election cycle

        Returns:
            List of committee dicts
        """
        try:
            data = await self._request(
                f'/candidate/{fec_id}/committees',
                {'cycle': cycle},
            )
            return data.get('results', [])
        except Exception as e:
            logger.warning(f'Failed to fetch committees for {fec_id}: {e}')
            return []


async def main():
    """Test the client."""
    import sys
    sys.path.insert(0, os.path.dirname(__file__))

    from ..config import AgentsConfig

    api_key = os.getenv('OPENFEC_API_KEY') or AgentsConfig.OPENFEC_API_KEY
    if not api_key:
        print('ERROR: OPENFEC_API_KEY not set in .env')
        return

    cache_dir = os.path.join(
        os.path.dirname(__file__), '../../..', 'backend', 'agents', 'cache', 'openfec'
    )
    client = OpenFECClient(api_key, cache_dir)

    # Test: get candidate info for a known FEC ID
    # Using a real example: Alexandria Ocasio-Cortez (House)
    fec_id = 'H8NY13283'

    print('\n=== Testing OpenFEC API ===')

    # Get candidate
    candidate = await client.get_candidate_by_fec_id(fec_id)
    if candidate:
        print(f'\nCandidate: {candidate.get("name")}')
        print(f'  Office: {candidate.get("office")}')
        print(f'  Party: {candidate.get("party")}')

    # Get totals
    totals = await client.get_candidate_totals(fec_id)
    if totals:
        print(f'\nFinance Totals (2024):')
        print(f'  Receipts: ${totals.receipts:,.2f}')
        print(f'  Disbursements: ${totals.disbursements:,.2f}')
        print(f'  Cash on Hand: ${totals.cash_on_hand:,.2f}')

    # Get top donors
    donors = await client.get_top_donors_individual(fec_id, limit=5)
    print(f'\nTop Individual Donors: {len(donors)}')
    for donor in donors[:3]:
        print(f'  {donor.get("contributor_name", "Unknown")} ({donor.get("contributor_state")}): ${donor.get("contribution_receipt_amount", 0):,.2f}')

    # Get top PACs
    pacs = await client.get_top_donors_pac(fec_id, limit=5)
    print(f'\nTop PAC Donors: {len(pacs)}')
    for pac in pacs[:3]:
        print(f'  {pac.get("committee_name", "Unknown")}: ${pac.get("contribution_receipt_amount", 0):,.2f}')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
