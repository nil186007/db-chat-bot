"""
Orchestrator agent that routes queries to SQL database agents (PostgreSQL).
Supports any SQL database flavor - MongoDB and other non-SQL DBs removed.
"""
import re
from typing import List, Optional, Dict, TypedDict, Literal
from langgraph.graph import StateGraph, END
from db_chatbot.config.settings import get_logger
from db_chatbot.agents.workflow_agent import WorkflowAgent
from db_chatbot.query_intent.database_router import DatabaseRouter
import pandas as pd

logger = get_logger(__name__)


class OrchestratorState(TypedDict, total=False):
    """State schema for the orchestrator agent."""
    user_query: str
    query_type: Optional[str]  # "db_query", "greeting", "general_question", "unknown"
    target_database: Optional[str]  # "postgresql", "unknown"
    postgres_schema: Optional[Dict]
    conversation_history: List[Dict]
    steps: List[Dict]

    # Results from sub-agents
    postgres_result: Optional[Dict]

    # Fallback tracking
    tried_postgres: bool
    should_try_fallback: bool

    # Final response
    final_response: Optional[str]
    df: Optional[pd.DataFrame]
    query_results: Optional[pd.DataFrame]


class OrchestratorAgent:
    """Orchestrator agent that routes queries to SQL database agents."""

    def __init__(
        self,
        postgres_workflow_agent: Optional[WorkflowAgent] = None,
        database_router: Optional[DatabaseRouter] = None,
        postgres_client=None,
        schema_rag=None
    ):
        """
        Initialize orchestrator agent.

        Args:
            postgres_workflow_agent: PostgreSQL workflow agent instance (optional)
            database_router: Database router instance (optional)
            postgres_client: PostgreSQL client for schema fetching (optional)
            schema_rag: Schema RAG instance for PostgreSQL schema (optional)
        """
        self.postgres_workflow_agent = postgres_workflow_agent
        self.database_router = database_router
        self.postgres_client = postgres_client
        self.schema_rag = schema_rag

        self.graph = self._build_graph()
        self.compiled_graph = self.graph.compile()

        logger.info("OrchestratorAgent initialized (SQL databases only)")

    def _log_step(self, state: OrchestratorState, step_num: int, name: str, status: str, message: str):
        """Log a workflow step to the state."""
        if "steps" not in state:
            state["steps"] = []

        step_info = {
            "step": step_num,
            "name": name,
            "status": status,
            "message": message
        }
        state["steps"].append(step_info)
        logger.info(f"Orchestrator Step {step_num}: {name} - {status} - {message}")

    def _classify_query_node(self, state: OrchestratorState) -> OrchestratorState:
        """Node: Classify query type (DB query, greeting, general question)."""
        self._log_step(state, 1, "Query Classification", "in_progress",
                      "Classifying user query...")

        user_query = state["user_query"]
        user_query_lower = user_query.lower()

        logger.info("INTENT CLASSIFICATION: Analyzing query...")
        logger.info(f"  Query: {user_query}")

        greeting_words = ['hi', 'hello', 'hey', 'greetings', 'good morning', 'good afternoon', 'good evening']
        matched_greetings = [w for w in greeting_words if re.search(r'\b' + re.escape(w) + r'\b', user_query_lower)]
        if matched_greetings:
            state["query_type"] = "greeting"
            logger.info(f"  Classification: GREETING (matched keywords: {matched_greetings})")
            self._log_step(state, 1, "Query Classification", "completed",
                          "Query classified as greeting")
            return state

        db_keywords = ['show', 'list', 'display', 'find', 'get', 'count', 'how many',
                      'what are', 'which', 'select', 'query', 'table',
                      'database', 'db', 'join']
        matched_db_keywords = [keyword for keyword in db_keywords if keyword in user_query_lower]
        if matched_db_keywords:
            state["query_type"] = "db_query"
            logger.info(f"  Classification: DB_QUERY (matched keywords: {matched_db_keywords})")
        else:
            state["query_type"] = "general_question"
            logger.info("  Classification: GENERAL_QUESTION (no DB keywords matched)")

        self._log_step(state, 1, "Query Classification", "completed",
                      f"Query classified as: {state['query_type']}")
        return state

    def _should_route_to_db(self, state: OrchestratorState) -> Literal["db_routing", "handle_general", "end"]:
        """Conditional edge: Route based on query type."""
        query_type = state.get("query_type")

        if query_type == "greeting":
            return "handle_general"
        elif query_type == "db_query":
            return "db_routing"
        elif query_type == "general_question":
            return "handle_general"
        else:
            return "end"

    def _route_database_node(self, state: OrchestratorState) -> OrchestratorState:
        """Node: Route query to SQL database (always PostgreSQL for now)."""
        self._log_step(state, 2, "Database Routing", "in_progress",
                      "Determining which database to query...")

        postgres_schema = None
        if self.postgres_client and hasattr(self.postgres_client, 'connection') and self.postgres_client.connection:
            try:
                postgres_schema = self.postgres_client.fetch_schema()
                state["postgres_schema"] = postgres_schema
            except Exception as e:
                logger.warning(f"Could not fetch PostgreSQL schema: {e}")

        if self.database_router and postgres_schema:
            postgres_db_name = None
            if self.schema_rag:
                if hasattr(self.schema_rag, 'database_name') and self.schema_rag.database_name:
                    postgres_db_name = self.schema_rag.database_name
                elif hasattr(self.schema_rag, 'knowledge_graph_rag') and self.schema_rag.knowledge_graph_rag:
                    try:
                        db_query = """
                        MATCH (db:Database {db_type: "postgresql"})
                        RETURN db.name as db_name
                        ORDER BY db.created_at DESC
                        LIMIT 1
                        """
                        result = self.schema_rag.knowledge_graph_rag.neo4j.execute_query(db_query)
                        if result:
                            postgres_db_name = result[0].get("db_name")
                    except Exception as e:
                        logger.warning(f"Could not get PostgreSQL database name from knowledge graph: {e}")

            target_db = self.database_router.route_query(
                user_query=state["user_query"],
                postgres_schema=postgres_schema,
                conversation_history=state.get("conversation_history", []),
                postgres_db_name=postgres_db_name
            )
            state["target_database"] = target_db
        else:
            state["target_database"] = "postgresql" if postgres_schema else "unknown"

        self._log_step(state, 2, "Database Routing", "completed",
                      f"Query routed to: {state['target_database']}")
        return state

    def _should_call_postgres(
        self, state: OrchestratorState
    ) -> Literal["postgres_workflow", "handle_general", "end"]:
        """Conditional edge: Route to PostgreSQL workflow or general handling."""
        target_db = state.get("target_database")

        if target_db in ("postgresql", "unknown") and self.postgres_workflow_agent:
            return "postgres_workflow"
        return "handle_general"

    def _is_response_satisfactory(self, result: Dict) -> bool:
        """Check if a workflow agent response is satisfactory."""
        if not result:
            return False

        final_response = result.get("final_response", "").lower()
        error_indicators = [
            "error", "failed", "not available", "no response",
            "could not", "unable to", "execution failed",
            "query execution failed", "validation failed"
        ]

        if any(indicator in final_response for indicator in error_indicators):
            return False

        if result.get("execution_error") or result.get("validation_error"):
            return False

        df = result.get("df")
        if df is not None:
            if len(df) == 0:
                logger.warning("  Response has empty results (0 rows)")
                return False
            return True

        query_results = result.get("query_results")
        if query_results and isinstance(query_results, dict):
            rows = query_results.get("rows", [])
            if len(rows) == 0:
                return False
            return True

        if final_response and len(final_response) > 20:
            return True

        return False

    def _execute_postgres_workflow_node(self, state: OrchestratorState) -> OrchestratorState:
        """Node: Execute PostgreSQL workflow agent."""
        self._log_step(state, 3, "SQL Workflow", "in_progress",
                      "Executing SQL query...")

        state["tried_postgres"] = True

        if not self.postgres_workflow_agent:
            state["final_response"] = "SQL workflow agent not available."
            self._log_step(state, 3, "SQL Workflow", "error",
                          "SQL workflow agent not available")
            return state

        try:
            result = self.postgres_workflow_agent.run(
                user_query=state["user_query"],
                conversation_history=state.get("conversation_history", [])
            )

            state["postgres_result"] = result
            is_satisfactory = self._is_response_satisfactory(result)

            if is_satisfactory:
                state["final_response"] = result.get("final_response", "No response from SQL agent.")
                state["df"] = result.get("df")
                state["query_results"] = result.get("df")
                state["should_try_fallback"] = False
                self._log_step(state, 3, "SQL Workflow", "completed",
                              "SQL workflow completed successfully")
            else:
                state["should_try_fallback"] = True
                if not state.get("final_response"):
                    state["final_response"] = result.get("final_response", "SQL query did not return satisfactory results.")
                self._log_step(state, 3, "SQL Workflow", "warning",
                              "SQL workflow completed but response not satisfactory")

            if result.get("steps"):
                for step in result["steps"]:
                    step["name"] = f"SQL: {step.get('name', '')}"
                    state["steps"].append(step)
        except Exception as e:
            logger.error(f"Error in SQL workflow: {e}")
            state["final_response"] = f"Error executing SQL query: {str(e)}"
            self._log_step(state, 3, "SQL Workflow", "error",
                          f"Error: {str(e)}")

        return state

    def _handle_general_node(self, state: OrchestratorState) -> OrchestratorState:
        """Node: Handle non-database queries (greetings, general questions)."""
        query_type = state.get("query_type")
        user_query = state["user_query"]

        if query_type == "greeting":
            state["final_response"] = "Hello! 👋 I'm your SQL database assistant. I can help you query your database using natural language. How can I help you today?"
            self._log_step(state, 2, "General Handling", "completed",
                          "Handled greeting")
        elif query_type == "general_question":
            if self.postgres_client and hasattr(self.postgres_client, 'connection') and self.postgres_client.connection:
                state["final_response"] = (
                    "I can help you query your SQL database. Ask me questions like:\n"
                    "- 'Show me all products'\n"
                    "- 'How many orders are there?'\n"
                    "- 'Find customers with email containing @example.com'"
                )
            else:
                state["final_response"] = (
                    "I'm a database assistant. Please connect to a SQL database (PostgreSQL) "
                    "to get started. You can ask me questions about your data once connected."
                )
            self._log_step(state, 2, "General Handling", "completed",
                          "Handled general question")
        else:
            state["final_response"] = "I'm not sure how to help with that. Please ask me a question about your database, or say hello!"
            self._log_step(state, 2, "General Handling", "completed",
                          "Handled unknown query type")

        return state

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph orchestrator workflow."""
        workflow = StateGraph(OrchestratorState)

        workflow.add_node("classify_query", self._classify_query_node)
        workflow.add_node("route_database", self._route_database_node)
        workflow.add_node("execute_postgres", self._execute_postgres_workflow_node)
        workflow.add_node("handle_general", self._handle_general_node)

        workflow.set_entry_point("classify_query")

        workflow.add_conditional_edges(
            "classify_query",
            self._should_route_to_db,
            {
                "db_routing": "route_database",
                "handle_general": "handle_general",
                "end": END
            }
        )

        workflow.add_conditional_edges(
            "route_database",
            self._should_call_postgres,
            {
                "postgres_workflow": "execute_postgres",
                "handle_general": "handle_general",
                "end": END
            }
        )

        workflow.add_edge("execute_postgres", END)
        workflow.add_edge("handle_general", END)

        return workflow

    def run(
        self,
        user_query: str,
        conversation_history: List[Dict] = None
    ) -> Dict:
        """Run the orchestrator workflow."""
        logger.info("=" * 80)
        logger.info("ORCHESTRATOR: Starting query processing")
        logger.info("=" * 80)
        logger.info(f"USER QUERY: {user_query}")

        initial_state: OrchestratorState = {
            "user_query": user_query,
            "conversation_history": conversation_history or [],
            "steps": [],
            "tried_postgres": False,
            "should_try_fallback": False,
        }

        final_state = self.compiled_graph.invoke(initial_state)

        logger.info("=" * 80)
        logger.info("ORCHESTRATOR: Query processing completed")
        logger.info("=" * 80)

        return dict(final_state)
