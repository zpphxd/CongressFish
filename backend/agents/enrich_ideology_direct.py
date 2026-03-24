#!/usr/bin/env python3
"""
Enrich Congress members with ideology scores using Voteview CSV data.

Downloads DW-NOMINATE scores directly from voteview.com and enriches profiles.

Usage:
  python backend/agents/enrich_ideology_direct.py

Download link (manual):
  https://voteview.com/data - Select 119th Congress, Both chambers, CSV format
"""

import os
import json
import csv
import logging
from pathlib import Path
from typing import Dict, Optional
import sys
import asyncio
import aiohttp

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from backend.agents.config import AgentsConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class VoteviewIdeologyEnricher:
    """Enriches Congress profiles with Voteview ideology scores."""

    def __init__(self):
        """Initialize enricher."""
        self.senate_dir = Path(AgentsConfig.CONGRESS_SENATE_PERSONAS_DIR)
        self.house_dir = Path(AgentsConfig.CONGRESS_HOUSE_PERSONAS_DIR)
        self.cache_dir = Path(AgentsConfig.CACHE_DIR) / 'voteview'
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    async def download_voteview_csv(self) -> Optional[Path]:
        """
        Download Voteview 119th Congress ideology CSV.

        Returns:
            Path to CSV file or None if download failed
        """
        csv_path = self.cache_dir / '119_congress_ideology.csv'

        # Check if already cached
        if csv_path.exists():
            logger.info(f"Using cached Voteview data: {csv_path}")
            return csv_path

        logger.info("Downloading Voteview 119th Congress data...")

        # Try direct download from voteview API
        # Note: This URL might change. As of March 2026, the data API is available at:
        url = "https://voteview.com/static/data/out/members/HD119.csv"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        content = await response.text()
                        with open(csv_path, 'w') as f:
                            f.write(content)
                        logger.info(f"Downloaded Voteview CSV: {csv_path}")
                        return csv_path
                    else:
                        logger.warning(f"Download failed with status {response.status}")
                        logger.info("Please manually download from https://voteview.com/data")
                        logger.info("Select: 119th Congress, Both chambers, CSV format")
                        return None
        except Exception as e:
            logger.error(f"Download error: {e}")
            logger.info("Please manually download from https://voteview.com/data")
            return None

    def load_ideology_data(self, csv_path: Path) -> Dict[str, Dict]:
        """
        Load ideology data from CSV.

        Expected columns: bioguide_id, nominate_dim1, nominate_dim2

        Returns:
            Dict mapping bioguide_id -> {dim1, dim2, ...}
        """
        ideology_map = {}

        try:
            with open(csv_path, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    bioguide_id = row.get('bioguide_id')
                    dim1_str = row.get('nominate_dim1', '').strip()
                    dim2_str = row.get('nominate_dim2', '').strip()

                    # Only add if we have bioguide_id and valid dim1
                    if bioguide_id and dim1_str:
                        try:
                            dim1 = float(dim1_str)
                            dim2 = float(dim2_str) if dim2_str else None
                            ideology_map[bioguide_id] = {
                                'dim1': dim1,
                                'dim2': dim2,
                            }
                        except (ValueError, TypeError):
                            pass

            logger.info(f"Loaded ideology data for {len(ideology_map)} members")
            return ideology_map

        except Exception as e:
            logger.error(f"Error loading CSV: {e}")
            return {}

    def get_all_profiles(self) -> Dict[str, Path]:
        """Get all Senate and House member profiles."""
        profiles = {}
        for profile_file in self.senate_dir.glob('*.json'):
            profiles[profile_file.stem] = profile_file
        for profile_file in self.house_dir.glob('*.json'):
            profiles[profile_file.stem] = profile_file
        return profiles

    async def enrich_profiles(self) -> Dict:
        """Enrich all profiles with ideology scores."""
        logger.info('='*70)
        logger.info('ENRICHING WITH VOTEVIEW IDEOLOGY SCORES')
        logger.info('='*70)

        # Download CSV
        csv_path = await self.download_voteview_csv()
        if not csv_path:
            logger.error("Cannot proceed without Voteview CSV data")
            return {'success': 0, 'failed': 0, 'skipped': 0}

        # Load ideology data
        ideology_data = self.load_ideology_data(csv_path)
        if not ideology_data:
            logger.error("No ideology data loaded")
            return {'success': 0, 'failed': 0, 'skipped': 0}

        # Enrich profiles
        profiles = self.get_all_profiles()
        stats = {'success': 0, 'failed': 0, 'skipped': 0}

        for i, (bioguide_id, profile_path) in enumerate(profiles.items(), 1):
            try:
                with open(profile_path, 'r') as f:
                    profile = json.load(f)

                ideology = ideology_data.get(bioguide_id)
                if ideology:
                    profile['ideology'] = {
                        'primary_dimension': ideology['dim1'],
                        'secondary_dimension': ideology['dim2'],
                        'source': 'Voteview',
                        'year': 2026
                    }

                    # Save updated profile
                    with open(profile_path, 'w') as f:
                        json.dump(profile, f, indent=2)
                    stats['success'] += 1

                    if i % 100 == 0:
                        logger.info(f'  ({i}/{len(profiles)}) Enriched {i} profiles')
                else:
                    stats['skipped'] += 1

            except Exception as e:
                logger.warning(f'Failed to enrich {bioguide_id}: {e}')
                stats['failed'] += 1

        return stats


async def main():
    """Main entry point."""
    enricher = VoteviewIdeologyEnricher()
    stats = await enricher.enrich_profiles()

    logger.info('')
    logger.info('='*70)
    logger.info('IDEOLOGY ENRICHMENT COMPLETE')
    logger.info('='*70)
    logger.info(f'Success: {stats["success"]}, Failed: {stats["failed"]}, Skipped: {stats["skipped"]}')


if __name__ == '__main__':
    asyncio.run(main())
