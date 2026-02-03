"""
Orchestrator agent that routes queries to appropriate database agents (PostgreSQL or MongoDB)
and handles non-database workflows.
"""
from typing import List, Optional, Dict, TypedDict, Literal, Annotated
from langgraph.graph import StateGraph, END
from db_chatbot.config.settings import get_logger
from db_chatbot.agents.workflow_agent import WorkflowAgent
from db_chatbot.agents.mongodb_workflow_agent import MongoDBWorkflowAgent
from db_chatbot.query_intent.database_router import DatabaseRouter
import pandas as pd

logger = get_logger(__name__)


class OrchestratorState(TypedDict, total=False):
    """State schema for the orchestrator agent."""
    user_query: str
    query_type: Optional[str]  # "db_query", "greeting", "general_question", "unknown"
    target_database: Optional[str]  # "postgresql", "mongodb", "both", "unknown"
    postgres_schema: Optional[Dict]
    mongodb_schema: Optional[Dict]
    conversation_history: List[Dict]
    steps: List[Dict]
    
    # Results from sub-agents
    postgres_result: Optional[Dict]
    mongodb_result: Optional[Dict]
    
    # Final response
    final_response: Optional[str]
    df: Optional[pd.DataFrame]
    query_results: Optional[pd.DataFrame]


