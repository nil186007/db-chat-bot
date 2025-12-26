"""
Handler for parsing and processing user annotations about database schema.
"""
import re
from typing import Optional, Dict, Tuple
from db_chatbot.config.settings import get_logger

logger = get_logger(__name__)


class AnnotationHandler:
    """Handles parsing and extraction of annotations from user chat messages."""
    
    # Patterns for detecting annotation statements
    ANNOTATION_PATTERNS = [
        # Table annotations: "The 'orders' table contains..."
        r"the\s+['\"]?(\w+)['\"]?\s+table\s+(?:contains|stores|has|is|represents|describes|means)",
        # Column annotations: "The 'orders.status' column..." or "The status column in orders table..."
        r"the\s+['\"]?(\w+)['\"]?\s+column\s+(?:in|of|for)?\s*(?:the\s+)?['\"]?(\w+)['\"]?\s+table",
        r"the\s+['\"]?(\w+\.\w+)['\"]?\s+column",
        # Database annotations: "The database stores..."
        r"the\s+database\s+(?:contains|stores|has|is)",
    ]
    
    def __init__(self):
        """Initialize annotation handler."""
        logger.debug("AnnotationHandler initialized")
    
    def is_annotation(self, message: str) -> bool:
        """
        Check if a message appears to be an annotation.
        
        Args:
            message: User message
        
        Returns:
            True if message appears to be an annotation
        """
        message_lower = message.lower().strip()
        
        # Check for annotation keywords
        annotation_keywords = [
            "the table", "the column", "the database",
            "this table", "this column", "this database",
            "table contains", "table stores", "column stores",
            "table represents", "table is", "column is"
        ]
        
        has_keyword = any(keyword in message_lower for keyword in annotation_keywords)
        
        # Additional check: if message doesn't look like a query
        query_keywords = ["show", "list", "find", "get", "count", "how many", "what", "which", "select"]
        is_query = any(keyword in message_lower for keyword in query_keywords)
        
        # If it has annotation keywords but not query keywords, likely an annotation
        return has_keyword and not is_query
    
    def parse_annotation(self, message: str) -> Optional[Dict[str, str]]:
        """
        Parse annotation from user message.
        
        Args:
            message: User message containing annotation
        
        Returns:
            Dictionary with annotation details or None if parsing fails
            {
                "entity_type": "table" | "column" | "database",
                "entity_name": str,
                "table_name": str (for columns),
                "content": str
            }
        """
        message_lower = message.lower().strip()
        
        # Try to parse table annotation
        table_match = re.search(r"the\s+['\"]?(\w+)['\"]?\s+table\s+(?:contains|stores|has|is|represents|describes|means)\s+(.+)", message_lower)
        if table_match:
            table_name = table_match.group(1)
            content = message[message_lower.find(table_match.group(2)):].strip()
            return {
                "entity_type": "table",
                "entity_name": table_name,
                "table_name": None,
                "content": content
            }
        
        # Try to parse column annotation with table.table format
        col_dot_match = re.search(r"the\s+['\"]?(\w+)\.(\w+)['\"]?\s+column\s+(?:stores|contains|is|represents)\s+(.+)", message_lower)
        if col_dot_match:
            table_name = col_dot_match.group(1)
            col_name = col_dot_match.group(2)
            content = message[message_lower.find(col_dot_match.group(3)):].strip()
            return {
                "entity_type": "column",
                "entity_name": col_name,
                "table_name": table_name,
                "content": content
            }
        
        # Try to parse column annotation with "column in table" format
        col_in_table_match = re.search(r"the\s+['\"]?(\w+)['\"]?\s+column\s+(?:in|of|for)\s+(?:the\s+)?['\"]?(\w+)['\"]?\s+table\s+(?:stores|contains|is|represents)\s+(.+)", message_lower)
        if col_in_table_match:
            col_name = col_in_table_match.group(1)
            table_name = col_in_table_match.group(2)
            content = message[message_lower.find(col_in_table_match.group(3)):].strip()
            return {
                "entity_type": "column",
                "entity_name": col_name,
                "table_name": table_name,
                "content": content
            }
        
        # Try to parse database annotation
        db_match = re.search(r"the\s+database\s+(?:contains|stores|has|is|represents)\s+(.+)", message_lower)
        if db_match:
            content = message[message_lower.find(db_match.group(1)):].strip()
            return {
                "entity_type": "database",
                "entity_name": "",  # Will be filled from context
                "table_name": None,
                "content": content
            }
        
        # Fallback: try to extract using LLM if available (future enhancement)
        logger.warning(f"Could not parse annotation from message: {message[:50]}...")
        return None
    
    def extract_annotation_content(self, message: str, entity_type: str, entity_name: str) -> str:
        """
        Extract the descriptive content from an annotation message.
        
        Args:
            message: Full annotation message
            entity_type: Type of entity
            entity_name: Name of entity
        
        Returns:
            Extracted content/description
        """
        message_lower = message.lower()
        entity_lower = entity_name.lower()
        
        # Try to find content after entity mention
        patterns = [
            f"the {entity_lower} {entity_type} (?:contains|stores|has|is|represents|describes|means) (.+)",
            f"the {entity_lower} (?:contains|stores|has|is|represents) (.+)",
            f"{entity_lower} (?:contains|stores|has|is|represents) (.+)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message_lower)
            if match:
                content_start = message_lower.find(match.group(1))
                if content_start > 0:
                    return message[content_start:].strip()
        
        # Fallback: return message as-is
        return message.strip()

