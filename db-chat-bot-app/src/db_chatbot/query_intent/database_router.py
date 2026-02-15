"""
Database router for SQL databases (PostgreSQL and other SQL flavors).
Routes queries to the connected SQL database.
"""
from typing import Optional, Literal
from db_chatbot.config.settings import get_logger
from db_chatbot.rag.knowledge_graph_rag import KnowledgeGraphRAG
import ollama

logger = get_logger(__name__)


class DatabaseRouter:
    """Routes queries to SQL database based on user intent using knowledge graph RAG."""

    def __init__(self, model_name: str = None, knowledge_graph_rag: Optional[KnowledgeGraphRAG] = None):
        """
        Initialize database router.

        Args:
            model_name: Name of the Ollama model to use. If None, uses first available model.
            knowledge_graph_rag: KnowledgeGraphRAG instance for relevance-based routing
        """
        self.model_name = model_name
        self.knowledge_graph_rag = knowledge_graph_rag
        if not self.model_name:
            self._auto_select_model()
        logger.info(f"DatabaseRouter initialized (SQL only), RAG: {knowledge_graph_rag is not None}")

    def _auto_select_model(self):
        """Auto-select the first available model."""
        try:
            response = ollama.list()
            models = response.get('models', [])
            if models:
                self.model_name = models[0].get('name', '')
                if self.model_name:
                    logger.info(f"Auto-selected model: {self.model_name}")
                else:
                    logger.warning("No valid model name found")
            else:
                logger.warning("No models available in Ollama")
        except Exception as e:
            logger.error(f"Error auto-selecting model: {str(e)}")

    def route_query(
        self,
        user_query: str,
        postgres_schema: Optional[dict] = None,
        conversation_history: list = None,
        postgres_db_name: Optional[str] = None,
    ) -> Literal["postgresql", "unknown"]:
        """
        Determine which SQL database to query. Always routes to PostgreSQL when connected.

        Args:
            user_query: User's natural language query
            postgres_schema: PostgreSQL schema information (optional)
            conversation_history: Previous conversation messages (optional)
            postgres_db_name: PostgreSQL database name for RAG search

        Returns:
            "postgresql" when SQL schema is available, otherwise "unknown"
        """
        logger.info(f"Routing query: {user_query[:50]}...")

        if postgres_schema and postgres_db_name and self.knowledge_graph_rag:
            return self._rag_based_routing(user_query, postgres_db_name)

        if postgres_schema:
            return "postgresql"
        return "unknown"

    def _rag_based_routing(
        self,
        user_query: str,
        postgres_db_name: Optional[str] = None
    ) -> Literal["postgresql", "unknown"]:
        """Route query based on knowledge graph RAG relevance scores."""
        logger.info("ROUTING: Knowledge Graph RAG-based (SQL only)")

        if not postgres_db_name:
            return "unknown"

        try:
            details = self.knowledge_graph_rag.get_relevance_score(
                user_query=user_query,
                database_name=postgres_db_name,
                db_type="postgresql"
            )
            score = details.get("score", 0)
            logger.info(f"  PostgreSQL relevance score: {score}")

            if score > 0:
                return "postgresql"
        except Exception as e:
            logger.warning(f"  Error getting relevance score: {e}")

        return "postgresql"  # Default to SQL when schema available