class OrchestratorAgent:
    """Orchestrator agent that routes queries to appropriate database agents."""
    
    def __init__(
        self,
        postgres_workflow_agent: Optional[WorkflowAgent] = None,
        mongodb_workflow_agent: Optional[MongoDBWorkflowAgent] = None,
        database_router: Optional[DatabaseRouter] = None,
        postgres_client=None,
        mongodb_client=None,
        schema_rag=None
    ):
        """
        Initialize orchestrator agent.
        
        Args:
            postgres_workflow_agent: PostgreSQL workflow agent instance (optional)
            mongodb_workflow_agent: MongoDB workflow agent instance (optional)
            database_router: Database router instance (optional)
            postgres_client: PostgreSQL client for schema fetching (optional)
            mongodb_client: MongoDB client for schema fetching (optional)
            schema_rag: Schema RAG instance for PostgreSQL schema (optional)
        """
        self.postgres_workflow_agent = postgres_workflow_agent
        self.mongodb_workflow_agent = mongodb_workflow_agent
        self.database_router = database_router
        self.postgres_client = postgres_client
        self.mongodb_client = mongodb_client
        self.schema_rag = schema_rag
        
        # Build the LangGraph workflow
        self.graph = self._build_graph()
        self.compiled_graph = self.graph.compile()
        
        logger.info("OrchestratorAgent initialized")
    
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
        
        user_query = state["user_query"].lower()
        
        # Check for greetings
        greeting_words = ['hi', 'hello', 'hey', 'greetings', 'good morning', 'good afternoon', 'good evening']
        if any(word in user_query for word in greeting_words):
            state["query_type"] = "greeting"
            self._log_step(state, 1, "Query Classification", "completed", 
                          "Query classified as greeting")
            return state
        
        # Check for database-related queries
        db_keywords = ['show', 'list', 'display', 'find', 'get', 'count', 'how many', 
                      'what are', 'which', 'select', 'query', 'table', 'collection', 
                      'database', 'db', 'aggregate', 'join']
        if any(keyword in user_query for keyword in db_keywords):
            state["query_type"] = "db_query"
        else:
            state["query_type"] = "general_question"
        
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
        """Node: Route query to appropriate database(s)."""
        self._log_step(state, 2, "Database Routing", "in_progress", 
                      "Determining which database(s) to query...")
        
        # Fetch schemas if available
        postgres_schema = None
        mongodb_schema = None
        
        if self.postgres_client and hasattr(self.postgres_client, 'connection') and self.postgres_client.connection:
            try:
                postgres_schema = self.postgres_client.fetch_schema()
                state["postgres_schema"] = postgres_schema
            except Exception as e:
                logger.warning(f"Could not fetch PostgreSQL schema: {e}")
        
        if self.mongodb_client and hasattr(self.mongodb_client, 'database') and self.mongodb_client.database is not None:
            try:
                mongodb_schema = self.mongodb_client.fetch_schema()
                state["mongodb_schema"] = mongodb_schema
            except Exception as e:
                logger.warning(f"Could not fetch MongoDB schema: {e}")
        
        # Use database router if available
        if self.database_router and (postgres_schema or mongodb_schema):
            target_db = self.database_router.route_query(
                user_query=state["user_query"],
                postgres_schema=postgres_schema,
                mongodb_schema=mongodb_schema,
                conversation_history=state.get("conversation_history", [])
            )
            state["target_database"] = target_db
            self._log_step(state, 2, "Database Routing", "completed", 
                          f"Query routed to: {target_db}")
        else:
            # Fallback routing
            if postgres_schema and not mongodb_schema:
                target_db = "postgresql"
            elif mongodb_schema and not postgres_schema:
                target_db = "mongodb"
            elif postgres_schema and mongodb_schema:
                # Default to PostgreSQL if both available
                target_db = "postgresql"
            else:
                target_db = "unknown"
            
            state["target_database"] = target_db
            self._log_step(state, 2, "Database Routing", "completed", 
                          f"Query routed to: {target_db} (fallback)")
        
        return state
    
    def _should_call_postgres(self, state: OrchestratorState) -> Literal["postgres_workflow", "mongodb_workflow", "both_workflows", "handle_general", "end"]:
        """Conditional edge: Route to appropriate database workflow."""
        target_db = state.get("target_database")
        
        if target_db == "postgresql":
            if self.postgres_workflow_agent:
                return "postgres_workflow"
            else:
                return "handle_general"
        elif target_db == "mongodb":
            if self.mongodb_workflow_agent:
                return "mongodb_workflow"
            else:
                return "handle_general"
        elif target_db == "both":
            if self.postgres_workflow_agent and self.mongodb_workflow_agent:
                return "both_workflows"
            elif self.postgres_workflow_agent:
                return "postgres_workflow"
            elif self.mongodb_workflow_agent:
                return "mongodb_workflow"
            else:
                return "handle_general"
        else:
            return "handle_general"
    
    def _execute_postgres_workflow_node(self, state: OrchestratorState) -> OrchestratorState:
        """Node: Execute PostgreSQL workflow agent."""
        self._log_step(state, 3, "PostgreSQL Workflow", "in_progress", 
                      "Executing PostgreSQL workflow agent...")
        
        if not self.postgres_workflow_agent:
            state["final_response"] = "PostgreSQL workflow agent not available."
            self._log_step(state, 3, "PostgreSQL Workflow", "error", 
                          "PostgreSQL workflow agent not available")
            return state
        
        try:
            result = self.postgres_workflow_agent.run(
                user_query=state["user_query"],
                conversation_history=state.get("conversation_history", [])
            )
            
            state["postgres_result"] = result
            state["final_response"] = result.get("final_response", "No response from PostgreSQL agent.")
            state["df"] = result.get("df")
            state["query_results"] = result.get("df")
            
            # Merge steps from PostgreSQL workflow
            if result.get("steps"):
                for step in result["steps"]:
                    step["name"] = f"PostgreSQL: {step.get('name', '')}"
                    state["steps"].append(step)
            
            self._log_step(state, 3, "PostgreSQL Workflow", "completed", 
                          "PostgreSQL workflow completed successfully")
        except Exception as e:
            logger.error(f"Error in PostgreSQL workflow: {e}")
            state["final_response"] = f"Error executing PostgreSQL query: {str(e)}"
            self._log_step(state, 3, "PostgreSQL Workflow", "error", 
                          f"Error: {str(e)}")
        
        return state
    
    def _execute_mongodb_workflow_node(self, state: OrchestratorState) -> OrchestratorState:
        """Node: Execute MongoDB workflow agent."""
        self._log_step(state, 3, "MongoDB Workflow", "in_progress", 
                      "Executing MongoDB workflow agent...")
        
        if not self.mongodb_workflow_agent:
            state["final_response"] = "MongoDB workflow agent not available."
            self._log_step(state, 3, "MongoDB Workflow", "error", 
                          "MongoDB workflow agent not available")
            return state
        
        try:
            result = self.mongodb_workflow_agent.run(
                user_query=state["user_query"],
                conversation_history=state.get("conversation_history", [])
            )
            
            state["mongodb_result"] = result
            state["final_response"] = result.get("final_response", "No response from MongoDB agent.")
            state["df"] = result.get("df")
            state["query_results"] = result.get("df")
            
            # Merge steps from MongoDB workflow
            if result.get("steps"):
                for step in result["steps"]:
                    step["name"] = f"MongoDB: {step.get('name', '')}"
                    state["steps"].append(step)
            
            self._log_step(state, 3, "MongoDB Workflow", "completed", 
                          "MongoDB workflow completed successfully")
        except Exception as e:
            logger.error(f"Error in MongoDB workflow: {e}")
            state["final_response"] = f"Error executing MongoDB query: {str(e)}"
            self._log_step(state, 3, "MongoDB Workflow", "error", 
                          f"Error: {str(e)}")
        
        return state
    
    def _execute_both_workflows_node(self, state: OrchestratorState) -> OrchestratorState:
        """Node: Execute both PostgreSQL and MongoDB workflows."""
        self._log_step(state, 3, "Multi-Database Workflow", "in_progress", 
                      "Executing queries on both databases...")
        
        # Execute PostgreSQL workflow
        if self.postgres_workflow_agent:
            try:
                pg_result = self.postgres_workflow_agent.run(
                    user_query=state["user_query"],
                    conversation_history=state.get("conversation_history", [])
                )
                state["postgres_result"] = pg_result
                
                # Merge PostgreSQL steps
                if pg_result.get("steps"):
                    for step in pg_result["steps"]:
                        step["name"] = f"PostgreSQL: {step.get('name', '')}"
                        state["steps"].append(step)
            except Exception as e:
                logger.error(f"Error in PostgreSQL workflow: {e}")
        
        # Execute MongoDB workflow
        if self.mongodb_workflow_agent:
            try:
                mongo_result = self.mongodb_workflow_agent.run(
                    user_query=state["user_query"],
                    conversation_history=state.get("conversation_history", [])
                )
                state["mongodb_result"] = mongo_result
                
                # Merge MongoDB steps
                if mongo_result.get("steps"):
                    for step in mongo_result["steps"]:
                        step["name"] = f"MongoDB: {step.get('name', '')}"
                        state["steps"].append(step)
            except Exception as e:
                logger.error(f"Error in MongoDB workflow: {e}")
        
        # Combine results
        responses = []
        dfs = []
        
        if state.get("postgres_result") and state["postgres_result"].get("final_response"):
            responses.append(f"**PostgreSQL Results:**\n{state['postgres_result']['final_response']}")
            if state["postgres_result"].get("df") is not None:
                dfs.append(("PostgreSQL", state["postgres_result"]["df"]))
        
        if state.get("mongodb_result") and state["mongodb_result"].get("final_response"):
            responses.append(f"**MongoDB Results:**\n{state['mongodb_result']['final_response']}")
            if state["mongodb_result"].get("df") is not None:
                dfs.append(("MongoDB", state["mongodb_result"]["df"]))
        
        if responses:
            state["final_response"] = "\n\n---\n\n".join(responses)
            # Combine dataframes if both exist
            if len(dfs) == 2:
                # For now, just use the first one or combine them
                state["df"] = dfs[0][1]  # Use PostgreSQL by default
                state["query_results"] = dfs[0][1]
            elif len(dfs) == 1:
                state["df"] = dfs[0][1]
                state["query_results"] = dfs[0][1]
        else:
            state["final_response"] = "No results from either database."
        
        self._log_step(state, 3, "Multi-Database Workflow", "completed", 
                      "Both workflows completed")
        
        return state
    
    def _handle_general_node(self, state: OrchestratorState) -> OrchestratorState:
        """Node: Handle non-database queries (greetings, general questions)."""
        query_type = state.get("query_type")
        user_query = state["user_query"]
        
        if query_type == "greeting":
            state["final_response"] = "Hello! 👋 I'm your database assistant. I can help you query your PostgreSQL and/or MongoDB databases. How can I help you today?"
            self._log_step(state, 2, "General Handling", "completed", 
                          "Handled greeting")
        elif query_type == "general_question":
            # Provide helpful information
            connected_dbs = []
            if self.postgres_client and hasattr(self.postgres_client, 'connection') and self.postgres_client.connection:
                connected_dbs.append("PostgreSQL")
            if self.mongodb_client and hasattr(self.mongodb_client, 'database') and self.mongodb_client.database is not None:
                connected_dbs.append("MongoDB")
            
            if connected_dbs:
                db_list = " and ".join(connected_dbs)
                state["final_response"] = f"I can help you query your {db_list} database(s). Ask me questions like:\n- 'Show me all products'\n- 'How many orders are there?'\n- 'List all collections in MongoDB'\n- 'Find customers with email containing @example.com'"
            else:
                state["final_response"] = "I'm a database assistant. Please connect to a database (PostgreSQL or MongoDB) to get started. You can ask me questions about your data once connected."
            
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
        
        # Add nodes
        workflow.add_node("classify_query", self._classify_query_node)
        workflow.add_node("route_database", self._route_database_node)
        workflow.add_node("execute_postgres", self._execute_postgres_workflow_node)
        workflow.add_node("execute_mongodb", self._execute_mongodb_workflow_node)
        workflow.add_node("execute_both", self._execute_both_workflows_node)
        workflow.add_node("handle_general", self._handle_general_node)
        
        # Set entry point
        workflow.set_entry_point("classify_query")
        
        # Add edges
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
                "mongodb_workflow": "execute_mongodb",
                "both_workflows": "execute_both",
                "handle_general": "handle_general",
                "end": END
            }
        )
        
        workflow.add_edge("execute_postgres", END)
        workflow.add_edge("execute_mongodb", END)
        workflow.add_edge("execute_both", END)
        workflow.add_edge("handle_general", END)
        
        return workflow
    
    def run(
        self,
        user_query: str,
        conversation_history: List[Dict] = None
    ) -> Dict:
        """
        Run the orchestrator workflow.
        
        Args:
            user_query: User's natural language query
            conversation_history: Previous conversation messages
        
        Returns:
            Dictionary with workflow results
        """
        # Initialize state
        initial_state: OrchestratorState = {
            "user_query": user_query,
            "conversation_history": conversation_history or [],
            "steps": [],
        }
        
        # Run the graph
        final_state = self.compiled_graph.invoke(initial_state)
        
        # Convert to regular dict for return
        result = dict(final_state)
        return result
