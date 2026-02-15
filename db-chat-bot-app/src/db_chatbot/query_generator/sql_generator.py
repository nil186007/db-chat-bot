"""
SQL query generation using local LLM (Ollama).
"""
import re
import ollama
import json
from typing import Optional, Dict, List
from db_chatbot.config.settings import get_logger

logger = get_logger(__name__)


class SQLGenerator:
    """Generates SQL queries from natural language using local LLM."""
    
    def __init__(self, model_name: str = None):
        """
        Initialize SQL generator.
        
        Args:
            model_name: Name of the Ollama model to use. If None, uses first available model.
        """
        logger.info(f"Initializing SQLGenerator with model: {model_name or 'auto-detect'}")
        self.model_name = model_name
        self._test_connection()
        if not self.model_name:
            self._auto_select_model()
    
    def _test_connection(self):
        """Test if Ollama is running and model is available."""
        logger.debug("Testing Ollama connection")
        try:
            ollama.list()
            logger.info("Ollama connection successful")
        except Exception as e:
            logger.error(f"Cannot connect to Ollama: {str(e)}")
            raise ConnectionError(
                f"Cannot connect to Ollama. Please make sure Ollama is running.\n"
                f"Install from: https://ollama.ai\n"
                f"Error: {str(e)}"
            )
    
    def _auto_select_model(self):
        """Auto-select the first available model."""
        try:
            models = self.get_available_models()
            if models:
                self.model_name = models[0]
                logger.info(f"Auto-selected model: {self.model_name}")
            else:
                logger.warning("No models available in Ollama")
                raise ValueError("No Ollama models found. Please install a model first.")
        except Exception as e:
            logger.error(f"Error auto-selecting model: {str(e)}")
            raise
    
    @staticmethod
    def get_available_models() -> List[str]:
        """
        Get list of available Ollama models.
        
        Returns:
            List of model names
        """
        logger.debug("Fetching available Ollama models")
        try:
            response = ollama.list()
            models = [model['name'] for model in response.get('models', [])]
            logger.info(f"Found {len(models)} available model(s): {', '.join(models)}")
            return models
        except Exception as e:
            logger.error(f"Error fetching available models: {str(e)}")
            return []
    
    def format_schema_for_prompt(self, schema_info: Dict) -> str:
        """
        Format database schema information for the LLM prompt.
        
        Args:
            schema_info: Schema dictionary from PostgresClient.fetch_schema()
        
        Returns:
            Formatted schema string
        """
        logger.debug("Formatting schema for LLM prompt")
        if not schema_info or not schema_info.get("tables"):
            logger.warning("No schema information available")
            return "No schema information available."
        
        schema_text = "Database Schema:\n\n"
        
        for table in schema_info["tables"]:
            schema_name = table.get("schema_name", "public")
            table_label = f'"{schema_name}".{table["name"]}' if schema_name != "public" else table["name"]
            schema_text += f"Table: {table_label}\n"
            schema_text += "Columns:\n"
            
            for col in table["columns"]:
                nullable = "NULL" if col["nullable"] else "NOT NULL"
                max_len = f"({col['max_length']})" if col["max_length"] else ""
                default = f" DEFAULT {col['default']}" if col["default"] else ""
                schema_text += f"  - {col['name']}: {col['type']}{max_len} {nullable}{default}\n"
            
            if table["primary_keys"]:
                schema_text += f"Primary Keys: {', '.join(table['primary_keys'])}\n"
            
            if table.get("foreign_keys"):
                schema_text += "Foreign Keys:\n"
                for fk in table["foreign_keys"]:
                    ref_schema = fk.get("references_schema")
                    ref_table = f'"{ref_schema}".{fk["references_table"]}' if ref_schema and ref_schema != "public" else fk["references_table"]
                    schema_text += f"  - {fk['column']} -> {ref_table}.{fk['references_column']}\n"
            
            schema_text += "\n"
        
        logger.debug(f"Schema formatted: {len(schema_text)} characters")
        return schema_text

    def _qualify_schema_in_sql(self, sql_query: str, schema_info: Dict) -> str:
        """
        Post-process SQL to add schema qualification for tables not in 'public'.
        Replaces unqualified table references (FROM/JOIN/comma) with "schema".table.
        """
        if not schema_info or not schema_info.get("tables"):
            return sql_query
        tables_to_qualify = [
            (t["name"], t["schema_name"])
            for t in schema_info["tables"]
            if t.get("schema_name") and t["schema_name"] != "public"
        ]
        if not tables_to_qualify:
            return sql_query
        for table_name, schema_name in sorted(tables_to_qualify, key=lambda x: -len(x[0])):
            escaped = re.escape(table_name)
            qualified = f'"{schema_name}".{table_name}'
            sql_query = re.sub(
                rf"(\bFROM\s+)(?<!\.){escaped}\b",
                r"\1" + qualified,
                sql_query,
                flags=re.IGNORECASE
            )
            for kw in ["JOIN", "LEFT JOIN", "RIGHT JOIN", "INNER JOIN", "CROSS JOIN",
                       "LEFT OUTER JOIN", "RIGHT OUTER JOIN"]:
                kw_pat = kw.replace(" ", r"\s+")
                sql_query = re.sub(
                    rf"(\b{kw_pat}\s+)(?<!\.){escaped}\b",
                    r"\1" + qualified,
                    sql_query,
                    flags=re.IGNORECASE
                )
            sql_query = re.sub(
                rf"(,\s*)(?<!\.){escaped}\b",
                ", " + qualified,
                sql_query,
                flags=re.IGNORECASE
            )
        logger.debug(f"Schema-qualified SQL: {sql_query[:80]}...")
        return sql_query

    def generate_sql(
        self,
        natural_language_query: str,
        schema_info: Dict,
        conversation_history: list = None,
        enhanced_context: str = None,
        query_examples: list = None
    ) -> Optional[str]:
        """
        Generate SQL query from natural language.
        
        Args:
            natural_language_query: User's natural language question
            schema_info: Database schema information (from RAG)
            conversation_history: Previous conversation messages for context
            enhanced_context: Enhanced schema context from knowledge graph (includes annotations)
            query_examples: List of {natural_language, sql_query} from graph - use/adapt when user query matches
        
        Returns:
            Generated SQL query string or None if generation fails
        """
        logger.info(f"Generating SQL for query: {natural_language_query[:50]}...")
        
        # Use enhanced context if provided (from knowledge graph), otherwise format from schema_info
        if enhanced_context:
            schema_text = enhanced_context
            logger.debug("Using enhanced context from knowledge graph")
        else:
            schema_text = self.format_schema_for_prompt(schema_info)
        
        # Build query examples section - use matching examples to guide SQL generation
        examples_text = ""
        if query_examples and len(query_examples) > 0:
            examples_text = "\n\nQuery Examples (use or adapt when user question matches):\n"
            for i, ex in enumerate(query_examples[:5], 1):
                nl = ex.get("natural_language", "")
                sql = ex.get("sql_query", "")
                if sql:
                    examples_text += f"{i}. \"{nl}\" → {sql}\n"
        
        # Build conversation context
        context = ""
        if conversation_history:
            context = "\n\nPrevious conversation:\n"
            for msg in conversation_history[-3:]:  # Last 3 messages for context
                if msg.get("role") == "user":
                    context += f"User: {msg.get('content', '')}\n"
                elif msg.get("role") == "assistant":
                    context += f"Assistant: {msg.get('content', '')}\n"
        
        prompt = f"""You are a SQL expert. Given a database schema, convert the natural language question into a valid PostgreSQL SELECT query.

IMPORTANT: You must ONLY generate SELECT queries. Do not generate INSERT, UPDATE, DELETE, DROP, or any other type of query.

{schema_text}
{examples_text}

{context}

User Question: {natural_language_query}

Instructions:
1. Generate ONLY a valid PostgreSQL SELECT query
2. Do not include any explanations, markdown formatting, or additional text
3. Use proper SQL syntax for PostgreSQL
4. Make sure to use correct table and column names from the schema
5. If Query Examples are provided and your question matches one, adapt that example's SQL rather than generating from scratch
5. SCHEMA QUALIFICATION: When tables are shown with a schema prefix (e.g., "schema_name".table_name), use them EXACTLY in your SQL. Always qualify table names with schema when the schema is not "public" (e.g., SELECT * FROM "sql-e-commerce".products).
6. Only SELECT statements are allowed - no data manipulation
7. If the question is unclear or cannot be answered with the given schema, return "ERROR: [explanation]"

SQL Query:"""

        try:
            logger.debug(f"Sending prompt to Ollama model: {self.model_name}")
            response = ollama.generate(
                model=self.model_name,
                prompt=prompt,
                options={
                    "temperature": 0.1,  # Lower temperature for more consistent SQL generation
                    "num_predict": 512,  # Limit SQL query length
                }
            )
            
            sql_query = response['response'].strip()
            logger.debug(f"Received response from Ollama: {sql_query[:100]}...")
            
            # Clean up the response - remove markdown code blocks if present
            if sql_query.startswith("```sql"):
                sql_query = sql_query[6:]
            elif sql_query.startswith("```"):
                sql_query = sql_query[3:]
            
            if sql_query.endswith("```"):
                sql_query = sql_query[:-3]
            
            sql_query = sql_query.strip()
            
            # Check for error response
            if sql_query.startswith("ERROR:"):
                logger.warning(f"LLM returned error: {sql_query}")
                return None

            # Post-process: add schema qualification for tables not in public
            sql_query = self._qualify_schema_in_sql(sql_query, schema_info)

            logger.info(f"SQL query generated successfully: {sql_query[:50]}...")
            return sql_query
            
        except Exception as e:
            logger.error(f"Error generating SQL: {str(e)}")
            return None
    
    def change_model(self, model_name: str):
        """Change the Ollama model being used."""
        logger.info(f"Changing model from {self.model_name} to {model_name}")
        self.model_name = model_name
        self._test_connection()

