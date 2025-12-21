"""
RAG (Retrieval Augmented Generation) module for database schema.
Treats database schema as a knowledge base for retrieval.
"""
from typing import Dict, Optional, List
from db_chatbot.config.settings import get_logger

logger = get_logger(__name__)


class SchemaRAG:
    """
    Schema RAG - Manages database schema as a retrievable knowledge base.
    Provides methods to store, retrieve, and format schema information for LLM use.
    """
    
    def __init__(self):
        """Initialize Schema RAG."""
        self.schema_info: Optional[Dict] = None
        logger.info("SchemaRAG initialized")
    
    def load_schema(self, schema_info: Dict):
        """
        Load schema information into RAG storage.
        
        Args:
            schema_info: Schema dictionary from PostgresClient.fetch_schema()
        """
        logger.info(f"Loading schema into RAG: {len(schema_info.get('tables', []))} table(s)")
        self.schema_info = schema_info
        logger.debug("Schema loaded successfully into RAG")
    
    def get_schema(self) -> Optional[Dict]:
        """
        Retrieve the stored schema information.
        
        Returns:
            Schema dictionary or None if not loaded
        """
        if self.schema_info is None:
            logger.warning("Schema not loaded in RAG")
            return None
        
        logger.debug("Retrieving schema from RAG")
        return self.schema_info
    
    def get_table_info(self, table_name: str) -> Optional[Dict]:
        """
        Retrieve information about a specific table.
        
        Args:
            table_name: Name of the table to retrieve
        
        Returns:
            Table information dictionary or None if not found
        """
        if not self.schema_info:
            logger.warning("Schema not loaded in RAG")
            return None
        
        for table in self.schema_info.get("tables", []):
            if table["name"].lower() == table_name.lower():
                logger.debug(f"Retrieved table info for: {table_name}")
                return table
        
        logger.warning(f"Table '{table_name}' not found in schema")
        return None
    
    def get_relevant_tables(self, query: str) -> List[Dict]:
        """
        Retrieve tables that might be relevant to a query (simple keyword matching).
        This can be enhanced with semantic search in the future.
        
        Args:
            query: User query string
        
        Returns:
            List of relevant table dictionaries
        """
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
    
    def format_schema_for_context(self, table_names: Optional[List[str]] = None) -> str:
        """
        Format schema information for LLM context.
        
        Args:
            table_names: Optional list of specific table names to include. If None, includes all tables.
        
        Returns:
            Formatted schema string
        """
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
    
    def clear(self):
        """Clear the stored schema."""
        logger.info("Clearing schema from RAG")
        self.schema_info = None

