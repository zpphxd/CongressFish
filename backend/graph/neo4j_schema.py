#!/usr/bin/env python3
"""
Neo4j schema definition and initialization for CongressFish knowledge graph.

Creates the node and relationship structure for Congress members, committees,
parties, and legislation interactions.
"""

from typing import List, Dict, Any
from neo4j import Driver, Session


class Neo4jSchema:
    """Manages Neo4j graph schema for Congress knowledge base."""

    def __init__(self, driver: Driver):
        """Initialize schema manager with Neo4j driver."""
        self.driver = driver

    def create_constraints(self) -> None:
        """Create unique constraints on node properties."""
        constraints = [
            "CREATE CONSTRAINT unique_bioguide IF NOT EXISTS ON (m:CongressMember) ASSERT m.bioguide_id IS UNIQUE",
            "CREATE CONSTRAINT unique_committee IF NOT EXISTS ON (c:Committee) ASSERT c.code IS UNIQUE",
            "CREATE CONSTRAINT unique_party IF NOT EXISTS ON (p:Party) ASSERT p.name IS UNIQUE",
            "CREATE CONSTRAINT unique_state IF NOT EXISTS ON (s:State) ASSERT s.code IS UNIQUE",
            "CREATE CONSTRAINT unique_bill IF NOT EXISTS ON (b:Bill) ASSERT b.id IS UNIQUE",
        ]

        with self.driver.session() as session:
            for constraint in constraints:
                try:
                    session.run(constraint)
                    print(f"✓ Created constraint: {constraint.split('ON')[1][:40]}")
                except Exception as e:
                    print(f"Constraint already exists or error: {e}")

    def create_indexes(self) -> None:
        """Create indexes for query performance."""
        indexes = [
            "CREATE INDEX idx_member_name IF NOT EXISTS FOR (m:CongressMember) ON (m.full_name)",
            "CREATE INDEX idx_member_state IF NOT EXISTS FOR (m:CongressMember) ON (m.state)",
            "CREATE INDEX idx_member_party IF NOT EXISTS FOR (m:CongressMember) ON (m.party)",
            "CREATE INDEX idx_committee_name IF NOT EXISTS FOR (c:Committee) ON (c.title)",
            "CREATE INDEX idx_bill_title IF NOT EXISTS FOR (b:Bill) ON (b.title)",
        ]

        with self.driver.session() as session:
            for index in indexes:
                try:
                    session.run(index)
                    print(f"✓ Created index: {index.split('FOR')[1][:40]}")
                except Exception as e:
                    print(f"Index already exists or error: {e}")

    def clear_graph(self) -> None:
        """DANGER: Delete all nodes and relationships. Use for reset only."""
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
            print("⚠️  Cleared all nodes and relationships from graph")

    def create_parties(self, parties: List[Dict[str, str]]) -> None:
        """Create Party nodes."""
        with self.driver.session() as session:
            for party in parties:
                session.run(
                    """
                    MERGE (p:Party {name: $name})
                    SET p.code = $code, p.color = $color
                    """,
                    name=party["name"],
                    code=party["code"],
                    color=party["color"]
                )
            print(f"✓ Created {len(parties)} Party nodes")

    def create_states(self, states: List[Dict[str, str]]) -> None:
        """Create State nodes."""
        with self.driver.session() as session:
            for state in states:
                session.run(
                    """
                    MERGE (s:State {code: $code})
                    SET s.name = $name, s.abbreviation = $abbreviation
                    """,
                    code=state["code"],
                    name=state["name"],
                    abbreviation=state["abbreviation"]
                )
            print(f"✓ Created {len(states)} State nodes")

    def create_committees(self, committees: List[Dict[str, Any]]) -> None:
        """Create Committee nodes."""
        with self.driver.session() as session:
            for committee in committees:
                session.run(
                    """
                    MERGE (c:Committee {code: $code})
                    SET c.title = $title, c.chamber = $chamber
                    """,
                    code=committee["code"],
                    title=committee["title"],
                    chamber=committee["chamber"]
                )
            print(f"✓ Created {len(committees)} Committee nodes")

    def get_schema_summary(self) -> Dict[str, int]:
        """Get counts of all node types."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (n)
                RETURN labels(n)[0] as label, count(*) as count
                ORDER BY count DESC
            """)
            return {record["label"]: record["count"] for record in result}


