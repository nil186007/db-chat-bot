"""
MongoDB query generation using local LLM (Ollama).
"""
import ollama
import json
from typing import Optional, Dict, List
from db_chatbot.config.settings import get_logger

logger = get_logger(__name__)


class MongoDBQueryGenerator:
    """Generates MongoDB queries from natural language using local LLM."""
    
    def __init__(self, model_name: str = None):
        """
        Initialize MongoDB query generator.
        
        Args:
            model_name: Name of the Ollama model to use. If None, uses first available model.
        """
        logger.info(f"Initializing MongoDBQueryGenerator with model: {model_name or 'auto-detect'}")
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
        Format MongoDB schema information for the LLM prompt.
        
        Args:
            schema_info: Schema dictionary from MongoDBClient.fetch_schema()
        
        Returns:
            Formatted schema string
        """
        logger.debug("Formatting MongoDB schema for LLM prompt")
        if not schema_info or not schema_info.get("collections"):
            logger.warning("No schema information available")
            return "No schema information available."
        
        schema_text = "MongoDB Database Schema:\n\n"
        schema_text += f"Database: {schema_info.get('database_name', 'unknown')}\n\n"
        
        for collection in schema_info["collections"]:
            schema_text += f"Collection: {collection['name']}\n"
            schema_text += f"Document Count: {collection.get('document_count', 0)}\n"
            schema_text += "Fields:\n"
            
            for field in collection.get("fields", []):
                types_str = ", ".join(field.get("types", []))
                nullable = " (nullable)" if field.get("nullable") else ""
                example = f" (example: {field.get('example')})" if field.get("example") else ""
                schema_text += f"  - {field['name']}: {types_str}{nullable}{example}\n"
            
            # Add indexes
            indexes = collection.get("indexes", [])
            if indexes:
                schema_text += "Indexes:\n"
                for idx in indexes:
                    keys_str = ", ".join([f"{k}: {v}" for k, v in idx.get("keys", {}).items()])
                    unique = " (unique)" if idx.get("unique") else ""
                    schema_text += f"  - {idx.get('name', 'unnamed')}: {keys_str}{unique}\n"
            
            schema_text += "\n"
        
        logger.debug(f"Schema formatted: {len(schema_text)} characters")
        return schema_text
    
    def generate_query(
        self,
        natural_language_query: str,
        schema_info: Dict,
        conversation_history: list = None,
        enhanced_context: str = None
    ) -> Optional[Dict]:
        """
        Generate MongoDB query from natural language.
        
        Args:
            natural_language_query: User's natural language question
            schema_info: Database schema information (from RAG)
            conversation_history: Previous conversation messages for context
            enhanced_context: Enhanced schema context from knowledge graph (includes annotations)
        
        Returns:
            Generated MongoDB query dictionary or None if generation fails
        """
        logger.info(f"Generating MongoDB query for: {natural_language_query[:50]}...")
        
        # Use enhanced context if provided (from knowledge graph), otherwise format from schema_info
        if enhanced_context:
            schema_text = enhanced_context
            logger.debug("Using enhanced context from knowledge graph")
        else:
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
        
        prompt = f"""You are a MongoDB query expert. Given a MongoDB database schema, convert the natural language question into a valid MongoDB query.

IMPORTANT: You must ONLY generate READ queries (find or aggregate operations). Do not generate insert, update, delete, or any data modification operations.

{schema_text}

{context}

User Question: {natural_language_query}

Instructions:
1. Generate ONLY a valid MongoDB query as a JSON object
2. The query must be a valid JSON dictionary with the following structure:
   - For find queries: {{"collection": "collection_name", "filter": {{}}, "projection": {{}}, "sort": {{}}, "limit": number}}
   - For aggregate queries: {{"collection": "collection_name", "aggregate": [{{"$match": {{}}}}, {{"$group": {{}}}}, ...]}}
3. Use proper MongoDB query syntax
4. Make sure to use correct collection and field names from the schema
5. Only READ operations are allowed - no data manipulation
6. Return ONLY the JSON query, no explanations, markdown formatting, or additional text
7. If the question is unclear or cannot be answered with the given schema, return: {{"error": "explanation"}}

MongoDB Query (JSON only):"""

        try:
            logger.debug(f"Sending prompt to Ollama model: {self.model_name}")
            response = ollama.generate(
                model=self.model_name,
                prompt=prompt,
                options={
                    "temperature": 0.1,  # Lower temperature for more consistent query generation
                    "num_predict": 512,  # Limit query length
                }
            )
            
            query_text = response['response'].strip()
            logger.debug(f"Received response from Ollama: {query_text[:100]}...")
            
            # Clean up the response - remove markdown code blocks if present
            if query_text.startswith("```json"):
                query_text = query_text[7:]
            elif query_text.startswith("```"):
                query_text = query_text[3:]
            
            if query_text.endswith("```"):
                query_text = query_text[:-3]
            
            query_text = query_text.strip()
            
            # Check for error response
            if query_text.startswith('{"error"') or query_text.startswith("{'error'"):
                logger.warning(f"LLM returned error: {query_text}")
                return None
            
            # Parse JSON
            try:
                query_dict = json.loads(query_text)
                logger.info(f"MongoDB query generated successfully: {query_dict.get('collection', 'unknown')}")
                return query_dict
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON query: {str(e)}")
                logger.debug(f"Query text: {query_text}")
                return None
            
        except Exception as e:
            logger.error(f"Error generating MongoDB query: {str(e)}")
            return None
    
    def change_model(self, model_name: str):
        """Change the Ollama model being used."""
        logger.info(f"Changing model from {self.model_name} to {model_name}")
        self.model_name = model_name
        self._test_connection()
