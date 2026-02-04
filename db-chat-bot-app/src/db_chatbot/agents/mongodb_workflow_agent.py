"""
LangGraph-based workflow agent for MongoDB query generation and execution with retry logic.
Similar to WorkflowAgent but for MongoDB queries.
"""
from typing import List, Optional, Dict, TypedDict, Literal
from langgraph.graph import StateGraph, END
from db_chatbot.config.settings import get_logger
from db_chatbot.query_generator.mongodb_query_generator import MongoDBQueryGenerator
from db_chatbot.query_generator.response_generator import ResponseGenerator
from db_chatbot.db_clients.mongodb_client import MongoDBClient
from db_chatbot.rag.knowledge_graph_rag import KnowledgeGraphRAG
import pandas as pd
import ollama
import json

logger = get_logger(__name__)


class MongoDBAgentState(TypedDict, total=False):
    """State schema for the MongoDB LangGraph agent workflow."""
    user_query: str
    query_type: Optional[str]
    schema_info: Optional[Dict]
    mongodb_query: Optional[Dict]
    validation_error: Optional[str]
    execution_error: Optional[str]
    query_results: Optional[Dict]
    retry_count: int
    steps: List[Dict]
    conversation_history: List[Dict]
    final_response: Optional[str]
    df: Optional[pd.DataFrame]


