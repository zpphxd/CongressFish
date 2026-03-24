#!/usr/bin/env python3
"""
Grok API client for enriching Congress member biographical data.

Uses xAI's Grok API with Grokpedia (real-time web search) to fetch comprehensive
biographical information for Congress members.

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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GrokClient:
    """Async HTTP client for Grok biographical data via Grokpedia."""

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

    async def _request(self, prompt: str, model: str = "grok-3") -> Optional[str]:
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
                "max_tokens": 2000,
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
        Get comprehensive biography for a Congress member from Grok using Grokpedia.

        Uses real-time web search to gather complete biographical information from
        Wikipedia, news sources, official biographies, and other public sources.

        Args:
            full_name: Full name (e.g., "Robert B. Aderholt")
            state: State name (e.g., "ALABAMA")
            chamber: Chamber (e.g., "house" or "senate")

        Returns:
            Dict with comprehensive biography data or None if not found
        """
        try:
            # Build comprehensive biography prompt using Grokpedia
            prompt = f"""Use Grokpedia to search for and extract COMPLETE biographical information for {full_name}, a US Congress member from {state} ({chamber.upper()}).

Search Wikipedia, official government sources, news archives, and other public sources to find:

BASIC INFORMATION:
- Full legal name and any nicknames/aliases
- Birth date (YYYY-MM-DD format if available)
- Birth place (City, State/Country)
- Death date if applicable (YYYY-MM-DD format)
- Age/current age
- Gender/pronouns

EDUCATION:
- All universities, colleges, schools attended (in chronological order)
- Degrees earned and fields of study
- Graduation years if available
- Any notable academic honors or achievements

CAREER BEFORE CONGRESS:
- Complete professional history before entering Congress
- Job titles, employers, tenure dates
- Military service if applicable (branch, rank, years)
- Business ownership or significant roles
- Key professional accomplishments

POLITICAL CAREER:
- First elected to Congress (year)
- Districts/states represented
- Committee assignments and subcommittee work
- Leadership positions held
- Major legislation sponsored or co-sponsored
- Committee rankings and seniority
- Political party affiliation
- Previous political offices (state legislature, local office, etc.)

PERSONAL INFORMATION:
- Family information (spouse, children if public)
- Religion/faith affiliation
- Known causes or advocacy areas
- Major controversies or notable incidents (if documented in reliable sources)

CURRENT STATUS:
- Term start and end dates
- Current committee assignments
- Leadership roles
- Office location and contact information if publicly available

Return a valid JSON object with ALL available fields. Use null ONLY for fields with no publicly available information. Be comprehensive and thorough.

Example JSON structure:
- full_name (string)
- birth_date (YYYY-MM-DD or null)
- birth_place (string or null)
- death_date (YYYY-MM-DD or null)
- age (number or null)
- gender (string or null)
- education (comma-separated list or null)
- education_details (detailed history or null)
- career_before_congress (detailed professional history or null)
- military_service (military background or null)
- political_career_summary (overview or null)
- committees (current assignments or null)
- committee_seniority (ranking/seniority information or null)
- first_elected (year or null)
- districts_represented (list or null)
- major_legislation (bills sponsored or null)
- political_party (affiliation or null)
- previous_offices (prior positions or null)
- family (family information if public or null)
- religion (faith affiliation or null)
- advocacy_areas (causes championed or null)
- notable_controversies (documented incidents or null)
- current_term_dates (term start/end or null)
- office_location (office address or null)
- wikipedia_summary (1-3 sentence summary or null)
- full_biography (comprehensive 2-4 paragraph narrative or null)

Be factual, comprehensive, and accurate. Include ALL available information. Return ONLY valid JSON, no other text."""

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

                # Filter out null values, keep everything else
                bio_data = {k: v for k, v in bio_data.items() if v is not None}

                if bio_data:
                    logger.debug(f'{full_name}: Got comprehensive biography data from Grok')
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
