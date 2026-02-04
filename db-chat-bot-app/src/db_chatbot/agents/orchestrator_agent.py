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
    
    # Fallback tracking
    tried_postgres: bool
    tried_mongodb: bool
    should_try_fallback: bool
    
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
        
        user_query = state["user_query"]
        user_query_lower = user_query.lower()
        
        logger.info("INTENT CLASSIFICATION: Analyzing query...")
        logger.info(f"  Query: {user_query}")
        
        # Check for greetings
        greeting_words = ['hi', 'hello', 'hey', 'greetings', 'good morning', 'good afternoon', 'good evening']
        matched_greetings = [word for word in greeting_words if word in user_query_lower]
        if matched_greetings:
            state["query_type"] = "greeting"
            logger.info(f"  Classification: GREETING (matched keywords: {matched_greetings})")
            self._log_step(state, 1, "Query Classification", "completed", 
                          "Query classified as greeting")
            return state
        
        # Check for database-related queries
        db_keywords = ['show', 'list', 'display', 'find', 'get', 'count', 'how many', 
                      'what are', 'which', 'select', 'query', 'table', 'collection', 
                      'database', 'db', 'aggregate', 'join']
        matched_db_keywords = [keyword for keyword in db_keywords if keyword in user_query_lower]
        if matched_db_keywords:
            state["query_type"] = "db_query"
            logger.info(f"  Classification: DB_QUERY (matched keywords: {matched_db_keywords})")
        else:
            state["query_type"] = "general_question"
            logger.info(f"  Classification: GENERAL_QUESTION (no DB keywords matched)")
        
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
        if self.database_router:
            logger.info("DATABASE ROUTING: Using database router...")
            
            # Get database names for RAG-based routing
            postgres_db_name = None
            mongodb_db_name = None
            
            # Get PostgreSQL database name from schema RAG
            if self.schema_rag:
                if hasattr(self.schema_rag, 'database_name') and self.schema_rag.database_name:
                    postgres_db_name = self.schema_rag.database_name
                    logger.info(f"  PostgreSQL DB name from schema_rag: {postgres_db_name}")
                elif hasattr(self.schema_rag, 'knowledge_graph_rag') and self.schema_rag.knowledge_graph_rag:
                    # Try to get from knowledge graph - find PostgreSQL database
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
                            logger.info(f"  PostgreSQL DB name from knowledge graph: {postgres_db_name}")
                    except Exception as e:
                        logger.warning(f"Could not get PostgreSQL database name from knowledge graph: {e}")
            
            # Get MongoDB database name from client
            if self.mongodb_client and hasattr(self.mongodb_client, 'database') and self.mongodb_client.database is not None:
                mongodb_db_name = self.mongodb_client.database.name
                logger.info(f"  MongoDB DB name from client: {mongodb_db_name}")
            
            logger.info(f"  Routing query: {state['user_query']}")
            logger.info(f"  Available schemas - PostgreSQL: {postgres_schema is not None}, MongoDB: {mongodb_schema is not None}")
            
            target_db = self.database_router.route_query(
                user_query=state["user_query"],
                postgres_schema=postgres_schema,
                mongodb_schema=mongodb_schema,
                conversation_history=state.get("conversation_history", []),
                postgres_db_name=postgres_db_name,
                mongodb_db_name=mongodb_db_name
            )
            state["target_database"] = target_db
            logger.info(f"  ROUTING DECISION: {target_db}")
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
    
    def _should_try_fallback_after_postgres(self, state: OrchestratorState) -> Literal["try_mongodb", "end"]:
        """Check if we should try MongoDB after PostgreSQL fails."""
        # Only try MongoDB if:
        # 1. PostgreSQL response was not satisfactory
        # 2. MongoDB agent is available
        # 3. We haven't tried MongoDB yet
        # 4. MongoDB is connected
        if (state.get("should_try_fallback", False) and 
            self.mongodb_workflow_agent and 
            not state.get("tried_mongodb", False) and
            self.mongodb_client and hasattr(self.mongodb_client, 'database') and self.mongodb_client.database is not None):
            logger.info("PostgreSQL response not satisfactory, trying MongoDB as fallback")
            self._log_step(state, 4, "Fallback Decision", "in_progress", 
                          "PostgreSQL response not satisfactory, trying MongoDB as fallback...")
            return "try_mongodb"
        return "end"
    
    def _should_try_fallback_after_mongodb(self, state: OrchestratorState) -> Literal["try_postgres", "end"]:
        """Check if we should try PostgreSQL after MongoDB fails."""
        # Only try PostgreSQL if:
        # 1. MongoDB response was not satisfactory
        # 2. PostgreSQL agent is available
        # 3. We haven't tried PostgreSQL yet
        # 4. PostgreSQL is connected
        if (state.get("should_try_fallback", False) and 
            self.postgres_workflow_agent and 
            not state.get("tried_postgres", False) and
            self.postgres_client and hasattr(self.postgres_client, 'connection') and self.postgres_client.connection):
            logger.info("MongoDB response not satisfactory, trying PostgreSQL as fallback")
            self._log_step(state, 4, "Fallback Decision", "in_progress", 
                          "MongoDB response not satisfactory, trying PostgreSQL as fallback...")
            return "try_postgres"
        return "end"
    
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
    
    def _is_response_satisfactory(self, result: Dict) -> bool:
        """
        Check if a workflow agent response is satisfactory.
        
        Args:
            result: Result dictionary from workflow agent
        
        Returns:
            True if response is satisfactory, False otherwise
        """
        if not result:
            return False
        
        final_response = result.get("final_response", "").lower()
        
        # Check for error indicators
        error_indicators = [
            "error", "failed", "not available", "no response", 
            "could not", "unable to", "execution failed",
            "query execution failed", "validation failed"
        ]
        
        if any(indicator in final_response for indicator in error_indicators):
            return False
        
        # Check if there are execution or validation errors
        if result.get("execution_error") or result.get("validation_error"):
            return False
        
        # Check if we have query results
        df = result.get("df")
        if df is not None:
            if len(df) == 0:
                # Empty results - not satisfactory, should try fallback
                logger.warning("  Response has empty results (0 rows), will try fallback")
                return False
            return True
        
        # Check query_results directly (for MongoDB or other formats)
        query_results = result.get("query_results")
        if query_results:
            if isinstance(query_results, dict):
                rows = query_results.get("rows", [])
                if len(rows) == 0:
                    logger.warning("  Response has empty results (0 rows), will try fallback")
                    return False
                return True
        
        # If no results but no errors, check if the response is meaningful
        if final_response and len(final_response) > 20:
            # Response exists and is substantial
            return True
        
        return False
    
    def _execute_postgres_workflow_node(self, state: OrchestratorState) -> OrchestratorState:
        """Node: Execute PostgreSQL workflow agent."""
        self._log_step(state, 3, "PostgreSQL Workflow", "in_progress", 
                      "Executing PostgreSQL workflow agent...")
        
        state["tried_postgres"] = True
        
        if not self.postgres_workflow_agent:
            state["final_response"] = "PostgreSQL workflow agent not available."
            state["should_try_fallback"] = True
            self._log_step(state, 3, "PostgreSQL Workflow", "error", 
                          "PostgreSQL workflow agent not available")
            return state
        
        try:
            result = self.postgres_workflow_agent.run(
                user_query=state["user_query"],
                conversation_history=state.get("conversation_history", [])
            )
            
            state["postgres_result"] = result
            
            # Check if response is satisfactory
            is_satisfactory = self._is_response_satisfactory(result)
            
            if is_satisfactory:
                state["final_response"] = result.get("final_response", "No response from PostgreSQL agent.")
                state["df"] = result.get("df")
                state["query_results"] = result.get("df")
                state["should_try_fallback"] = False
                self._log_step(state, 3, "PostgreSQL Workflow", "completed", 
                              "PostgreSQL workflow completed successfully")
            else:
                # Response not satisfactory, mark for fallback but keep the result
                state["should_try_fallback"] = True
                # Don't overwrite final_response yet - let fallback try first
                if not state.get("final_response"):
                    state["final_response"] = result.get("final_response", "PostgreSQL query did not return satisfactory results.")
                self._log_step(state, 3, "PostgreSQL Workflow", "warning", 
                              "PostgreSQL workflow completed but response not satisfactory, will try fallback")
            
            # Merge steps from PostgreSQL workflow
            if result.get("steps"):
                for step in result["steps"]:
                    step["name"] = f"PostgreSQL: {step.get('name', '')}"
                    state["steps"].append(step)
        except Exception as e:
            logger.error(f"Error in PostgreSQL workflow: {e}")
            state["final_response"] = f"Error executing PostgreSQL query: {str(e)}"
            state["should_try_fallback"] = True
            self._log_step(state, 3, "PostgreSQL Workflow", "error", 
                          f"Error: {str(e)}, will try fallback")
        
        return state
    
    def _execute_mongodb_workflow_node(self, state: OrchestratorState) -> OrchestratorState:
        """Node: Execute MongoDB workflow agent."""
        self._log_step(state, 3, "MongoDB Workflow", "in_progress", 
                      "Executing MongoDB workflow agent...")
        
        state["tried_mongodb"] = True
        
        if not self.mongodb_workflow_agent:
            state["final_response"] = "MongoDB workflow agent not available."
            state["should_try_fallback"] = True
            self._log_step(state, 3, "MongoDB Workflow", "error", 
                          "MongoDB workflow agent not available")
            return state
        
        try:
            result = self.mongodb_workflow_agent.run(
                user_query=state["user_query"],
                conversation_history=state.get("conversation_history", [])
            )
            
            state["mongodb_result"] = result
            
            # Check if response is satisfactory
            is_satisfactory = self._is_response_satisfactory(result)
            
            if is_satisfactory:
                # If this is a fallback attempt and it succeeds, use this result
                if state.get("should_try_fallback", False):
                    self._log_step(state, 4, "MongoDB Workflow (Fallback)", "completed", 
                                  "MongoDB fallback succeeded!")
                state["final_response"] = result.get("final_response", "No response from MongoDB agent.")
                # Extract df from MongoDB result - it should be a DataFrame
                state["df"] = result.get("df")
                state["query_results"] = result.get("df")
                # Also store mongodb_query for display
                state["mongodb_query"] = result.get("mongodb_query")
                state["should_try_fallback"] = False
                self._log_step(state, 3, "MongoDB Workflow", "completed", 
                              "MongoDB workflow completed successfully")
            else:
                # Response not satisfactory, mark for fallback but keep the result
                state["should_try_fallback"] = True
                # Don't overwrite final_response yet - let fallback try first
                if not state.get("final_response"):
                    state["final_response"] = result.get("final_response", "MongoDB query did not return satisfactory results.")
                # Still store df and query even if not satisfactory (for display)
                if result.get("df") is not None:
                    state["df"] = result.get("df")
                    state["query_results"] = result.get("df")
                if result.get("mongodb_query"):
                    state["mongodb_query"] = result.get("mongodb_query")
                self._log_step(state, 3, "MongoDB Workflow", "warning", 
                              "MongoDB workflow completed but response not satisfactory, will try fallback")
            
            # Merge steps from MongoDB workflow
            if result.get("steps"):
                for step in result["steps"]:
                    step["name"] = f"MongoDB: {step.get('name', '')}"
                    state["steps"].append(step)
        except Exception as e:
            logger.error(f"Error in MongoDB workflow: {e}")
            state["final_response"] = f"Error executing MongoDB query: {str(e)}"
            state["should_try_fallback"] = True
            self._log_step(state, 3, "MongoDB Workflow", "error", 
                          f"Error: {str(e)}, will try fallback")
        
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
        
        # Add conditional edges after workflow execution to check for fallback
        workflow.add_conditional_edges(
            "execute_postgres",
            self._should_try_fallback_after_postgres,
            {
                "try_mongodb": "execute_mongodb",
                "end": END
            }
        )
        
        workflow.add_conditional_edges(
            "execute_mongodb",
            self._should_try_fallback_after_mongodb,
            {
                "try_postgres": "execute_postgres",
                "end": END
            }
        )
        
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
        logger.info("=" * 80)
        logger.info("ORCHESTRATOR: Starting query processing")
        logger.info("=" * 80)
        logger.info(f"USER QUERY: {user_query}")
        logger.info(f"Conversation history length: {len(conversation_history or [])}")
        
        # Initialize state
        initial_state: OrchestratorState = {
            "user_query": user_query,
            "conversation_history": conversation_history or [],
            "steps": [],
            "tried_postgres": False,
            "tried_mongodb": False,
            "should_try_fallback": False,
        }
        
        # Run the graph
        final_state = self.compiled_graph.invoke(initial_state)
        
        # Log final results
        logger.info("=" * 80)
        logger.info("ORCHESTRATOR: Query processing completed")
        logger.info(f"Query Type: {final_state.get('query_type', 'unknown')}")
        logger.info(f"Target Database: {final_state.get('target_database', 'unknown')}")
        logger.info(f"Final Response Length: {len(final_state.get('final_response', '') or '')}")
        logger.info(f"Total Steps: {len(final_state.get('steps', []))}")
        logger.info("=" * 80)
        
        # Convert to regular dict for return
        result = dict(final_state)
        return result
