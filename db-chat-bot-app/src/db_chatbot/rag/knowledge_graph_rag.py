"""
Knowledge Graph-based RAG using Neo4j for database schema and metadata storage.
"""
from typing import Dict, List, Optional, Any
from datetime import datetime
from db_chatbot.config.settings import get_logger
from db_chatbot.db_clients.neo4j_client import Neo4jClient

logger = get_logger(__name__)


class KnowledgeGraphRAG:
    """
    Knowledge Graph RAG - Stores database schema and user annotations in Neo4j graph.
    Provides graph-based retrieval of schema context for SQL generation.
    """
    
    def __init__(self, neo4j_client: Neo4jClient):
        """
        Initialize Knowledge Graph RAG.
        
        Args:
            neo4j_client: Neo4j client instance
        """
        self.neo4j = neo4j_client
        logger.info("KnowledgeGraphRAG initialized")
    
    def build_graph_from_schema(self, schema_info: Dict, database_name: str, host: str, port: int, db_type: str = "postgresql"):
        """
        Build knowledge graph from database schema information.
        
        Args:
            schema_info: Schema dictionary from PostgresClient.fetch_schema() or MongoDBClient.fetch_schema()
            database_name: Name of the database
            host: Database host
            port: Database port
            db_type: Database type ("postgresql" or "mongodb")
        """
        logger.info(f"Building knowledge graph for {db_type} database: {database_name}")
        
        # Clear existing graph for this database
        self.clear_database_graph(database_name)
        
        # Create database node
        db_query = """
        CREATE (db:Database {
            name: $name,
            host: $host,
            port: $port,
            db_type: $db_type,
            description: "",
            query_examples: [],
            created_at: datetime()
        })
        RETURN db
        """
        self.neo4j.execute_query(db_query, {
            "name": database_name,
            "host": host,
            "port": port,
            "db_type": db_type
        })
        
        if db_type == "mongodb":
            # Process MongoDB collections
            for collection in schema_info.get("collections", []):
                self._create_mongodb_collection_node(database_name, collection)
            logger.info(f"Knowledge graph built: {len(schema_info.get('collections', []))} collection(s) added")
        else:
            # Process PostgreSQL tables
            for table in schema_info.get("tables", []):
                self._create_table_node(database_name, table)
            logger.info(f"Knowledge graph built: {len(schema_info.get('tables', []))} table(s) added")
    
    def _create_table_node(self, database_name: str, table_info: Dict):
        """Create table node and related nodes/relationships."""
        table_name = table_info["name"]
        
        # Create table node with description property
        table_query = """
        MATCH (db:Database {name: $db_name})
        CREATE (t:Table {
            name: $table_name,
            description: "",
            query_examples: [],
            created_at: datetime(),
            database_name: $db_name
        })
        CREATE (db)-[:HAS_TABLE]->(t)
        RETURN t
        """
        self.neo4j.execute_query(table_query, {
            "db_name": database_name,
            "table_name": table_name
        })
        
        # Create column nodes
        for col in table_info.get("columns", []):
            col_query = """
            MATCH (t:Table {name: $table_name, database_name: $db_name})
            CREATE (c:Column {
                name: $col_name,
                type: $col_type,
                nullable: $nullable,
                default_value: $default,
                max_length: $max_length,
                description: "",
                query_examples: [],
                created_at: datetime(),
                database_name: $db_name,
                table_name: $table_name
            })
            CREATE (t)-[:HAS_COLUMN]->(c)
            RETURN c
            """
            self.neo4j.execute_query(col_query, {
                "table_name": table_name,
                "db_name": database_name,
                "col_name": col["name"],
                "col_type": col["type"],
                "nullable": col.get("nullable", True),
                "default": str(col.get("default", "")),
                "max_length": col.get("max_length")
            })
        
        # Create primary key relationships
        for pk in table_info.get("primary_keys", []):
            pk_query = """
            MATCH (t:Table {name: $table_name, database_name: $db_name})-[:HAS_COLUMN]->(c:Column {name: $pk_col})
            CREATE (t)-[:HAS_PRIMARY_KEY]->(c)
            """
            self.neo4j.execute_query(pk_query, {
                "table_name": table_name,
                "db_name": database_name,
                "pk_col": pk
            })
        
        # Create foreign key relationships
        for fk in table_info.get("foreign_keys", []):
            fk_query = """
            MATCH (t1:Table {name: $table_name, database_name: $db_name}),
                  (t2:Table {name: $ref_table, database_name: $db_name})
            CREATE (t1)-[:HAS_FOREIGN_KEY {
                from_column: $from_col,
                to_column: $to_col
            }]->(t2)
            """
            self.neo4j.execute_query(fk_query, {
                "table_name": table_name,
                "ref_table": fk["references_table"],
                "from_col": fk["column"],
                "to_col": fk["references_column"],
                "db_name": database_name
            })
    
    def _create_mongodb_collection_node(self, database_name: str, collection_info: Dict):
        """Create MongoDB collection node and related nodes/relationships."""
        collection_name = collection_info["name"]
        
        # Create collection node
        collection_query = """
        MATCH (db:Database {name: $db_name})
        CREATE (c:Collection {
            name: $collection_name,
            document_count: $doc_count,
            description: "",
            query_examples: [],
            created_at: datetime(),
            database_name: $db_name,
            db_type: "mongodb"
        })
        CREATE (db)-[:HAS_COLLECTION]->(c)
        RETURN c
        """
        self.neo4j.execute_query(collection_query, {
            "db_name": database_name,
            "collection_name": collection_name,
            "doc_count": collection_info.get("document_count", 0)
        })
        
        # Create field nodes
        for field in collection_info.get("fields", []):
            field_query = """
            MATCH (c:Collection {name: $collection_name, database_name: $db_name})
            CREATE (f:Field {
                name: $field_name,
                types: $types,
                nullable: $nullable,
                example: $example,
                description: "",
                query_examples: [],
                created_at: datetime(),
                database_name: $db_name,
                collection_name: $collection_name,
                db_type: "mongodb"
            })
            CREATE (c)-[:HAS_FIELD]->(f)
            RETURN f
            """
            self.neo4j.execute_query(field_query, {
                "collection_name": collection_name,
                "db_name": database_name,
                "field_name": field["name"],
                "types": field.get("types", []),
                "nullable": field.get("nullable", False),
                "example": field.get("example")
            })
    
    def add_annotation(
        self,
        entity_type: str,
        entity_name: str,
        table_name: Optional[str] = None,
        content: str = "",
        database_name: Optional[str] = None
    ):
        """
        Add user annotation to the knowledge graph.
        
        Args:
            entity_type: Type of entity ('table', 'column', 'database')
            entity_name: Name of the entity (table name or column name)
            table_name: Required if entity_type is 'column'
            content: Annotation content/description
            database_name: Database name (optional, will find if not provided)
        """
        logger.info(f"Adding annotation for {entity_type}: {entity_name}")
        
        # Find the entity node first
        params = {
            "entity_name": entity_name,
            "table_name": table_name,
            "db_name": database_name
        }
        
        if entity_type == "database":
            # For database, use database name as entity_name
            entity_query = """
            MATCH (e:Database {name: $db_name})
            RETURN e
            LIMIT 1
            """
            params["entity_name"] = database_name  # Use db_name as entity_name for databases
        elif entity_type == "table":
            entity_query = """
            MATCH (e:Table {name: $entity_name, database_name: $db_name})
            RETURN e
            LIMIT 1
            """
        else:  # column
            entity_query = """
            MATCH (e:Column {name: $entity_name, table_name: $table_name, database_name: $db_name})
            RETURN e
            LIMIT 1
            """
        
        entity_result = self.neo4j.execute_query(entity_query, params)
        
        if not entity_result:
            logger.warning(f"Entity not found for annotation: {entity_type}:{entity_name}")
            return
        
        # Check if annotation exists
        if entity_type == "database":
            check_query = """
            MATCH (e:Database {name: $db_name})
            OPTIONAL MATCH (existing:UserAnnotation)-[:DESCRIBES]->(e)
            WHERE existing.entity_type = $entity_type
            RETURN existing
            LIMIT 1
            """
        elif entity_type == "column":
            check_query = """
            MATCH (e:Column {name: $entity_name, table_name: $table_name, database_name: $db_name})
            OPTIONAL MATCH (existing:UserAnnotation)-[:DESCRIBES]->(e)
            WHERE existing.entity_type = $entity_type AND existing.entity_name = $entity_name
            RETURN existing
            LIMIT 1
            """
        else:  # table
            check_query = """
            MATCH (e:Table {name: $entity_name, database_name: $db_name})
            OPTIONAL MATCH (existing:UserAnnotation)-[:DESCRIBES]->(e)
            WHERE existing.entity_type = $entity_type AND existing.entity_name = $entity_name
            RETURN existing
            LIMIT 1
            """
        
        existing = self.neo4j.execute_query(check_query, {
            "entity_name": entity_name,
            "entity_type": entity_type,
            "content": content,
            "table_name": table_name,
            "db_name": database_name
        })
        
        if existing and existing[0].get("existing"):
            # Update existing annotation
            if entity_type == "database":
                update_query = """
                MATCH (ann:UserAnnotation)-[:DESCRIBES]->(e:Database {name: $db_name})
                WHERE ann.entity_type = $entity_type
                SET ann.content = $content,
                    ann.updated_at = datetime()
                RETURN ann
                """
            elif entity_type == "column":
                update_query = """
                MATCH (ann:UserAnnotation)-[:DESCRIBES]->(e:Column {name: $entity_name, table_name: $table_name, database_name: $db_name})
                WHERE ann.entity_type = $entity_type AND ann.entity_name = $entity_name
                SET ann.content = $content,
                    ann.updated_at = datetime()
                RETURN ann
                """
            else:  # table
                update_query = """
                MATCH (ann:UserAnnotation)-[:DESCRIBES]->(e:Table {name: $entity_name, database_name: $db_name})
                WHERE ann.entity_type = $entity_type AND ann.entity_name = $entity_name
                SET ann.content = $content,
                    ann.updated_at = datetime()
                RETURN ann
                """
            self.neo4j.execute_query(update_query, {
                "entity_name": entity_name,
                "entity_type": entity_type,
                "content": content,
                "table_name": table_name,
                "db_name": database_name
            })
        else:
            # Create new annotation
            if entity_type == "database":
                create_query = """
                MATCH (e:Database {name: $db_name})
                CREATE (ann:UserAnnotation {
                    content: $content,
                    entity_type: $entity_type,
                    entity_name: $db_name,
                    table_name: null,
                    database_name: $db_name,
                    created_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (ann)-[:DESCRIBES]->(e)
                RETURN ann
                """
            elif entity_type == "column":
                create_query = """
                MATCH (e:Column {name: $entity_name, table_name: $table_name, database_name: $db_name})
                CREATE (ann:UserAnnotation {
                    content: $content,
                    entity_type: $entity_type,
                    entity_name: $entity_name,
                    table_name: $table_name,
                    database_name: $db_name,
                    created_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (ann)-[:DESCRIBES]->(e)
                RETURN ann
                """
            else:  # table
                create_query = """
                MATCH (e:Table {name: $entity_name, database_name: $db_name})
                CREATE (ann:UserAnnotation {
                    content: $content,
                    entity_type: $entity_type,
                    entity_name: $entity_name,
                    table_name: null,
                    database_name: $db_name,
                    created_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (ann)-[:DESCRIBES]->(e)
                RETURN ann
                """
            self.neo4j.execute_query(create_query, {
                "entity_name": entity_name,
                "entity_type": entity_type,
                "content": content,
                "table_name": table_name,
                "db_name": database_name
            })
        
        logger.debug(f"Annotation added/updated for {entity_type}: {entity_name}")
    
    def get_mongodb_schema_context(
        self,
        query_keywords: Optional[List[str]] = None,
        collection_names: Optional[List[str]] = None,
        database_name: Optional[str] = None
    ) -> str:
        """
        Retrieve MongoDB schema context from knowledge graph.
        
        Args:
            query_keywords: Keywords to search for relevant collections/fields
            collection_names: Specific collection names to retrieve
            database_name: Database name filter
        
        Returns:
            Formatted schema context string
        """
        logger.debug(f"Retrieving MongoDB schema context for collections: {collection_names}, keywords: {query_keywords}")
        
        if collection_names:
            # Retrieve specific collections
            cypher_query = """
            MATCH (c:Collection {database_name: $db_name, db_type: "mongodb"})
            WHERE c.name IN $collection_names
            OPTIONAL MATCH (c)-[:HAS_FIELD]->(f:Field)
            OPTIONAL MATCH (ann:UserAnnotation)-[:DESCRIBES]->(c)
            OPTIONAL MATCH (field_ann:UserAnnotation)-[:DESCRIBES]->(f)
            WHERE field_ann.entity_type = 'field'
            WITH c, collect(DISTINCT f) as fields, 
                 collect(DISTINCT ann.content) as collection_annotations,
                 collect(DISTINCT field_ann) as field_annotations
            RETURN c.name as collection_name, c.description as collection_description,
                   c.document_count as document_count,
                   fields, collection_annotations, field_annotations
            ORDER BY c.name
            """
            results = self.neo4j.execute_query(cypher_query, {
                "db_name": database_name,
                "collection_names": collection_names
            })
        elif query_keywords:
            # Search by keywords
            cypher_query = """
            MATCH (c:Collection {database_name: $db_name, db_type: "mongodb"})
            WHERE ANY(keyword IN $keywords WHERE c.name CONTAINS keyword OR 
                     EXISTS((c)-[:HAS_FIELD]->(f:Field {name: keyword})))
            OPTIONAL MATCH (c)-[:HAS_FIELD]->(f:Field)
            WHERE ANY(keyword IN $keywords WHERE f.name CONTAINS keyword)
            OPTIONAL MATCH (ann:UserAnnotation)-[:DESCRIBES]->(c)
            OPTIONAL MATCH (field_ann:UserAnnotation)-[:DESCRIBES]->(f)
            WHERE field_ann.entity_type = 'field'
            WITH c, collect(DISTINCT f) as fields,
                 collect(DISTINCT ann.content) as collection_annotations,
                 collect(DISTINCT field_ann) as field_annotations
            RETURN c.name as collection_name, c.description as collection_description,
                   c.document_count as document_count,
                   fields, collection_annotations, field_annotations
            ORDER BY c.name
            LIMIT 10
            """
            results = self.neo4j.execute_query(cypher_query, {
                "db_name": database_name,
                "keywords": query_keywords
            })
        else:
            # Retrieve all collections
            cypher_query = """
            MATCH (c:Collection {database_name: $db_name, db_type: "mongodb"})
            OPTIONAL MATCH (c)-[:HAS_FIELD]->(f:Field)
            OPTIONAL MATCH (ann:UserAnnotation)-[:DESCRIBES]->(c)
            OPTIONAL MATCH (field_ann:UserAnnotation)-[:DESCRIBES]->(f)
            WHERE field_ann.entity_type = 'field'
            WITH c, collect(DISTINCT f) as fields,
                 collect(DISTINCT ann.content) as collection_annotations,
                 collect(DISTINCT field_ann) as field_annotations
            RETURN c.name as collection_name, c.description as collection_description,
                   c.document_count as document_count,
                   fields, collection_annotations, field_annotations
            ORDER BY c.name
            """
            results = self.neo4j.execute_query(cypher_query, {
                "db_name": database_name
            })
        
        # Format results
        context = "MongoDB Database Schema:\n\n"
        for record in results:
            collection_name = record["collection_name"]
            fields = record.get("fields", [])
            collection_annotations = record.get("collection_annotations", [])
            field_annotations = record.get("field_annotations", [])
            collection_description = record.get("collection_description", "")
            document_count = record.get("document_count", 0)
            
            context += f"Collection: {collection_name}\n"
            context += f"Document Count: {document_count}\n"
            
            # Add collection description (includes query examples)
            if collection_description:
                context += f"Description: {collection_description}\n"
            
            # Add collection annotations
            if collection_annotations:
                for ann in collection_annotations:
                    if ann:
                        context += f"Additional Notes: {ann}\n"
            
            context += "Fields:\n"
            for field in fields:
                if field:
                    field_name = field.get("name", "")
                    types = field.get("types", [])
                    nullable = " (nullable)" if field.get("nullable") else ""
                    example = field.get("example")
                    
                    field_info = f"  - {field_name}: {', '.join(types)}{nullable}"
                    if example:
                        field_info += f" (example: {example})"
                    context += field_info + "\n"
                    
                    # Add field description
                    field_desc = field.get("description", "")
                    if field_desc:
                        context += f"    Description: {field_desc}\n"
                    
                    # Add field annotations
                    for field_ann in field_annotations:
                        if field_ann and field_ann.get("entity_name") == field_name:
                            context += f"    Additional Notes: {field_ann.get('content', '')}\n"
            
            context += "\n"
        
        logger.debug(f"MongoDB schema context retrieved: {len(context)} characters")
        return context
    
    def get_schema_context(
        self,
        query_keywords: Optional[List[str]] = None,
        table_names: Optional[List[str]] = None,
        database_name: Optional[str] = None
    ) -> str:
        """
        Retrieve schema context from knowledge graph.
        
        Args:
            query_keywords: Keywords to search for relevant tables/columns
            table_names: Specific table names to retrieve
            database_name: Database name filter
        
        Returns:
            Formatted schema context string
        """
        logger.debug(f"Retrieving schema context for tables: {table_names}, keywords: {query_keywords}")
        
        if table_names:
            # Retrieve specific tables
            cypher_query = """
            MATCH (t:Table {database_name: $db_name})
            WHERE t.name IN $table_names
            OPTIONAL MATCH (t)-[:HAS_COLUMN]->(c:Column)
            OPTIONAL MATCH (ann:UserAnnotation)-[:DESCRIBES]->(t)
            OPTIONAL MATCH (col_ann:UserAnnotation)-[:DESCRIBES]->(c)
            WHERE col_ann.entity_type = 'column'
            WITH t, collect(DISTINCT c) as columns, 
                 collect(DISTINCT ann.content) as table_annotations,
                 collect(DISTINCT col_ann) as column_annotations
            RETURN t.name as table_name, t.description as table_description,
                   columns, table_annotations, column_annotations
            ORDER BY t.name
            """
            results = self.neo4j.execute_query(cypher_query, {
                "db_name": database_name,
                "table_names": table_names
            })
        elif query_keywords:
            # Search by keywords
            cypher_query = """
            MATCH (t:Table {database_name: $db_name})
            WHERE ANY(keyword IN $keywords WHERE t.name CONTAINS keyword OR 
                     EXISTS((t)-[:HAS_COLUMN]->(c:Column {name: keyword})))
            OPTIONAL MATCH (t)-[:HAS_COLUMN]->(c:Column)
            WHERE ANY(keyword IN $keywords WHERE c.name CONTAINS keyword)
            OPTIONAL MATCH (ann:UserAnnotation)-[:DESCRIBES]->(t)
            OPTIONAL MATCH (col_ann:UserAnnotation)-[:DESCRIBES]->(c)
            WHERE col_ann.entity_type = 'column'
            WITH t, collect(DISTINCT c) as columns,
                 collect(DISTINCT ann.content) as table_annotations,
                 collect(DISTINCT col_ann) as column_annotations
            RETURN t.name as table_name, t.description as table_description,
                   columns, table_annotations, column_annotations
            ORDER BY t.name
            LIMIT 10
            """
            results = self.neo4j.execute_query(cypher_query, {
                "db_name": database_name,
                "keywords": query_keywords
            })
        else:
            # Retrieve all tables
            cypher_query = """
            MATCH (t:Table {database_name: $db_name})
            OPTIONAL MATCH (t)-[:HAS_COLUMN]->(c:Column)
            OPTIONAL MATCH (ann:UserAnnotation)-[:DESCRIBES]->(t)
            OPTIONAL MATCH (col_ann:UserAnnotation)-[:DESCRIBES]->(c)
            WHERE col_ann.entity_type = 'column'
            WITH t, collect(DISTINCT c) as columns,
                 collect(DISTINCT ann.content) as table_annotations,
                 collect(DISTINCT col_ann) as column_annotations
            RETURN t.name as table_name, t.description as table_description,
                   columns, table_annotations, column_annotations
            ORDER BY t.name
            """
            results = self.neo4j.execute_query(cypher_query, {
                "db_name": database_name
            })
        
        # Format results
        context = "Database Schema:\n\n"
        for record in results:
            table_name = record["table_name"]
            columns = record.get("columns", [])
            table_annotations = record.get("table_annotations", [])
            column_annotations = record.get("column_annotations", [])
            table_description = record.get("table_description", "")
            
            context += f"Table: {table_name}\n"
            
            # Add table description (includes query examples)
            if table_description:
                context += f"Description: {table_description}\n"
            
            # Add table annotations
            if table_annotations:
                for ann in table_annotations:
                    if ann:
                        context += f"Additional Notes: {ann}\n"
            
            context += "Columns:\n"
            for col in columns:
                if col:
                    col_name = col.get("name", "")
                    col_type = col.get("type", "")
                    nullable = "NULL" if col.get("nullable", True) else "NOT NULL"
                    default = col.get("default_value", "")
                    max_len = col.get("max_length")
                    
                    col_info = f"  - {col_name}: {col_type}"
                    if max_len:
                        col_info += f"({max_len})"
                    col_info += f" {nullable}"
                    if default:
                        col_info += f" DEFAULT {default}"
                    context += col_info + "\n"
                    
                    # Add column description (includes query examples)
                    col_desc = col.get("description", "")
                    if col_desc:
                        context += f"    Description: {col_desc}\n"
                    
                    # Add column annotations
                    for col_ann in column_annotations:
                        if col_ann and col_ann.get("entity_name") == col_name:
                            context += f"    Additional Notes: {col_ann.get('content', '')}\n"
            
            context += "\n"
        
        logger.debug(f"Schema context retrieved: {len(context)} characters")
        return context
    
    def get_table_info(self, table_name: str, database_name: Optional[str] = None) -> Optional[Dict]:
        """Get information about a specific table from the graph."""
        query = """
        MATCH (t:Table {name: $table_name, database_name: $db_name})
        OPTIONAL MATCH (t)-[:HAS_COLUMN]->(c:Column)
        OPTIONAL MATCH (ann:UserAnnotation)-[:DESCRIBES]->(t)
        RETURN t, collect(DISTINCT c) as columns, collect(DISTINCT ann.content) as annotations
        """
        results = self.neo4j.execute_query(query, {
            "table_name": table_name,
            "db_name": database_name
        })
        
        if results:
            record = results[0]
            return {
                "name": table_name,
                "columns": record.get("columns", []),
                "annotations": record.get("annotations", [])
            }
        return None
    
    def clear_database_graph(self, database_name: str):
        """Clear all nodes and relationships for a specific database."""
        # First, find all nodes connected to this database
        query = """
        MATCH (db:Database {name: $db_name})
        OPTIONAL MATCH (db)-[*]->(n)
        WITH db, collect(DISTINCT n) as nodes
        DETACH DELETE db, nodes
        """
        self.neo4j.execute_query(query, {"db_name": database_name})
        
        # Also delete any remaining nodes with database_name property
        cleanup_query = """
        MATCH (n)
        WHERE n.database_name = $db_name
        DETACH DELETE n
        """
        self.neo4j.execute_query(cleanup_query, {"db_name": database_name})
        logger.info(f"Cleared graph for database: {database_name}")
    
    def get_all_annotations(self, database_name: Optional[str] = None) -> List[Dict]:
        """Get all user annotations."""
        query = """
        MATCH (ann:UserAnnotation)
        WHERE $db_name IS NULL OR ann.database_name = $db_name
        RETURN ann.entity_type, ann.entity_name, ann.table_name, ann.content, ann.updated_at
        ORDER BY ann.updated_at DESC
        """
        results = self.neo4j.execute_query(query, {"db_name": database_name})
        return results
    
    def get_annotation(self, entity_type: str, entity_name: str, table_name: Optional[str] = None, database_name: Optional[str] = None) -> Optional[str]:
        """
        Get annotation content for a specific entity.
        
        Args:
            entity_type: Type of entity ('table', 'column', 'database')
            entity_name: Name of the entity
            table_name: Table name (required for columns)
            database_name: Database name
        
        Returns:
            Annotation content string or None if not found
        """
        params = {
            "entity_name": entity_name,
            "entity_type": entity_type,
            "db_name": database_name
        }
        
        if entity_type == "database":
            query = """
            MATCH (ann:UserAnnotation)-[:DESCRIBES]->(e:Database)
            WHERE e.name = $db_name
              AND ann.entity_type = $entity_type
            RETURN ann.content as content
            LIMIT 1
            """
        elif entity_type == "column" and table_name:
            query = """
            MATCH (ann:UserAnnotation)-[:DESCRIBES]->(e:Column)
            WHERE e.name = $entity_name AND e.table_name = $table_name AND e.database_name = $db_name
              AND ann.entity_type = $entity_type AND ann.entity_name = $entity_name
            RETURN ann.content as content
            LIMIT 1
            """
            params["table_name"] = table_name
        else:  # table
            query = """
            MATCH (ann:UserAnnotation)-[:DESCRIBES]->(e:Table)
            WHERE e.name = $entity_name AND e.database_name = $db_name
              AND ann.entity_type = $entity_type AND ann.entity_name = $entity_name
            RETURN ann.content as content
            LIMIT 1
            """
        
        results = self.neo4j.execute_query(query, params)
        if results and results[0].get("content"):
            return results[0]["content"]
        return None
    
    def add_query_example(
        self,
        entity_type: str,
        entity_name: str,
        query: str,
        description: str = "",
        table_name: Optional[str] = None,
        database_name: Optional[str] = None
    ):
        """
        Add a query example to a node's description.
        
        Args:
            entity_type: Type of entity ('table', 'column', 'database')
            entity_name: Name of the entity
            query: SQL query example
            description: Optional description of the query
            table_name: Table name (required for columns)
            database_name: Database name
        """
        logger.info(f"Adding query example for {entity_type}: {entity_name}")
        
        # Build query example text
        example_text = f"Query Example: {query}"
        if description:
            example_text = f"{description}\n\n{example_text}"
        
        # Get current description
        current_desc = self._get_node_description(entity_type, entity_name, table_name, database_name)
        
        # Append new example
        if current_desc:
            new_desc = f"{current_desc}\n\n{example_text}"
        else:
            new_desc = example_text
        
        # Update node description
        self._update_node_description(entity_type, entity_name, new_desc, table_name, database_name)
        
        logger.debug(f"Query example added to {entity_type}: {entity_name}")
    
    def _get_node_description(self, entity_type: str, entity_name: str, table_name: Optional[str], database_name: Optional[str]) -> str:
        """Get current description from node."""
        params = {"entity_name": entity_name, "db_name": database_name}
        
        if entity_type == "database":
            query = "MATCH (e:Database {name: $db_name}) RETURN e.description as description"
        elif entity_type == "column":
            query = """
            MATCH (e:Column {name: $entity_name, table_name: $table_name, database_name: $db_name})
            RETURN e.description as description
            """
            params["table_name"] = table_name
        else:  # table
            query = """
            MATCH (e:Table {name: $entity_name, database_name: $db_name})
            RETURN e.description as description
            """
        
        results = self.neo4j.execute_query(query, params)
        if results and results[0].get("description"):
            return results[0]["description"]
        return ""
    
    def _update_node_description(self, entity_type: str, entity_name: str, description: str, table_name: Optional[str], database_name: Optional[str]):
        """Update node description property."""
        params = {"entity_name": entity_name, "db_name": database_name, "description": description}
        
        if entity_type == "database":
            query = """
            MATCH (e:Database {name: $db_name})
            SET e.description = $description
            RETURN e
            """
        elif entity_type == "column":
            query = """
            MATCH (e:Column {name: $entity_name, table_name: $table_name, database_name: $db_name})
            SET e.description = $description
            RETURN e
            """
            params["table_name"] = table_name
        else:  # table
            query = """
            MATCH (e:Table {name: $entity_name, database_name: $db_name})
            SET e.description = $description
            RETURN e
            """
        
        self.neo4j.execute_query(query, params)
    
    def get_database_summary(self, database_name: Optional[str] = None) -> str:
        """
        Get a summary of all tables and columns in the database.
        
        Args:
            database_name: Database name (optional, uses first available if not provided)
        
        Returns:
            Formatted summary string
        """
        logger.info(f"Generating database summary for: {database_name}")
        
        # Get all tables with their columns
        query = """
        MATCH (db:Database)
        WHERE $db_name IS NULL OR db.name = $db_name
        WITH db
        LIMIT 1
        MATCH (db)-[:HAS_TABLE]->(t:Table)
        OPTIONAL MATCH (t)-[:HAS_COLUMN]->(c:Column)
        OPTIONAL MATCH (ann:UserAnnotation)-[:DESCRIBES]->(t)
        WITH db, t, COLLECT(DISTINCT c) as columns, COLLECT(DISTINCT ann.content) as table_descriptions
        ORDER BY t.name
        RETURN db.name as db_name, t.name as table_name, 
               columns, table_descriptions
        """
        
        results = self.neo4j.execute_query(query, {"db_name": database_name})
        
        if not results:
            return "No database schema found in knowledge graph."
        
        summary_parts = []
        db_name = results[0].get("db_name", "Unknown")
        summary_parts.append(f"# Database Summary: {db_name}\n")
        
        for record in results:
            table_name = record.get("table_name")
            columns = record.get("columns", [])
            descriptions = record.get("table_descriptions", [])
            
            summary_parts.append(f"\n## Table: {table_name}")
            
            if descriptions:
                summary_parts.append(f"Description: {descriptions[0]}")
            
            summary_parts.append(f"\nColumns ({len(columns)}):")
            for col in columns:
                col_name = col.get("name", "")
                col_type = col.get("type", "")
                col_desc = col.get("description", "")
                nullable = col.get("nullable", True)
                null_str = "NULL" if nullable else "NOT NULL"
                
                col_line = f"  - {col_name}: {col_type} ({null_str})"
                if col_desc:
                    col_line += f" - {col_desc}"
                summary_parts.append(col_line)
        
        return "\n".join(summary_parts)
    
    def find_entities_without_descriptions(self, database_name: Optional[str] = None) -> Dict[str, List[Dict]]:
        """
        Find tables and columns that don't have descriptions.
        
        Args:
            database_name: Database name (optional)
        
        Returns:
            Dictionary with 'tables' and 'columns' lists
        """
        logger.info("Finding entities without descriptions")
        
        # Find tables without descriptions
        table_query = """
        MATCH (db:Database)
        WHERE $db_name IS NULL OR db.name = $db_name
        WITH db LIMIT 1
        MATCH (db)-[:HAS_TABLE]->(t:Table)
        WHERE t.description IS NULL OR t.description = ""
        OPTIONAL MATCH (ann:UserAnnotation)-[:DESCRIBES]->(t)
        WHERE ann IS NULL
        RETURN t.name as table_name, t.database_name as db_name
        ORDER BY t.name
        """
        
        # Find columns without descriptions
        column_query = """
        MATCH (db:Database)
        WHERE $db_name IS NULL OR db.name = $db_name
        WITH db LIMIT 1
        MATCH (db)-[:HAS_TABLE]->(t:Table)-[:HAS_COLUMN]->(c:Column)
        WHERE c.description IS NULL OR c.description = ""
        OPTIONAL MATCH (ann:UserAnnotation)-[:DESCRIBES]->(c)
        WHERE ann IS NULL
        RETURN t.name as table_name, c.name as column_name, c.type as column_type,
               c.database_name as db_name
        ORDER BY t.name, c.name
        """
        
        tables = self.neo4j.execute_query(table_query, {"db_name": database_name})
        columns = self.neo4j.execute_query(column_query, {"db_name": database_name})
        
        return {
            "tables": tables,
            "columns": columns
        }

