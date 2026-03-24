"""
Neo4j Graph Schema & CRUD Operations
====================================
Defines node labels, relationships, constraints, and indexes for CongressFish.

New node labels (alongside MiroFish's Entity/Episode/Graph):
- Member: Congress member
- Justice: Supreme Court justice
- Executive: Executive branch official
- Committee: Congressional committee
- Caucus: Congressional caucus (party, ideological)
- Party: Political party
- Organization: Influence organization (PAC, advocacy group, etc.)
- Sector: Industry sector

No random generation—only explicit nodes from real data sources.
"""

import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class CongressFishGraphSchema:
    """Neo4j schema definition for CongressFish."""

    # Node Labels
    MEMBER = "Member"
    JUSTICE = "Justice"
    EXECUTIVE = "Executive"
    COMMITTEE = "Committee"
    CAUCUS = "Caucus"
    PARTY = "Party"
    ORGANIZATION = "Organization"
    SECTOR = "Sector"

    # Relationship Types
    SERVES_ON = "SERVES_ON"
    MEMBER_OF = "MEMBER_OF"
    PARTY_MEMBER = "PARTY_MEMBER"
    COSPONSORS_WITH = "COSPONSORS_WITH"
    VOTES_WITH = "VOTES_WITH"
    FUNDED_BY = "FUNDED_BY"
    AGREES_WITH = "AGREES_WITH"
    APPOINTED_BY = "APPOINTED_BY"
    LOBBIES = "LOBBIES"
    TARGETS = "TARGETS"

    @staticmethod
    def get_constraints() -> List[str]:
        """Return Cypher statements for unique constraints."""
        return [
            # Member constraints
            f"CREATE CONSTRAINT FOR (m:{CongressFishGraphSchema.MEMBER}) REQUIRE m.bioguide_id IS UNIQUE;",
            f"CREATE CONSTRAINT FOR (m:{CongressFishGraphSchema.MEMBER}) REQUIRE m.name IS UNIQUE;",

            # Justice constraints
            f"CREATE CONSTRAINT FOR (j:{CongressFishGraphSchema.JUSTICE}) REQUIRE j.oyez_id IS UNIQUE;",
            f"CREATE CONSTRAINT FOR (j:{CongressFishGraphSchema.JUSTICE}) REQUIRE j.name IS UNIQUE;",

            # Committee constraints
            f"CREATE CONSTRAINT FOR (c:{CongressFishGraphSchema.COMMITTEE}) REQUIRE c.code IS UNIQUE;",

            # Party constraints
            f"CREATE CONSTRAINT FOR (p:{CongressFishGraphSchema.PARTY}) REQUIRE p.name IS UNIQUE;",

            # Organization constraints
            f"CREATE CONSTRAINT FOR (o:{CongressFishGraphSchema.ORGANIZATION}) REQUIRE o.name IS UNIQUE;",

            # Executive constraints
            f"CREATE CONSTRAINT FOR (e:{CongressFishGraphSchema.EXECUTIVE}) REQUIRE e.name IS UNIQUE;",
        ]

    @staticmethod
    def get_indexes() -> List[str]:
        """Return Cypher statements for performance indexes."""
        return [
            # Member indexes
            f"CREATE INDEX FOR (m:{CongressFishGraphSchema.MEMBER}) ON (m.party);",
            f"CREATE INDEX FOR (m:{CongressFishGraphSchema.MEMBER}) ON (m.chamber);",
            f"CREATE INDEX FOR (m:{CongressFishGraphSchema.MEMBER}) ON (m.state);",
            f"CREATE INDEX FOR (m:{CongressFishGraphSchema.MEMBER}) ON (m.ideology_primary);",

            # Justice indexes
            f"CREATE INDEX FOR (j:{CongressFishGraphSchema.JUSTICE}) ON (j.ideology_primary);",

            # Committee indexes
            f"CREATE INDEX FOR (c:{CongressFishGraphSchema.COMMITTEE}) ON (c.chamber);",

            # Organization indexes
            f"CREATE INDEX FOR (o:{CongressFishGraphSchema.ORGANIZATION}) ON (o.org_type);",
        ]


