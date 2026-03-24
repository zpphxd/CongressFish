#!/usr/bin/env python3
"""
Enrich Congress member profiles with campaign finance data from weball26.txt.
Matches by name since FEC IDs aren't in legislators-current.yaml.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Tuple
import difflib

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(), logging.FileHandler('enrichment_finance.log')]
)
logger = logging.getLogger(__name__)

project_root = Path(__file__).parent.parent.parent


def parse_weball26() -> Dict[str, Dict]:
    """Parse weball26.txt and return FEC data keyed by normalized name."""
    weball_path = project_root / 'weball26.txt'

    if not weball_path.exists():
        logger.error(f"✗ Cannot find weball26.txt at {weball_path}")
        return {}

    data = {}
    try:
        with open(weball_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                parts = line.split('|')
                if len(parts) < 15:
                    continue

                fec_id = parts[0]  # Committee ID (has chamber prefix)
                name = parts[1].strip()  # NAME field
                
                try:
                    finance = {
                        'fec_id': fec_id,
                        'name': name,
                        'receipts': float(parts[5]) if parts[5] else 0.0,
                        'disbursements': float(parts[7]) if parts[7] else 0.0,
                        'cash_on_hand': float(parts[10]) if parts[10] else 0.0,
                        'candidate_contribution': float(parts[11]) if parts[11] else 0.0,
                        'candidate_loans': float(parts[12]) if parts[12] else 0.0,
                        'other_loans': float(parts[13]) if parts[13] else 0.0,
                    }
                    # Use normalized name as key
                    norm_name = name.upper()
                    if norm_name not in data:
                        data[norm_name] = finance
                    else:
                        # Keep record with highest receipts
                        if finance['receipts'] > data[norm_name]['receipts']:
                            data[norm_name] = finance
                except (ValueError, IndexError):
                    continue

        logger.info(f"✓ Parsed {len(data)} unique candidate records from weball26.txt")
        return data

    except Exception as e:
        logger.error(f"✗ Error parsing weball26.txt: {e}")
        return {}


def find_best_match(profile_name: str, weball_data: Dict) -> Dict | None:
    """Find best matching FEC record by name similarity."""
    if not weball_data:
        return None
    
    norm_profile_name = profile_name.upper()
    
    # Exact match first
    if norm_profile_name in weball_data:
        return weball_data[norm_profile_name]
    
    # Fuzzy match
    matches = difflib.get_close_matches(norm_profile_name, weball_data.keys(), n=1, cutoff=0.6)
    if matches:
        return weball_data[matches[0]]
    
    return None


def enrich_profiles_with_finance(weball_data: Dict) -> Tuple[int, int]:
    """Enrich all Congress member profiles with campaign finance data."""
    congress_dir = project_root / 'backend' / 'agents' / 'personas' / 'congress'

    success_count = 0
    total_count = 0
    unmatched = []

    for chamber_dir in ['house', 'senate']:
        chamber_path = congress_dir / chamber_dir
        if not chamber_path.exists():
            continue

        for profile_file in sorted(chamber_path.glob('*.json')):
            total_count += 1
            bioguide_id = profile_file.stem

            try:
                with open(profile_file, 'r') as f:
                    profile = json.load(f)

                full_name = profile.get('full_name', '')
                finance = find_best_match(full_name, weball_data)
                
                if not finance:
                    unmatched.append((bioguide_id, full_name, 'No matching FEC record'))
                    continue

                if 'ids' not in profile:
                    profile['ids'] = {}
                profile['ids']['fec_id'] = finance['fec_id']

                profile['campaign_finance'] = {
                    'cycle': 2026,
                    'receipts': finance['receipts'],
                    'disbursements': finance['disbursements'],
                    'cash_on_hand': finance['cash_on_hand'],
                    'candidate_contribution': finance['candidate_contribution'],
                    'candidate_loans': finance['candidate_loans'],
                    'other_loans': finance['other_loans'],
                    'total_loans': finance['candidate_loans'] + finance['other_loans'],
                }

                with open(profile_file, 'w') as f:
                    json.dump(profile, f, indent=2)

                success_count += 1

                if success_count % 50 == 0:
                    logger.info(f"✓ Enriched {success_count} profiles...")

            except Exception as e:
                logger.warning(f"✗ Error processing {bioguide_id}: {e}")

    if unmatched:
        logger.warning(f"\n⚠ {len(unmatched)} profiles could not be matched:")
        for bioguide, name, reason in unmatched[:10]:
            logger.warning(f"  - {name} ({bioguide}): {reason}")
        if len(unmatched) > 10:
            logger.warning(f"  ... and {len(unmatched) - 10} more")

    return success_count, total_count


def main():
    """Main enrichment flow."""
    logger.info("=" * 60)
    logger.info("Campaign Finance Enrichment Started")
    logger.info("=" * 60)

    logger.info("\n1. Parsing FEC data from weball26.txt...")
    weball_data = parse_weball26()

    logger.info("\n2. Enriching profiles...")
    success_count, total_count = enrich_profiles_with_finance(weball_data)

    logger.info("\n" + "=" * 60)
    logger.info(f"✓ Finance Enrichment Complete: {success_count}/{total_count} profiles")
    logger.info("=" * 60)


if __name__ == '__main__':
    main()
