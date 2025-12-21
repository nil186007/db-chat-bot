"""
Output guardrails for query results validation and sanitization.
"""
import re
import pandas as pd
from typing import Tuple, Optional, Dict, Any
from db_chatbot.config.settings import get_logger

logger = get_logger(__name__)


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

