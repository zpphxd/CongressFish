#!/usr/bin/env python3
"""
Generate AI personas for Congress members using Ollama.

Analyzes biographical data, ideology scores, committee assignments, and
generates behavioral profiles that capture each member's priorities,
decision-making style, and negotiation characteristics.

Usage:
  python backend/agents/generate_personas.py [--model mistral|neural-chat|llama2]
"""

import os
import json
import logging
import asyncio
import argparse
import sys
from pathlib import Path
from typing import Dict, Optional, Any

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('persona_generation.log')
    ]
)
logger = logging.getLogger(__name__)


class OllamaPersonaGenerator:
    """Generates AI personas using Ollama local LLM."""

    def __init__(self, model: str = "mistral", base_url: str = "http://localhost:11434"):
        """
        Initialize persona generator.

        Args:
            model: Ollama model name (mistral, neural-chat, llama2)
            base_url: Ollama API base URL
        """
        self.model = model
        self.base_url = base_url
        self.api_endpoint = f"{base_url}/api/generate"

    async def generate_persona(self, profile: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """
        Generate persona narrative for a Congress member.

        Args:
            profile: Congress member profile dict

        Returns:
            Dict with persona fields or None if generation failed
        """
        full_name = profile.get("full_name")
        chamber = profile.get("chamber", "").upper()
        state = profile.get("state", "")
        party = profile.get("party", "")

        # Extract biographical context
        bio = profile.get("biography", {})
        ideology = profile.get("ideology", {})
        committees = profile.get("committee_assignments", [])
        finance = profile.get("campaign_finance", {})

        committee_list = ", ".join([c.get("title", c.get("code", "")) for c in committees[:3]])

        prompt = f"""Based on this Congress member's profile, generate a detailed behavioral persona.

NAME: {full_name}
CHAMBER: {chamber}
STATE: {state}
PARTY: {party}

BACKGROUND:
- Birth date: {bio.get('birth_date', 'Unknown')}
- Education: {bio.get('education', 'Unknown')}
- Occupation before Congress: {bio.get('occupation', 'Unknown')}
- Summary: {bio.get('wikipedia_summary', 'No summary available')}
- Full biography: {bio.get('full_biography', 'Not available')[:200]}...

IDEOLOGY & VOTING:
- Primary ideology score: {ideology.get('primary_dimension', 'Unknown')} (from -1 far left to +1 far right)
- Secondary dimension: {ideology.get('secondary_dimension', 'Unknown')}

COMMITTEES:
- {committee_list}

CAMPAIGN FINANCE:
- Receipts: ${finance.get('receipts', 0):,.0f}
- Cash on hand: ${finance.get('cash_on_hand', 0):,.0f}

Generate a behavioral persona that captures:
1. **Core values & priorities** - What issues does this member care most about? How does their background shape their priorities?
2. **Decision-making style** - Are they ideological or pragmatic? Do they negotiate or hold firm? How do they vote?
3. **Communication style** - Formal or personable? Technical or emotional appeals? Likely to debate or stay quiet?
4. **Party relationship** - Are they party loyalists or mavericks? Where do they diverge from the party line?
5. **Negotiation approach** - What would persuade this member to support/oppose a bill?
6. **Key interests** - Which policy areas are they most passionate about?

Format as a JSON object with these fields:
- core_values: String describing main values and priorities
- decision_style: How they make legislative decisions
- communication_style: How they communicate and debate
- party_relationship: Their relationship with party leadership
- negotiation_approach: What would persuade them
- key_interests: Main policy focus areas
- voting_pattern: Typical voting behavior
- likely_positions: Where they'd typically stand on common bills

Be specific and persona-based, as if describing a real political actor."""

        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "num_predict": 1500,
                    }
                }

                async with session.post(self.api_endpoint, json=payload, timeout=300) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        response_text = data.get("response", "")

                        # Extract JSON from response
                        try:
                            # Find JSON object in response
                            json_start = response_text.find("{")
                            json_end = response_text.rfind("}") + 1
                            if json_start != -1 and json_end > json_start:
                                json_str = response_text[json_start:json_end]
                                persona = json.loads(json_str)
                                logger.info(f"✓ Generated persona for {full_name}")
                                return persona
                        except json.JSONDecodeError:
                            # Return as raw narrative if JSON extraction fails
                            logger.warning(f"{full_name}: Could not parse as JSON, storing as narrative")
                            return {"persona_narrative": response_text}
                    else:
                        logger.warning(f"{full_name}: Ollama API error {resp.status}")
                        return None

        except Exception as e:
            logger.warning(f"{full_name}: Error generating persona: {e}")
            return None

    async def generate_all_personas(
        self,
        profiles: list,
        max_concurrent: int = 2
    ) -> int:
        """
        Generate personas for all Congress members.

        Args:
            profiles: List of member profile dicts
            max_concurrent: Max concurrent Ollama requests (keep low to avoid overload)

        Returns:
            Count of successfully generated personas
        """
        logger.info(f"Starting persona generation for {len(profiles)} members")
        logger.info(f"Using model: {self.model}")

        semaphore = asyncio.Semaphore(max_concurrent)
        success_count = 0

        async def bounded_generate(profile):
            async with semaphore:
                persona = await self.generate_persona(profile)
                return (profile.get("bioguide_id"), persona)

        tasks = [bounded_generate(p) for p in profiles]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for bioguide_id, persona in results:
            if isinstance(persona, Exception):
                logger.error(f"{bioguide_id}: Generation error: {persona}")
                continue

            if persona:
                # Find and update the profile file
                profile_path = self._find_profile_file(bioguide_id)
                if profile_path:
                    self._save_persona_to_profile(profile_path, persona)
                    success_count += 1

        logger.info(f"✓ Generated {success_count} personas")
        return success_count

    def _find_profile_file(self, bioguide_id: str) -> Optional[str]:
        """Locate a profile file by bioguide_id."""
        congress_dir = Path(project_root) / "backend" / "agents" / "personas" / "congress"
        for chamber_dir in ["house", "senate"]:
            profile_file = congress_dir / chamber_dir / f"{bioguide_id}.json"
            if profile_file.exists():
                return str(profile_file)
        return None

    def _save_persona_to_profile(self, profile_path: str, persona: Dict[str, str]) -> None:
        """Merge generated persona into profile JSON."""
        try:
            with open(profile_path, "r") as f:
                profile = json.load(f)

            # Add persona fields
            if "persona" not in profile:
                profile["persona"] = {}

            profile["persona"].update(persona)
            profile["persona_narrative"] = persona.get(
                "persona_narrative",
                json.dumps(persona, indent=2)
            )

            with open(profile_path, "w") as f:
                json.dump(profile, f, indent=2)

        except Exception as e:
            logger.error(f"Error saving persona to {profile_path}: {e}")


