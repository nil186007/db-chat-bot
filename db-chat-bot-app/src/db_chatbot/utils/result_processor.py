"""
Result processor for formatting and summarizing query results.
"""
import pandas as pd
from typing import Dict, List, Optional, Tuple
from db_chatbot.config.settings import get_logger

logger = get_logger(__name__)


class ResultProcessor:
    """Processes and formats query results."""
    
    MAX_ROWS_DISPLAY = 10
    
    def __init__(self):
        """Initialize the result processor."""
        logger.debug("ResultProcessor initialized")
    
    def process_results(self, results: Dict, user_query: str, show_summary: bool = False) -> Tuple[pd.DataFrame, str]:
        """
        Process query results and optionally generate summary.
        
        Args:
            results: Query results dictionary with 'columns' and 'rows'
            user_query: Original user query
            show_summary: Whether to show summary instead of full table
        
        Returns:
            Tuple of (dataframe, message)
        """
        logger.info(f"Processing results: {len(results.get('rows', []))} rows")
        
        if not results or 'columns' not in results or 'rows' not in results:
            logger.warning("Invalid results format")
            return pd.DataFrame(), "No results to display."
        
        # Create DataFrame
        df = pd.DataFrame(results['rows'], columns=results['columns'])
        total_rows = len(df)
        
        # Limit to MAX_ROWS_DISPLAY
        if total_rows > self.MAX_ROWS_DISPLAY:
            df_display = df.head(self.MAX_ROWS_DISPLAY)
            logger.info(f"Limited results from {total_rows} to {self.MAX_ROWS_DISPLAY} rows")
        else:
            df_display = df
        
        # Generate message
        if show_summary and total_rows > 0:
            message = self._generate_summary(df, user_query, total_rows)
        else:
            if total_rows > self.MAX_ROWS_DISPLAY:
                message = f"Showing first {self.MAX_ROWS_DISPLAY} of {total_rows} rows. "
            else:
                message = f"Found {total_rows} row(s). "
            
            if total_rows == 0:
                message = "Query executed successfully but returned no results."
            else:
                message += "Here are the results:"
        
        return df_display, message
    
    def _generate_summary(self, df: pd.DataFrame, user_query: str, total_rows: int) -> str:
        """
        Generate a text summary of the results based on user query.
        
        Args:
            df: DataFrame with results
            user_query: Original user query
            total_rows: Total number of rows
        
        Returns:
            Summary message
        """
        logger.debug("Generating summary for results")
        query_lower = user_query.lower()
        
        # Count queries
        if any(word in query_lower for word in ['how many', 'count', 'number of']):
            return f"The query returned **{total_rows}** result(s)."
        
        # Top N queries
        if 'top' in query_lower:
            if total_rows > self.MAX_ROWS_DISPLAY:
                return f"Top {self.MAX_ROWS_DISPLAY} results (showing {self.MAX_ROWS_DISPLAY} of {total_rows} total):"
            else:
                return f"Top {total_rows} results:"
        
        # Average/aggregate queries
        if any(word in query_lower for word in ['average', 'avg', 'mean']):
            numeric_cols = df.select_dtypes(include=['number']).columns
            if len(numeric_cols) > 0:
                summary_lines = []
                for col in numeric_cols[:3]:  # Limit to first 3 numeric columns
                    avg = df[col].mean()
                    summary_lines.append(f"Average {col}: {avg:.2f}")
                return f"Summary of {total_rows} row(s): " + " | ".join(summary_lines)
        
        # Min/Max queries
        if 'maximum' in query_lower or 'max' in query_lower or 'highest' in query_lower:
            numeric_cols = df.select_dtypes(include=['number']).columns
            if len(numeric_cols) > 0:
                col = numeric_cols[0]
                max_val = df[col].max()
                return f"Maximum {col}: {max_val} (from {total_rows} row(s))"
        
        if 'minimum' in query_lower or 'min' in query_lower or 'lowest' in query_lower:
            numeric_cols = df.select_dtypes(include=['number']).columns
            if len(numeric_cols) > 0:
                col = numeric_cols[0]
                min_val = df[col].min()
                return f"Minimum {col}: {min_val} (from {total_rows} row(s))"
        
        # Default summary
        if total_rows > self.MAX_ROWS_DISPLAY:
            return f"Query returned {total_rows} result(s). Showing first {self.MAX_ROWS_DISPLAY}:"
        else:
            return f"Query returned {total_rows} result(s):"
    
    def should_summarize(self, user_query: str, row_count: int) -> bool:
        """
        Determine if results should be summarized based on query and row count.
        
        Args:
            user_query: Original user query
            row_count: Number of rows returned
        
        Returns:
            True if should summarize, False otherwise
        """
        query_lower = user_query.lower()
        
        # Always summarize count queries
        if any(word in query_lower for word in ['how many', 'count', 'number of', 'total']):
            return True
        
        # Summarize aggregate queries
        if any(word in query_lower for word in ['average', 'avg', 'mean', 'maximum', 'max', 'minimum', 'min', 'sum', 'total']):
            return row_count <= 10  # Summarize if small result set
        
        # Don't summarize list/show queries
        return False

