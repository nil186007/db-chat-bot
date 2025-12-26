"""
RAG (Retrieval Augmented Generation) module for database schema.
Uses KnowledgeGraphRAG for persistent storage and retrieval.
"""
from typing import Dict, Optional, List
from db_chatbot.config.settings import get_logger
from db_chatbot.rag.knowledge_graph_rag import KnowledgeGraphRAG

logger = get_logger(__name__)


class SchemaRAG:
    """
    Schema RAG - Manages database schema as a retrievable knowledge base.
    Uses KnowledgeGraphRAG internally for persistent graph storage.
    Provides backward-compatible interface for existing code.
    """
    
    def __init__(self, knowledge_graph_rag: Optional[KnowledgeGraphRAG] = None):
        """
        Initialize Schema RAG.
        
        Args:
            knowledge_graph_rag: Optional KnowledgeGraphRAG instance. If None, falls back to in-memory storage.
        """
        self.knowledge_graph_rag = knowledge_graph_rag
        self.schema_info: Optional[Dict] = None  # Fallback in-memory storage
        self.database_name: Optional[str] = None
        logger.info("SchemaRAG initialized" + (" with KnowledgeGraphRAG" if knowledge_graph_rag else " (in-memory)"))
    
    def load_schema(self, schema_info: Dict, database_name: Optional[str] = None, host: Optional[str] = None, port: Optional[int] = None):
        """
        Load schema information into RAG storage.
        
        Args:
            schema_info: Schema dictionary from PostgresClient.fetch_schema()
            database_name: Database name (required if using KnowledgeGraphRAG)
            host: Database host (required if using KnowledgeGraphRAG)
            port: Database port (required if using KnowledgeGraphRAG)
        """
        logger.info(f"Loading schema into RAG: {len(schema_info.get('tables', []))} table(s)")
        
        # Store in-memory for backward compatibility
        self.schema_info = schema_info
        self.database_name = database_name
        
        # Also store in knowledge graph if available
        if self.knowledge_graph_rag and database_name and host and port:
            try:
                self.knowledge_graph_rag.build_graph_from_schema(
                    schema_info=schema_info,
                    database_name=database_name,
                    host=host,
                    port=port
                )
                logger.info("Schema loaded into knowledge graph")
            except Exception as e:
                logger.error(f"Failed to load schema into knowledge graph: {e}")
        else:
            logger.debug("KnowledgeGraphRAG not available, using in-memory storage only")
    
    def get_schema(self) -> Optional[Dict]:
        """
        Retrieve the stored schema information.
        
        Returns:
            Schema dictionary or None if not loaded
        """
        # Return in-memory schema (backward compatibility)
        if self.schema_info:
            logger.debug("Retrieving schema from in-memory storage")
            return self.schema_info
        
        logger.warning("Schema not loaded in RAG")
        return None
    
    def get_table_info(self, table_name: str) -> Optional[Dict]:
        """
        Retrieve information about a specific table.
        
        Args:
            table_name: Name of the table to retrieve
        
        Returns:
            Table information dictionary or None if not found
        """
        # Try knowledge graph first
        if self.knowledge_graph_rag and self.database_name:
            try:
                graph_info = self.knowledge_graph_rag.get_table_info(table_name, self.database_name)
                if graph_info:
                    logger.debug(f"Retrieved table info from knowledge graph: {table_name}")
                    return graph_info
            except Exception as e:
                logger.warning(f"Failed to retrieve from knowledge graph: {e}")
        
        # Fallback to in-memory
        if not self.schema_info:
            logger.warning("Schema not loaded in RAG")
            return None
        
        for table in self.schema_info.get("tables", []):
            if table["name"].lower() == table_name.lower():
                logger.debug(f"Retrieved table info from memory: {table_name}")
                return table
        
        logger.warning(f"Table '{table_name}' not found in schema")
        return None
    
    def get_relevant_tables(self, query: str) -> List[Dict]:
        """
        Retrieve tables that might be relevant to a query.
        
        Args:
            query: User query string
        
        Returns:
            List of relevant table dictionaries
        """
        # Extract keywords from query
        keywords = query.lower().split()
        
        # Try knowledge graph first
        if self.knowledge_graph_rag and self.database_name:
            try:
                context = self.knowledge_graph_rag.get_schema_context(
                    query_keywords=keywords,
                    database_name=self.database_name
                )
                # Parse context to extract table info (simplified)
                # In a real implementation, you'd parse the formatted context
                logger.debug(f"Retrieved relevant tables from knowledge graph for query")
            except Exception as e:
                logger.warning(f"Failed to retrieve from knowledge graph: {e}")
        
        # Fallback to in-memory search
        if not self.schema_info:
            logger.warning("Schema not loaded in RAG")
            return []
        
        query_lower = query.lower()
        relevant_tables = []
        
        for table in self.schema_info.get("tables", []):
            table_name_lower = table["name"].lower()
            
            # Check if table name or column names match query keywords
            if table_name_lower in query_lower:
                relevant_tables.append(table)
                continue
            
            # Check column names
            for col in table.get("columns", []):
                if col["name"].lower() in query_lower:
                    relevant_tables.append(table)
                    break
        
        logger.debug(f"Found {len(relevant_tables)} relevant table(s) for query")
        return relevant_tables
    
    def format_schema_for_context(
        self, 
        table_names: Optional[List[str]] = None,
        query_keywords: Optional[List[str]] = None
    ) -> str:
        """
        Format schema information for LLM context.
        Uses knowledge graph if available for enhanced context with annotations.
        
        Args:
            table_names: Optional list of specific table names to include. If None, includes all tables.
            query_keywords: Optional keywords for context retrieval
        
        Returns:
            Formatted schema string
        """
        # Try knowledge graph first for enhanced context
        if self.knowledge_graph_rag and self.database_name:
            try:
                context = self.knowledge_graph_rag.get_schema_context(
                    table_names=table_names,
                    query_keywords=query_keywords,
                    database_name=self.database_name
                )
                if context and context != "Database Schema:\n\n":
                    logger.debug("Retrieved schema context from knowledge graph")
                    return context
            except Exception as e:
                logger.warning(f"Failed to retrieve from knowledge graph: {e}")
        
        # Fallback to in-memory formatting
        if not self.schema_info:
            logger.warning("Schema not loaded in RAG")
            return "No schema information available."
        
        schema_text = "Database Schema:\n\n"
        tables_to_include = []
        
        if table_names:
            # Include only specified tables
            for table_name in table_names:
                table_info = self.get_table_info(table_name)
                if table_info:
                    tables_to_include.append(table_info)
        else:
            # Include all tables
            tables_to_include = self.schema_info.get("tables", [])
        
        for table in tables_to_include:
            schema_text += f"Table: {table['name']}\n"
            schema_text += "Columns:\n"
            
            for col in table["columns"]:
                nullable = "NULL" if col["nullable"] else "NOT NULL"
                max_len = f"({col['max_length']})" if col["max_length"] else ""
                default = f" DEFAULT {col['default']}" if col["default"] else ""
                schema_text += f"  - {col['name']}: {col['type']}{max_len} {nullable}{default}\n"
            
            if table.get("primary_keys"):
                schema_text += f"Primary Keys: {', '.join(table['primary_keys'])}\n"
            
            if table.get("foreign_keys"):
                schema_text += "Foreign Keys:\n"
                for fk in table["foreign_keys"]:
                    schema_text += f"  - {fk['column']} -> {fk['references_table']}.{fk['references_column']}\n"
            
            schema_text += "\n"
        
        logger.debug(f"Formatted schema context: {len(schema_text)} characters for {len(tables_to_include)} table(s)")
        return schema_text
    
    def add_annotation(
        self,
        entity_type: str,
        entity_name: str,
        content: str,
        table_name: Optional[str] = None
    ):
        """
        Add user annotation to the schema.
        
        Args:
            entity_type: Type of entity ('table', 'column', 'database')
            entity_name: Name of the entity
            content: Annotation content
            table_name: Table name (required for column annotations)
        """
        if self.knowledge_graph_rag and self.database_name:
            try:
                self.knowledge_graph_rag.add_annotation(
                    entity_type=entity_type,
                    entity_name=entity_name,
                    table_name=table_name,
                    content=content,
                    database_name=self.database_name
                )
                logger.info(f"Annotation added to knowledge graph: {entity_type}:{entity_name}")
            except Exception as e:
                logger.error(f"Failed to add annotation to knowledge graph: {e}")
        else:
            logger.warning("KnowledgeGraphRAG not available, annotation not stored")
    
    def get_annotation(
        self,
        entity_type: str,
        entity_name: str,
        table_name: Optional[str] = None
    ) -> Optional[str]:
        """
        Get annotation content for a specific entity.
        
        Args:
            entity_type: Type of entity ('table', 'column', 'database')
            entity_name: Name of the entity
            table_name: Table name (required for columns)
        
        Returns:
            Annotation content string or None if not found
        """
        if self.knowledge_graph_rag and self.database_name:
            try:
                return self.knowledge_graph_rag.get_annotation(
                    entity_type=entity_type,
                    entity_name=entity_name,
                    table_name=table_name,
                    database_name=self.database_name
                )
            except Exception as e:
                logger.error(f"Failed to get annotation from knowledge graph: {e}")
                return None
        return None
    
    def clear(self):
        """Clear the stored schema."""
        logger.info("Clearing schema from RAG")
        self.schema_info = None
        if self.knowledge_graph_rag and self.database_name:
            try:
                self.knowledge_graph_rag.clear_database_graph(self.database_name)
            except Exception as e:
                logger.error(f"Failed to clear knowledge graph: {e}")