class MongoDBWorkflowAgent:
    """LangGraph-based workflow agent for MongoDB query generation and execution with retry logic."""
    
    def __init__(
        self,
        mongodb_query_generator: MongoDBQueryGenerator,
        mongodb_client: MongoDBClient,
        knowledge_graph_rag: KnowledgeGraphRAG,
        response_generator: Optional[ResponseGenerator] = None,
        max_retries: int = 3
    ):
        """
        Initialize MongoDB workflow agent with LangGraph.
        
        Args:
            mongodb_query_generator: MongoDB query generator instance
            mongodb_client: MongoDB client tool instance
            knowledge_graph_rag: Knowledge Graph RAG instance for schema retrieval
            response_generator: Response generator instance (optional)
            max_retries: Maximum number of retry attempts
        """
        self.mongodb_query_generator = mongodb_query_generator
        self.mongodb_client = mongodb_client
        self.knowledge_graph_rag = knowledge_graph_rag
        self.response_generator = response_generator
        self.max_retries = max_retries
        
        # Build the LangGraph workflow
        self.graph = self._build_graph()
        self.compiled_graph = self.graph.compile()
        
        logger.info(f"MongoDBWorkflowAgent initialized with LangGraph, max_retries={max_retries}")
    
    def _log_step(self, state: MongoDBAgentState, step_num: int, name: str, status: str, message: str, query: Dict = None, error: str = None):
        """Log a workflow step to the state."""
        if "steps" not in state:
            state["steps"] = []
        
        step_info = {
            "step": step_num,
            "name": name,
            "status": status,
            "message": message
        }
        if query:
            step_info["mongodb_query"] = query
        if error:
            step_info["error"] = error
        state["steps"].append(step_info)
        logger.info(f"Step {step_num}: {name} - {status} - {message}")
    
    def _classify_query_node(self, state: MongoDBAgentState) -> MongoDBAgentState:
        """Node: Classify query type and route accordingly."""
        self._log_step(state, 1, "Input Validation & Classification", "in_progress", 
                      "Checking query type...")
        
        user_query = state["user_query"].lower()
        
        # Simple classification
        greeting_words = ['hi', 'hello', 'hey', 'greetings']
        if any(word in user_query for word in greeting_words):
            state["query_type"] = "greeting"
            state["final_response"] = "Hello! 👋 I'm your MongoDB assistant. How can I help you query your database today?"
            return state
        
        query_keywords = ['show', 'list', 'display', 'find', 'get', 'count', 'how many', 'what are', 'which', 'aggregate']
        if any(keyword in user_query for keyword in query_keywords):
            state["query_type"] = "mongodb_query"
        else:
            state["query_type"] = "general_question"
            state["final_response"] = "I can help you query your MongoDB database. Ask me questions like 'Show me all vendors' or 'How many documents are in inventory?'"
            return state
        
        self._log_step(state, 1, "Input Validation & Classification", "completed", 
                      "Query requires MongoDB query generation")
        return state
    
    def _should_continue_to_query(self, state: MongoDBAgentState) -> Literal["mongodb_workflow", "end"]:
        """Conditional edge: Route based on query type."""
        query_type = state.get("query_type")
        if query_type == "mongodb_query":
            return "mongodb_workflow"
        return "end"
    
    def _retrieve_schema_node(self, state: MongoDBAgentState) -> MongoDBAgentState:
        """Node: Retrieve schema from knowledge graph or database."""
        self._log_step(state, 2, "Schema Retrieval (RAG)", "in_progress", 
                      "Retrieving MongoDB schema from knowledge graph...")
        
        # Fetch schema from MongoDB
        schema_info = self.mongodb_client.fetch_schema()
        
        if schema_info:
            collection_count = len(schema_info.get("collections", []))
            state["schema_info"] = schema_info
            self._log_step(state, 2, "Schema Retrieval (RAG)", "completed", 
                          f"Retrieved schema with {collection_count} collection(s)")
            
            # Build/update knowledge graph if available
            if self.knowledge_graph_rag:
                try:
                    # Get database connection info from state or use defaults
                    db_name = schema_info.get("database_name", "vendor_supply_chain_db")
                    self.knowledge_graph_rag.build_graph_from_schema(
                        schema_info,
                        database_name=db_name,
                        host="localhost",  # Could be passed from state
                        port=27017,  # Could be passed from state
                        db_type="mongodb"
                    )
                    logger.info("MongoDB schema loaded into knowledge graph")
                except Exception as e:
                    logger.warning(f"Could not build knowledge graph: {e}")
        else:
            self._log_step(state, 2, "Schema Retrieval (RAG)", "error", 
                          "Failed to retrieve schema")
            state["final_response"] = "Failed to retrieve MongoDB schema. Please check your connection."
        
        return state
    
    def _generate_query_node(self, state: MongoDBAgentState) -> MongoDBAgentState:
        """Node: Generate MongoDB query from natural language."""
        retry_count = state.get("retry_count", 0)
        step_num = 3 + (retry_count * 2)
        
        if retry_count > 0:
            self._log_step(state, step_num, f"MongoDB Query Generation (Retry {retry_count})", "in_progress", 
                          "Regenerating MongoDB query...")
        else:
            self._log_step(state, step_num, "MongoDB Query Generation", "in_progress", 
                          "Generating MongoDB query from natural language...")
        
        # Extract keywords from query for enhanced context retrieval
        query_keywords = state["user_query"].lower().split()
        
        # Use RAG's enhanced context retrieval (includes annotations from knowledge graph)
        schema_context = None
        if self.knowledge_graph_rag:
            try:
                schema_context = self.knowledge_graph_rag.get_mongodb_schema_context(
                    query_keywords=query_keywords
                )
            except Exception as e:
                logger.warning(f"Could not get enhanced context: {e}")
        
        # Generate MongoDB query
        mongodb_query = self.mongodb_query_generator.generate_query(
            natural_language_query=state["user_query"],
            schema_info=state["schema_info"],
            conversation_history=state.get("conversation_history", []),
            enhanced_context=schema_context
        )
        
        if not mongodb_query:
            self._log_step(state, step_num, "MongoDB Query Generation", "error", 
                          "Failed to generate MongoDB query")
            state["final_response"] = "I couldn't generate a MongoDB query for your question. Please try rephrasing it."
            return state
        
        state["mongodb_query"] = mongodb_query
        collection_name = mongodb_query.get("collection", "unknown")
        self._log_step(state, step_num, "MongoDB Query Generation", "completed", 
                      f"Generated MongoDB query for collection: {collection_name}",
                      query=mongodb_query)
        return state
    
    def _validate_query_node(self, state: MongoDBAgentState) -> MongoDBAgentState:
        """Node: Validate MongoDB query."""
        retry_count = state.get("retry_count", 0)
        step_num = 3 + (retry_count * 2) + 1
        
        self._log_step(state, step_num, "MongoDB Query Validation", "in_progress", 
                      "Validating MongoDB query...")
        
        mongodb_query = state.get("mongodb_query")
        
        # Basic validation
        if not mongodb_query:
            state["validation_error"] = "No query generated"
            self._log_step(state, step_num, "MongoDB Query Validation", "error", 
                          "No query to validate")
            return state
        
        # Check for required fields
        if "collection" not in mongodb_query:
            state["validation_error"] = "Query missing collection name"
            self._log_step(state, step_num, "MongoDB Query Validation", "error", 
                          "Query missing collection name", error=state["validation_error"])
            return state
        
        # Check for read-only operations
        if "error" in mongodb_query:
            state["validation_error"] = mongodb_query.get("error", "Query generation error")
            self._log_step(state, step_num, "MongoDB Query Validation", "error", 
                          state["validation_error"], error=state["validation_error"])
            return state
        
        self._log_step(state, step_num, "MongoDB Query Validation", "completed", 
                      "MongoDB query passed validation")
        state["validation_error"] = None
        return state
    
    def _should_retry_validation(self, state: MongoDBAgentState) -> Literal["fix_query", "execute_query"]:
        """Conditional edge: Route based on validation result."""
        if state.get("validation_error"):
            retry_count = state.get("retry_count", 0)
            if retry_count < self.max_retries:
                return "fix_query"
            else:
                state["final_response"] = f"MongoDB query validation failed after {self.max_retries} attempts: {state.get('validation_error')}"
                return "execute_query"  # Will go to end
        return "execute_query"
    
    def _execute_query_node(self, state: MongoDBAgentState) -> MongoDBAgentState:
        """Node: Execute MongoDB query using mongodb_client tool."""
        if state.get("validation_error") and state.get("retry_count", 0) >= self.max_retries:
            return state
        
        retry_count = state.get("retry_count", 0)
        step_num = 3 + (retry_count * 2) + 2
        
        self._log_step(state, step_num, "MongoDB Query Execution", "in_progress", 
                      "Executing MongoDB query...")
        
        mongodb_query = state.get("mongodb_query")
        success, results, error = self.mongodb_client.execute_query(mongodb_query)
        
        if success and results:
            doc_count = results.get("count", 0)
            self._log_step(state, step_num, "MongoDB Query Execution", "completed", 
                          f"Query executed successfully. Returned {doc_count} document(s)")
            state["query_results"] = results
            state["execution_error"] = None
            return state
        else:
            self._log_step(state, step_num, "MongoDB Query Execution", "error", 
                          f"Execution failed: {error}", error=error)
            state["execution_error"] = error
            return state
    
    def _should_retry_execution(self, state: MongoDBAgentState) -> Literal["fix_query", "generate_response", "end"]:
        """Conditional edge: Route based on execution result."""
        if state.get("execution_error"):
            retry_count = state.get("retry_count", 0)
            if retry_count < self.max_retries:
                return "fix_query"
            else:
                state["final_response"] = f"MongoDB query execution failed after {self.max_retries} attempts. Error: {state.get('execution_error')}"
                return "end"
        
        if state.get("validation_error") and state.get("retry_count", 0) >= self.max_retries:
            return "end"
        
        if state.get("query_results"):
            return "generate_response"
        
        return "end"
    
    def _fix_query_node(self, state: MongoDBAgentState) -> MongoDBAgentState:
        """Node: Attempt to fix failed MongoDB query."""
        retry_count = state.get("retry_count", 0)
        state["retry_count"] = retry_count + 1
        
        step_num = 3 + (retry_count * 2) + 2
        
        failed_query = state.get("mongodb_query")
        error = state.get("execution_error") or state.get("validation_error")
        user_query = state["user_query"]
        
        self._log_step(state, step_num, f"Query Fix (Attempt {retry_count + 1}/{self.max_retries})", 
                      "in_progress", f"Attempting to fix MongoDB query. Previous error: {error[:100] if error else 'Unknown error'}...",
                      query=failed_query, error=error)
        
        fixed_query = self._fix_query(failed_query, error, user_query)
        if fixed_query and fixed_query != failed_query:
            state["mongodb_query"] = fixed_query
            self._log_step(state, step_num + 1, f"Query Fixed (Attempt {retry_count + 1}/{self.max_retries})", 
                          "completed", "Successfully generated new MongoDB query", 
                          query=fixed_query)
        else:
            self._log_step(state, step_num + 1, f"Query Fix Failed (Attempt {retry_count + 1}/{self.max_retries})", 
                          "error", "Could not generate a fixed query", 
                          query=failed_query, error=error)
        
        return state
    
    def _fix_query(self, failed_query: Dict, error: str, user_query: str) -> Optional[Dict]:
        """Attempt to fix a failed MongoDB query."""
        try:
            fix_prompt = f"""The following MongoDB query failed with error: {error}

Failed Query:
{json.dumps(failed_query, indent=2)}

User's original question: {user_query}

Please generate a corrected MongoDB query that fixes the error. Only return the corrected query as JSON, nothing else. Make sure it's a valid MongoDB query (find or aggregate operation)."""
            
            response = ollama.generate(
                model=self.mongodb_query_generator.model_name,
                prompt=fix_prompt,
                options={"temperature": 0.1, "num_predict": 512}
            )
            
            fixed_query_text = response['response'].strip()
            # Clean up markdown if present
            if fixed_query_text.startswith("```json"):
                fixed_query_text = fixed_query_text[7:]
            elif fixed_query_text.startswith("```"):
                fixed_query_text = fixed_query_text[3:]
            if fixed_query_text.endswith("```"):
                fixed_query_text = fixed_query_text[:-3]
            fixed_query_text = fixed_query_text.strip()
            
            import json
            fixed_query = json.loads(fixed_query_text)
            return fixed_query
            
        except Exception as e:
            logger.error(f"Error fixing MongoDB query: {str(e)}")
            return None
    
    def _generate_response_node(self, state: MongoDBAgentState) -> MongoDBAgentState:
        """Node: Generate natural language response from query results."""
        retry_count = state.get("retry_count", 0)
        step_num = 3 + (retry_count * 2) + 3
        
        self._log_step(state, step_num, "Response Generation", "in_progress", 
                      "Generating natural language response...")
        
        results = state.get("query_results")
        if results:
            documents = results.get("documents", [])
            if documents:
                df = pd.DataFrame(documents)
                state["df"] = df
                row_count = len(df)
                
                if self.response_generator:
                    try:
                        response = self.response_generator.generate_response(
                            user_query=state["user_query"],
                            query_results=df,
                            sql_query=str(state.get("mongodb_query")),  # Convert to string for compatibility
                            conversation_history=state.get("conversation_history", [])
                        )
                        state["final_response"] = response
                    except Exception as e:
                        logger.error(f"Error generating response: {str(e)}")
                        state["final_response"] = f"I found {row_count} document(s) for your query."
                else:
                    state["final_response"] = f"I found {row_count} document(s) for your query."
            else:
                state["final_response"] = "No documents found matching your query."
            
            self._log_step(state, step_num, "Response Generation", "completed", 
                          "Response generated successfully")
        
        return state
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow graph."""
        workflow = StateGraph(MongoDBAgentState)
        
        # Add nodes
        workflow.add_node("classify_query", self._classify_query_node)
        workflow.add_node("retrieve_schema", self._retrieve_schema_node)
        workflow.add_node("generate_query", self._generate_query_node)
        workflow.add_node("validate_query", self._validate_query_node)
        workflow.add_node("execute_query", self._execute_query_node)
        workflow.add_node("fix_query", self._fix_query_node)
        workflow.add_node("generate_response", self._generate_response_node)
        
        # Set entry point
        workflow.set_entry_point("classify_query")
        
        # Add edges
        workflow.add_conditional_edges(
            "classify_query",
            self._should_continue_to_query,
            {
                "mongodb_workflow": "retrieve_schema",
                "end": END
            }
        )
        
        workflow.add_edge("retrieve_schema", "generate_query")
        workflow.add_edge("generate_query", "validate_query")
        
        workflow.add_conditional_edges(
            "validate_query",
            self._should_retry_validation,
            {
                "fix_query": "fix_query",
                "execute_query": "execute_query"
            }
        )
        
        workflow.add_conditional_edges(
            "execute_query",
            self._should_retry_execution,
            {
                "fix_query": "fix_query",
                "generate_response": "generate_response",
                "end": END
            }
        )
        
        # Loop back from fix_query to validate_query
        workflow.add_edge("fix_query", "validate_query")
        workflow.add_edge("generate_response", END)
        
        return workflow
    
    def run(
        self,
        user_query: str,
        conversation_history: List[Dict] = None
    ) -> Dict:
        """
        Run the MongoDB agent workflow using LangGraph.
        
        Args:
            user_query: User's natural language query
            conversation_history: Previous conversation messages
        
        Returns:
            Dictionary with workflow results
        """
        # Initialize state
        initial_state: MongoDBAgentState = {
            "user_query": user_query,
            "conversation_history": conversation_history or [],
            "retry_count": 0,
            "steps": [],
        }
        
        # Run the graph
        final_state = self.compiled_graph.invoke(initial_state)
        
        # Convert to regular dict for return
        result = dict(final_state)
        return result
