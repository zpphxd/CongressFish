"""
Wikipedia Biographical Data Scraper
====================================
Extracts biographical backgrounds for Congress members, SCOTUS justices,
and other government officials from Wikipedia.

Uses the wikipedia_id field from unitedstates cross-reference data.

Rate limit: ~1-2 requests per second (Wikipedia has loose limits for user agents).
All responses cached to disk to avoid re-scraping during development.
"""

import os
import json
import aiohttp
import asyncio
import logging
import time
from typing import Dict, List, Optional, Any
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)


class WikipediaClient:
    """Async HTTP client for Wikipedia biographical data."""

    BASE_URL = 'https://en.wikipedia.org/w/api.php'
    REQUEST_TIMEOUT = 30
    MIN_REQUEST_INTERVAL = 1.0  # Seconds between requests (respectful rate limiting)

    def __init__(self, cache_dir: str):
        """
        Args:
            cache_dir: Directory to cache Wikipedia responses
        """
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.last_request_time = 0

    def _get_cache_path(self, wikipedia_id: str) -> str:
        """Generate a cache file path for a Wikipedia article."""
        # Sanitize filename
        safe_id = wikipedia_id.replace('/', '_').replace(' ', '_')
        return os.path.join(self.cache_dir, f'{safe_id}.json')

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

    async def _request(self, params: Dict) -> Dict:
        """
        Make an HTTP GET request to Wikipedia API with caching.

        Args:
            params: Query parameters for Wikipedia API

        Returns:
            Parsed JSON response
        """
        # Rate limit
        await self._rate_limit()

        logger.debug(f'GET Wikipedia API with params: {params}')

        async with aiohttp.ClientSession() as session:
            async with session.get(
                self.BASE_URL,
                params=params,
                timeout=aiohttp.ClientTimeout(total=self.REQUEST_TIMEOUT),
                headers={'User-Agent': 'CongressFish/1.0 (+https://github.com/zpphxd/CongressFish)'},
            ) as resp:
                if resp.status != 200:
                    raise aiohttp.ClientError(f'{resp.status} {resp.reason}')

                data = await resp.json()
                return data

    async def get_biography(self, wikipedia_id: str) -> Optional[Dict]:
        """
        Get biography for a person from Wikipedia.

        Args:
            wikipedia_id: Wikipedia article title (e.g., "John_Smith")

        Returns:
            Dict with biography data:
            {
                'wikipedia_id': str,
                'title': str,
                'extract': str,  # First paragraph plain text
                'birth_date': Optional[str],
                'birth_place': Optional[str],
                'death_date': Optional[str],
                'occupation': Optional[str],
                'education': Optional[str],
                'full_text': str,  # Full article text (sanitized)
                'infobox': Optional[Dict],  # Infobox data if available
            }
        """
        cache_path = self._get_cache_path(wikipedia_id)

        # Check cache
        cached = self._load_from_cache(cache_path)
        if cached:
            logger.debug(f'Cache hit: {wikipedia_id}')
            return cached

        try:
            # Step 1: Get page info and extract
            query_params = {
                'action': 'query',
                'format': 'json',
                'titles': wikipedia_id,
                'prop': 'extracts|pageimages|pageterms',
                'explaintext': True,
                'exintro': True,  # Only intro section
                'piprop': 'thumbnail',
                'pithumbsize': '300',
                'redirects': 1,  # Follow redirects
            }

            data = await self._request(query_params)
            pages = data.get('query', {}).get('pages', {})
            if not pages:
                logger.warning(f'No Wikipedia article found for {wikipedia_id}')
                return None

            page_id = list(pages.keys())[0]
            page = pages[page_id]

            # Check for missing page
            if 'missing' in page:
                logger.warning(f'Wikipedia article missing: {wikipedia_id}')
                return None

            title = page.get('title', wikipedia_id)
            extract = page.get('extract', '')
            image_url = None

            # Try to get image
            if 'thumbnail' in page:
                image_url = page['thumbnail'].get('source')

            # Step 2: Get full text (all sections)
            full_text_params = {
                'action': 'query',
                'format': 'json',
                'titles': title,
                'prop': 'extracts',
                'explaintext': True,
                'redirects': 1,
            }

            full_data = await self._request(full_text_params)
            full_pages = full_data.get('query', {}).get('pages', {})
            full_page_id = list(full_pages.keys())[0]
            full_text = full_pages[full_page_id].get('extract', '')

            # Step 3: Parse biography fields from intro/infobox
            bio_data = {
                'wikipedia_id': wikipedia_id,
                'title': title,
                'extract': extract,
                'full_text': full_text,
                'image_url': image_url,
                'birth_date': self._extract_field(extract, ['born', 'b.', 'birth']),
                'birth_place': self._extract_field(extract, ['born in', 'birthplace']),
                'occupation': self._extract_field(extract, ['occupation', 'profession']),
                'education': self._extract_field(full_text, ['education', 'educated at', 'graduated from']),
                'infobox': None,
            }

            # Cache result
            self._save_to_cache(cache_path, bio_data)

            return bio_data

        except Exception as e:
            logger.warning(f'Failed to fetch biography for {wikipedia_id}: {e}')
            return None

    def _extract_field(self, text: str, keywords: List[str]) -> Optional[str]:
        """
        Simple extraction of a field from text based on keywords.
        Returns the text following the first matching keyword, up to next sentence.
        """
        text_lower = text.lower()
        for keyword in keywords:
            idx = text_lower.find(keyword.lower())
            if idx != -1:
                # Find end of this sentence
                start = idx + len(keyword)
                end = text.find('.', start)
                if end == -1:
                    end = text.find('\n', start)
                if end == -1:
                    end = len(text)

                snippet = text[start:end].strip().lstrip(':').strip()
                if snippet and len(snippet) > 3:  # Only return if non-trivial
                    return snippet

        return None

    async def get_biographies_batch(
        self,
        wikipedia_ids: List[str],
        max_concurrent: int = 3,
    ) -> Dict[str, Optional[Dict]]:
        """
        Fetch biographies for multiple Wikipedia IDs concurrently (respectfully).

        Args:
            wikipedia_ids: List of Wikipedia article titles
            max_concurrent: Maximum concurrent requests (be respectful to Wikipedia)

        Returns:
            Dict mapping wikipedia_id → biography data or None if not found
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def bounded_fetch(wiki_id: str) -> tuple:
            async with semaphore:
                bio = await self.get_biography(wiki_id)
                return (wiki_id, bio)

        tasks = [bounded_fetch(wiki_id) for wiki_id in wikipedia_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        bio_dict = {}
        for result in results:
            if isinstance(result, Exception):
                logger.error(f'Batch fetch error: {result}')
                continue
            wiki_id, bio = result
            bio_dict[wiki_id] = bio

        return bio_dict


async def main():
    """Test the client."""
    cache_dir = os.path.join(
        os.path.dirname(__file__), '../../..', 'backend', 'agents', 'cache', 'wikipedia'
    )
    client = WikipediaClient(cache_dir)

    # Test: get a few Congress members' bios
    test_ids = [
        'John_F._Kennedy',
        'Alexandria_Ocasio-Cortez',
        'Mitch_McConnell',
    ]

    print('\n=== Testing Wikipedia Client ===')
    biographies = await client.get_biographies_batch(test_ids, max_concurrent=2)

    for wiki_id, bio in biographies.items():
        if bio:
            print(f'\n{wiki_id}:')
            print(f'  Title: {bio["title"]}')
            print(f'  Extract: {bio["extract"][:200]}...')
            print(f'  Birth: {bio["birth_date"]}')
        else:
            print(f'\n{wiki_id}: Not found')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
