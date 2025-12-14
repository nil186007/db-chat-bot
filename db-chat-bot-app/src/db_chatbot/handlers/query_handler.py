"""
Query handler agent that classifies user queries and routes them appropriately.
"""
import re
from typing import Dict, Tuple, Optional
from db_chatbot.config.settings import get_logger
from db_chatbot.core.query_classifier import QueryClassifier

logger = get_logger(__name__)


class QueryHandler:
    """Handles different types of user queries and routes them appropriately."""
    
    # Greeting patterns (for quick greeting detection)
    GREETING_PATTERNS = [
        r'\b(hi|hello|hey|greetings|good morning|good afternoon|good evening)\b',
        r'\bhow are you\b',
        r'\bwhat\'?s up\b',
        r'\bnice to meet you\b',
    ]
    
    def __init__(self, model_name: str = None):
        """
        Initialize the query handler.
        
        Args:
            model_name: Ollama model name for LLM-based classification (optional)
        """
        self.model_name = model_name
        self.query_classifier = QueryClassifier(model_name) if model_name else None
        logger.debug(f"QueryHandler initialized with model: {model_name}")
    
    def is_greeting(self, user_query: str) -> bool:
        """
        Check if the query is a greeting (fast pattern matching).
        
        Args:
            user_query: User's input query
        
        Returns:
            True if greeting, False otherwise
        """
        query_lower = user_query.lower().strip()
        for pattern in self.GREETING_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                return True
        return False
    
    def needs_sql(self, user_query: str, schema_info: Optional[Dict] = None) -> Tuple[bool, str]:
        """
        Determine if the query needs SQL generation using LLM.
        
        Args:
            user_query: User's input query
            schema_info: Database schema information (optional)
        
        Returns:
            Tuple of (needs_sql: bool, reasoning: str)
        """
        if self.query_classifier:
            return self.query_classifier.classify(user_query, schema_info)
        else:
            # Fallback: assume SQL needed if not a greeting
            return not self.is_greeting(user_query), "LLM classifier not available, using fallback"
    
    def handle_greeting(self, user_query: str) -> str:
        """
        Handle greeting queries.
        
        Args:
            user_query: User's greeting
        
        Returns:
            Appropriate greeting response
        """
        logger.debug("Handling greeting query")
        responses = [
            "Hello! 👋 I'm your database assistant. I can help you query your PostgreSQL database using natural language. What would you like to know?",
            "Hi there! I'm here to help you explore your database. Just ask me questions about your data, and I'll convert them to SQL queries.",
            "Hey! Ready to query your database? Ask me anything about your data, and I'll help you find the answers!",
        ]
        
        if any(word in user_query.lower() for word in ['how are you', 'how\'s it going']):
            return "I'm doing great! Ready to help you query your database. What would you like to explore?"
        
        return responses[0]
    
    def handle_general_question(self, user_query: str) -> str:
        """
        Handle general questions that don't require SQL generation.
        
        Args:
            user_query: User's question
        
        Returns:
            Appropriate response
        """
        logger.debug("Handling general question")
        query_lower = user_query.lower()
        
        if 'what can you do' in query_lower or 'help' in query_lower:
            return """I can help you:
• Convert natural language questions into SQL queries
• Query your PostgreSQL database
• Display results in tables or summaries
• Answer questions about your database schema

Try asking things like:
- "Show me all products"
- "How many orders are there?"
- "List customers from New York"
- "What are the top 5 products by price?"
"""
        
        if 'how does this work' in query_lower or 'what is this' in query_lower:
            return """This is a Database ChatBot that uses AI to convert your natural language questions into SQL queries.

Here's how it works:
1. You ask a question in plain English
2. I analyze your question and the database schema
3. I generate an appropriate SELECT query
4. You review and confirm the query
5. The query executes and shows results

You can ask questions about tables, columns, relationships, and data in your database!"""
        
        if 'who are you' in query_lower:
            return "I'm a Database Assistant powered by a local LLM (via Ollama). I help you query your PostgreSQL database using natural language instead of writing SQL yourself!"
        
        return "I'm here to help you query your database! Ask me questions about your data, and I'll convert them to SQL queries for you."
    
    def handle_query(self, user_query: str, schema_info: Optional[Dict] = None) -> Tuple[str, Optional[str]]:
        """
        Main handler that routes queries to appropriate handlers.
        
        Args:
            user_query: User's input query
            schema_info: Database schema information (optional)
        
        Returns:
            Tuple of (response_type, response_message)
            response_type: 'greeting', 'general_question', 'sql_query'
        """
        logger.info(f"Handling user query: {user_query[:50]}...")
        
        # Fast check for greetings
        if self.is_greeting(user_query):
            response = self.handle_greeting(user_query)
            return ('greeting', response)
        
        # Use LLM to determine if SQL is needed
        needs_sql, reasoning = self.needs_sql(user_query, schema_info)
        
        if needs_sql:
            logger.debug(f"Query needs SQL: {reasoning}")
            return ('sql_query', None)  # SQL generation will be handled separately
        else:
            logger.debug(f"Query does not need SQL: {reasoning}")
            response = self.handle_general_question(user_query)
            return ('general_question', response)