class CongressGraphClient:
    """Neo4j client for CongressFish graph operations."""

    def __init__(self, driver):
        """
        Args:
            driver: Neo4j driver instance
        """
        self.driver = driver

    def ensure_schema(self):
        """Create all constraints and indexes."""
        with self.driver.session() as session:
            # Create constraints
            for constraint in CongressFishGraphSchema.get_constraints():
                try:
                    session.run(constraint)
                    logger.info(f'Created constraint')
                except Exception as e:
                    # Constraint may already exist
                    if 'already exists' not in str(e):
                        logger.warning(f'Constraint creation: {e}')

            # Create indexes
            for index in CongressFishGraphSchema.get_indexes():
                try:
                    session.run(index)
                    logger.info(f'Created index')
                except Exception as e:
                    if 'already exists' not in str(e):
                        logger.warning(f'Index creation: {e}')

    def create_member(self, profile: Dict) -> bool:
        """
        Create or update Member node.

        Args:
            profile: CongressMemberProfile as dict

        Returns:
            True if successful
        """
        try:
            with self.driver.session() as session:
                query = f"""
                MERGE (m:{CongressFishGraphSchema.MEMBER} {{bioguide_id: $bioguide_id}})
                SET m.name = $name,
                    m.party = $party,
                    m.chamber = $chamber,
                    m.state = $state,
                    m.district = $district,
                    m.ideology_primary = $ideology_primary,
                    m.ideology_secondary = $ideology_secondary,
                    m.persona_narrative = $persona_narrative,
                    m.updated_at = $updated_at
                RETURN m
                """
                session.run(query, **{
                    'bioguide_id': profile.get('bioguide_id'),
                    'name': profile.get('full_name'),
                    'party': profile.get('party'),
                    'chamber': profile.get('chamber'),
                    'state': profile.get('state'),
                    'district': profile.get('district'),
                    'ideology_primary': profile.get('ideology', {}).get('primary_dimension'),
                    'ideology_secondary': profile.get('ideology', {}).get('secondary_dimension'),
                    'persona_narrative': profile.get('persona_narrative'),
                    'updated_at': profile.get('updated_at'),
                })
                return True
        except Exception as e:
            logger.error(f'Failed to create member {profile.get("full_name")}: {e}')
            return False

    def create_justice(self, profile: Dict) -> bool:
        """Create or update Justice node."""
        try:
            with self.driver.session() as session:
                query = f"""
                MERGE (j:{CongressFishGraphSchema.JUSTICE} {{oyez_id: $oyez_id}})
                SET j.name = $name,
                    j.ideology_primary = $ideology_primary,
                    j.total_opinions = $total_opinions,
                    j.persona_narrative = $persona_narrative,
                    j.updated_at = $updated_at
                RETURN j
                """
                session.run(query, **{
                    'oyez_id': profile.get('oyez_id'),
                    'name': profile.get('name'),
                    'ideology_primary': profile.get('ideology', {}).get('primary_dimension'),
                    'total_opinions': profile.get('total_opinions', 0),
                    'persona_narrative': profile.get('persona_narrative'),
                    'updated_at': profile.get('updated_at'),
                })
                return True
        except Exception as e:
            logger.error(f'Failed to create justice {profile.get("name")}: {e}')
            return False

    def create_committee(self, committee_data: Dict) -> bool:
        """Create or update Committee node."""
        try:
            with self.driver.session() as session:
                query = f"""
                MERGE (c:{CongressFishGraphSchema.COMMITTEE} {{code: $code}})
                SET c.name = $name,
                    c.chamber = $chamber,
                    c.jurisdiction = $jurisdiction
                RETURN c
                """
                session.run(query, **{
                    'code': committee_data.get('code'),
                    'name': committee_data.get('name'),
                    'chamber': committee_data.get('chamber'),
                    'jurisdiction': committee_data.get('jurisdiction'),
                })
                return True
        except Exception as e:
            logger.error(f'Failed to create committee {committee_data.get("name")}: {e}')
            return False

    def create_party(self, party_name: str) -> bool:
        """Create or ensure Party node exists."""
        try:
            with self.driver.session() as session:
                query = f"""
                MERGE (p:{CongressFishGraphSchema.PARTY} {{name: $name}})
                RETURN p
                """
                session.run(query, **{'name': party_name})
                return True
        except Exception as e:
            logger.error(f'Failed to create party {party_name}: {e}')
            return False

    def create_organization(self, org_data: Dict) -> bool:
        """Create or update Organization node."""
        try:
            with self.driver.session() as session:
                query = f"""
                MERGE (o:{CongressFishGraphSchema.ORGANIZATION} {{name: $name}})
                SET o.org_type = $org_type,
                    o.total_raised = $total_raised,
                    o.total_spent = $total_spent
                RETURN o
                """
                session.run(query, **{
                    'name': org_data.get('name'),
                    'org_type': org_data.get('org_type'),
                    'total_raised': org_data.get('total_raised'),
                    'total_spent': org_data.get('total_spent'),
                })
                return True
        except Exception as e:
            logger.error(f'Failed to create organization {org_data.get("name")}: {e}')
            return False

    # Relationship creation methods

    def create_member_party_relationship(self, bioguide_id: str, party: str) -> bool:
        """Create PARTY_MEMBER relationship."""
        try:
            with self.driver.session() as session:
                query = f"""
                MATCH (m:{CongressFishGraphSchema.MEMBER} {{bioguide_id: $bioguide_id}})
                MATCH (p:{CongressFishGraphSchema.PARTY} {{name: $party}})
                MERGE (m)-[:{CongressFishGraphSchema.PARTY_MEMBER}]->(p)
                """
                session.run(query, **{'bioguide_id': bioguide_id, 'party': party})
                return True
        except Exception as e:
            logger.warning(f'Failed to create party relationship for {bioguide_id}: {e}')
            return False

    def create_committee_service(
        self,
        bioguide_id: str,
        committee_code: str,
        rank: Optional[int] = None,
        is_chair: bool = False,
    ) -> bool:
        """Create SERVES_ON relationship."""
        try:
            with self.driver.session() as session:
                query = f"""
                MATCH (m:{CongressFishGraphSchema.MEMBER} {{bioguide_id: $bioguide_id}})
                MATCH (c:{CongressFishGraphSchema.COMMITTEE} {{code: $committee_code}})
                MERGE (m)-[r:{CongressFishGraphSchema.SERVES_ON}]->(c)
                SET r.rank = $rank, r.is_chair = $is_chair
                """
                session.run(query, **{
                    'bioguide_id': bioguide_id,
                    'committee_code': committee_code,
                    'rank': rank,
                    'is_chair': is_chair,
                })
                return True
        except Exception as e:
            logger.warning(f'Failed to create committee service for {bioguide_id}: {e}')
            return False

    def create_cosponsorship_relationship(
        self,
        bioguide_id1: str,
        bioguide_id2: str,
        count: int,
    ) -> bool:
        """Create COSPONSORS_WITH relationship."""
        try:
            with self.driver.session() as session:
                query = f"""
                MATCH (m1:{CongressFishGraphSchema.MEMBER} {{bioguide_id: $bioguide_id1}})
                MATCH (m2:{CongressFishGraphSchema.MEMBER} {{bioguide_id: $bioguide_id2}})
                MERGE (m1)-[r:{CongressFishGraphSchema.COSPONSORS_WITH}]-(m2)
                SET r.count = $count
                """
                session.run(query, **{
                    'bioguide_id1': bioguide_id1,
                    'bioguide_id2': bioguide_id2,
                    'count': count,
                })
                return True
        except Exception as e:
            logger.warning(f'Failed to create cosponsorship for {bioguide_id1}-{bioguide_id2}: {e}')
            return False

    def create_voting_alignment(
        self,
        bioguide_id1: str,
        bioguide_id2: str,
        agreement_pct: float,
    ) -> bool:
        """Create VOTES_WITH relationship."""
        try:
            with self.driver.session() as session:
                query = f"""
                MATCH (m1:{CongressFishGraphSchema.MEMBER} {{bioguide_id: $bioguide_id1}})
                MATCH (m2:{CongressFishGraphSchema.MEMBER} {{bioguide_id: $bioguide_id2}})
                MERGE (m1)-[r:{CongressFishGraphSchema.VOTES_WITH}]-(m2)
                SET r.agreement_pct = $agreement_pct
                """
                session.run(query, **{
                    'bioguide_id1': bioguide_id1,
                    'bioguide_id2': bioguide_id2,
                    'agreement_pct': agreement_pct,
                })
                return True
        except Exception as e:
            logger.warning(f'Failed to create voting alignment for {bioguide_id1}-{bioguide_id2}: {e}')
            return False

    def get_member_count(self) -> int:
        """Get count of Member nodes."""
        try:
            with self.driver.session() as session:
                result = session.run(f"MATCH (m:{CongressFishGraphSchema.MEMBER}) RETURN count(m) as count")
                return result.single()['count']
        except Exception as e:
            logger.warning(f'Failed to count members: {e}')
            return 0

    def get_justice_count(self) -> int:
        """Get count of Justice nodes."""
        try:
            with self.driver.session() as session:
                result = session.run(f"MATCH (j:{CongressFishGraphSchema.JUSTICE}) RETURN count(j) as count")
                return result.single()['count']
        except Exception as e:
            logger.warning(f'Failed to count justices: {e}')
            return 0

    def get_relationship_count(self, rel_type: str) -> int:
        """Get count of specific relationship type."""
        try:
            with self.driver.session() as session:
                query = f"MATCH ()-[r:{rel_type}]-() RETURN count(r) as count"
                result = session.run(query)
                return result.single()['count']
        except Exception as e:
            logger.warning(f'Failed to count {rel_type} relationships: {e}')
            return 0
