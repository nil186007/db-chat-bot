"""
LLM-based query classifier that determines if a query needs SQL generation.
"""
import ollama
from typing import Tuple, Dict, Optional, List
from db_chatbot.config.settings import get_logger

logger = get_logger(__name__)


class QueryClassifier:
    """Uses LLM to classify whether a user query needs SQL generation."""
    
    def __init__(self, model_name: str):
        """
        Initialize query classifier.
        
        Args:
            model_name: Name of the Ollama model to use
        """
        self.model_name = model_name
        logger.debug(f"QueryClassifier initialized with model: {model_name}")
    
    def classify(self, user_query: str, schema_info: Optional[Dict] = None) -> Tuple[bool, str]:
        """
        Classify if the query needs SQL generation.
        
        Args:
            user_query: User's input query
            schema_info: Database schema information (optional)
        
        Returns:
            Tuple of (needs_sql: bool, reasoning: str)
        """
        return self.classify_query(user_query, schema_info, [])
    
    def classify_query(
        self,
        user_query: str,
        schema_info: Optional[Dict] = None,
        conversation_history: Optional[List[Dict]] = None
    ) -> Tuple[bool, str]:
        """
        Classify if the query needs SQL generation.
        
        Args:
            user_query: User's input query
            schema_info: Database schema information (optional)
            conversation_history: Previous conversation messages (optional)
        
        Returns:
            Tuple of (needs_sql: bool, reasoning: str)
        """
        logger.info(f"Classifying query: {user_query[:50]}...")
        
        # Build schema context if available
        schema_context = ""
        if schema_info and schema_info.get("tables"):
            schema_context = "\n\nAvailable database tables:\n"
            for table in schema_info["tables"][:10]:  # Limit to first 10 tables
                schema_context += f"- {table['name']}\n"
        
        prompt = f"""You are a database assistant. A user has asked a question. Determine if this question requires querying a database to answer.

User Question: {user_query}
{schema_context}

Answer with ONLY one word: "YES" or "NO"

- Answer "YES" if the question asks about data in the database (e.g., "show products", "how many orders", "list customers")
- Answer "NO" if it's a greeting (e.g., "hello", "hi"), general question about the system (e.g., "what can you do", "help"), or doesn't require database access

Your answer (YES or NO):"""

        try:
            logger.debug(f"Classifying query using model: {self.model_name}")
            response = ollama.generate(
                model=self.model_name,
                prompt=prompt,
                options={
                    "temperature": 0.1,  # Low temperature for consistent classification
                    "num_predict": 10,  # Very short response
                }
            )
            
            answer = response['response'].strip().upper()
            
            # Extract YES/NO from response
            needs_sql = "YES" in answer
            
            reasoning = "Query requires database access" if needs_sql else "Query does not require database access"
            logger.info(f"Query classification: needs_sql={needs_sql}, reasoning={reasoning}")
            
            return needs_sql, reasoning
            
        except Exception as e:
            logger.error(f"Error classifying query: {str(e)}")
            # Default to needing SQL if classification fails
            return True, "Could not classify, defaulting to SQL query"

