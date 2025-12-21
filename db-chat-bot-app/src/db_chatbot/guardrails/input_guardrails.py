"""
Input guardrails for SQL validation and security checks.
"""
import re
import sqlparse
from sqlparse.sql import Statement, TokenList
from sqlparse.tokens import Keyword, DML
from typing import Tuple, Optional
from db_chatbot.config.settings import get_logger

logger = get_logger(__name__)


class InputGuardrails:
    """Validates SQL queries for security and compliance (input guardrails)."""
    
    # Dangerous SQL keywords that should not be allowed
    FORBIDDEN_KEYWORDS = {
        'DROP', 'DELETE', 'INSERT', 'UPDATE', 'TRUNCATE', 'ALTER',
        'CREATE', 'GRANT', 'REVOKE', 'EXEC', 'EXECUTE', 'CALL'
    }
    
    # SQL injection patterns
    SQL_INJECTION_PATTERNS = [
        r'--',  # SQL comment
        r'/\*.*?\*/',  # Multi-line comment
        r'union.*select',  # Union injection
        r';.*DROP',  # Multiple statements with DROP
        r';.*DELETE',  # Multiple statements with DELETE
        r'xp_',  # SQL Server extended procedures
        r'sp_',  # SQL Server stored procedures
        r'exec\s*\(',  # Execution
        r'0x[0-9a-f]+',  # Hex encoded strings
    ]
    
    @staticmethod
    def validate_select_only(query: str) -> Tuple[bool, Optional[str]]:
        """
        Validate that the query is a SELECT statement only.
        
        Args:
            query: SQL query string
        
        Returns:
            Tuple of (is_valid: bool, error_message: str or None)
        """
        logger.debug(f"Validating query for SELECT-only restriction: {query[:100]}...")
        
        try:
            # Parse the SQL
            parsed = sqlparse.parse(query)
            
            if not parsed:
                logger.warning("Empty SQL query")
                return False, "Empty SQL query"
            
            # Check each statement
            for statement in parsed:
                # Get the first token (should be SELECT)
                tokens = statement.tokens
                
                # Find the first keyword
                first_keyword = None
                for token in tokens:
                    if token.ttype is DML:
                        first_keyword = token.value.upper()
                        break
                    elif token.ttype is Keyword:
                        first_keyword = token.value.upper()
                        break
                
                # If no DML keyword found, check for forbidden keywords
                if first_keyword is None:
                    query_upper = query.upper().strip()
                    for keyword in InputGuardrails.FORBIDDEN_KEYWORDS:
                        if keyword in query_upper:
                            logger.warning(f"Forbidden keyword '{keyword}' detected in query")
                            return False, f"Forbidden operation: {keyword} statements are not allowed. Only SELECT queries are permitted."
                
                # Check if it's a SELECT statement
                if first_keyword and first_keyword != 'SELECT':
                    logger.warning(f"Non-SELECT statement detected: {first_keyword}")
                    return False, f"Only SELECT queries are allowed. Found: {first_keyword}"
                
                # Check for multiple statements (SQL injection attempt)
                if len(parsed) > 1:
                    logger.warning("Multiple SQL statements detected")
                    return False, "Multiple SQL statements are not allowed. Only single SELECT queries are permitted."
        
        except Exception as e:
            logger.error(f"Error parsing SQL query: {str(e)}")
            return False, f"Invalid SQL syntax: {str(e)}"
        
        logger.debug("Query passed SELECT-only validation")
        return True, None
    
    @staticmethod
    def check_sql_injection(query: str) -> Tuple[bool, Optional[str]]:
        """
        Check for SQL injection patterns.
        
        Args:
            query: SQL query string
        
        Returns:
            Tuple of (is_safe: bool, error_message: str or None)
        """
        logger.debug("Checking for SQL injection patterns")
        
        query_normalized = query.upper()
        
        # Check for forbidden keywords in the query
        for keyword in InputGuardrails.FORBIDDEN_KEYWORDS:
            # Use word boundary to avoid false positives
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, query_normalized, re.IGNORECASE):
                logger.warning(f"Potential SQL injection detected: forbidden keyword '{keyword}'")
                return False, f"Security violation: '{keyword}' keyword detected. Only SELECT queries are allowed."
        
        # Check for SQL injection patterns
        for pattern in InputGuardrails.SQL_INJECTION_PATTERNS:
            if re.search(pattern, query_normalized, re.IGNORECASE):
                logger.warning(f"Potential SQL injection detected: pattern '{pattern}'")
                return False, "Security violation: Potential SQL injection detected."
        
        logger.debug("No SQL injection patterns detected")
        return True, None
    
    @staticmethod
    def validate_query(query: str) -> Tuple[bool, Optional[str]]:
        """
        Perform all validation checks on a SQL query.
        
        Args:
            query: SQL query string
        
        Returns:
            Tuple of (is_valid: bool, error_message: str or None)
        """
        logger.info("Starting comprehensive SQL validation")
        
        # Check for SQL injection
        is_safe, error = InputGuardrails.check_sql_injection(query)
        if not is_safe:
            return False, error
        
        # Check for SELECT-only
        is_select, error = InputGuardrails.validate_select_only(query)
        if not is_select:
            return False, error
        
        logger.info("Query passed all validation checks")
        return True, None

