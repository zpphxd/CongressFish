#!/usr/bin/env python3
"""Import prebuilt Congress member personas into Neo4j graph.

This script reads all persona JSON files from the personas/ directory
and creates corresponding CongressMember nodes in Neo4j with all their
properties (party, ideology, state, biography, finance, etc).
"""

import json
import logging
from pathlib import Path
from typing import Dict, List

from neo4j import GraphDatabase

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


class PersonaImporter:
    """Import personas into Neo4j."""

    def __init__(self, neo4j_uri: str = "bolt://localhost:7687", auth=("neo4j", "password")):
        """Initialize Neo4j connection."""
        self.driver = GraphDatabase.driver(neo4j_uri, auth=auth)
        logger.info(f"✓ Connected to Neo4j at {neo4j_uri}")

    def close(self):
        """Close Neo4j connection."""
        self.driver.close()

    def import_personas(self, personas_dir: str):
        """Import all personas from directory."""
        personas_path = Path(personas_dir)

        if not personas_path.exists():
            logger.error(f"✗ Personas directory not found: {personas_dir}")
            return

        # Import Congress members
        self._import_congress_members(personas_path / "congress" / "house", "house")
        self._import_congress_members(personas_path / "congress" / "senate", "senate")

        # Import executive branch
        self._import_executive_branch(personas_path / "executive")

        # Import SCOTUS
        self._import_scotus(personas_path / "scotus")

        logger.info("✓ Persona import complete")

    def _import_congress_members(self, chamber_dir: Path, chamber: str):
        """Import Congress members from chamber directory."""
        if not chamber_dir.exists():
            logger.warning(f"⚠ Chamber directory not found: {chamber_dir}")
            return

        member_files = list(chamber_dir.glob("*.json"))
        logger.info(f"📥 Importing {len(member_files)} {chamber.title()} members...")

        success = 0
        for persona_file in member_files:
            try:
                with open(persona_file, 'r') as f:
                    persona = json.load(f)

                # Create or update CongressMember node
                self._create_congress_member_node(persona, chamber)
                success += 1

            except Exception as e:
                logger.warning(f"  ✗ Failed to import {persona_file.stem}: {e}")

        logger.info(f"  ✓ Imported {success}/{len(member_files)} {chamber} members")

    def _create_congress_member_node(self, persona: Dict, chamber: str):
        """Create CongressMember node in Neo4j."""
        bioguide_id = persona.get("bioguide_id")
        if not bioguide_id:
            logger.warning(f"  ⚠ No bioguide_id in persona: {persona.get('full_name', 'Unknown')}")
            return

        # Build properties dictionary
        properties = {
            "bioguide_id": bioguide_id,
            "full_name": persona.get("full_name", ""),
            "first_name": persona.get("first_name", ""),
            "last_name": persona.get("last_name", ""),
            "party": persona.get("party", "I"),
            "state": persona.get("state", ""),
            "chamber": chamber,
            "ideology_score": float(persona.get("ideology_score", 0)),
            "wikipedia_summary": persona.get("biography", {}).get("summary", "") if persona.get("biography") else "",
            "website": persona.get("website", ""),
            "twitter": persona.get("twitter", ""),
        }

        # Add campaign finance if available
        if persona.get("campaign_finance"):
            cf = persona["campaign_finance"]
            properties["receipts"] = float(cf.get("receipts", 0))
            properties["disbursements"] = float(cf.get("disbursements", 0))
            properties["cash_on_hand"] = float(cf.get("cash_on_hand", 0))

        # Create node with MERGE (update if exists)
        with self.driver.session() as session:
            query = """
            MERGE (m:CongressMember {bioguide_id: $bioguide_id})
            SET m += $properties
            RETURN m.bioguide_id
            """
            try:
                session.run(query, bioguide_id=bioguide_id, properties=properties)
            except Exception as e:
                logger.warning(f"  ✗ Neo4j error for {bioguide_id}: {e}")

    def _import_executive_branch(self, exec_dir: Path):
        """Import executive branch members."""
        if not exec_dir.exists():
            logger.warning(f"⚠ Executive directory not found: {exec_dir}")
            return

        exec_files = list(exec_dir.glob("*.json"))
        logger.info(f"📥 Importing {len(exec_files)} executive branch members...")

        success = 0
        for persona_file in exec_files:
            try:
                with open(persona_file, 'r') as f:
                    persona = json.load(f)

                person_id = persona.get("id") or persona.get("bioguide_id")
                if not person_id:
                    continue

                properties = {
                    "id": person_id,
                    "full_name": persona.get("full_name", ""),
                    "title": persona.get("title", ""),
                    "branch": "executive",
                    "ideology_score": float(persona.get("ideology_score", 0)),
                }

                with self.driver.session() as session:
                    query = """
                    MERGE (e:ExecutiveBranch {id: $id})
                    SET e += $properties
                    RETURN e.id
                    """
                    session.run(query, id=person_id, properties=properties)
                    success += 1

            except Exception as e:
                logger.warning(f"  ✗ Failed to import {persona_file.stem}: {e}")

        logger.info(f"  ✓ Imported {success}/{len(exec_files)} executive members")

    def _import_scotus(self, scotus_dir: Path):
        """Import SCOTUS justices."""
        if not scotus_dir.exists():
            logger.warning(f"⚠ SCOTUS directory not found: {scotus_dir}")
            return

        justice_files = list(scotus_dir.glob("*.json"))
        logger.info(f"📥 Importing {len(justice_files)} SCOTUS justices...")

        success = 0
        for persona_file in justice_files:
            try:
                with open(persona_file, 'r') as f:
                    persona = json.load(f)

                justice_id = persona.get("id") or persona.get("bioguide_id")
                if not justice_id:
                    continue

                properties = {
                    "id": justice_id,
                    "full_name": persona.get("full_name", ""),
                    "title": persona.get("title", ""),
                    "branch": "judicial",
                    "ideology_score": float(persona.get("ideology_score", 0)),
                }

                with self.driver.session() as session:
                    query = """
                    MERGE (j:Judicial {id: $id})
                    SET j += $properties
                    RETURN j.id
                    """
                    session.run(query, id=justice_id, properties=properties)
                    success += 1

            except Exception as e:
                logger.warning(f"  ✗ Failed to import {persona_file.stem}: {e}")

        logger.info(f"  ✓ Imported {success}/{len(justice_files)} SCOTUS justices")


def main():
    """Run persona import."""
    logger.info("=" * 60)
    logger.info("CongressFish Persona Import to Neo4j")
    logger.info("=" * 60)

    importer = PersonaImporter()
    try:
        # Import from backend/agents/personas directory
        personas_dir = Path(__file__).parent / "personas"
        importer.import_personas(str(personas_dir))
    finally:
        importer.close()

    logger.info("=" * 60)


if __name__ == "__main__":
    main()
