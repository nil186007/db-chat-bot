"""
Output guardrails for query results validation and sanitization.
"""
import re
import pandas as pd
from typing import Tuple, Optional, Dict, Any, List
from db_chatbot.config.settings import get_logger

logger = get_logger(__name__)


# Mask placeholder for all sensitive data
MASK_VALUE = "*****"


class OutputGuardrails:
    """Validates and sanitizes query output/results."""
    
    MAX_ROWS_LIMIT = 1000  # Maximum rows to return
    MAX_COLUMNS_LIMIT = 50  # Maximum columns to return
    
    @staticmethod
    def validate_results(results: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validate query results structure and size.
        
        Args:
            results: Query results dictionary with 'columns' and 'rows'
        
        Returns:
            Tuple of (is_valid: bool, error_message: str or None)
        """
        logger.debug("Validating query results")
        
        if not results:
            logger.warning("Empty results")
            return False, "Empty results returned"
        
        if 'columns' not in results or 'rows' not in results:
            logger.warning("Invalid results structure")
            return False, "Invalid results structure: missing 'columns' or 'rows'"
        
        row_count = len(results.get('rows', []))
        column_count = len(results.get('columns', []))
        
        # Check row limit
        if row_count > OutputGuardrails.MAX_ROWS_LIMIT:
            logger.warning(f"Results exceed row limit: {row_count} > {OutputGuardrails.MAX_ROWS_LIMIT}")
            return False, f"Results exceed maximum allowed rows ({OutputGuardrails.MAX_ROWS_LIMIT})"
        
        # Check column limit
        if column_count > OutputGuardrails.MAX_COLUMNS_LIMIT:
            logger.warning(f"Results exceed column limit: {column_count} > {OutputGuardrails.MAX_COLUMNS_LIMIT}")
            return False, f"Results exceed maximum allowed columns ({OutputGuardrails.MAX_COLUMNS_LIMIT})"
        
        logger.debug(f"Results validated: {row_count} rows, {column_count} columns")
        return True, None
    
    @staticmethod
    def sanitize_results(results: Dict[str, Any], max_rows: int = 100) -> Dict[str, Any]:
        """
        Sanitize and limit query results to prevent excessive data transfer.
        
        Args:
            results: Query results dictionary
            max_rows: Maximum number of rows to return
        
        Returns:
            Sanitized results dictionary
        """
        logger.debug(f"Sanitizing results with max_rows={max_rows}")
        
        if not results or 'rows' not in results:
            return results
        
        # Limit rows
        rows = results['rows']
        if len(rows) > max_rows:
            logger.info(f"Limiting results from {len(rows)} to {max_rows} rows")
            results['rows'] = rows[:max_rows]
            results['truncated'] = True
            results['original_row_count'] = len(rows)
        else:
            results['truncated'] = False
        
        # Sanitize column names (remove any potentially problematic characters)
        if 'columns' in results:
            sanitized_columns = []
            for col in results['columns']:
                # Remove any non-alphanumeric characters except underscore
                sanitized_col = re.sub(r'[^a-zA-Z0-9_]', '_', str(col))
                sanitized_columns.append(sanitized_col)
            results['columns'] = sanitized_columns
        
        return results
    
    @staticmethod
    def sanitize_dataframe(df: pd.DataFrame, max_rows: int = 100) -> pd.DataFrame:
        """
        Sanitize and limit DataFrame to prevent excessive data transfer.
        
        Args:
            df: Input DataFrame
            max_rows: Maximum number of rows to return
        
        Returns:
            Sanitized DataFrame
        """
        logger.debug(f"Sanitizing DataFrame with max_rows={max_rows}")
        
        # Limit rows
        if len(df) > max_rows:
            logger.info(f"Limiting DataFrame from {len(df)} to {max_rows} rows")
            df = df.head(max_rows)
        
        # Sanitize column names
        df.columns = [re.sub(r'[^a-zA-Z0-9_]', '_', str(col)) for col in df.columns]
        
        return df

    # Patterns for sensitive data detection (email, phone, credit card, password only)
    _EMAIL_RE = re.compile(
        r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b',
        re.IGNORECASE
    )
    _PHONE_RE = re.compile(
        r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'
        r'|\b\d{10}\b'
        r'|\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b'
    )
    _CREDIT_CARD_RE = re.compile(
        r'\b\d{4}[-.\s]?\d{4}[-.\s]?\d{4}[-.\s]?\d{4}\b'
    )
    # Column name patterns for masking: only email, phone, credit card, password
    _SENSITIVE_COL_PATTERNS = [
        r'email', r'e_mail',
        r'phone', r'mobile', r'fax', r'telephone',
        r'credit_card', r'card_number', r'cc_number', r'cardnumber',
        r'password', r'pwd', r'passwd', r'pass_word',
    ]

    # Skip value-based masking for numeric values (ratings, counts, prices, etc.)
    _NUMERIC_RE = re.compile(r'^-?\d*\.?\d+$')

    @staticmethod
    def _mask_value(val: Any, col_name: str = "") -> Any:
        """Mask a single value if it looks like email, phone, credit card, or password."""
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return val
        s = str(val).strip()
        if not s:
            return val
        col_lower = col_name.lower()
        # Never mask numeric values (ratings, averages, counts, etc.) - they are not PII
        if OutputGuardrails._NUMERIC_RE.match(s):
            return val
        # Check column name first
        for pat in OutputGuardrails._SENSITIVE_COL_PATTERNS:
            if re.search(pat, col_lower):
                if re.search(r'email|e_mail', col_lower) and OutputGuardrails._EMAIL_RE.search(s):
                    return MASK_VALUE
                if re.search(r'phone|mobile|fax|telephone', col_lower) and OutputGuardrails._PHONE_RE.search(s):
                    return MASK_VALUE
                if re.search(r'credit_card|card_number|cc_number|cardnumber', col_lower) and OutputGuardrails._CREDIT_CARD_RE.search(s):
                    return MASK_VALUE
                if re.search(r'password|pwd|passwd|pass_word', col_lower):
                    return MASK_VALUE  # Always mask password columns
                break
        # Value-based detection (only for non-numeric values - emails, phones, credit cards)
        if OutputGuardrails._EMAIL_RE.search(s):
            return MASK_VALUE
        if OutputGuardrails._PHONE_RE.search(s):
            return MASK_VALUE
        if OutputGuardrails._CREDIT_CARD_RE.search(s):
            return MASK_VALUE
        return val

    @staticmethod
    def mask_sensitive_dataframe(df: pd.DataFrame) -> pd.DataFrame:
        """
        Mask sensitive data (emails, phone numbers, credit cards, passwords) in a DataFrame.
        Returns a copy with masked values. Original is unchanged.
        """
        if df is None or df.empty:
            return df
        df_masked = df.copy()
        for col in df_masked.columns:
            col_str = str(col)
            df_masked[col] = df_masked[col].apply(
                lambda v, cn=col_str: OutputGuardrails._mask_value(v, cn)
            )
        return df_masked

    @staticmethod
    def mask_sensitive_results(results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Mask sensitive data (emails, phones, credit cards, passwords) in query results dict (columns + rows).
        Returns a copy. Original is unchanged.
        """
        if not results or 'rows' not in results or 'columns' not in results:
            return results
        columns = results['columns']
        rows = results['rows']
        masked_rows: List[tuple] = []
        for row in rows:
            if isinstance(row, (list, tuple)):
                masked_row = []
                for i, val in enumerate(row):
                    col_name = columns[i] if i < len(columns) else ""
                    masked_row.append(OutputGuardrails._mask_value(val, str(col_name)))
                masked_rows.append(tuple(masked_row) if isinstance(row, tuple) else masked_row)
            else:
                masked_rows.append(row)
        return {**results, 'rows': masked_rows}