class Neo4jLoader:
    """Loads enriched Congress member profiles into Neo4j graph."""

    def __init__(self, driver: Driver):
        """Initialize loader with Neo4j driver."""
        self.driver = driver

    def load_congress_member(self, profile: Dict[str, Any]) -> None:
        """Load a single Congress member profile into Neo4j."""
        with self.driver.session() as session:
            # Create CongressMember node
            session.run(
                """
                MERGE (m:CongressMember {bioguide_id: $bioguide_id})
                SET m.full_name = $full_name,
                    m.first_name = $first_name,
                    m.last_name = $last_name,
                    m.chamber = $chamber,
                    m.state = $state,
                    m.party = $party,
                    m.fec_id = $fec_id,
                    m.birth_date = $birth_date,
                    m.birth_place = $birth_place,
                    m.education = $education,
                    m.occupation = $occupation,
                    m.wikipedia_summary = $wikipedia_summary,
                    m.full_biography = $full_biography,
                    m.ideology_primary = $ideology_primary,
                    m.ideology_secondary = $ideology_secondary,
                    m.persona_narrative = $persona_narrative,
                    m.updated_at = datetime()
                """,
                bioguide_id=profile.get("bioguide_id"),
                full_name=profile.get("full_name"),
                first_name=profile.get("first_name"),
                last_name=profile.get("last_name"),
                chamber=profile.get("chamber"),
                state=profile.get("state"),
                party=profile.get("party"),
                fec_id=profile.get("ids", {}).get("fec_id"),
                birth_date=profile.get("biography", {}).get("birth_date"),
                birth_place=profile.get("biography", {}).get("birth_place"),
                education=profile.get("biography", {}).get("education"),
                occupation=profile.get("biography", {}).get("occupation"),
                wikipedia_summary=profile.get("biography", {}).get("wikipedia_summary"),
                full_biography=profile.get("biography", {}).get("full_biography"),
                ideology_primary=profile.get("ideology", {}).get("primary_dimension"),
                ideology_secondary=profile.get("ideology", {}).get("secondary_dimension"),
                persona_narrative=profile.get("persona_narrative")
            )

            # Link to Party
            if profile.get("party"):
                session.run(
                    """
                    MATCH (m:CongressMember {bioguide_id: $bioguide_id})
                    MATCH (p:Party {code: $party_code})
                    MERGE (m)-[:PARTY_MEMBER]->(p)
                    """,
                    bioguide_id=profile.get("bioguide_id"),
                    party_code=profile.get("party")
                )

            # Link to State
            if profile.get("state"):
                session.run(
                    """
                    MATCH (m:CongressMember {bioguide_id: $bioguide_id})
                    MATCH (s:State {code: $state_code})
                    MERGE (m)-[:FROM_STATE]->(s)
                    """,
                    bioguide_id=profile.get("bioguide_id"),
                    state_code=profile.get("state")
                )

            # Link to Committees
            for committee in profile.get("committee_assignments", []):
                session.run(
                    """
                    MATCH (m:CongressMember {bioguide_id: $bioguide_id})
                    MERGE (c:Committee {code: $committee_code})
                    MERGE (m)-[:MEMBER_OF {rank: $rank, title: $title}]->(c)
                    """,
                    bioguide_id=profile.get("bioguide_id"),
                    committee_code=committee.get("code"),
                    rank=committee.get("rank"),
                    title=committee.get("title")
                )

    def load_all_members(self, profiles: List[Dict[str, Any]]) -> None:
        """Load all Congress member profiles."""
        print(f"Loading {len(profiles)} Congress member profiles into Neo4j...")
        for i, profile in enumerate(profiles):
            self.load_congress_member(profile)
            if (i + 1) % 100 == 0:
                print(f"  Loaded {i + 1}/{len(profiles)} members...")
        print(f"✓ Loaded all {len(profiles)} members")

    def create_cosponsorship_network(self) -> None:
        """Create COSPONSORED_WITH relationships based on committee overlap."""
        with self.driver.session() as session:
            # Members on same committees have collaborated
            session.run(
                """
                MATCH (m1:CongressMember)-[:MEMBER_OF]->(c:Committee)<-[:MEMBER_OF]-(m2:CongressMember)
                WHERE m1.bioguide_id < m2.bioguide_id
                MERGE (m1)-[r:COSPONSORED_WITH]-(m2)
                ON CREATE SET r.committee_count = 1
                ON MATCH SET r.committee_count = r.committee_count + 1
                """
            )
            print("✓ Created cosponsorship network based on committee memberships")

    def create_ideology_clusters(self) -> None:
        """Create IDEOLOGICALLY_ALIGNED relationships based on voting scores."""
        with self.driver.session() as session:
            # Members with similar ideology scores
            session.run(
                """
                MATCH (m1:CongressMember)-[:PARTY_MEMBER]->(p:Party)
                MATCH (m2:CongressMember)-[:PARTY_MEMBER]->(p)
                WHERE m1.bioguide_id < m2.bioguide_id
                  AND abs(m1.ideology_primary - m2.ideology_primary) < 0.2
                MERGE (m1)-[r:IDEOLOGICALLY_ALIGNED]-(m2)
                SET r.primary_distance = abs(m1.ideology_primary - m2.ideology_primary)
                """
            )
            print("✓ Created ideology-based alignment relationships")


# Party and state definitions for initialization
DEFAULT_PARTIES = [
    {"name": "Democratic Party", "code": "D", "color": "#0015BC"},
    {"name": "Republican Party", "code": "R", "color": "#E81B23"},
    {"name": "Independent", "code": "I", "color": "#808080"},
    {"name": "Libertarian", "code": "L", "color": "#F0A000"},
]

DEFAULT_STATES = [
    {"name": "Alabama", "code": "ALABAMA", "abbreviation": "AL"},
    {"name": "Alaska", "code": "ALASKA", "abbreviation": "AK"},
    # ... full US state list would be added here
]
