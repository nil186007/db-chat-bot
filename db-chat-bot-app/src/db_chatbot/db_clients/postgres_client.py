"""
PostgreSQL database client tool for the agent.
"""
import psycopg2
from psycopg2 import sql, extensions
from typing import Dict, List, Optional, Tuple
from db_chatbot.config.settings import get_logger
from db_chatbot.guardrails.input_guardrails import InputGuardrails

logger = get_logger(__name__)


class PostgresClient:
    """PostgreSQL database client tool for agent use."""
    
    def __init__(self):
        """Initialize PostgreSQL client."""
        self.connection = None
        logger.info("PostgresClient instance created")
    
    def connect(self, host: str, port: int, database: str, user: str, password: str) -> Tuple[bool, str]:
        """
        Connect to PostgreSQL database.
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        logger.info(f"Attempting to connect to database: {host}:{port}/{database}")
        try:
            self.connection = psycopg2.connect(
                host=host,
                port=port,
                database=database,
                user=user,
                password=password
            )
            logger.info("Database connection established successfully")
            return True, "Connection successful!"
        except psycopg2.Error as e:
            logger.error(f"Database connection failed: {str(e)}")
            return False, f"Connection failed: {str(e)}"
    
    def fetch_schema(self) -> Optional[Dict]:
        """
        Fetch all schemas and their tables from the database.
        Returns hierarchy: Database -> Schema -> Table -> Column (attributes).
        
        Returns:
            Dictionary with "schemas" (list of {name, tables}) and "tables" (flat list with schema_name)
        """
        if not self.connection:
            logger.warning("Cannot fetch schema: not connected to database")
            return None
        
        logger.info("Starting schema fetch - all schemas and tables")
        schema_info: Dict = {"schemas": [], "tables": []}
        
        try:
            cursor = self.connection.cursor()
            
            # Get all user schemas (exclude system schemas)
            cursor.execute("""
                SELECT schema_name 
                FROM information_schema.schemata 
                WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
                  AND schema_name NOT LIKE 'pg_temp_%'
                  AND schema_name NOT LIKE 'pg_toast_temp_%'
                ORDER BY schema_name;
            """)
            schemas = [row[0] for row in cursor.fetchall()]
            logger.info(f"Found {len(schemas)} schema(s): {schemas}")
            
            for schema_name in schemas:
                # Get all tables in this schema
                cursor.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = %s
                      AND table_type = 'BASE TABLE'
                    ORDER BY table_name;
                """, (schema_name,))
                tables = cursor.fetchall()
                
                schema_tables = []
                for (table_name,) in tables:
                    table_info = self._fetch_table_info(cursor, schema_name, table_name)
                    if table_info:
                        table_info["schema_name"] = schema_name
                        schema_tables.append(table_info)
                        schema_info["tables"].append(table_info)
                
                schema_info["schemas"].append({
                    "name": schema_name,
                    "tables": schema_tables
                })
            
            cursor.close()
            total_tables = len(schema_info["tables"])
            logger.info(f"Schema fetch completed. {len(schemas)} schema(s), {total_tables} table(s)")
            return schema_info
            
        except psycopg2.Error as e:
            logger.error(f"Error fetching schema: {str(e)}")
            return None
    
    def _fetch_table_info(self, cursor, schema_name: str, table_name: str) -> Optional[Dict]:
        """Fetch column and constraint info for a single table."""
        cursor.execute("""
            SELECT column_name, data_type, character_maximum_length, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position;
        """, (schema_name, table_name))
        columns = cursor.fetchall()
        
        cursor.execute("""
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
            WHERE tc.table_schema = %s AND tc.table_name = %s AND tc.constraint_type = 'PRIMARY KEY';
        """, (schema_name, table_name))
        primary_keys = [row[0] for row in cursor.fetchall()]
        
        cursor.execute("""
            SELECT kcu.column_name, ccu.table_schema, ccu.table_name, ccu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = %s AND tc.table_name = %s;
        """, (schema_name, table_name))
        foreign_keys_raw = cursor.fetchall()
        
        table_info = {
            "name": table_name,
            "columns": [],
            "primary_keys": primary_keys,
            "foreign_keys": []
        }
        for col in columns:
            table_info["columns"].append({
                "name": col[0],
                "type": col[1],
                "max_length": col[2],
                "nullable": col[3] == "YES",
                "default": col[4]
            })
        for fk in foreign_keys_raw:
            table_info["foreign_keys"].append({
                "column": fk[0],
                "references_schema": fk[1],
                "references_table": fk[2],
                "references_column": fk[3]
            })
        return table_info
    
    def execute_query(self, query: str) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """
        Execute a SQL query and return results.
        Validates for SQL injection and SELECT-only before execution.
        
        Returns:
            Tuple of (success: bool, results: Dict, error_message: str)
        """
        if not self.connection:
            logger.warning("Cannot execute query: not connected to database")
            return False, None, "Not connected to database"

        # Mandatory pre-execution check: block SQL injection and non-SELECT
        is_valid, validation_error = InputGuardrails.validate_query(query)
        if not is_valid:
            logger.warning(f"Query blocked before execution: {validation_error}")
            return False, None, validation_error

        logger.info(f"Executing query: {query[:100]}...")
        cursor = None
        try:
            # Rollback any previous failed transaction to ensure clean state
            # This is important when retrying queries after a failure
            try:
                if self.connection.status == extensions.STATUS_IN_TRANSACTION:
                    logger.debug("Rolling back previous transaction to ensure clean state")
                    self.connection.rollback()
            except Exception:
                # If rollback fails, connection might be in bad state, try to reset
                pass
            
            cursor = self.connection.cursor()
            cursor.execute(query)
            
            # Check if query returns results
            if cursor.description:
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                cursor.close()
                logger.info(f"Query executed successfully. Returned {len(rows)} row(s)")
                return True, {"columns": columns, "rows": rows}, None
            else:
                # For INSERT, UPDATE, DELETE queries (should not happen with validation)
                self.connection.commit()
                affected_rows = cursor.rowcount
                cursor.close()
                logger.warning(f"Query executed but no results returned. {affected_rows} row(s) affected")
                return True, {"affected_rows": affected_rows}, None
                
        except psycopg2.Error as e:
            logger.error(f"Query execution failed: {str(e)}")
            # Rollback the transaction on error to allow subsequent queries
            # This is critical for retry logic to work properly
            try:
                if cursor:
                    cursor.close()
                # Always attempt rollback on error to reset transaction state
                try:
                    if self.connection.status == extensions.STATUS_IN_TRANSACTION:
                        logger.debug("Rolling back transaction after error")
                        self.connection.rollback()
                    else:
                        # Even if not in transaction, try rollback to be safe
                        self.connection.rollback()
                except Exception as rollback_inner:
                    # If rollback also fails, log but don't fail
                    logger.warning(f"Rollback failed (may be expected): {str(rollback_inner)}")
            except Exception as rollback_error:
                logger.warning(f"Error during cleanup after query failure: {str(rollback_error)}")
            return False, None, str(e)
    
    def close(self):
        """Close database connection."""
        if self.connection:
            logger.info("Closing database connection")
            self.connection.close()
            self.connection = None

