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
    
    # SQL injection patterns (order matters: more specific first)
    SQL_INJECTION_PATTERNS = [
        r'--',  # SQL comment (e.g. '' OR 1=1; --)
        r'/\*',  # Multi-line comment start
        r'\*/',  # Multi-line comment end
        r'#(?:\s|$)',  # MySQL/Unix line comment
        r'union\s+.*\s+select',  # Union injection
        r';\s*[-/#\w]',  # Multiple statements (semicolon followed by anything)
        r';\s*--',  # Semicolon then comment (e.g. ; --)
        r'\bor\s+1\s*=\s*1\b',  # OR 1=1 injection
        r"\'\s*or\s+1\s*=\s*1",  # ' OR 1=1 (after empty string)
        r"\'\s*or\s*\'1\'\s*=\s*\'1",  # ' OR '1'='1
        r'"\s*or\s+1\s*=\s*1',  # " OR 1=1
        r"=\s*'\s*'\s*or\s+1",  # = '' OR 1 (empty string then OR 1=1)
        r'xp_',  # SQL Server extended procedures
        r'sp_',  # SQL Server stored procedures
        r'exec\s*\(',  # Execution
        r'\bexec\b',  # EXEC keyword
        r'0x[0-9a-fA-F]+',  # Hex encoded strings
        r'\bwaitfor\b',  # SQL Server WAITFOR
        r'\bpg_sleep\s*\(',  # PostgreSQL sleep (injection test)
        r'\bsleep\s*\(',  # Sleep function
        r'\bbenchmark\s*\(',  # MySQL benchmark
        r'insert\s+into\s+.*\bselect\b',  # INSERT...SELECT injection
        r'\binto\s+outfile\b',  # MySQL file export
        r'\binto\s+dumpfile\b',  # MySQL dump
        r"\bor\s+'\s*'\s*=\s*'\s*'",  # OR ''='' (always-true variant)
        r'\band\s+1\s*=\s*1\b',  # AND 1=1 injection
        r'\bhaving\s+1\s*=\s*1\b',  # HAVING 1=1
    ]

    # User intent keywords that indicate forbidden operations (reject before SQL generation)
    # Use specific patterns to avoid false positives (e.g. "create table of contents")
    DANGEROUS_INTENT_PATTERNS = [
        r'\bdelete\s+(from|all|everything|the\s+data|all\s+rows?|all\s+records?)\b',
        r'\bdelete\s+from\s+\w+',  # delete from <table>
        r'\bdrop\s+(table|database|schema|view)\s+\w+',
        r'\btruncate\s+table\b',
        r'\binsert\s+into\s+\w+',
        r'\bupdate\s+\w+\s+set\s+',  # update X set 
        r'\balter\s+table\s+\w+',
        r'\bcreate\s+table\s+\w+',  # create table X (avoids "table of contents")
        r'\bgrant\s+',
        r'\brevoke\s+',
        r'\bremove\s+(all\s+)?data\s+from\b',
        r'\bclear\s+(the\s+)?(table|data)\b',
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
    def is_security_violation(error_message: str) -> bool:
        """
        Check if a validation error is a security violation (forbidden ops, SQL injection).
        Security violations should NOT be retried/fixed - they must be rejected.
        """
        if not error_message:
            return False
        err_lower = error_message.lower()
        security_indicators = [
            "forbidden", "not allowed", "only select", "security violation",
            "sql injection", "multiple sql statements"
        ]
        return any(ind in err_lower for ind in security_indicators)

    @staticmethod
    def validate_user_input(user_query: str) -> Tuple[bool, Optional[str]]:
        """
        Validate raw user input for dangerous intent and SQL injection before processing.
        Rejects requests for delete/drop/update etc. and obvious injection attempts.
        
        Returns:
            Tuple of (is_safe: bool, error_message: str or None)
        """
        if not user_query or not user_query.strip():
            return True, None
        query_lower = user_query.lower().strip()
        query_upper = user_query.upper()

        # Check for dangerous intent (natural language)
        for pattern in InputGuardrails.DANGEROUS_INTENT_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                logger.warning(f"Dangerous intent detected in user input: {pattern}")
                return False, (
                    "This type of operation is not allowed. "
                    "Only read-only SELECT queries are permitted. "
                    "For data modifications, please use your database client directly."
                )

        # Check for raw SQL in user input (possible injection)
        raw_sql_indicators = [
            (r'\b(delete|drop|truncate|insert|update)\s+', "Raw SQL with write operation detected."),
            (r';\s*\S', "Multiple statements detected - not allowed."),
            (r';\s*--', "SQL comment after semicolon detected - possible injection."),
            (r'\s--\s', "SQL comment pattern detected in input."),
            (r'\bor\s+1\s*=\s*1\b', "SQL injection pattern (OR 1=1) detected."),
            (r"'\s*or\s+1\s*=\s*1", "SQL injection pattern (' OR 1=1) detected."),
            (r"=\s*'\s*'\s*or\s+1", "SQL injection pattern (= '' OR 1=1) detected."),
            (r'union\s+.*select', "Union-based injection pattern detected."),
            (r'/\*', "SQL comment detected."),
        ]
        for pattern, msg in raw_sql_indicators:
            if re.search(pattern, query_upper, re.IGNORECASE):
                logger.warning(f"Potential SQL injection in user input: {pattern}")
                return False, (
                    "Security violation: Your input contains patterns that are not allowed. "
                    "Please rephrase your question in natural language."
                )

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