def load_all_profiles(congress_dir: str) -> list:
    """Load all Congress member profiles from disk."""
    profiles = []
    congress_path = Path(congress_dir)

    for chamber_dir in ["house", "senate"]:
        chamber_path = congress_path / chamber_dir
        if chamber_path.exists():
            for profile_file in chamber_path.glob("*.json"):
                try:
                    with open(profile_file) as f:
                        profiles.append(json.load(f))
                except Exception as e:
                    logger.warning(f"Failed to load {profile_file}: {e}")

    return profiles


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Generate AI personas for Congress members")
    parser.add_argument(
        "--model",
        default="mistral",
        choices=["mistral", "neural-chat", "llama2"],
        help="Ollama model to use"
    )
    parser.add_argument(
        "--ollama-url",
        default="http://localhost:11434",
        help="Ollama API base URL"
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=2,
        help="Max concurrent requests (keep low)"
    )
    args = parser.parse_args()

    # Load profiles
    congress_dir = os.path.join(project_root, "backend", "agents", "personas", "congress")
    profiles = load_all_profiles(congress_dir)

    if not profiles:
        logger.error(f"No profiles found in {congress_dir}")
        sys.exit(1)

    logger.info(f"Loaded {len(profiles)} profiles")

    # Generate personas
    generator = OllamaPersonaGenerator(model=args.model, base_url=args.ollama_url)
    success = await generator.generate_all_personas(profiles, max_concurrent=args.concurrency)

    logger.info(f"\n{'='*50}")
    logger.info(f"Persona generation complete: {success}/{len(profiles)} successful")
    logger.info(f"{'='*50}")


if __name__ == "__main__":
    asyncio.run(main())
