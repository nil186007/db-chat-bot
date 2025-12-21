"""
Response generator that uses LLM to generate natural language responses from query results.
"""
import ollama
from typing import Dict, Optional, List
import pandas as pd
from db_chatbot.config.settings import get_logger

logger = get_logger(__name__)


class ResponseGenerator:
    """Generates natural language responses from query results using LLM."""
    
    def __init__(self, model_name: str):
        """
        Initialize response generator.
        
        Args:
            model_name: Name of the Ollama model to use
        """
        self.model_name = model_name
        logger.debug(f"ResponseGenerator initialized with model: {model_name}")
    
    def generate_response(
        self,
        user_query: str,
        query_results: Optional[pd.DataFrame],
        sql_query: Optional[str] = None,
        conversation_history: Optional[List[Dict]] = None
    ) -> str:
        """
        Generate a natural language response based on query results.
        
        Args:
            user_query: Original user question
            query_results: DataFrame with query results (can be None)
            sql_query: The SQL query that was executed (optional)
            conversation_history: Previous conversation messages for context
        
        Returns:
            Natural language response string
        """
        logger.info(f"Generating response for query: {user_query[:50]}...")
        
        # Build context from conversation history
        context = ""
        if conversation_history:
            context = "\n\nPrevious conversation:\n"
            for msg in conversation_history[-5:]:  # Last 5 messages for context
                if msg.get("role") == "user":
                    context += f"User: {msg.get('content', '')}\n"
                elif msg.get("role") == "assistant":
                    content = msg.get('content', '')
                    # Don't include raw SQL or data in context, just summaries
                    if 'sql_query' in msg:
                        context += f"Assistant: [Executed a database query]\n"
                    else:
                        context += f"Assistant: {content}\n"
        
        # Format query results
        results_text = ""
        if query_results is not None and len(query_results) > 0:
            results_text = "\n\nQuery Results:\n"
            # Convert DataFrame to a readable format (limit to first 20 rows for prompt)
            df_preview = query_results.head(20)
            results_text += df_preview.to_string(index=False)
            if len(query_results) > 20:
                results_text += f"\n... (showing 20 of {len(query_results)} total rows)"
        elif query_results is not None and len(query_results) == 0:
            results_text = "\n\nThe query returned no results."
        
        # Build prompt
        sql_info = f"\n\nSQL Query executed: {sql_query}" if sql_query else ""
        
        prompt = f"""You are a helpful database assistant. A user asked a question, and we executed a database query to get the answer. 

User Question: {user_query}
{sql_info}
{results_text}
{context}

Your task:
1. Answer the user's question in a natural, conversational way
2. Use the query results to provide specific information
3. If there are no results, explain that clearly
4. Be concise but informative
5. If numbers or statistics are involved, highlight them
6. Do not mention SQL queries or technical details unless the user specifically asked about them

Provide a clear, helpful answer to the user's question:"""

        try:
            logger.debug(f"Generating response using model: {self.model_name}")
            response = ollama.generate(
                model=self.model_name,
                prompt=prompt,
                options={
                    "temperature": 0.7,  # Slightly higher for more natural responses
                    "num_predict": 512,
                }
            )
            
            generated_response = response['response'].strip()
            logger.info(f"Response generated successfully: {generated_response[:50]}...")
            return generated_response
            
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            # Fallback response
            if query_results is not None and len(query_results) > 0:
                return f"I found {len(query_results)} result(s) for your query. Here's the data:"
            else:
                return "I couldn't generate a proper response. The query executed but returned no results."

