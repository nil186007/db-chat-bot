"""
SQL query generation using local LLM (Ollama).
"""
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
            schema_text += f"Table: {table['name']}\n"
            schema_text += "Columns:\n"
            
            for col in table["columns"]:
                nullable = "NULL" if col["nullable"] else "NOT NULL"
                max_len = f"({col['max_length']})" if col["max_length"] else ""
                default = f" DEFAULT {col['default']}" if col["default"] else ""
                schema_text += f"  - {col['name']}: {col['type']}{max_len} {nullable}{default}\n"
            
            if table["primary_keys"]:
                schema_text += f"Primary Keys: {', '.join(table['primary_keys'])}\n"
            
            if table["foreign_keys"]:
                schema_text += "Foreign Keys:\n"
                for fk in table["foreign_keys"]:
                    schema_text += f"  - {fk['column']} -> {fk['references_table']}.{fk['references_column']}\n"
            
            schema_text += "\n"
        
        logger.debug(f"Schema formatted: {len(schema_text)} characters")
        return schema_text
    
    def generate_sql(self, natural_language_query: str, schema_info: Dict, conversation_history: list = None) -> Optional[str]:
        """
        Generate SQL query from natural language.
        
        Args:
            natural_language_query: User's natural language question
            schema_info: Database schema information (from RAG)
            conversation_history: Previous conversation messages for context
        
        Returns:
            Generated SQL query string or None if generation fails
        """
        logger.info(f"Generating SQL for query: {natural_language_query[:50]}...")
        schema_text = self.format_schema_for_prompt(schema_info)
        
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

{context}

User Question: {natural_language_query}

Instructions:
1. Generate ONLY a valid PostgreSQL SELECT query
2. Do not include any explanations, markdown formatting, or additional text
3. Use proper SQL syntax for PostgreSQL
4. Make sure to use correct table and column names from the schema
5. Only SELECT statements are allowed - no data manipulation
6. If the question is unclear or cannot be answered with the given schema, return "ERROR: [explanation]"

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

