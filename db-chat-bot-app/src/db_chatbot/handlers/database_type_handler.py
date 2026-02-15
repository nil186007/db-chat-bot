"""
Handler for parsing database type descriptions from user messages.
Supports SQL databases (PostgreSQL) only.
"""
import re
from typing import Optional, Dict
from db_chatbot.config.settings import get_logger

logger = get_logger(__name__)


class DatabaseTypeHandler:
    """Handler for parsing database type descriptions (SQL databases)."""

    def is_database_type_description(self, message: str) -> bool:
        """
        Check if the message contains a database type description.
        Examples: "PostgreSQL stores: products, orders", "Postgres database has: sales data"
        """
        message_lower = message.lower()
        patterns = [
            r'(postgresql|postgres|pg)\s+(stores|contains|has|holds|manages|includes)',
            r'(postgresql|postgres|pg)\s+database\s+(stores|contains|has|holds|manages|includes)',
        ]
        return any(re.search(pattern, message_lower) for pattern in patterns)

    def parse_database_type_description(self, message: str) -> Optional[Dict]:
        """Parse database type description from message."""
        message_lower = message.lower()
        db_type = None
        if re.search(r'(postgresql|postgres|pg)', message_lower):
            db_type = "postgresql"
        
        if not db_type:
            return None
        
        # Extract description after keywords
        patterns = [
            r'(?:stores|contains|has|holds|manages|includes)[\s:]+(.+)',
            r'(?:database\s+)?(?:stores|contains|has|holds|manages|includes)[\s:]+(.+)',
        ]
        
        description = None
        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                description = match.group(1).strip()
                # Remove trailing punctuation if it's just a period
                if description.endswith('.') and not description.endswith('...'):
                    description = description[:-1]
                break
        
        if not description:
            match = re.search(
                r'(?:postgresql|postgres|pg)[\s:]+(.+)',
                message,
                re.IGNORECASE
            )
            if match:
                description = match.group(1).strip()
                # Remove common prefixes
                description = re.sub(
                    r'^(stores|contains|has|holds|manages|includes|database)[\s:]+',
                    '',
                    description,
                    flags=re.IGNORECASE
                ).strip()
        
        if description and len(description) > 3:
            return {
                "db_type": db_type,
                "description": description
            }
        
        return None
