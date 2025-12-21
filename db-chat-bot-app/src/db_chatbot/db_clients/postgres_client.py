"""
PostgreSQL database client tool for the agent.
"""
import psycopg2
from psycopg2 import sql
from typing import Dict, List, Optional, Tuple
from db_chatbot.config.settings import get_logger

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
        Fetch all table schemas from the database.
        
        Returns:
            Dictionary containing schema information
        """
        if not self.connection:
            logger.warning("Cannot fetch schema: not connected to database")
            return None
        
        logger.info("Starting schema fetch process")
        schema_info = {
            "tables": []
        }
        
        try:
            cursor = self.connection.cursor()
            logger.debug("Cursor created for schema fetching")
            
            # Get all tables from public schema (can be extended for other schemas)
            logger.debug("Fetching list of tables")
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name;
            """)
            
            tables = cursor.fetchall()
            logger.info(f"Found {len(tables)} table(s) in database")
            
            for (table_name,) in tables:
                logger.debug(f"Processing table: {table_name}")
                
                # Get column information for each table
                cursor.execute("""
                    SELECT 
                        column_name,
                        data_type,
                        character_maximum_length,
                        is_nullable,
                        column_default
                    FROM information_schema.columns
                    WHERE table_schema = 'public' 
                    AND table_name = %s
                    ORDER BY ordinal_position;
                """, (table_name,))
                
                columns = cursor.fetchall()
                logger.debug(f"Found {len(columns)} column(s) in table {table_name}")
                
                # Get primary keys
                cursor.execute("""
                    SELECT kcu.column_name
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                    WHERE tc.table_schema = 'public'
                    AND tc.table_name = %s
                    AND tc.constraint_type = 'PRIMARY KEY';
                """, (table_name,))
                
                primary_keys = [row[0] for row in cursor.fetchall()]
                
                # Get foreign keys
                cursor.execute("""
                    SELECT
                        kcu.column_name,
                        ccu.table_name AS foreign_table_name,
                        ccu.column_name AS foreign_column_name
                    FROM information_schema.table_constraints AS tc
                    JOIN information_schema.key_column_usage AS kcu
                    ON tc.constraint_name = kcu.constraint_name
                    JOIN information_schema.constraint_column_usage AS ccu
                    ON ccu.constraint_name = tc.constraint_name
                    WHERE tc.constraint_type = 'FOREIGN KEY'
                    AND tc.table_schema = 'public'
                    AND tc.table_name = %s;
                """, (table_name,))
                
                foreign_keys = cursor.fetchall()
                
                table_info = {
                    "name": table_name,
                    "columns": [],
                    "primary_keys": primary_keys,
                    "foreign_keys": []
                }
                
                for col in columns:
                    column_info = {
                        "name": col[0],
                        "type": col[1],
                        "max_length": col[2],
                        "nullable": col[3] == "YES",
                        "default": col[4]
                    }
                    table_info["columns"].append(column_info)
                
                for fk in foreign_keys:
                    table_info["foreign_keys"].append({
                        "column": fk[0],
                        "references_table": fk[1],
                        "references_column": fk[2]
                    })
                
                schema_info["tables"].append(table_info)
            
            cursor.close()
            logger.info(f"Schema fetch completed successfully. Loaded {len(schema_info['tables'])} table(s)")
            return schema_info
            
        except psycopg2.Error as e:
            logger.error(f"Error fetching schema: {str(e)}")
            return None
    
    def execute_query(self, query: str) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """
        Execute a SQL query and return results.
        
        Returns:
            Tuple of (success: bool, results: Dict, error_message: str)
        """
        if not self.connection:
            logger.warning("Cannot execute query: not connected to database")
            return False, None, "Not connected to database"
        
        logger.info(f"Executing query: {query[:100]}...")
        try:
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
            return False, None, str(e)
    
    def close(self):
        """Close database connection."""
        if self.connection:
            logger.info("Closing database connection")
            self.connection.close()
            self.connection = None

