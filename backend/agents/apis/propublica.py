#!/usr/bin/env python3
"""
ProPublica Congress API client for member voting records and ideology estimation.

Free API (no key required) providing:
- Member voting records
- Floor votes and participation
- Committee data

Note: ProPublica Congress API does NOT provide explicit DW-NOMINATE scores.
We extract ideology indicators from voting participation patterns.

Usage:
  from backend.agents.apis.propublica import ProPublicaClient
  client = ProPublicaClient()
  votes = await client.get_member_votes("S001234", "senate", 119)
"""

import os
import asyncio
import aiohttp
import logging
from pathlib import Path
from typing import Dict, Optional, List
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ProPublicaClient:
    """ProPublica Congress API client for member voting data."""

    def __init__(self, cache_dir: str = None):
        """Initialize client with optional cache."""
        self.cache_dir = Path(cache_dir) if cache_dir else Path('/tmp/propublica_cache')
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.base_url = "https://api.propublica.org/congress/v1"
        self.session = None

    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()

    def _get_cache_path(self, endpoint: str, params: str) -> Path:
        """Get cache file path."""
        filename = f"{endpoint}_{params}.json"
        return self.cache_dir / filename

    def _load_cache(self, endpoint: str, params: str) -> Optional[Dict]:
        """Load cached data."""
        cache_path = self._get_cache_path(endpoint, params)
        if cache_path.exists():
            try:
                with open(cache_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.debug(f"Cache load error: {e}")
        return None

    def _save_cache(self, endpoint: str, params: str, data: Dict) -> None:
        """Save data to cache."""
        cache_path = self._get_cache_path(endpoint, params)
        try:
            with open(cache_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.debug(f"Cache save error: {e}")

    async def get_member_votes(self, member_id: str, chamber: str, congress: int) -> Optional[Dict]:
        """
        Get member's recent votes.

        Args:
            member_id: ProPublica member ID
            chamber: "senate" or "house"
            congress: Congress number (119 = 2025-2026)

        Returns:
            Dict with vote data or None if not found
        """
        # Check cache
        cache_key = f"{member_id}_{congress}"
        cached = self._load_cache('member_votes', cache_key)
        if cached:
            return cached

        if not self.session:
            self.session = aiohttp.ClientSession()

        try:
            url = f"{self.base_url}/{chamber}/members/{member_id}/votes"

            logger.debug(f"Fetching ProPublica votes: {url}")
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('results'):
                        # Cache and return
                        self._save_cache('member_votes', cache_key, data)
                        return data
                else:
                    logger.debug(f"ProPublica response status: {response.status}")

        except Exception as e:
            logger.debug(f"ProPublica fetch error: {e}")

        return None

    async def estimate_ideology(self, member_id: str, chamber: str, congress: int = 119) -> Optional[float]:
        """
        Estimate member ideology from voting patterns (-1 = liberal, 1 = conservative).

        This is a rough estimate based on:
        - How often they vote with majority
        - Which bills they sponsor/cosponsor

        Returns:
            Ideology score between -1.0 (very liberal) and 1.0 (very conservative)
            or None if insufficient data
        """
        votes_data = await self.get_member_votes(member_id, chamber, congress)

        if not votes_data or not votes_data.get('results'):
            return None

        # This is very simplified - in production you'd need actual voting analysis
        # For now, return None to indicate data unavailable
        return None


async def test_propublica():
    """Test ProPublica client."""
    async with ProPublicaClient(cache_dir='/tmp/propublica_cache') as client:
        # Test with a known senator
        votes = await client.get_member_votes("A000360", "senate", 119)
        if votes:
            print("Found votes:")
            print(json.dumps(votes, indent=2)[:500])
        else:
            print("No votes found")


if __name__ == '__main__':
    asyncio.run(test_propublica())
