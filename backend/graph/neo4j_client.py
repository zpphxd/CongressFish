#!/usr/bin/env python3
"""
Neo4j connection and query client for CongressFish knowledge graph.

Handles connections, queries, and graph operations.
"""

import os
import logging
from typing import Dict, List, Any, Optional
from neo4j import GraphDatabase, Driver, Session

logger = logging.getLogger(__name__)


class Neo4jClient:
    """Client for Neo4j graph database operations."""

    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        user: str = "neo4j",
        password: str = "password",
    ):
        """
        Initialize Neo4j client.

        Args:
            uri: Neo4j connection URI (default local)
            user: Database user
            password: Database password
        """
        self.uri = uri
        self.user = user
        self.password = password
        self.driver: Optional[Driver] = None

    def connect(self) -> bool:
        """Connect to Neo4j database."""
        try:
            self.driver = GraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password),
                max_connection_lifetime=3600
            )
            self.driver.verify_connectivity()
            logger.info(f"✓ Connected to Neo4j at {self.uri}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            return False

    def close(self) -> None:
        """Close Neo4j connection."""
        if self.driver:
            self.driver.close()
            logger.info("Closed Neo4j connection")

    def query(self, cypher: str, **parameters) -> List[Dict[str, Any]]:
        """
        Execute a Cypher query.

        Args:
            cypher: Cypher query string
            **parameters: Query parameters

        Returns:
            List of result records as dicts
        """
        if not self.driver:
            raise RuntimeError("Not connected to Neo4j")

        with self.driver.session() as session:
            result = session.run(cypher, **parameters)
            return [dict(record) for record in result]

    def get_member_by_bioguide(self, bioguide_id: str) -> Optional[Dict[str, Any]]:
        """Get a Congress member by bioguide ID."""
        result = self.query(
            "MATCH (m:CongressMember {bioguide_id: $bioguide_id}) RETURN m",
            bioguide_id=bioguide_id
        )
        return dict(result[0]["m"]) if result else None

    def get_members_by_chamber(self, chamber: str) -> List[Dict[str, Any]]:
        """Get all Congress members in a chamber (House or Senate)."""
        result = self.query(
            """
            MATCH (m:CongressMember {chamber: $chamber})
            RETURN m ORDER BY m.full_name
            """,
            chamber=chamber
        )
        return [dict(record["m"]) for record in result]

    def get_members_by_party(self, party_code: str) -> List[Dict[str, Any]]:
        """Get all Congress members in a party."""
        result = self.query(
            """
            MATCH (m:CongressMember)-[:PARTY_MEMBER]->(p:Party {code: $party_code})
            RETURN m ORDER BY m.full_name
            """,
            party_code=party_code
        )
        return [dict(record["m"]) for record in result]

    def get_members_by_committee(self, committee_code: str) -> List[Dict[str, Any]]:
        """Get all Congress members on a committee."""
        result = self.query(
            """
            MATCH (m:CongressMember)-[:MEMBER_OF]->(c:Committee {code: $committee_code})
            RETURN m, r ORDER BY r.rank
            """,
            committee_code=committee_code
        )
        return [dict(record["m"]) for record in result]

    def get_member_committees(self, bioguide_id: str) -> List[Dict[str, Any]]:
        """Get all committees for a Congress member."""
        result = self.query(
            """
            MATCH (m:CongressMember {bioguide_id: $bioguide_id})-[r:MEMBER_OF]->(c:Committee)
            RETURN c, r ORDER BY r.rank
            """,
            bioguide_id=bioguide_id
        )
        committees = []
        for record in result:
            committee = dict(record["c"])
            committee["rank"] = record["r"]["rank"]
            committee["title"] = record["r"]["title"]
            committees.append(committee)
        return committees

    def get_ideological_spectrum(self, party_code: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get ideology spectrum for members, optionally filtered by party.

        Returns members sorted by primary ideology dimension.
        """
        if party_code:
            result = self.query(
                """
                MATCH (m:CongressMember)-[:PARTY_MEMBER]->(p:Party {code: $party_code})
                RETURN m ORDER BY m.ideology_primary
                """,
                party_code=party_code
            )
        else:
            result = self.query(
                "MATCH (m:CongressMember) RETURN m ORDER BY m.ideology_primary"
            )
        return [dict(record["m"]) for record in result]

    def get_ally_network(self, bioguide_id: str, depth: int = 1) -> Dict[str, Any]:
        """
        Get alliance network around a member (connected by committees/ideology).

        Args:
            bioguide_id: Target member
            depth: Relationship depth (1-2 recommended)

        Returns:
            Dict with central member and connected allies
        """
        result = self.query(
            f"""
            MATCH (m:CongressMember {{bioguide_id: $bioguide_id}})
            OPTIONAL MATCH (m)-[:MEMBER_OF]->(c:Committee)<-[:MEMBER_OF]-(ally:CongressMember)
            OPTIONAL MATCH (m)-[:IDEOLOGICALLY_ALIGNED]-(ideologue:CongressMember)
            RETURN m, collect(distinct ally) as committee_allies,
                   collect(distinct ideologue) as ideology_allies
            """,
            bioguide_id=bioguide_id
        )
        if result:
            record = result[0]
            return {
                "member": dict(record["m"]),
                "committee_allies": [dict(a) for a in record["committee_allies"]],
                "ideology_allies": [dict(a) for a in record["ideology_allies"]]
            }
        return {}

    def get_bill_prediction_context(self, bioguide_id: str) -> Dict[str, Any]:
        """
        Get context for predicting a member's vote on a bill.

        Returns member profile + committee assignments + party info + allies.
        """
        member = self.get_member_by_bioguide(bioguide_id)
        committees = self.get_member_committees(bioguide_id)
        allies = self.get_ally_network(bioguide_id)

        result = self.query(
            "MATCH (m:CongressMember {bioguide_id: $bioguide_id})-[:PARTY_MEMBER]->(p:Party) RETURN p",
            bioguide_id=bioguide_id
        )
        party = dict(result[0]["p"]) if result else {}

        return {
            "member": member,
            "party": party,
            "committees": committees,
            "allies": allies,
        }

    def search_members(self, query: str) -> List[Dict[str, Any]]:
        """Full-text search for Congress members by name."""
        result = self.query(
            """
            MATCH (m:CongressMember)
            WHERE m.full_name CONTAINS $query OR m.last_name CONTAINS $query
            RETURN m ORDER BY m.full_name
            """,
            query=query
        )
        return [dict(record["m"]) for record in result]

    def get_graph_stats(self) -> Dict[str, int]:
        """Get overall graph statistics."""
        stats = {}

        # Count nodes by type
        node_types = ["CongressMember", "Party", "Committee", "State"]
        for node_type in node_types:
            result = self.query(f"MATCH (n:{node_type}) RETURN count(n) as count")
            stats[node_type] = result[0]["count"] if result else 0

        # Count relationships
        result = self.query("MATCH ()-[r]->() RETURN count(r) as count")
        stats["relationships"] = result[0]["count"] if result else 0

        return stats
