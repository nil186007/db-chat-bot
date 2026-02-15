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
        
        New Structure:
        - databases (root node)
          - database_name (Database node with name, type, description)
            - If postgresql/relational: Table nodes → Column nodes
            - If mongodb: Collection nodes → Field nodes
        
        Args:
            schema_info: Schema dictionary from PostgresClient.fetch_schema() or MongoDBClient.fetch_schema()
            database_name: Name of the database
            host: Database host
            port: Database port
            db_type: Database type ("postgresql" or "mongodb")
        """
        logger.info(f"Building knowledge graph for {db_type} database: {database_name}")
        
        # Create or get root "databases" node
        root_query = """
        MERGE (root:Databases {name: "databases"})
        ON CREATE SET 
            root.created_at = datetime()
        RETURN root
        """
        self.neo4j.execute_query(root_query, {})
        
        # Clear existing graph for this database
        self.clear_database_graph(database_name)
        
        # Create or get Database node with name, type, and description
        db_query = """
        MATCH (root:Databases {name: "databases"})
        MERGE (db:Database {name: $db_name})
        ON CREATE SET 
            db.type = $db_type,
            db.host = $host,
            db.port = $port,
            db.description = "",
            db.query_examples = [],
            db.created_at = datetime()
        ON MATCH SET
            db.type = $db_type,
            db.host = $host,
            db.port = $port
        MERGE (root)-[:HAS_DATABASE]->(db)
        RETURN db
        """
        self.neo4j.execute_query(db_query, {
            "db_name": database_name,
            "db_type": db_type,
            "host": host,
            "port": port
        })
        
        if db_type == "mongodb":
            for collection in schema_info.get("collections", []):
                self._create_mongodb_collection_node(database_name, collection)
            logger.info(f"Knowledge graph built: {len(schema_info.get('collections', []))} collection(s) added")
        else:
            # PostgreSQL: Database -> Schema -> Table -> Column
            if schema_info.get("schemas"):
                for schema_obj in schema_info["schemas"]:
                    schema_name = schema_obj["name"]
                    for table in schema_obj.get("tables", []):
                        table["schema_name"] = schema_name
                        self._create_table_node(database_name, schema_name, table)
                total = sum(len(s.get("tables", [])) for s in schema_info["schemas"])
            else:
                # Backward compat: flat tables (treat as public schema)
                for table in schema_info.get("tables", []):
                    schema_name = table.get("schema_name", "public")
                    self._create_table_node(database_name, schema_name, table)
                total = len(schema_info.get("tables", []))
            logger.info(f"Knowledge graph built: {total} table(s) across schemas")
    
    def _create_table_node(self, database_name: str, schema_name: str, table_info: Dict):
        """Create Schema node (if needed), Table node, and Column nodes. Hierarchy: Database->Schema->Table->Column."""
        table_name = table_info["name"]
        
        # Create or get Schema node under Database
        schema_query = """
        MATCH (db:Database {name: $db_name})
        MERGE (s:Schema {name: $schema_name, database_name: $db_name})
        ON CREATE SET s.description = "", s.created_at = datetime()
        MERGE (db)-[:HAS_SCHEMA]->(s)
        RETURN s
        """
        self.neo4j.execute_query(schema_query, {
            "db_name": database_name,
            "schema_name": schema_name
        })
        
        # Create Table node linked to Schema
        table_query = """
        MATCH (s:Schema {name: $schema_name, database_name: $db_name})
        CREATE (t:Table {
            name: $table_name,
            schema_name: $schema_name,
            description: "",
            query_examples: [],
            created_at: datetime(),
            database_name: $db_name
        })
        CREATE (s)-[:HAS_TABLE]->(t)
        RETURN t
        """
        self.neo4j.execute_query(table_query, {
            "db_name": database_name,
            "schema_name": schema_name,
            "table_name": table_name
        })
        
        # Create Column (attribute) nodes under Table
        for col in table_info.get("columns", []):
            col_query = """
            MATCH (t:Table {name: $table_name, schema_name: $schema_name, database_name: $db_name})
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
                "schema_name": schema_name,
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
            MATCH (t:Table {name: $table_name, schema_name: $schema_name, database_name: $db_name})-[:HAS_COLUMN]->(c:Column {name: $pk_col})
            CREATE (t)-[:HAS_PRIMARY_KEY]->(c)
            """
            self.neo4j.execute_query(pk_query, {
                "table_name": table_name,
                "schema_name": schema_name,
                "db_name": database_name,
                "pk_col": pk
            })
        
        # Create foreign key relationships (reference table may be in same or different schema)
        for fk in table_info.get("foreign_keys", []):
            ref_schema = fk.get("references_schema", schema_name)
            fk_query = """
            MATCH (t1:Table {name: $table_name, schema_name: $schema_name, database_name: $db_name}),
                  (t2:Table {name: $ref_table, schema_name: $ref_schema, database_name: $db_name})
            CREATE (t1)-[:HAS_FOREIGN_KEY {
                from_column: $from_col,
                to_column: $to_col
            }]->(t2)
            """
            self.neo4j.execute_query(fk_query, {
                "table_name": table_name,
                "schema_name": schema_name,
                "ref_table": fk["references_table"],
                "ref_schema": ref_schema,
                "from_col": fk["column"],
                "to_col": fk["references_column"],
                "db_name": database_name
            })
    
    def _create_mongodb_collection_node(self, database_name: str, collection_info: Dict):
        """Create MongoDB collection node with Field nodes as children under Database node."""
        collection_name = collection_info["name"]
        
        # Create collection node linked to Database
        collection_query = """
        MATCH (db:Database {name: $db_name})
        CREATE (c:Collection {
            name: $collection_name,
            document_count: $doc_count,
            description: "",
            query_examples: [],
            created_at: datetime(),
            database_name: $db_name
        })
        CREATE (db)-[:HAS_COLLECTION]->(c)
        RETURN c
        """
        self.neo4j.execute_query(collection_query, {
            "db_name": database_name,
            "collection_name": collection_name,
            "doc_count": collection_info.get("document_count", 0)
        })
        
        # Create Field nodes for each field in the collection
        for field in collection_info.get("fields", []):
            field_query = """
            MATCH (c:Collection {name: $collection_name, database_name: $db_name})
            CREATE (f:Field {
                name: $field_name,
                types: $field_types,
                nullable: $nullable,
                example: $example,
                description: "",
                query_examples: [],
                created_at: datetime(),
                database_name: $db_name,
                collection_name: $collection_name
            })
            CREATE (c)-[:HAS_FIELD]->(f)
            RETURN f
            """
            self.neo4j.execute_query(field_query, {
                "collection_name": collection_name,
                "db_name": database_name,
                "field_name": field.get("name", ""),
                "field_types": field.get("types", []),
                "nullable": field.get("nullable", False),
                "example": str(field.get("example", "")) if field.get("example") else ""
            })
    
    def add_annotation(
        self,
        entity_type: str,
        entity_name: str,
        table_name: Optional[str] = None,
        content: str = "",
        database_name: Optional[str] = None,
        schema_name: Optional[str] = None
    ):
        """
        Add user annotation to the knowledge graph.
        
        Args:
            entity_type: Type of entity ('table', 'column', 'database')
            entity_name: Name of the entity (table name or column name)
            table_name: Required if entity_type is 'column' (supports "schema.table" format)
            content: Annotation content/description
            database_name: Database name (optional, will find if not provided)
            schema_name: Schema name for table/column (optional; parsed from table_name if "schema.table" format)
        """
        logger.info(f"Adding annotation for {entity_type}: {entity_name}")
        
        # Parse schema from "schema.table" format
        eff_schema = schema_name
        eff_table_name = entity_name if entity_type == "table" else (table_name or "")
        if eff_table_name and "." in eff_table_name:
            parts = eff_table_name.split(".", 1)
            eff_schema, eff_table_name = parts[0], parts[1]
        if not eff_schema:
            eff_schema = "public"
        
        params = {
            "entity_name": eff_table_name if entity_type == "table" else entity_name,
            "table_name": eff_table_name if entity_type == "column" else eff_table_name,
            "schema_name": eff_schema,
            "db_name": database_name
        }
        
        if entity_type == "database":
            # For database, use database name as entity_name
            entity_query = """
            MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
                  (e:Database {name: $db_name})
            RETURN e
            LIMIT 1
            """
            params["entity_name"] = database_name  # Use db_name as entity_name for databases
        elif entity_type == "table":
            entity_query = """
            MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
                  (db:Database {type: "postgresql"})-[:HAS_SCHEMA]->(s:Schema {name: $schema_name})-[:HAS_TABLE]->(e:Table {name: $entity_name})
            RETURN e
            LIMIT 1
            """
        elif entity_type == "column":
            entity_query = """
            MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
                  (db:Database {type: "postgresql"})-[:HAS_SCHEMA]->(s:Schema {name: $schema_name})-[:HAS_TABLE]->
                  (t:Table {name: $table_name})-[:HAS_COLUMN]->(e:Column {name: $entity_name})
            RETURN e
            LIMIT 1
            """
        elif entity_type == "collection":
            entity_query = """
            MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
                  (db:Database {type: "mongodb"})-[:HAS_COLLECTION]->(e:Collection {name: $entity_name})
            RETURN e
            LIMIT 1
            """
        elif entity_type == "field":
            # For fields, table_name is actually collection_name
            entity_query = """
            MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
                  (db:Database {type: "mongodb"})-[:HAS_COLLECTION]->
                  (coll:Collection {name: $table_name})-[:HAS_FIELD]->(e:Field {name: $entity_name})
            RETURN e
            LIMIT 1
            """
        else:
            logger.warning(f"Unknown entity type: {entity_type}")
            return
        
        entity_result = self.neo4j.execute_query(entity_query, params)
        
        if not entity_result:
            logger.warning(f"Entity not found for annotation: {entity_type}:{entity_name}")
            return
        
        # Check if annotation exists
        if entity_type == "database":
            check_query = """
            MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
                  (e:Database {name: $db_name})
            OPTIONAL MATCH (existing:UserAnnotation)-[:DESCRIBES]->(e)
            WHERE existing.entity_type = $entity_type
            RETURN existing
            LIMIT 1
            """
        elif entity_type == "column":
            check_query = """
            MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
                  (db:Database {type: "postgresql"})-[:HAS_SCHEMA]->(s:Schema {name: $schema_name})-[:HAS_TABLE]->
                  (t:Table {name: $table_name})-[:HAS_COLUMN]->(e:Column {name: $entity_name})
            OPTIONAL MATCH (existing:UserAnnotation)-[:DESCRIBES]->(e)
            WHERE existing.entity_type = $entity_type AND existing.entity_name = $entity_name
            RETURN existing
            LIMIT 1
            """
        elif entity_type == "field":
            check_query = """
            MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
                  (db:Database {type: "mongodb"})-[:HAS_COLLECTION]->
                  (coll:Collection {name: $table_name})-[:HAS_FIELD]->(e:Field {name: $entity_name})
            OPTIONAL MATCH (existing:UserAnnotation)-[:DESCRIBES]->(e)
            WHERE existing.entity_type = $entity_type AND existing.entity_name = $entity_name
            RETURN existing
            LIMIT 1
            """
        elif entity_type == "collection":
            check_query = """
            MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
                  (db:Database {type: "mongodb"})-[:HAS_COLLECTION]->(e:Collection {name: $entity_name})
            OPTIONAL MATCH (existing:UserAnnotation)-[:DESCRIBES]->(e)
            WHERE existing.entity_type = $entity_type AND existing.entity_name = $entity_name
            RETURN existing
            LIMIT 1
            """
        else:  # table
            check_query = """
            MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
                  (db:Database {type: "postgresql"})-[:HAS_SCHEMA]->(s:Schema {name: $schema_name})-[:HAS_TABLE]->(e:Table {name: $entity_name})
            OPTIONAL MATCH (existing:UserAnnotation)-[:DESCRIBES]->(e)
            WHERE existing.entity_type = $entity_type AND existing.entity_name = $entity_name
            RETURN existing
            LIMIT 1
            """
        
        existing = self.neo4j.execute_query(check_query, {
            "entity_name": params["entity_name"],
            "entity_type": entity_type,
            "content": content,
            "table_name": params["table_name"],
            "schema_name": params["schema_name"],
            "db_name": database_name
        })
        
        if existing and existing[0].get("existing"):
            # Update existing annotation
            if entity_type == "database":
                update_query = """
                MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
                      (e:Database {name: $db_name})
                MATCH (ann:UserAnnotation)-[:DESCRIBES]->(e)
                WHERE ann.entity_type = $entity_type
                SET ann.content = $content,
                    ann.updated_at = datetime()
                RETURN ann
                """
            elif entity_type == "column":
                update_query = """
                MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
                      (db:Database {type: "postgresql"})-[:HAS_SCHEMA]->(s:Schema {name: $schema_name})-[:HAS_TABLE]->
                      (t:Table {name: $table_name})-[:HAS_COLUMN]->(e:Column {name: $entity_name})
                MATCH (ann:UserAnnotation)-[:DESCRIBES]->(e)
                WHERE ann.entity_type = $entity_type AND ann.entity_name = $entity_name
                SET ann.content = $content,
                    ann.updated_at = datetime()
                RETURN ann
                """
            elif entity_type == "field":
                update_query = """
                MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
                      (db:Database {type: "mongodb"})-[:HAS_COLLECTION]->
                      (coll:Collection {name: $table_name})-[:HAS_FIELD]->(e:Field {name: $entity_name})
                MATCH (ann:UserAnnotation)-[:DESCRIBES]->(e)
                WHERE ann.entity_type = $entity_type AND ann.entity_name = $entity_name
                SET ann.content = $content,
                    ann.updated_at = datetime()
                RETURN ann
                """
            elif entity_type == "collection":
                update_query = """
                MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
                      (db:Database {type: "mongodb"})-[:HAS_COLLECTION]->(e:Collection {name: $entity_name})
                MATCH (ann:UserAnnotation)-[:DESCRIBES]->(e)
                WHERE ann.entity_type = $entity_type AND ann.entity_name = $entity_name
                SET ann.content = $content,
                    ann.updated_at = datetime()
                RETURN ann
                """
            else:  # table
                update_query = """
                MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
                      (db:Database {type: "postgresql"})-[:HAS_SCHEMA]->(s:Schema {name: $schema_name})-[:HAS_TABLE]->(e:Table {name: $entity_name})
                MATCH (ann:UserAnnotation)-[:DESCRIBES]->(e)
                WHERE ann.entity_type = $entity_type AND ann.entity_name = $entity_name
                SET ann.content = $content,
                    ann.updated_at = datetime()
                RETURN ann
                """
            self.neo4j.execute_query(update_query, {
                "entity_name": params["entity_name"],
                "entity_type": entity_type,
                "content": content,
                "table_name": params["table_name"],
                "schema_name": params["schema_name"],
                "db_name": database_name
            })
        else:
            # Create new annotation
            if entity_type == "database":
                create_query = """
                MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
                      (e:Database {name: $db_name})
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
                MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
                      (db:Database {type: "postgresql"})-[:HAS_SCHEMA]->(s:Schema {name: $schema_name})-[:HAS_TABLE]->
                      (t:Table {name: $table_name})-[:HAS_COLUMN]->(e:Column {name: $entity_name})
                CREATE (ann:UserAnnotation {
                    content: $content,
                    entity_type: $entity_type,
                    entity_name: $entity_name,
                    table_name: $table_name,
                    schema_name: $schema_name,
                    database_name: $db_name,
                    created_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (ann)-[:DESCRIBES]->(e)
                RETURN ann
                """
            elif entity_type == "field":
                create_query = """
                MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
                      (db:Database {type: "mongodb"})-[:HAS_COLLECTION]->
                      (coll:Collection {name: $table_name})-[:HAS_FIELD]->(e:Field {name: $entity_name})
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
            elif entity_type == "collection":
                create_query = """
                MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
                      (db:Database {type: "mongodb"})-[:HAS_COLLECTION]->(e:Collection {name: $entity_name})
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
            else:  # table
                create_query = """
                MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
                      (db:Database {type: "postgresql"})-[:HAS_SCHEMA]->(s:Schema {name: $schema_name})-[:HAS_TABLE]->(e:Table {name: $entity_name})
                CREATE (ann:UserAnnotation {
                    content: $content,
                    entity_type: $entity_type,
                    entity_name: $entity_name,
                    table_name: null,
                    schema_name: $schema_name,
                    database_name: $db_name,
                    created_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (ann)-[:DESCRIBES]->(e)
                RETURN ann
                """
            self.neo4j.execute_query(create_query, {
                "entity_name": params["entity_name"],
                "entity_type": entity_type,
                "content": content,
                "table_name": params["table_name"],
                "schema_name": params["schema_name"],
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
            # Retrieve specific collections through new hierarchy
            cypher_query = """
            MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
                  (db:Database {type: "mongodb"})-[:HAS_COLLECTION]->(c:Collection)
            WHERE c.name IN $collection_names
            OPTIONAL MATCH (c)-[:HAS_FIELD]->(f:Field)
            OPTIONAL MATCH (ann:UserAnnotation)-[:DESCRIBES]->(c)
            WHERE ann.entity_type = 'collection' OR ann.entity_type IS NULL
            WITH c, collect(DISTINCT f) as fields, collect(DISTINCT ann.content) as collection_annotations
            RETURN c.name as collection_name, c.description as collection_description,
                   c.document_count as document_count,
                   fields, collection_annotations
            ORDER BY c.name
            """
            results = self.neo4j.execute_query(cypher_query, {
                "collection_names": collection_names
            })
        elif query_keywords:
            # Search by keywords - check collection name and field names through new hierarchy
            cypher_query = """
            MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
                  (db:Database {type: "mongodb"})-[:HAS_COLLECTION]->(c:Collection)
            WHERE ANY(keyword IN $keywords WHERE c.name CONTAINS keyword)
            OPTIONAL MATCH (c)-[:HAS_FIELD]->(f:Field)
            WHERE ANY(keyword IN $keywords WHERE f.name CONTAINS keyword)
            OPTIONAL MATCH (ann:UserAnnotation)-[:DESCRIBES]->(c)
            WHERE ann.entity_type = 'collection' OR ann.entity_type IS NULL
            WITH c, collect(DISTINCT f) as fields, collect(DISTINCT ann.content) as collection_annotations
            RETURN c.name as collection_name, c.description as collection_description,
                   c.document_count as document_count,
                   fields, collection_annotations
            ORDER BY c.name
            LIMIT 10
            """
            results = self.neo4j.execute_query(cypher_query, {
                "keywords": query_keywords
            })
        else:
            # Retrieve all collections through new hierarchy
            cypher_query = """
            MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
                  (db:Database {type: "mongodb"})-[:HAS_COLLECTION]->(c:Collection)
            OPTIONAL MATCH (c)-[:HAS_FIELD]->(f:Field)
            OPTIONAL MATCH (ann:UserAnnotation)-[:DESCRIBES]->(c)
            WHERE ann.entity_type = 'collection' OR ann.entity_type IS NULL
            WITH c, collect(DISTINCT f) as fields, collect(DISTINCT ann.content) as collection_annotations
            RETURN c.name as collection_name, c.description as collection_description,
                   c.document_count as document_count,
                   fields, collection_annotations
            ORDER BY c.name
            """
            results = self.neo4j.execute_query(cypher_query, {})
        
        # Format results
        context = "MongoDB Database Schema:\n\n"
        for record in results:
            collection_name = record["collection_name"]
            fields = record.get("fields", [])  # Fields are now nodes, not dicts
            collection_annotations = record.get("collection_annotations", [])
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
            if fields:
                for field in fields:
                    if field:  # Field is now a node
                        field_name = field.get("name", "")
                        types = field.get("types", [])
                        nullable = " (nullable)" if field.get("nullable") else ""
                        example = field.get("example")
                        
                        field_info = f"  - {field_name}: {', '.join(types) if isinstance(types, list) else types}{nullable}"
                        if example:
                            field_info += f" (example: {example})"
                        context += field_info + "\n"
                        
                        # Add field description
                        field_desc = field.get("description", "")
                        if field_desc:
                            context += f"    Description: {field_desc}\n"
            
            context += "\n"
        
        logger.debug(f"MongoDB schema context retrieved: {len(context)} characters")
        return context
    
    def get_relevance_score(
        self,
        user_query: str,
        database_name: Optional[str] = None,
        db_type: str = "postgresql"
    ) -> Dict[str, Any]:
        """
        Get relevance score for a query against a database in the knowledge graph.
        
        Uses the new graph structure: databases → Database → Tables/Collections → Columns/Fields
        
        Args:
            user_query: User's natural language query
            database_name: Database name (deprecated, kept for compatibility)
            db_type: Database type ("postgresql" or "mongodb")
        
        Returns:
            Dictionary with relevance score, matched entities, and match details
        """
        logger.debug(f"RAG RETRIEVAL: Getting relevance score for {db_type}")
        logger.debug(f"  Query: {user_query}")
        
        query_lower = user_query.lower()
        query_words = set(query_lower.split())
        # Also create a set with singular/plural variations
        query_words_extended = set(query_words)
        for word in query_words:
            if word.endswith('s') and len(word) > 1:
                query_words_extended.add(word[:-1])  # Add singular form
            else:
                query_words_extended.add(word + 's')  # Add plural form
        
        logger.debug(f"  Query words: {query_words}")
        logger.debug(f"  Extended words: {len(query_words_extended)} words")
        
        score = 0
        matched_entities = []
        match_details = {
            "table_matches": [],
            "column_matches": [],
            "collection_matches": [],
            "field_matches": [],
            "database_description_match": False,
            "database_description_score": 0
        }
        
        if db_type == "postgresql":
            # Search PostgreSQL tables and columns through the new hierarchy
            # Database → Table → Column (for PostgreSQL)
            cypher_query = """
            MATCH (db:Database {type: "postgresql"})-[:HAS_SCHEMA]->(s:Schema)-[:HAS_TABLE]->(t:Table)
            OPTIONAL MATCH (t)-[:HAS_COLUMN]->(c:Column)
            WITH t, s, collect(c) as columns
            RETURN t.name as table_name, t.schema_name as schema_name, t.description as table_description,
                   columns
            ORDER BY s.name, t.name
            """
            results = self.neo4j.execute_query(cypher_query, {})
            
            for record in results:
                table_name = record.get("table_name", "").lower()
                table_desc = record.get("table_description", "").lower()
                columns = record.get("columns", [])
                
                # Check table name match (exact, partial, singular/plural)
                table_match_score = 0
                table_name_words = set(table_name.split('_'))  # Handle snake_case
                
                # Exact match
                if table_name in query_words or table_name in query_lower:
                    table_match_score += 15
                    match_details["table_matches"].append(table_name)
                # Word match (handles singular/plural)
                elif any(word in query_words_extended for word in table_name_words) or \
                     any(word in table_name for word in query_words_extended):
                    table_match_score += 10
                    match_details["table_matches"].append(table_name)
                # Partial match
                elif any(word in query_lower for word in table_name_words) or \
                     any(word in table_name for word in query_words):
                    table_match_score += 5
                    match_details["table_matches"].append(table_name)
                
                # Check table description match
                if table_desc and any(word in table_desc for word in query_words_extended):
                    table_match_score += 5
                
                # Check column matches
                column_matches = []
                for col in columns:
                    if col:
                        col_name = col.get("name", "").lower()
                        col_name_words = set(col_name.split('_'))
                        
                        # Exact or word match
                        if col_name in query_words_extended or \
                           any(word in query_words_extended for word in col_name_words) or \
                           any(word in col_name for word in query_words_extended):
                            table_match_score += 3
                            column_matches.append(col_name)
                            match_details["column_matches"].append(f"{table_name}.{col_name}")
                
                if table_match_score > 0:
                    score += table_match_score
                    schema_name = record.get("schema_name", "public")
                    qualified_name = f'"{schema_name}".{table_name}' if schema_name != "public" else table_name
                    matched_entities.append({
                        "type": "table",
                        "name": table_name,
                        "schema_name": schema_name,
                        "qualified_name": qualified_name,
                        "score": table_match_score,
                        "column_matches": column_matches
                    })
        
        else:  # mongodb
            # Search MongoDB collections and fields through the new hierarchy
            # databases → Database (with type=mongodb) → Collection → Field
            logger.debug("  Querying MongoDB schema from knowledge graph...")
            cypher_query = """
            MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
                  (db:Database {type: "mongodb"})-[:HAS_COLLECTION]->(c:Collection)
            OPTIONAL MATCH (c)-[:HAS_FIELD]->(f:Field)
            WITH c, collect(f) as fields
            RETURN c.name as collection_name, c.description as collection_description,
                   fields
            ORDER BY c.name
            """
            results = self.neo4j.execute_query(cypher_query, {})
            logger.debug(f"  Retrieved {len(results)} MongoDB collections from knowledge graph")
            
            for record in results:
                collection_name = record.get("collection_name", "").lower()
                collection_desc = record.get("collection_description", "").lower()
                fields = record.get("fields", [])
                
                # Check collection name match (exact, partial, singular/plural)
                collection_match_score = 0
                collection_name_words = set(collection_name.split('_'))  # Handle snake_case
                
                # Exact match
                if collection_name in query_words or collection_name in query_lower:
                    collection_match_score += 15
                    match_details["collection_matches"].append(collection_name)
                # Word match (handles singular/plural)
                elif any(word in query_words_extended for word in collection_name_words) or \
                     any(word in collection_name for word in query_words_extended):
                    collection_match_score += 10
                    match_details["collection_matches"].append(collection_name)
                # Partial match
                elif any(word in query_lower for word in collection_name_words) or \
                     any(word in collection_name for word in query_words):
                    collection_match_score += 5
                    match_details["collection_matches"].append(collection_name)
                
                # Check collection description match
                if collection_desc and any(word in collection_desc for word in query_words_extended):
                    collection_match_score += 5
                
                # Check field matches
                field_matches = []
                if fields:
                    for field in fields:
                        if field:  # Field is now a node, not a dict
                            field_name = field.get("name", "").lower()
                            field_name_words = set(field_name.split('_'))
                            
                            # Exact or word match
                            if field_name in query_words_extended or \
                               any(word in query_words_extended for word in field_name_words) or \
                               any(word in field_name for word in query_words_extended):
                                collection_match_score += 3
                                field_matches.append(field_name)
                                match_details["field_matches"].append(f"{collection_name}.{field_name}")
                
                if collection_match_score > 0:
                    score += collection_match_score
                    matched_entities.append({
                        "type": "collection",
                        "name": collection_name,
                        "score": collection_match_score,
                        "field_matches": field_matches
                    })
        
        # Check Database description match (add significant weight)
        db_desc_query = """
        MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
              (db:Database {type: $db_type})
        RETURN db.description as description
        LIMIT 1
        """
        db_results = self.neo4j.execute_query(db_desc_query, {"db_type": db_type})
        
        if db_results and db_results[0].get("description"):
            db_description = db_results[0].get("description", "").lower()
            # Check if query words match database description
            description_matches = sum(1 for word in query_words_extended if word in db_description)
            if description_matches > 0:
                # Add significant score boost for database description match
                db_score = description_matches * 10  # 10 points per matching word
                score += db_score
                logger.debug(f"  Database description match: +{db_score} points ({description_matches} words matched)")
                match_details["database_description_match"] = True
                match_details["database_description_score"] = db_score
        
        logger.debug(f"  Final relevance score: {score}")
        logger.debug(f"  Total matched entities: {len(matched_entities)}")
        
        return {
            "score": score,
            "matched_entities": matched_entities,
            "match_details": match_details,
            "total_matches": len(matched_entities)
        }
    
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
        
        # Query through new hierarchy: databases → Database (type=postgresql) → Table → Column
        if table_names:
            # Retrieve specific tables
            cypher_query = """
            MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
                  (db:Database {type: "postgresql"})-[:HAS_SCHEMA]->(:Schema)-[:HAS_TABLE]->(t:Table)
            WHERE t.name IN $table_names
            OPTIONAL MATCH (t)-[:HAS_COLUMN]->(c:Column)
            OPTIONAL MATCH (ann:UserAnnotation)-[:DESCRIBES]->(t)
            OPTIONAL MATCH (col_ann:UserAnnotation)-[:DESCRIBES]->(c)
            WHERE col_ann.entity_type = 'column'
            WITH t, collect(DISTINCT c) as columns, 
                 collect(DISTINCT ann.content) as table_annotations,
                 collect(DISTINCT col_ann) as column_annotations
            RETURN t.name as table_name, t.schema_name as schema_name, t.description as table_description,
                   columns, table_annotations, column_annotations
            ORDER BY t.name
            """
            results = self.neo4j.execute_query(cypher_query, {
                "table_names": table_names
            })
        elif query_keywords:
            # Search by keywords
            cypher_query = """
            MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
                  (db:Database {type: "postgresql"})-[:HAS_SCHEMA]->(:Schema)-[:HAS_TABLE]->(t:Table)
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
            RETURN t.name as table_name, t.schema_name as schema_name, t.description as table_description,
                   columns, table_annotations, column_annotations
            ORDER BY t.name
            LIMIT 10
            """
            results = self.neo4j.execute_query(cypher_query, {
                "keywords": query_keywords
            })
        else:
            # Retrieve all tables
            cypher_query = """
            MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
                  (db:Database {type: "postgresql"})-[:HAS_SCHEMA]->(:Schema)-[:HAS_TABLE]->(t:Table)
            OPTIONAL MATCH (t)-[:HAS_COLUMN]->(c:Column)
            OPTIONAL MATCH (ann:UserAnnotation)-[:DESCRIBES]->(t)
            OPTIONAL MATCH (col_ann:UserAnnotation)-[:DESCRIBES]->(c)
            WHERE col_ann.entity_type = 'column'
            WITH t, collect(DISTINCT c) as columns,
                 collect(DISTINCT ann.content) as table_annotations,
                 collect(DISTINCT col_ann) as column_annotations
            RETURN t.name as table_name, t.schema_name as schema_name, t.description as table_description,
                   columns, table_annotations, column_annotations
            ORDER BY t.name
            """
            results = self.neo4j.execute_query(cypher_query, {})
        
        # Format results - include schema_name for multi-schema support
        context = "Database Schema:\n\n"
        for record in results:
            table_name = record["table_name"]
            schema_name = record.get("schema_name", "public")
            columns = record.get("columns", [])
            table_annotations = record.get("table_annotations", [])
            column_annotations = record.get("column_annotations", [])
            table_description = record.get("table_description", "")
            
            table_label = f'"{schema_name}".{table_name}' if schema_name != "public" else table_name
            context += f"Table: {table_label}\n"
            
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
    
    def get_schema_info(self, database_name: Optional[str] = None) -> Optional[Dict]:
        """
        Retrieve full schema info from the graph in the same format as PostgresClient.fetch_schema().
        Returns {"schemas": [...], "tables": [...]} with schema_name on each table for SQL qualification.
        
        Args:
            database_name: Optional database name filter. If None, returns first PostgreSQL database.
        
        Returns:
            Schema dict with tables (each having schema_name, name, columns, primary_keys, foreign_keys)
            or None if graph has no schema.
        """
        db_filter = "AND db.name = $db_name" if database_name else ""
        params = {} if not database_name else {"db_name": database_name}
        
        cypher = f"""
        MATCH (db:Database {{type: "postgresql"}})-[:HAS_SCHEMA]->(s:Schema)-[:HAS_TABLE]->(t:Table)
        {db_filter}
        OPTIONAL MATCH (t)-[:HAS_COLUMN]->(c:Column)
        OPTIONAL MATCH (t)-[:HAS_PRIMARY_KEY]->(pk:Column)
        OPTIONAL MATCH (t)-[fk:HAS_FOREIGN_KEY]->(t2:Table)
        WITH t, s, collect(DISTINCT c) as columns, collect(DISTINCT pk.name) as pk_names, 
             collect(DISTINCT {{from_col: fk.from_column, to_col: fk.to_column, ref_table: t2.name, ref_schema: t2.schema_name}}) as fk_records
        RETURN t.name as table_name, t.schema_name as schema_name, columns, pk_names, fk_records
        ORDER BY s.name, t.name
        """
        results = self.neo4j.execute_query(cypher, params)
        if not results:
            logger.debug("No schema found in knowledge graph")
            return None
        
        tables = []
        seen_schemas: Dict[str, List[Dict]] = {}
        for record in results:
            table_name = record.get("table_name", "")
            schema_name = record.get("schema_name", "public")
            columns_raw = record.get("columns", [])
            pk_names = [n for n in (record.get("pk_names") or []) if n]
            fk_records = [r for r in (record.get("fk_records") or []) if r and r.get("from_col")]
            
            cols = []
            for c in columns_raw:
                if not c:
                    continue
                col = c if isinstance(c, dict) else (getattr(c, "__dict__", {}) or {})
                cols.append({
                    "name": col.get("name", ""),
                    "type": col.get("type", "text"),
                    "nullable": col.get("nullable", True),
                    "default": col.get("default_value") or col.get("default", ""),
                    "max_length": col.get("max_length"),
                })
            
            fks = []
            for r in fk_records:
                fks.append({
                    "column": r.get("from_col", ""),
                    "references_schema": r.get("ref_schema", "public"),
                    "references_table": r.get("ref_table", ""),
                    "references_column": r.get("to_col", ""),
                })
            
            table_info = {
                "name": table_name,
                "schema_name": schema_name,
                "columns": cols,
                "primary_keys": pk_names,
                "foreign_keys": fks,
            }
            tables.append(table_info)
            if schema_name not in seen_schemas:
                seen_schemas[schema_name] = []
            seen_schemas[schema_name].append(table_info)
        
        schemas = [{"name": sn, "tables": seen_schemas[sn]} for sn in sorted(seen_schemas.keys())]
        schema_info = {"schemas": schemas, "tables": tables}
        logger.info(f"Retrieved schema from graph: {len(tables)} table(s), {len(schemas)} schema(s)")
        return schema_info
    
    def get_table_info(self, table_name: str, database_name: Optional[str] = None, schema_name: Optional[str] = None) -> Optional[Dict]:
        """Get information about a specific table from the graph."""
        # Support "schema.table" format
        if "." in table_name and not schema_name:
            parts = table_name.split(".", 1)
            schema_name, table_name = parts[0], parts[1]
        schema_filter = "AND t.schema_name = $schema_name" if schema_name else ""
        db_filter = "AND db.name = $db_name" if database_name else ""
        query = f"""
        MATCH (db:Database {{type: "postgresql"}})-[:HAS_SCHEMA]->(:Schema)-[:HAS_TABLE]->(t:Table {{name: $table_name}})
        {schema_filter} {db_filter}
        OPTIONAL MATCH (t)-[:HAS_COLUMN]->(c:Column)
        OPTIONAL MATCH (ann:UserAnnotation)-[:DESCRIBES]->(t)
        RETURN t, collect(DISTINCT c) as columns, collect(DISTINCT ann.content) as annotations
        LIMIT 1
        """
        params = {"table_name": table_name}
        if schema_name:
            params["schema_name"] = schema_name
        if database_name:
            params["db_name"] = database_name
        results = self.neo4j.execute_query(query, params)
        
        if results:
            record = results[0]
            t = record.get("t")
            table_node = t if isinstance(t, dict) else (getattr(t, "__dict__", {}) or {})
            return {
                "name": table_name,
                "schema_name": schema_name or table_node.get("schema_name", "public"),
                "columns": record.get("columns", []),
                "annotations": record.get("annotations", [])
            }
        return None
    
    def clear_database_graph(self, database_name: str):
        """Clear all nodes and relationships for a specific database."""
        # Delete all nodes under the Database
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
    
    def update_database_description(self, database_name: str, description: str):
        """
        Update the description of a Database node.
        
        Args:
            database_name: Name of the database
            description: Description of what this database stores
        """
        logger.info(f"Updating Database description for {database_name}")
        
        query = """
        MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
              (db:Database {name: $db_name})
        SET db.description = $description,
            db.updated_at = datetime()
        RETURN db
        """
        result = self.neo4j.execute_query(query, {
            "db_name": database_name,
            "description": description
        })
        
        if result:
            logger.info(f"Database description updated for {database_name}")
        else:
            logger.warning(f"Database {database_name} not found in knowledge graph")
    
    def update_database_type_description(self, db_type: str, description: str):
        """
        Update the description of a Database node by type (for backward compatibility).
        
        Args:
            db_type: Database type ("postgresql" or "mongodb")
            description: Description of what this database stores
        """
        # Find database by type
        query = """
        MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
              (db:Database {type: $db_type})
        SET db.description = $description,
            db.updated_at = datetime()
        RETURN db
        """
        result = self.neo4j.execute_query(query, {
            "db_type": db_type,
            "description": description
        })
        
        if result:
            logger.info(f"Database description updated for type {db_type}")
        else:
            logger.warning(f"Database with type {db_type} not found in knowledge graph")
    
    def get_database_type_description(self, db_type: str) -> Optional[str]:
        """
        Get the description of a Database node by type.
        
        Args:
            db_type: Database type ("postgresql" or "mongodb")
        
        Returns:
            Description string or None if not found
        """
        query = """
        MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
              (db:Database {type: $db_type})
        RETURN db.description as description
        LIMIT 1
        """
        result = self.neo4j.execute_query(query, {"db_type": db_type})
        
        if result and result[0].get("description"):
            return result[0]["description"]
        return None
    
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
    
    def get_annotation(self, entity_type: str, entity_name: str, table_name: Optional[str] = None, database_name: Optional[str] = None, schema_name: Optional[str] = None) -> Optional[str]:
        """
        Get annotation content for a specific entity.
        
        Args:
            entity_type: Type of entity ('table', 'column', 'database')
            entity_name: Name of the entity (supports "schema.table" for tables)
            table_name: Table name (required for columns; supports "schema.table")
            database_name: Database name
            schema_name: Schema name (optional; parsed from entity/table name if "schema.table" format)
        """
        eff_schema = schema_name or "public"
        eff_entity = entity_name
        eff_table = table_name
        if entity_type == "table" and entity_name and "." in entity_name:
            parts = entity_name.split(".", 1)
            eff_schema, eff_entity = parts[0], parts[1]
        elif entity_type == "column" and table_name and "." in table_name:
            parts = table_name.split(".", 1)
            eff_schema, eff_table = parts[0], parts[1]
        
        params = {
            "entity_name": eff_entity,
            "entity_type": entity_type,
            "table_name": eff_table or eff_entity,
            "schema_name": eff_schema,
            "db_name": database_name
        }
        
        if entity_type == "database":
            query = """
            MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
                  (e:Database {name: $db_name})
            MATCH (ann:UserAnnotation)-[:DESCRIBES]->(e)
            WHERE ann.entity_type = $entity_type
            RETURN ann.content as content
            LIMIT 1
            """
        elif entity_type == "column" and params.get("table_name"):
            query = """
            MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
                  (db:Database {type: "postgresql"})-[:HAS_SCHEMA]->(s:Schema {name: $schema_name})-[:HAS_TABLE]->
                  (t:Table {name: $table_name})-[:HAS_COLUMN]->(e:Column {name: $entity_name})
            MATCH (ann:UserAnnotation)-[:DESCRIBES]->(e)
            WHERE ann.entity_type = $entity_type AND ann.entity_name = $entity_name
            RETURN ann.content as content
            LIMIT 1
            """
        else:  # table
            query = """
            MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
                  (db:Database {type: "postgresql"})-[:HAS_SCHEMA]->(s:Schema {name: $schema_name})-[:HAS_TABLE]->(e:Table {name: $entity_name})
            MATCH (ann:UserAnnotation)-[:DESCRIBES]->(e)
            WHERE ann.entity_type = $entity_type AND ann.entity_name = $entity_name
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
        natural_language: str = "",
        description: str = "",
        table_name: Optional[str] = None,
        schema_name: Optional[str] = None,
        database_name: Optional[str] = None
    ):
        """
        Add a query example as a QueryExample node linked to the entity.
        Stored in graph for retrieval during SQL generation.
        
        Args:
            entity_type: Type of entity ('table', 'column', 'database')
            entity_name: Name of the entity (table name or column name)
            query: SQL query example
            natural_language: Natural language description of what the query does (for matching)
            description: Optional description of the query
            table_name: Table name (required for columns)
            schema_name: Schema name (optional, default public)
            database_name: Database name
        """
        logger.info(f"Adding query example for {entity_type}: {entity_name}")
        eff_schema = schema_name or "public"
        eff_table = table_name or (entity_name if entity_type == "table" else None)
        nl_text = natural_language or description or query[:80]
        
        db_filter = " WHERE db.name = $db_name" if database_name else ""
        params = {
            "natural_language": nl_text,
            "sql_query": query,
            "description": description or "",
            "entity_type": entity_type,
            "entity_name": entity_name,
            "table_name": eff_table or "",
            "schema_name": eff_schema,
            "db_name": database_name,
        }
        params = {k: v for k, v in params.items() if v is not None}
        
        if entity_type == "database":
            cypher = """
            MATCH (db:Database {name: $db_name})
            CREATE (q:QueryExample {{
                natural_language: $natural_language,
                sql_query: $sql_query,
                description: $description,
                entity_type: 'database',
                entity_name: $db_name,
                created_at: datetime()
            }})
            CREATE (db)-[:HAS_QUERY_EXAMPLE]->(q)
            RETURN q
            """
            if not database_name:
                logger.warning("database_name required for database-level query example")
                return
            params["db_name"] = database_name
        elif entity_type == "table":
            cypher = f"""
            MATCH (db:Database {{type: "postgresql"}})-[:HAS_SCHEMA]->(s:Schema {{name: $schema_name}})-[:HAS_TABLE]->(t:Table {{name: $entity_name}}){db_filter}
            CREATE (q:QueryExample {{
                natural_language: $natural_language,
                sql_query: $sql_query,
                description: $description,
                entity_type: 'table',
                entity_name: $entity_name,
                table_name: $entity_name,
                schema_name: $schema_name,
                created_at: datetime()
            }})
            CREATE (t)-[:HAS_QUERY_EXAMPLE]->(q)
            RETURN q
            """
            params["entity_name"] = entity_name
            if database_name:
                params["db_name"] = database_name
        else:  # column
            cypher = f"""
            MATCH (db:Database {{type: "postgresql"}})-[:HAS_SCHEMA]->(s:Schema {{name: $schema_name}})-[:HAS_TABLE]->(t:Table {{name: $table_name}})-[:HAS_COLUMN]->(c:Column {{name: $entity_name}}){db_filter}
            CREATE (q:QueryExample {{
                natural_language: $natural_language,
                sql_query: $sql_query,
                description: $description,
                entity_type: 'column',
                entity_name: $entity_name,
                table_name: $table_name,
                schema_name: $schema_name,
                created_at: datetime()
            }})
            CREATE (t)-[:HAS_QUERY_EXAMPLE]->(q)
            RETURN q
            """
            params["table_name"] = eff_table
            if database_name:
                params["db_name"] = database_name
            if not eff_table:
                logger.warning("table_name required for column-level query example")
                return
        
        try:
            self.neo4j.execute_query(cypher, params)
            logger.info(f"Query example stored in graph for {entity_type}:{entity_name}")
        except Exception as e:
            logger.error(f"Failed to add query example: {e}")
            raise
    
    def get_query_examples(
        self,
        user_query: str,
        database_name: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict[str, str]]:
        """
        Retrieve query examples from the graph that match the user's natural language query.
        Uses keyword overlap for matching. Returns examples to guide SQL generation.
        
        Args:
            user_query: User's natural language question
            database_name: Database name filter
            limit: Max number of examples to return
        
        Returns:
            List of {natural_language, sql_query, entity_type, entity_name}
        """
        params: Dict[str, Any] = {"limit": limit}
        if database_name:
            params["db_name"] = database_name
            cypher = """
            MATCH (db:Database {type: "postgresql", name: $db_name})-[:HAS_SCHEMA]->(:Schema)-[:HAS_TABLE]->(t:Table)
            OPTIONAL MATCH (t)-[:HAS_QUERY_EXAMPLE]->(q:QueryExample)
            WITH collect(DISTINCT q) as table_examples
            OPTIONAL MATCH (db2:Database {name: $db_name})-[:HAS_QUERY_EXAMPLE]->(q2:QueryExample)
            WITH table_examples + collect(DISTINCT q2) as all_examples
            UNWIND [ex IN all_examples WHERE ex IS NOT NULL] as q
            RETURN q.natural_language as natural_language, q.sql_query as sql_query,
                   q.entity_type as entity_type, q.entity_name as entity_name,
                   q.table_name as table_name, q.description as description
            LIMIT $limit * 2
            """
        else:
            cypher = """
            MATCH (db:Database {type: "postgresql"})-[:HAS_SCHEMA]->(:Schema)-[:HAS_TABLE]->(t:Table)
            OPTIONAL MATCH (t)-[:HAS_QUERY_EXAMPLE]->(q:QueryExample)
            WITH db, collect(DISTINCT q) as examples
            UNWIND [ex IN examples WHERE ex IS NOT NULL] as q
            RETURN q.natural_language as natural_language, q.sql_query as sql_query,
                   q.entity_type as entity_type, q.entity_name as entity_name,
                   q.table_name as table_name, q.description as description
            LIMIT $limit * 2
            """
        
        results = self.neo4j.execute_query(cypher, params)
        if not results:
            return []
        
        # Score by keyword overlap with user query
        query_words = set(user_query.lower().split())
        scored = []
        for r in results:
            nl = (r.get("natural_language") or "").lower()
            nl_words = set(nl.split())
            overlap = len(query_words & nl_words)
            scored.append((overlap, r))
        
        scored.sort(key=lambda x: -x[0])
        selected = [r for _, r in scored[:limit]]
        
        return [
            {
                "natural_language": s.get("natural_language", ""),
                "sql_query": s.get("sql_query", ""),
                "entity_type": s.get("entity_type", "table"),
                "entity_name": s.get("entity_name", ""),
            }
            for s in selected
        ]
    
    def get_query_examples_for_table(self, table_name: str, database_name: str, schema_name: Optional[str] = None) -> List[Dict[str, str]]:
        """Get all query examples linked to a table (for UI display)."""
        eff_schema = schema_name or "public"
        cypher = """
        MATCH (db:Database {name: $db_name})-[:HAS_SCHEMA]->(s:Schema {name: $schema_name})-[:HAS_TABLE]->(t:Table {name: $table_name})
        MATCH (t)-[:HAS_QUERY_EXAMPLE]->(q:QueryExample)
        RETURN q.natural_language as natural_language, q.sql_query as sql_query
        ORDER BY q.created_at DESC
        """
        results = self.neo4j.execute_query(cypher, {
            "db_name": database_name,
            "schema_name": eff_schema,
            "table_name": table_name
        })
        return [{"natural_language": r.get("natural_language", ""), "sql_query": r.get("sql_query", "")} for r in (results or [])]
    
    def _get_node_description(self, entity_type: str, entity_name: str, table_name: Optional[str], database_name: Optional[str]) -> str:
        """Get current description from node."""
        params = {"entity_name": entity_name, "db_name": database_name}
        
        if entity_type == "database":
            query = "MATCH (e:Database {name: $db_name}) RETURN e.description as description"
        elif entity_type == "column":
            query = """
            MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
                  (db:Database {type: "postgresql"})-[:HAS_SCHEMA]->(:Schema)-[:HAS_TABLE]->
                  (t:Table {name: $table_name})-[:HAS_COLUMN]->(e:Column {name: $entity_name})
            RETURN e.description as description
            """
            params["table_name"] = table_name
        else:  # table
            query = """
            MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
                  (db:Database {type: "postgresql"})-[:HAS_SCHEMA]->(:Schema)-[:HAS_TABLE]->(e:Table {name: $entity_name})
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
            MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
                  (e:Database {name: $db_name})
            SET e.description = $description
            RETURN e
            """
        elif entity_type == "column":
            query = """
            MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
                  (db:Database {type: "postgresql"})-[:HAS_SCHEMA]->(:Schema)-[:HAS_TABLE]->
                  (t:Table {name: $table_name})-[:HAS_COLUMN]->(e:Column {name: $entity_name})
            SET e.description = $description
            RETURN e
            """
            params["table_name"] = table_name
        else:  # table
            query = """
            MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->
                  (db:Database {type: "postgresql"})-[:HAS_SCHEMA]->(:Schema)-[:HAS_TABLE]->(e:Table {name: $entity_name})
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
        
        # Get all tables with their columns for the specified database
        if database_name:
            query = """
            MATCH (db:Database {name: $db_name})-[:HAS_SCHEMA]->(s:Schema)-[:HAS_TABLE]->(t:Table)
            OPTIONAL MATCH (t)-[:HAS_COLUMN]->(c:Column)
            OPTIONAL MATCH (ann:UserAnnotation)-[:DESCRIBES]->(t)
            WITH db, t, s, COLLECT(DISTINCT c) as columns, COLLECT(DISTINCT ann.content) as table_descriptions
            ORDER BY s.name, t.name
            RETURN db.name as db_name, t.name as table_name, t.schema_name as schema_name,
                   columns, table_descriptions
            """
            results = self.neo4j.execute_query(query, {"db_name": database_name})
        else:
            # If no database name specified, get from all PostgreSQL databases
            query = """
            MATCH (db:Database {type: "postgresql"})-[:HAS_SCHEMA]->(s:Schema)-[:HAS_TABLE]->(t:Table)
            OPTIONAL MATCH (t)-[:HAS_COLUMN]->(c:Column)
            OPTIONAL MATCH (ann:UserAnnotation)-[:DESCRIBES]->(t)
            WITH db, t, s, COLLECT(DISTINCT c) as columns, COLLECT(DISTINCT ann.content) as table_descriptions
            ORDER BY db.name, s.name, t.name
            RETURN db.name as db_name, t.name as table_name, t.schema_name as schema_name,
                   columns, table_descriptions
            """
            results = self.neo4j.execute_query(query, {})
        
        if not results:
            return "No database schema found in knowledge graph."
        
        summary_parts = []
        db_name = results[0].get("db_name", "Unknown")
        summary_parts.append(f"# Database Summary: {db_name}\n")
        
        for record in results:
            table_name = record.get("table_name")
            schema_name = record.get("schema_name", "public")
            columns = record.get("columns", [])
            descriptions = record.get("table_descriptions", [])
            
            table_label = f'"{schema_name}".{table_name}' if schema_name != "public" else table_name
            summary_parts.append(f"\n## Table: {table_label}")
            
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
        if database_name:
            table_query = """
            MATCH (db:Database {name: $db_name})-[:HAS_SCHEMA]->(:Schema)-[:HAS_TABLE]->(t:Table)
            WHERE t.description IS NULL OR t.description = ""
            OPTIONAL MATCH (ann:UserAnnotation)-[:DESCRIBES]->(t)
            WHERE ann IS NULL
            RETURN t.name as table_name, db.name as db_name
            ORDER BY t.name
            """
            column_query = """
            MATCH (db:Database {name: $db_name})-[:HAS_SCHEMA]->(:Schema)-[:HAS_TABLE]->
                  (t:Table)-[:HAS_COLUMN]->(c:Column)
            WHERE c.description IS NULL OR c.description = ""
            OPTIONAL MATCH (ann:UserAnnotation)-[:DESCRIBES]->(c)
            WHERE ann IS NULL
            RETURN t.name as table_name, c.name as column_name, c.type as column_type,
                   db.name as db_name
            ORDER BY t.name, c.name
            """
            tables = self.neo4j.execute_query(table_query, {"db_name": database_name})
            columns = self.neo4j.execute_query(column_query, {"db_name": database_name})
        else:
            # If no database name specified, search all databases
            table_query = """
            MATCH (db:Database)-[:HAS_SCHEMA]->(:Schema)-[:HAS_TABLE]->(t:Table)
            WHERE t.description IS NULL OR t.description = ""
            OPTIONAL MATCH (ann:UserAnnotation)-[:DESCRIBES]->(t)
            WHERE ann IS NULL
            RETURN t.name as table_name, db.name as db_name
            ORDER BY db.name, t.name
            """
            column_query = """
            MATCH (db:Database)-[:HAS_SCHEMA]->(:Schema)-[:HAS_TABLE]->
                  (t:Table)-[:HAS_COLUMN]->(c:Column)
            WHERE c.description IS NULL OR c.description = ""
            OPTIONAL MATCH (ann:UserAnnotation)-[:DESCRIBES]->(c)
            WHERE ann IS NULL
            RETURN t.name as table_name, c.name as column_name, c.type as column_type,
                   db.name as db_name
            ORDER BY db.name, t.name, c.name
            """
            tables = self.neo4j.execute_query(table_query, {})
            columns = self.neo4j.execute_query(column_query, {})
        
        return {
            "tables": tables,
            "columns": columns
        }
    
    def get_all_databases(self) -> List[Dict[str, Any]]:
        """
        Get all databases from the knowledge graph.
        
        Returns:
            List of dictionaries with database information (name, type, description, host, port)
        """
        logger.info("Retrieving all databases from knowledge graph")
        
        query = """
        MATCH (root:Databases {name: "databases"})-[:HAS_DATABASE]->(db:Database)
        RETURN db.name as name, db.type as type, db.description as description,
               db.host as host, db.port as port
        ORDER BY db.name
        """
        
        results = self.neo4j.execute_query(query, {})
        databases = []
        for record in results:
            databases.append({
                "name": record.get("name", ""),
                "type": record.get("type", ""),
                "description": record.get("description", ""),
                "host": record.get("host", ""),
                "port": record.get("port", 0)
            })
        
        logger.info(f"Found {len(databases)} database(s) in knowledge graph")
        return databases
    
    def get_tables_for_database(self, database_name: str) -> List[Dict[str, Any]]:
        """
        Get all tables for a PostgreSQL database (across all schemas).
        
        Returns:
            List of {name, schema_name, description, column_count}
        """
        logger.info(f"Retrieving tables for database: {database_name}")
        
        query = """
        MATCH (db:Database {name: $db_name})-[:HAS_SCHEMA]->(s:Schema)-[:HAS_TABLE]->(t:Table)
        OPTIONAL MATCH (t)-[:HAS_COLUMN]->(c:Column)
        WITH t, s, count(c) as column_count
        RETURN t.name as name, s.name as schema_name, t.description as description, column_count
        ORDER BY s.name, t.name
        """
        
        results = self.neo4j.execute_query(query, {"db_name": database_name})
        tables = []
        for record in results:
            tables.append({
                "name": record.get("name", ""),
                "schema_name": record.get("schema_name", "public"),
                "description": record.get("description", ""),
                "column_count": record.get("column_count", 0)
            })
        
        logger.info(f"Found {len(tables)} table(s) for database {database_name}")
        return tables
    
    def get_columns_for_table(
        self, table_name: str, database_name: str, schema_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all columns (attributes) for a table.
        
        Args:
            table_name: Name of the table (supports "schema.table" format)
            database_name: Name of the database
            schema_name: Schema name (optional; parsed from table_name if "schema.table" format)
        """
        if "." in table_name and not schema_name:
            parts = table_name.split(".", 1)
            schema_name, table_name = parts[0], parts[1]
        logger.info(f"Retrieving columns for table: {table_name} in database: {database_name}")
        
        if schema_name:
            query = """
            MATCH (db:Database {name: $db_name})-[:HAS_SCHEMA]->(s:Schema {name: $schema_name})-[:HAS_TABLE]->(t:Table {name: $table_name})
            MATCH (t)-[:HAS_COLUMN]->(c:Column)
            RETURN c.name as name, c.type as type, c.description as description, c.nullable as nullable
            ORDER BY c.name
            """
            params = {"db_name": database_name, "table_name": table_name, "schema_name": schema_name}
        else:
            # No schema specified - use first matching table (e.g. public schema)
            query = """
            MATCH (db:Database {name: $db_name})-[:HAS_SCHEMA]->(s:Schema)-[:HAS_TABLE]->(t:Table {name: $table_name})
            WITH t LIMIT 1
            MATCH (t)-[:HAS_COLUMN]->(c:Column)
            RETURN c.name as name, c.type as type, c.description as description, c.nullable as nullable
            ORDER BY c.name
            """
            params = {"db_name": database_name, "table_name": table_name}
        
        results = self.neo4j.execute_query(query, params)
        columns = []
        for record in results:
            columns.append({
                "name": record.get("name", ""),
                "type": record.get("type", ""),
                "description": record.get("description", ""),
                "nullable": record.get("nullable", False)
            })
        
        logger.info(f"Found {len(columns)} column(s) for table {table_name}")
        return columns
    
    def get_collections_for_database(self, database_name: str) -> List[Dict[str, Any]]:
        """
        Get all collections for a MongoDB database.
        
        Args:
            database_name: Name of the database
            
        Returns:
            List of dictionaries with collection information (name, description, field_count, document_count)
        """
        logger.info(f"Retrieving collections for database: {database_name}")
        
        query = """
        MATCH (db:Database {name: $db_name})-[:HAS_COLLECTION]->(coll:Collection)
        OPTIONAL MATCH (coll)-[:HAS_FIELD]->(f:Field)
        WITH coll, count(f) as field_count
        RETURN coll.name as name, coll.description as description, 
               coll.document_count as document_count, field_count
        ORDER BY coll.name
        """
        
        results = self.neo4j.execute_query(query, {"db_name": database_name})
        collections = []
        for record in results:
            collections.append({
                "name": record.get("name", ""),
                "description": record.get("description", ""),
                "document_count": record.get("document_count", 0),
                "field_count": record.get("field_count", 0)
            })
        
        logger.info(f"Found {len(collections)} collection(s) for database {database_name}")
        return collections
    
    def get_fields_for_collection(self, collection_name: str, database_name: str) -> List[Dict[str, Any]]:
        """
        Get all fields for a MongoDB collection.
        
        Args:
            collection_name: Name of the collection
            database_name: Name of the database
            
        Returns:
            List of dictionaries with field information (name, types, description, nullable, example)
        """
        logger.info(f"Retrieving fields for collection: {collection_name} in database: {database_name}")
        
        query = """
        MATCH (db:Database {name: $db_name})-[:HAS_COLLECTION]->(coll:Collection {name: $coll_name})
        MATCH (coll)-[:HAS_FIELD]->(f:Field)
        RETURN f.name as name, f.types as types, f.description as description,
               f.nullable as nullable, f.example as example
        ORDER BY f.name
        """
        
        results = self.neo4j.execute_query(query, {
            "db_name": database_name,
            "coll_name": collection_name
        })
        fields = []
        for record in results:
            types = record.get("types", [])
            if isinstance(types, str):
                types = [types]
            fields.append({
                "name": record.get("name", ""),
                "types": types,
                "description": record.get("description", ""),
                "nullable": record.get("nullable", False),
                "example": record.get("example", "")
            })
        
        logger.info(f"Found {len(fields)} field(s) for collection {collection_name}")
        return fields

