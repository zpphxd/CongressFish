#!/usr/bin/env python3
"""
Enrich Congress member profiles with FEC campaign finance data from weball26.txt.

This script:
1. Parses cache/unitedstates/legislators-current.yaml to build bioguide→fec_id mapping
2. Parses weball26.txt (FEC bulk data file) to build fec_id→finance_data mapping
3. Updates all 614 Congress member profiles with:
   - ids.fec_id (FEC candidate ID)
   - campaign_finance (receipts, disbursements, cash_on_hand, loans, contributions)

Usage:
  python backend/agents/enrich_with_finance.py
"""

import os
import json
import logging
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('enrichment_finance.log')
    ]
)
logger = logging.getLogger(__name__)


class FinanceEnricher:
    """Enriches Congress member profiles with FEC campaign finance data."""

    # weball26.txt column indices (0-based)
    COL_FEC_ID = 0
    COL_CAND_NAME = 1
    COL_TOTAL_RECEIPTS = 5
    COL_TOTAL_DISB = 7
    COL_CASH_BEGIN = 9
    COL_CASH_END = 10
    COL_CAND_CONTRIB = 11
    COL_CAND_LOANS = 12
    COL_OTHER_LOANS = 13
    COL_STATE = 18
    COL_DISTRICT = 19
    COL_COVERAGE_DATE = 27

    def __init__(self, project_root: str):
        """Initialize paths."""
        self.project_root = project_root
        self.legislators_yaml = os.path.join(project_root, 'cache', 'unitedstates', 'legislators-current.yaml')
        self.weball_file = os.path.join(project_root, 'weball26.txt')
        self.congress_dir = os.path.join(project_root, 'backend', 'agents', 'personas', 'congress')

    def load_legislators_yaml(self) -> Dict[str, str]:
        """
        Load legislators YAML and build bioguide→fec_id mapping.

        Returns dict: {fec_id: bioguide_id}
        For members with multiple FEC IDs, prefer current chamber (H for House, S for Senate).
        """
        logger.info(f'Loading {self.legislators_yaml}')

        if not os.path.exists(self.legislators_yaml):
            raise FileNotFoundError(f'Legislators YAML not found: {self.legislators_yaml}')

        fec_to_bioguide = {}
        with open(self.legislators_yaml, 'r') as f:
            legislators = yaml.safe_load(f)

        for member in legislators:
            bioguide = member.get('id', {}).get('bioguide')
            fec_ids = member.get('id', {}).get('fec', [])

            if not bioguide or not fec_ids:
                continue

            # For members with multiple FEC IDs, pick the current chamber ID
            # (House starts with H, Senate with S, preferring current service)
            selected_fec = None

            # First pass: try to match current chamber from terms
            current_chamber = None
            terms = member.get('terms', [])
            if terms:
                last_term = terms[-1]
                current_chamber = last_term.get('type')  # 'rep' or 'sen'

            if current_chamber:
                chamber_prefix = 'H' if current_chamber == 'rep' else 'S'
                for fec_id in fec_ids:
                    if fec_id.startswith(chamber_prefix):
                        selected_fec = fec_id
                        break

            # Fallback: just pick the first one
            if not selected_fec:
                selected_fec = fec_ids[0]

            fec_to_bioguide[selected_fec] = bioguide

        logger.info(f'Loaded {len(fec_to_bioguide)} FEC ID→bioguide mappings')
        return fec_to_bioguide

    def load_weball_data(self) -> Dict[str, List[str]]:
        """
        Parse weball26.txt (FEC bulk data file).

        Returns dict: {fec_id: row_fields}
        """
        logger.info(f'Loading {self.weball_file}')

        if not os.path.exists(self.weball_file):
            raise FileNotFoundError(f'weball26.txt not found: {self.weball_file}')

        weball_data = {}
        with open(self.weball_file, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.rstrip('\n')
                fields = line.split('|')

                if len(fields) < 30:
                    logger.warning(f'Line {line_num}: Expected 30 fields, got {len(fields)}, skipping')
                    continue

                fec_id = fields[self.COL_FEC_ID].strip()
                if not fec_id:
                    logger.warning(f'Line {line_num}: Empty FEC ID, skipping')
                    continue

                weball_data[fec_id] = fields

        logger.info(f'Loaded {len(weball_data)} FEC candidate records')
        return weball_data

    def parse_float(self, value: str) -> Optional[float]:
        """Safely parse float from string, handling empty/invalid values."""
        if not value or not value.strip():
            return 0.0
        try:
            return float(value)
        except ValueError:
            logger.warning(f'Could not parse float: {value}')
            return 0.0

    def enrich_profile(self, profile: Dict, fec_id: str, weball_row: List[str]) -> Dict:
        """Enrich a Congress member profile with FEC finance data."""

        # Set FEC ID in cross-reference
        if not profile.get('ids'):
            profile['ids'] = {}
        profile['ids']['fec_id'] = fec_id

        # Parse financial fields
        receipts = self.parse_float(weball_row[self.COL_TOTAL_RECEIPTS])
        disbursements = self.parse_float(weball_row[self.COL_TOTAL_DISB])
        cash_end = self.parse_float(weball_row[self.COL_CASH_END])
        cand_contrib = self.parse_float(weball_row[self.COL_CAND_CONTRIB])
        cand_loans = self.parse_float(weball_row[self.COL_CAND_LOANS])
        other_loans = self.parse_float(weball_row[self.COL_OTHER_LOANS])

        # Create campaign_finance record
        profile['campaign_finance'] = {
            'cycle': 2026,
            'receipts': receipts,
            'disbursements': disbursements,
            'cash_on_hand': cash_end,
            'loans': cand_loans + other_loans,
            'candidate_contribution': cand_contrib,
            'top_individual_donors': [],
            'top_pac_donors': []
        }

        return profile

    def enrich_all(self):
        """Main enrichment pipeline."""
        logger.info('Starting finance enrichment pipeline')

        # Load mappings
        fec_to_bioguide = self.load_legislators_yaml()
        weball_data = self.load_weball_data()

        # Find all Congress member profile files
        house_dir = os.path.join(self.congress_dir, 'house')
        senate_dir = os.path.join(self.congress_dir, 'senate')

        profiles_updated = 0
        profiles_not_found = 0

        for chamber_dir, chamber_name in [(house_dir, 'house'), (senate_dir, 'senate')]:
            if not os.path.exists(chamber_dir):
                logger.warning(f'{chamber_name.title()} directory not found: {chamber_dir}')
                continue

            profile_files = list(Path(chamber_dir).glob('*.json'))
            logger.info(f'Found {len(profile_files)} {chamber_name} member profiles')

            for profile_path in profile_files:
                bioguide_id = profile_path.stem  # filename without extension

                # Load profile
                with open(profile_path, 'r') as f:
                    profile = json.load(f)

                # Look up FEC ID(s) for this bioguide
                matching_fec_ids = [
                    fec_id for fec_id, bg in fec_to_bioguide.items()
                    if bg == bioguide_id
                ]

                if not matching_fec_ids:
                    logger.warning(f'{bioguide_id}: No FEC ID found in legislators YAML')
                    profiles_not_found += 1
                    continue

                # Prefer the first matching FEC ID (primary for current chamber)
                fec_id = matching_fec_ids[0]

                # Look up finance data in weball
                if fec_id not in weball_data:
                    logger.warning(f'{bioguide_id} (FEC {fec_id}): Not found in weball26.txt')
                    profiles_not_found += 1
                    continue

                # Enrich profile
                self.enrich_profile(profile, fec_id, weball_data[fec_id])

                # Save updated profile
                with open(profile_path, 'w') as f:
                    json.dump(profile, f, indent=2)

                profiles_updated += 1
                if profiles_updated % 100 == 0:
                    logger.info(f'Updated {profiles_updated} profiles...')

        logger.info(f'Enrichment complete: {profiles_updated} updated, {profiles_not_found} not found')
        return profiles_updated, profiles_not_found


if __name__ == '__main__':
    enricher = FinanceEnricher(project_root)
    updated, not_found = enricher.enrich_all()

    if updated == 0:
        logger.error('No profiles were updated. Check paths and data.')
        sys.exit(1)

    logger.info(f'Success: {updated} Congress member profiles enriched with FEC finance data')
