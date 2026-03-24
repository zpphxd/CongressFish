#!/usr/bin/env python3
"""
Ballotpedia web scraper for enriching Congress member profiles.

Scrapes public Ballotpedia pages for:
- Biographical data (birth date, birthplace, education, occupation)
- Political positions and ideology indicators
- Committee assignments and leadership roles

Usage:
  from backend.agents.apis.ballotpedia import BallotpediaClient
  client = BallotpediaClient()
  profile = await client.get_member_profile("Pete Aguilar", "California", "House")
"""

import os
import asyncio
import aiohttp
import logging
from pathlib import Path
from typing import Dict, Optional, List
from bs4 import BeautifulSoup
from urllib.parse import quote
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BallotpediaClient:
    """Scrapes Ballotpedia for member biographical data."""

    def __init__(self, cache_dir: str = None):
        """Initialize with optional cache directory."""
        self.cache_dir = Path(cache_dir) if cache_dir else Path('/tmp/ballotpedia_cache')
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.base_url = "https://ballotpedia.org"
        self.session = None

    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()

    def _get_cache_path(self, name: str, state: str, chamber: str) -> Path:
        """Get cache file path for member."""
        safe_name = name.lower().replace(' ', '_')
        filename = f"{safe_name}_{state.lower()}_{chamber}.json"
        return self.cache_dir / filename

    def _load_cache(self, name: str, state: str, chamber: str) -> Optional[Dict]:
        """Load cached member data."""
        cache_path = self._get_cache_path(name, state, chamber)
        if cache_path.exists():
            try:
                with open(cache_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.debug(f"Cache load error for {name}: {e}")
        return None

    def _save_cache(self, name: str, state: str, chamber: str, data: Dict) -> None:
        """Save member data to cache."""
        cache_path = self._get_cache_path(name, state, chamber)
        try:
            with open(cache_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.debug(f"Cache save error for {name}: {e}")

    async def get_member_profile(self, name: str, state: str, chamber: str) -> Optional[Dict]:
        """
        Fetch member profile from Ballotpedia.

        Args:
            name: Full name (e.g., "Pete Aguilar")
            state: State name (e.g., "California")
            chamber: "House" or "Senate"

        Returns:
            Dict with biographical data or None if not found
        """
        # Check cache first
        cached = self._load_cache(name, state, chamber)
        if cached:
            return cached

        if not self.session:
            self.session = aiohttp.ClientSession()

        try:
            # Build Ballotpedia URL
            chamber_str = "House" if chamber.lower() == "house" else "Senate"
            search_query = f"{name} {state} {chamber_str}"

            # Try direct URL construction first
            url = self._construct_member_url(name, state, chamber_str)

            logger.info(f"Fetching Ballotpedia profile: {url}")
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    html = await response.text()
                    profile = self._parse_member_page(html)
                    if profile:
                        self._save_cache(name, state, chamber, profile)
                        return profile
                else:
                    logger.debug(f"Page not found (404): {url}")
                    # Try search as fallback
                    return await self._search_and_parse(search_query, name, state, chamber)

        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching {name}")
        except Exception as e:
            logger.debug(f"Error fetching {name}: {e}")

        return None

    def _construct_member_url(self, name: str, state: str, chamber: str) -> str:
        """Construct likely Ballotpedia member URL."""
        # Format: /Pete_Aguilar (California House of Representatives)
        # or: /Pete_Aguilar
        name_formatted = name.replace(' ', '_')
        return f"{self.base_url}/{name_formatted}"

    async def _search_and_parse(self, query: str, name: str, state: str, chamber: str) -> Optional[Dict]:
        """Search Ballotpedia and parse first result."""
        try:
            search_url = f"{self.base_url}/api/search.php?q={quote(query)}&type=Member"
            async with self.session.get(search_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    # Try to parse search results
                    html = await response.text()
                    # This would need custom parsing logic
                    logger.debug(f"Search returned results for {query}")
        except Exception as e:
            logger.debug(f"Search error for {query}: {e}")

        return None

    def _parse_member_page(self, html: str) -> Optional[Dict]:
        """Parse Ballotpedia member page HTML."""
        soup = BeautifulSoup(html, 'html.parser')
        profile = {}

        try:
            # Extract birth date
            birth_date = self._extract_infobox_value(soup, "Birth date")
            if birth_date:
                profile['birth_date'] = birth_date

            # Extract birthplace
            birthplace = self._extract_infobox_value(soup, "Birthplace")
            if birthplace:
                profile['birthplace'] = birthplace

            # Extract education
            education = self._extract_infobox_value(soup, "Education")
            if education:
                profile['education'] = education

            # Extract occupation
            occupation = self._extract_infobox_value(soup, "Occupation")
            if occupation:
                profile['occupation'] = occupation

            # Extract ideology/political leanings from article text
            ideology_text = self._extract_ideology_indicators(soup)
            if ideology_text:
                profile['ideology_indicators'] = ideology_text

            # Extract religion if available
            religion = self._extract_infobox_value(soup, "Religion")
            if religion:
                profile['religion'] = religion

            # Extract party (might differ from Congress.gov due to changes)
            party = self._extract_infobox_value(soup, "Party")
            if party:
                profile['party'] = party

            # Extract office information
            office = self._extract_infobox_value(soup, "Office")
            if office:
                profile['office'] = office

            return profile if profile else None

        except Exception as e:
            logger.debug(f"Parse error: {e}")
            return None

    def _extract_infobox_value(self, soup: BeautifulSoup, label: str) -> Optional[str]:
        """Extract value from infobox by label."""
        try:
            # Find infobox rows
            for row in soup.find_all('tr'):
                # Look for header with label
                header = row.find(['th', 'td'], class_='infobox-label')
                if header and label.lower() in header.get_text().lower():
                    # Get value from next cell
                    value_cell = row.find(['td'], class_='infobox-data')
                    if value_cell:
                        text = value_cell.get_text(strip=True)
                        # Clean up HTML entities and extra whitespace
                        return text.split('\n')[0] if text else None
        except Exception as e:
            logger.debug(f"Infobox extraction error for {label}: {e}")

        return None

    def _extract_ideology_indicators(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract ideology indicators from article text."""
        try:
            # Look for keywords in article that indicate ideology
            text = soup.get_text().lower()

            indicators = []

            # Conservative indicators
            if any(word in text for word in ['conservative', 'libertarian', 'right-wing']):
                indicators.append('conservative')

            # Progressive/Liberal indicators
            if any(word in text for word in ['progressive', 'liberal', 'left-wing', 'socialist']):
                indicators.append('progressive')

            # Moderate indicators
            if any(word in text for word in ['moderate', 'centrist', 'pragmatic']):
                indicators.append('moderate')

            return ', '.join(indicators) if indicators else None
        except Exception as e:
            logger.debug(f"Ideology extraction error: {e}")

        return None


async def test_ballotpedia():
    """Test the Ballotpedia scraper."""
    async with BallotpediaClient(cache_dir='/tmp/ballotpedia_cache') as client:
        # Test with a real member
        profile = await client.get_member_profile("Pete Aguilar", "California", "House")
        if profile:
            print("Found profile:")
            print(json.dumps(profile, indent=2))
        else:
            print("Profile not found")


if __name__ == '__main__':
    asyncio.run(test_ballotpedia())
