"""
Handler for parsing and storing query examples provided by users.
"""
import re
from typing import Optional, Dict, List
from db_chatbot.config.settings import get_logger

logger = get_logger(__name__)


class QueryExampleHandler:
    """Handles parsing and extraction of query examples from user chat messages."""
    
    # Patterns for detecting query examples
    QUERY_EXAMPLE_PATTERNS = [
        r"example\s+query\s+(?:for|about|on)\s+(?:the\s+)?['\"]?(\w+)['\"]?\s*(?:table|column)?",
        r"query\s+example\s+(?:for|about|on)\s+(?:the\s+)?['\"]?(\w+)['\"]?\s*(?:table|column)?",
        r"sample\s+query\s+(?:for|about|on)\s+(?:the\s+)?['\"]?(\w+)['\"]?\s*(?:table|column)?",
        r"here['\"]?s\s+(?:an\s+)?(?:example|sample)\s+(?:query|sql)\s+(?:for|about|on)",
    ]
    
    # SQL query pattern (starts with SELECT, contains SQL keywords)
    SQL_PATTERN = r"(?:SELECT|select)\s+.+?(?:FROM|from)\s+\w+"
    
    def __init__(self):
        """Initialize query example handler."""
        logger.debug("QueryExampleHandler initialized")
    
    def is_query_example(self, message: str) -> bool:
        """
        Check if a message contains a query example.
        
        Args:
            message: User message
        
        Returns:
            True if message appears to contain a query example
        """
        message_lower = message.lower().strip()
        
        # Check for query example keywords
        has_keyword = any(
            keyword in message_lower 
            for keyword in ["example query", "query example", "sample query", "here's an example", "example sql"]
        )
        
        # Check if message contains SQL
        has_sql = bool(re.search(self.SQL_PATTERN, message, re.IGNORECASE | re.DOTALL))
        
        return has_keyword or has_sql
    
    def parse_query_example(self, message: str) -> Optional[Dict[str, str]]:
        """
        Parse query example from user message.
        
        Args:
            message: User message containing query example
        
        Returns:
            Dictionary with query example details or None if parsing fails
            {
                "entity_type": "table" | "column" | "database",
                "entity_name": str,
                "table_name": str (for columns),
                "query": str (the SQL query),
                "description": str (optional description)
            }
        """
        # Extract SQL query
        sql_match = re.search(r"(SELECT\s+.+?)(?:;|$)", message, re.IGNORECASE | re.DOTALL)
        if not sql_match:
            # Try without SELECT requirement
            sql_match = re.search(r"((?:SELECT|INSERT|UPDATE|DELETE)\s+.+?)(?:;|$)", message, re.IGNORECASE | re.DOTALL)
        
        if not sql_match:
            logger.warning("No SQL query found in message")
            return None
        
        query = sql_match.group(1).strip()
        
        # Extract entity information
        message_lower = message.lower()
        
        # Try to find table name
        table_match = re.search(r"(?:for|about|on)\s+(?:the\s+)?['\"]?(\w+)['\"]?\s+table", message_lower)
        if table_match:
            table_name = table_match.group(1)
            return {
                "entity_type": "table",
                "entity_name": table_name,
                "table_name": None,
                "query": query,
                "description": self._extract_description(message, query)
            }
        
        # Try to find column reference
        col_match = re.search(r"(?:for|about|on)\s+(?:the\s+)?['\"]?(\w+)['\"]?\s+column\s+(?:in|of)\s+(?:the\s+)?['\"]?(\w+)['\"]?\s+table", message_lower)
        if col_match:
            col_name = col_match.group(1)
            table_name = col_match.group(2)
            return {
                "entity_type": "column",
                "entity_name": col_name,
                "table_name": table_name,
                "query": query,
                "description": self._extract_description(message, query)
            }
        
        # Try to find table.column format
        table_col_match = re.search(r"(?:for|about|on)\s+(?:the\s+)?['\"]?(\w+)\.(\w+)['\"]?", message_lower)
        if table_col_match:
            table_name = table_col_match.group(1)
            col_name = table_col_match.group(2)
            return {
                "entity_type": "column",
                "entity_name": col_name,
                "table_name": table_name,
                "query": query,
                "description": self._extract_description(message, query)
            }
        
        # Default to database level
        return {
            "entity_type": "database",
            "entity_name": "",
            "table_name": None,
            "query": query,
            "description": self._extract_description(message, query)
        }
    
    def _extract_description(self, message: str, query: str) -> str:
        """Extract description text from message, excluding the query."""
        # Remove the query from message
        query_start = message.upper().find(query.upper()[:20])
        if query_start > 0:
            description = message[:query_start].strip()
            # Clean up common prefixes
            description = re.sub(r"^(?:here['\"]?s\s+)?(?:an\s+)?(?:example|sample)\s+(?:query|sql)\s*:?\s*", "", description, flags=re.IGNORECASE)
            return description.strip()
        return ""
