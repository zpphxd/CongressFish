#!/usr/bin/env python3
"""
Grok API client for enriching Congress member biographical data.

Uses xAI's Grok API to fetch and parse biographical information for Congress members.

Usage:
  from backend.agents.apis.grok import GrokClient
  client = GrokClient(api_key="xai-...")
  bio = await client.get_biography("Robert B. Aderholt", "ALABAMA", "house")
"""

import os
import asyncio
import aiohttp
import logging
import json
from typing import Dict, Optional
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GrokClient:
    """Async HTTP client for Grok biographical data."""

    BASE_URL = "https://api.x.ai/v1/chat/completions"
    REQUEST_TIMEOUT = 60
    MIN_REQUEST_INTERVAL = 0.5  # Seconds between requests (rate limiting)

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Grok client.

        Args:
            api_key: xAI API key. If not provided, reads from XAI_API_KEY env var.
        """
        self.api_key = api_key or os.getenv("XAI_API_KEY")
        if not self.api_key:
            raise ValueError("XAI_API_KEY not provided and not in environment")

        self.last_request_time = 0

    async def _rate_limit(self) -> None:
        """Enforce minimum interval between requests."""
        elapsed = asyncio.get_event_loop().time() - self.last_request_time
        if elapsed < self.MIN_REQUEST_INTERVAL:
            await asyncio.sleep(self.MIN_REQUEST_INTERVAL - elapsed)
        self.last_request_time = asyncio.get_event_loop().time()

    async def _request(self, prompt: str, model: str = "grok") -> Optional[str]:
        """
        Make an async HTTP request to Grok API.

        Args:
            prompt: The prompt to send to Grok
            model: Model to use (tries alternatives if first fails)

        Returns:
            Response text or None if request failed
        """
        await self._rate_limit()

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Try multiple model names in case API has changed
        models_to_try = [model, "grok-3", "grok-beta", "grok-2", "grok-1", "grok-vision"]

        for try_model in models_to_try:
            payload = {
                "model": try_model,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.7,
                "max_tokens": 1000,
            }

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        self.BASE_URL,
                        json=payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=self.REQUEST_TIMEOUT),
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            message = data.get('choices', [{}])[0].get('message', {})
                            content = message.get('content', '')
                            logger.info(f'Successfully used model: {try_model}')
                            return content
                        elif resp.status == 400:
                            error_text = await resp.text()
                            if 'model not found' in error_text.lower():
                                logger.debug(f'Model {try_model} not found, trying next...')
                                continue
                            else:
                                logger.warning(f'Grok API error {resp.status}: {error_text}')
                                return None
                        else:
                            error_text = await resp.text()
                            logger.warning(f'Grok API error {resp.status}: {error_text}')
                            return None

            except asyncio.TimeoutError:
                logger.warning(f'Grok API request timeout with model {try_model}')
                continue
            except Exception as e:
                logger.warning(f'Grok API request failed with model {try_model}: {e}')
                continue

        logger.warning(f'All Grok models failed: {models_to_try}')
        return None

    async def get_biography(self, full_name: str, state: str, chamber: str) -> Optional[Dict]:
        """
        Get biography for a Congress member from Grok using Grokpedia (real-time web search).

        Args:
            full_name: Full name (e.g., "Robert B. Aderholt")
            state: State name (e.g., "ALABAMA")
            chamber: Chamber (e.g., "house" or "senate")

        Returns:
            Dict with biography data or None if not found
        """
        try:
            # Build a specific prompt for Congress member biography using Grokpedia
            # Grokpedia allows Grok to search the web for real-time information
            prompt = f"""Use Grokpedia to search for and extract biographical information for {full_name}, a US Congress member from {state} ({chamber.upper()}).

Search for their Wikipedia page, official biography, and news sources to find:
- Birth date (YYYY-MM-DD format if available)
- Birth place (City, State or country)
- Education (universities/schools attended)
- Prior occupation/profession before Congress
- Brief 1-2 sentence biographical summary

Return ONLY a valid JSON object with these exact fields (use null for any missing data):
{{
  "birth_date": "YYYY-MM-DD or null",
  "birth_place": "City, State or null",
  "education": "School/University names or null",
  "occupation": "Prior occupation or profession or null",
  "summary": "1-2 sentence biographical summary or null"
}}

Be factual and accurate. Return ONLY the JSON object, no other text or explanation."""

            response = await self._request(prompt)

            if not response:
                logger.debug(f'{full_name}: No response from Grok')
                return None

            # Parse JSON response
            try:
                # Try to extract JSON from the response (in case there's extra text)
                response_clean = response.strip()
                if response_clean.startswith('{'):
                    # Find the closing brace
                    json_end = response_clean.rfind('}')
                    if json_end != -1:
                        response_clean = response_clean[:json_end + 1]

                bio_data = json.loads(response_clean)

                # Rename 'summary' to 'wikipedia_summary' for consistency with profile model
                if 'summary' in bio_data:
                    bio_data['wikipedia_summary'] = bio_data.pop('summary')

                # Filter out null values
                bio_data = {k: v for k, v in bio_data.items() if v is not None}

                if bio_data:
                    logger.debug(f'{full_name}: Got biography data from Grok')
                    return bio_data
                else:
                    logger.debug(f'{full_name}: No data returned from Grok')
                    return None

            except json.JSONDecodeError as e:
                logger.warning(f'{full_name}: Failed to parse Grok response as JSON: {e}')
                logger.debug(f'Raw response: {response}')
                return None

        except Exception as e:
            logger.warning(f'{full_name}: Error fetching biography from Grok: {e}')
            return None

    async def get_biographies_batch(
        self,
        congress_members: list,
        max_concurrent: int = 5,
    ) -> Dict[str, Optional[Dict]]:
        """
        Fetch biographies for multiple Congress members concurrently.

        Args:
            congress_members: List of dicts with 'full_name', 'state', 'chamber' keys
            max_concurrent: Maximum concurrent requests

        Returns:
            Dict mapping full_name → biography data or None if not found
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def bounded_fetch(member: Dict) -> tuple:
            async with semaphore:
                bio = await self.get_biography(
                    member['full_name'],
                    member['state'],
                    member['chamber']
                )
                return (member['full_name'], bio)

        tasks = [bounded_fetch(member) for member in congress_members]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        bio_dict = {}
        for result in results:
            if isinstance(result, Exception):
                logger.error(f'Batch fetch error: {result}')
                continue
            name, bio = result
            bio_dict[name] = bio

        return bio_dict


async def main():
    """Test the Grok client."""
    try:
        client = GrokClient()
    except ValueError as e:
        logger.error(f'Failed to initialize Grok client: {e}')
        return

    # Test: get a few Congress members' bios
    test_members = [
        {"full_name": "Robert B. Aderholt", "state": "ALABAMA", "chamber": "house"},
        {"full_name": "Alexandria Ocasio-Cortez", "state": "NEW YORK", "chamber": "house"},
    ]

    logger.info(f'Testing Grok client with {len(test_members)} members...')

    results = await client.get_biographies_batch(test_members)

    for name, bio in results.items():
        if bio:
            logger.info(f'{name}: {bio}')
        else:
            logger.warning(f'{name}: No biography found')


if __name__ == '__main__':
    asyncio.run(main())
