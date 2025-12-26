"""
Neo4j client for knowledge graph operations.
"""
from typing import Dict, List, Optional, Any
from neo4j import GraphDatabase
from db_chatbot.config.settings import get_logger

logger = get_logger(__name__)


class Neo4jClient:
    """Neo4j database client for knowledge graph operations."""
    
    def __init__(self, uri: str = "bolt://localhost:7687", user: str = "neo4j", password: str = "neo4jpassword"):
        """
        Initialize Neo4j client.
        
        Args:
            uri: Neo4j connection URI
            user: Neo4j username
            password: Neo4j password
        """
        self.uri = uri
        self.user = user
        self.password = password
        self.driver = None
        logger.info(f"Neo4jClient initialized for {uri}")
    
    def connect(self) -> bool:
        """
        Connect to Neo4j database.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            # Test connection
            with self.driver.session() as session:
                session.run("RETURN 1")
            logger.info("Neo4j connection established successfully")
            return True
        except Exception as e:
            logger.error(f"Neo4j connection failed: {str(e)}")
            return False
    
    def close(self):
        """Close Neo4j connection."""
        if self.driver:
            logger.info("Closing Neo4j connection")
            self.driver.close()
            self.driver = None
    
    def execute_query(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Execute a Cypher query.
        
        Args:
            query: Cypher query string
            parameters: Query parameters
        
        Returns:
            List of result records as dictionaries
        """
        if not self.driver:
            logger.error("Neo4j driver not connected")
            return []
        
        try:
            with self.driver.session() as session:
                result = session.run(query, parameters or {})
                records = [record.data() for record in result]
                logger.debug(f"Cypher query executed: {len(records)} record(s) returned")
                return records
        except Exception as e:
            logger.error(f"Error executing Cypher query: {str(e)}")
            return []
    
    def clear_database(self, database_name: str = "neo4j"):
        """
        Clear all nodes and relationships for a specific database.
        
        Args:
            database_name: Name of the database to clear (neo4j by default)
        """
        query = """
        MATCH (n)
        WHERE n.database_name = $database_name OR EXISTS((n)-[:HAS_TABLE]->())
        DETACH DELETE n
        """
        try:
            with self.driver.session(database=database_name) as session:
                # First, delete all relationships and nodes
                session.run("MATCH (n) DETACH DELETE n")
                logger.info(f"Database {database_name} cleared")
        except Exception as e:
            logger.error(f"Error clearing database: {str(e)}")
    
    def health_check(self) -> bool:
        """
        Check if Neo4j connection is healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            if not self.driver:
                return False
            with self.driver.session() as session:
                result = session.run("RETURN 1 as health")
                return result.single() is not None
        except Exception as e:
            logger.error(f"Neo4j health check failed: {str(e)}")
            return False

