#!/usr/bin/env python3
"""
Load enriched Congress profiles into Neo4j knowledge graph.

Usage:
  python backend/graph/load_graph.py [--reset] [--neo4j-uri bolt://localhost:7687]
"""

import os
import json
import logging
import argparse
import sys
from pathlib import Path
from typing import List, Dict, Any

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from backend.graph.neo4j_client import Neo4jClient
from backend.graph.neo4j_schema import Neo4jSchema, Neo4jLoader, DEFAULT_PARTIES, DEFAULT_STATES

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_profiles_from_disk(congress_dir: str) -> List[Dict[str, Any]]:
    """Load all Congress member profiles from JSON files."""
    profiles = []
    profile_dir = Path(congress_dir)

    for chamber_dir in profile_dir.glob("*/"):
        if chamber_dir.is_dir():
            for profile_file in chamber_dir.glob("*.json"):
                try:
                    with open(profile_file) as f:
                        profile = json.load(f)
                        profiles.append(profile)
                except Exception as e:
                    logger.warning(f"Failed to load {profile_file}: {e}")

    return profiles


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Load Congress profiles into Neo4j")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear all data before loading (dangerous!)"
    )
    parser.add_argument(
        "--neo4j-uri",
        default="bolt://localhost:7687",
        help="Neo4j connection URI"
    )
    parser.add_argument(
        "--neo4j-user",
        default="neo4j",
        help="Neo4j username"
    )
    parser.add_argument(
        "--neo4j-password",
        default="password",
        help="Neo4j password"
    )
    args = parser.parse_args()

    # Connect to Neo4j
    client = Neo4jClient(
        uri=args.neo4j_uri,
        user=args.neo4j_user,
        password=args.neo4j_password
    )

    if not client.connect():
        logger.error("Could not connect to Neo4j. Make sure it's running.")
        sys.exit(1)

    # Initialize schema
    logger.info("Initializing Neo4j schema...")
    schema = Neo4jSchema(client.driver)

    if args.reset:
        logger.warning("Resetting graph (deleting all data)...")
        schema.clear_graph()

    schema.create_constraints()
    schema.create_indexes()

    # Create foundational nodes
    logger.info("Creating Party and State nodes...")
    schema.create_parties(DEFAULT_PARTIES)

    # Load US states (full list)
    us_states = [
        {"name": "Alabama", "code": "ALABAMA", "abbreviation": "AL"},
        {"name": "Alaska", "code": "ALASKA", "abbreviation": "AK"},
        {"name": "Arizona", "code": "ARIZONA", "abbreviation": "AZ"},
        {"name": "Arkansas", "code": "ARKANSAS", "abbreviation": "AR"},
        {"name": "California", "code": "CALIFORNIA", "abbreviation": "CA"},
        {"name": "Colorado", "code": "COLORADO", "abbreviation": "CO"},
        {"name": "Connecticut", "code": "CONNECTICUT", "abbreviation": "CT"},
        {"name": "Delaware", "code": "DELAWARE", "abbreviation": "DE"},
        {"name": "Florida", "code": "FLORIDA", "abbreviation": "FL"},
        {"name": "Georgia", "code": "GEORGIA", "abbreviation": "GA"},
        {"name": "Hawaii", "code": "HAWAII", "abbreviation": "HI"},
        {"name": "Idaho", "code": "IDAHO", "abbreviation": "ID"},
        {"name": "Illinois", "code": "ILLINOIS", "abbreviation": "IL"},
        {"name": "Indiana", "code": "INDIANA", "abbreviation": "IN"},
        {"name": "Iowa", "code": "IOWA", "abbreviation": "IA"},
        {"name": "Kansas", "code": "KANSAS", "abbreviation": "KS"},
        {"name": "Kentucky", "code": "KENTUCKY", "abbreviation": "KY"},
        {"name": "Louisiana", "code": "LOUISIANA", "abbreviation": "LA"},
        {"name": "Maine", "code": "MAINE", "abbreviation": "ME"},
        {"name": "Maryland", "code": "MARYLAND", "abbreviation": "MD"},
        {"name": "Massachusetts", "code": "MASSACHUSETTS", "abbreviation": "MA"},
        {"name": "Michigan", "code": "MICHIGAN", "abbreviation": "MI"},
        {"name": "Minnesota", "code": "MINNESOTA", "abbreviation": "MN"},
        {"name": "Mississippi", "code": "MISSISSIPPI", "abbreviation": "MS"},
        {"name": "Missouri", "code": "MISSOURI", "abbreviation": "MO"},
        {"name": "Montana", "code": "MONTANA", "abbreviation": "MT"},
        {"name": "Nebraska", "code": "NEBRASKA", "abbreviation": "NE"},
        {"name": "Nevada", "code": "NEVADA", "abbreviation": "NV"},
        {"name": "New Hampshire", "code": "NEW HAMPSHIRE", "abbreviation": "NH"},
        {"name": "New Jersey", "code": "NEW JERSEY", "abbreviation": "NJ"},
        {"name": "New Mexico", "code": "NEW MEXICO", "abbreviation": "NM"},
        {"name": "New York", "code": "NEW YORK", "abbreviation": "NY"},
        {"name": "North Carolina", "code": "NORTH CAROLINA", "abbreviation": "NC"},
        {"name": "North Dakota", "code": "NORTH DAKOTA", "abbreviation": "ND"},
        {"name": "Ohio", "code": "OHIO", "abbreviation": "OH"},
        {"name": "Oklahoma", "code": "OKLAHOMA", "abbreviation": "OK"},
        {"name": "Oregon", "code": "OREGON", "abbreviation": "OR"},
        {"name": "Pennsylvania", "code": "PENNSYLVANIA", "abbreviation": "PA"},
        {"name": "Rhode Island", "code": "RHODE ISLAND", "abbreviation": "RI"},
        {"name": "South Carolina", "code": "SOUTH CAROLINA", "abbreviation": "SC"},
        {"name": "South Dakota", "code": "SOUTH DAKOTA", "abbreviation": "SD"},
        {"name": "Tennessee", "code": "TENNESSEE", "abbreviation": "TN"},
        {"name": "Texas", "code": "TEXAS", "abbreviation": "TX"},
        {"name": "Utah", "code": "UTAH", "abbreviation": "UT"},
        {"name": "Vermont", "code": "VERMONT", "abbreviation": "VT"},
        {"name": "Virginia", "code": "VIRGINIA", "abbreviation": "VA"},
        {"name": "Washington", "code": "WASHINGTON", "abbreviation": "WA"},
        {"name": "West Virginia", "code": "WEST VIRGINIA", "abbreviation": "WV"},
        {"name": "Wisconsin", "code": "WISCONSIN", "abbreviation": "WI"},
        {"name": "Wyoming", "code": "WYOMING", "abbreviation": "WY"},
        {"name": "District of Columbia", "code": "DISTRICT OF COLUMBIA", "abbreviation": "DC"},
    ]
    schema.create_states(us_states)

    # Load Congress member profiles
    congress_dir = os.path.join(project_root, "backend", "agents", "personas", "congress")
    logger.info(f"Loading Congress member profiles from {congress_dir}...")
    profiles = load_profiles_from_disk(congress_dir)

    if not profiles:
        logger.error(f"No profiles found in {congress_dir}")
        sys.exit(1)

    logger.info(f"Found {len(profiles)} profiles")

    # Load members into graph
    loader = Neo4jLoader(client.driver)
    loader.load_all_members(profiles)

    # Create relationships
    logger.info("Creating relationship networks...")
    loader.create_cosponsorship_network()
    loader.create_ideology_clusters()

    # Report stats
    logger.info("Graph loading complete!")
    stats = Neo4jClient(
        uri=args.neo4j_uri,
        user=args.neo4j_user,
        password=args.neo4j_password
    ).get_graph_stats()

    print("\n" + "="*50)
    print("GRAPH STATISTICS")
    print("="*50)
    for key, value in stats.items():
        print(f"  {key}: {value:,}")
    print("="*50 + "\n")

    client.close()


if __name__ == "__main__":
    main()
