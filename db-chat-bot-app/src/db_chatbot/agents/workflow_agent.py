"""
LangGraph-based workflow agent for SQL query generation and execution with retry logic.
Uses db_clients as tools, RAG for schema, and guardrails for validation.
"""
from typing import List, Optional, Dict, TypedDict, Literal, Annotated
from langgraph.graph import StateGraph, END
from db_chatbot.config.settings import get_logger
from db_chatbot.guardrails.input_guardrails import InputGuardrails
from db_chatbot.query_generator.sql_generator import SQLGenerator
from db_chatbot.query_generator.response_generator import ResponseGenerator
from db_chatbot.db_clients.postgres_client import PostgresClient
from db_chatbot.rag.schema_rag import SchemaRAG
from db_chatbot.query_intent.classifier import QueryClassifier
import pandas as pd
import ollama

logger = get_logger(__name__)


class AgentState(TypedDict, total=False):
    """State schema for the LangGraph agent workflow."""
    user_query: str
    query_type: Optional[str]
    schema_info: Optional[Dict]
    sql_query: Optional[str]
    validation_error: Optional[str]
    execution_error: Optional[str]
    query_results: Optional[Dict]
    retry_count: int
    steps: List[Dict]
    conversation_history: List[Dict]
    final_response: Optional[str]
    df: Optional[pd.DataFrame]


class WorkflowAgent:
    """LangGraph-based workflow agent for SQL query generation and execution with retry logic."""
    
    def __init__(
        self,
        sql_generator: SQLGenerator,
        db_client: PostgresClient,
        schema_rag: SchemaRAG,
        response_generator: Optional[ResponseGenerator] = None,
        query_classifier: Optional[QueryClassifier] = None,
        max_retries: int = 3
    ):
        """
        Initialize workflow agent with LangGraph.
        
        Args:
            sql_generator: SQL generator instance
            db_client: Database client tool instance
            schema_rag: Schema RAG instance for schema retrieval
            response_generator: Response generator instance (optional)
            query_classifier: Query classifier instance (optional)
            max_retries: Maximum number of retry attempts
        """
        self.sql_generator = sql_generator
        self.db_client = db_client
        self.schema_rag = schema_rag
        self.response_generator = response_generator
        self.query_classifier = query_classifier
        self.max_retries = max_retries
        
        # Build the LangGraph workflow
        self.graph = self._build_graph()
        self.compiled_graph = self.graph.compile()
        
        logger.info(f"WorkflowAgent initialized with LangGraph, max_retries={max_retries}")
    
    def _log_step(self, state: AgentState, step_num: int, name: str, status: str, message: str):
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
        logger.info(f"Step {step_num}: {name} - {status} - {message}")
    
    def _classify_query_node(self, state: AgentState) -> AgentState:
        """Node: Classify query type and route accordingly."""
        self._log_step(state, 1, "Input Validation & Classification", "in_progress", 
                      "Checking query type and guardrails...")
        
        user_query = state["user_query"]
        
        # Use QueryClassifier if available
        if self.query_classifier:
            try:
                schema_info = self.schema_rag.get_schema()
                needs_sql, reasoning = self.query_classifier.classify_query(
                    user_query,
                    schema_info,
                    state.get("conversation_history", [])
                )
                query_type = "sql_query" if needs_sql else "general_question"
                self._log_step(state, 1, "Input Validation & Classification", "completed", 
                              f"Query classified: {reasoning}")
            except Exception as e:
                logger.error(f"Error in QueryClassifier: {e}, falling back to simple classification")
                query_type = self._classify_query(user_query)
                self._log_step(state, 1, "Input Validation & Classification", "completed", 
                              f"Query classified as: {query_type}")
        else:
            query_type = self._classify_query(user_query)
            self._log_step(state, 1, "Input Validation & Classification", "completed", 
                          f"Query classified as: {query_type}")
        
        state["query_type"] = query_type
        
        # Handle greetings and general questions
        if query_type == "greeting":
            state["final_response"] = "Hello! 👋 I'm your database assistant. How can I help you query your database today?"
            self._log_step(state, 1, "Input Validation & Classification", "completed", 
                          "Query classified as greeting")
            return state
        
        if query_type == "general_question":
            state["final_response"] = "I can help you query your database. Ask me questions like 'Show me all products' or 'How many orders are there?'"
            self._log_step(state, 1, "Input Validation & Classification", "completed", 
                          "Query classified as general question")
            return state
        
        self._log_step(state, 1, "Input Validation & Classification", "completed", 
                      "Query requires SQL generation")
        return state
    
    def _should_continue_to_sql(self, state: AgentState) -> Literal["sql_workflow", "end"]:
        """Conditional edge: Route based on query type."""
        query_type = state.get("query_type")
        if query_type == "sql_query":
            return "sql_workflow"
        return "end"
    
    def _retrieve_schema_node(self, state: AgentState) -> AgentState:
        """Node: Retrieve schema from RAG or database."""
        self._log_step(state, 2, "Schema Retrieval (RAG)", "in_progress", 
                      "Retrieving database schema from RAG...")
        
        schema_info = self.schema_rag.get_schema()
        
        if schema_info:
            table_count = len(schema_info.get("tables", []))
            state["schema_info"] = schema_info
            self._log_step(state, 2, "Schema Retrieval (RAG)", "completed", 
                          f"Retrieved schema with {table_count} table(s) from RAG")
        else:
            # Fetch from database client if not in RAG
            self._log_step(state, 2, "Schema Retrieval (RAG)", "in_progress", 
                          "Schema not in RAG, fetching from database...")
            schema_info = self.db_client.fetch_schema()
            if schema_info:
                self.schema_rag.load_schema(schema_info)
                table_count = len(schema_info.get("tables", []))
                state["schema_info"] = schema_info
                self._log_step(state, 2, "Schema Retrieval (RAG)", "completed", 
                              f"Fetched and stored schema with {table_count} table(s)")
            else:
                self._log_step(state, 2, "Schema Retrieval (RAG)", "error", 
                              "Failed to retrieve schema")
                state["final_response"] = "Failed to retrieve database schema. Please check your connection."
        
        return state
    
    def _generate_sql_node(self, state: AgentState) -> AgentState:
        """Node: Generate SQL query from natural language."""
        retry_count = state.get("retry_count", 0)
        step_num = 3 + (retry_count * 2)
        
        if retry_count > 0:
            self._log_step(state, step_num, f"SQL Generation (Retry {retry_count})", "in_progress", 
                          "Regenerating SQL query...")
        else:
            self._log_step(state, step_num, "SQL Generation", "in_progress", 
                          "Generating SQL query from natural language...")
        
        # Extract keywords from query for enhanced context retrieval
        query_keywords = state["user_query"].lower().split()
        
        # Use RAG's enhanced context retrieval (includes annotations from knowledge graph)
        schema_context = self.schema_rag.format_schema_for_context(
            query_keywords=query_keywords
        )
        
        # For backward compatibility, still pass schema_info but use enhanced context in prompt
        sql_query = self.sql_generator.generate_sql(
            natural_language_query=state["user_query"],
            schema_info=state["schema_info"],
            conversation_history=state.get("conversation_history", []),
            enhanced_context=schema_context  # Pass enhanced context
        )
        
        if not sql_query:
            self._log_step(state, step_num, "SQL Generation", "error", 
                          "Failed to generate SQL query")
            state["final_response"] = "I couldn't generate a SQL query for your question. Please try rephrasing it."
            return state
        
        state["sql_query"] = sql_query
        self._log_step(state, step_num, "SQL Generation", "completed", 
                      f"Generated SQL query: {sql_query[:60]}...")
        return state
    
    def _validate_sql_node(self, state: AgentState) -> AgentState:
        """Node: Validate SQL query using input guardrails."""
        retry_count = state.get("retry_count", 0)
        step_num = 3 + (retry_count * 2) + 1
        
        self._log_step(state, step_num, "SQL Validation (Input Guardrails)", "in_progress", 
                      "Validating SQL query for security and syntax...")
        
        sql_query = state.get("sql_query")
        is_valid, validation_error = InputGuardrails.validate_query(sql_query)
        
        if not is_valid:
            self._log_step(state, step_num, "SQL Validation (Input Guardrails)", "error", 
                          f"Validation failed: {validation_error}")
            state["validation_error"] = validation_error
            return state
        
        self._log_step(state, step_num, "SQL Validation (Input Guardrails)", "completed", 
                      "SQL query passed validation")
        state["validation_error"] = None
        return state
    
    def _should_retry_validation(self, state: AgentState) -> Literal["fix_query", "execute_query"]:
        """Conditional edge: Route based on validation result."""
        if state.get("validation_error"):
            retry_count = state.get("retry_count", 0)
            if retry_count < self.max_retries:
                return "fix_query"
            else:
                state["final_response"] = f"SQL validation failed after {self.max_retries} attempts: {state.get('validation_error')}"
                return "execute_query"  # Will go to end
        return "execute_query"
    
    def _execute_query_node(self, state: AgentState) -> AgentState:
        """Node: Execute SQL query using db_client tool."""
        # Check if we should skip execution (validation failed max retries)
        if state.get("validation_error") and state.get("retry_count", 0) >= self.max_retries:
            return state
        
        retry_count = state.get("retry_count", 0)
        step_num = 3 + (retry_count * 2) + 2
        
        self._log_step(state, step_num, "Query Execution (DB Client Tool)", "in_progress", 
                      "Executing SQL query...")
        
        sql_query = state.get("sql_query")
        success, results, error = self.db_client.execute_query(sql_query)
        
        if success and results and "columns" in results:
            row_count = len(results.get("rows", []))
            self._log_step(state, step_num, "Query Execution (DB Client Tool)", "completed", 
                          f"Query executed successfully. Returned {row_count} row(s)")
            state["query_results"] = results
            state["execution_error"] = None
            return state
        else:
            self._log_step(state, step_num, "Query Execution (DB Client Tool)", "error", 
                          f"Execution failed: {error}")
            state["execution_error"] = error
            return state
    
    def _should_retry_execution(self, state: AgentState) -> Literal["fix_query", "generate_response", "end"]:
        """Conditional edge: Route based on execution result."""
        if state.get("execution_error"):
            retry_count = state.get("retry_count", 0)
            if retry_count < self.max_retries:
                return "fix_query"
            else:
                state["final_response"] = f"Query execution failed after {self.max_retries} attempts. Error: {state.get('execution_error')}"
                return "end"
        
        if state.get("validation_error") and state.get("retry_count", 0) >= self.max_retries:
            return "end"
        
        if state.get("query_results"):
            return "generate_response"
        
        return "end"
    
    def _fix_query_node(self, state: AgentState) -> AgentState:
        """Node: Attempt to fix failed SQL query."""
        retry_count = state.get("retry_count", 0)
        state["retry_count"] = retry_count + 1
        
        step_num = 3 + (retry_count * 2) + 2
        self._log_step(state, step_num, f"Query Fix (Attempt {retry_count + 1}/{self.max_retries})", 
                      "in_progress", "Attempting to fix SQL query...")
        
        failed_query = state.get("sql_query")
        error = state.get("execution_error") or state.get("validation_error")
        user_query = state["user_query"]
        
        fixed_query = self._fix_query(failed_query, error, user_query)
        if fixed_query and fixed_query != failed_query:
            state["sql_query"] = fixed_query
            self._log_step(state, step_num, f"Query Fix (Attempt {retry_count + 1}/{self.max_retries})", 
                          "completed", f"Generated fixed query: {fixed_query[:60]}...")
        else:
            self._log_step(state, step_num, f"Query Fix (Attempt {retry_count + 1}/{self.max_retries})", 
                          "error", "Could not fix query")
        
        return state
    
    def _generate_response_node(self, state: AgentState) -> AgentState:
        """Node: Generate natural language response from query results."""
        retry_count = state.get("retry_count", 0)
        step_num = 3 + (retry_count * 2) + 3
        
        self._log_step(state, step_num, "Response Generation", "in_progress", 
                      "Generating natural language response...")
        
        results = state.get("query_results")
        if results:
            df = pd.DataFrame(results["rows"], columns=results["columns"])
            state["df"] = df
            row_count = len(df)
            
            if self.response_generator:
                try:
                    response = self.response_generator.generate_response(
                        user_query=state["user_query"],
                        query_results=df,
                        sql_query=state.get("sql_query"),
                        conversation_history=state.get("conversation_history", [])
                    )
                    state["final_response"] = response
                except Exception as e:
                    logger.error(f"Error generating response: {str(e)}")
                    state["final_response"] = f"I found {row_count} result(s) for your query."
            else:
                state["final_response"] = f"I found {row_count} result(s) for your query."
            
            self._log_step(state, step_num, "Response Generation", "completed", 
                          "Response generated successfully")
        
        return state
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow graph."""
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("classify_query", self._classify_query_node)
        workflow.add_node("retrieve_schema", self._retrieve_schema_node)
        workflow.add_node("generate_sql", self._generate_sql_node)
        workflow.add_node("validate_sql", self._validate_sql_node)
        workflow.add_node("execute_query", self._execute_query_node)
        workflow.add_node("fix_query", self._fix_query_node)
        workflow.add_node("generate_response", self._generate_response_node)
        
        # Set entry point
        workflow.set_entry_point("classify_query")
        
        # Add edges
        workflow.add_conditional_edges(
            "classify_query",
            self._should_continue_to_sql,
            {
                "sql_workflow": "retrieve_schema",
                "end": END
            }
        )
        
        workflow.add_edge("retrieve_schema", "generate_sql")
        workflow.add_edge("generate_sql", "validate_sql")
        
        workflow.add_conditional_edges(
            "validate_sql",
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
        
        # Loop back from fix_query to validate_sql (fixed queries need re-validation)
        workflow.add_edge("fix_query", "validate_sql")
        workflow.add_edge("generate_response", END)
        
        return workflow
    
    def visualize_graph(self, output_file: str = "workflow_graph.mmd") -> str:
        """
        Generate a Mermaid diagram of the workflow graph.
        
        Args:
            output_file: Optional file path to save the Mermaid diagram
        
        Returns:
            Mermaid diagram as string
        """
        try:
            mermaid_diagram = self.compiled_graph.get_graph().draw_mermaid()
            if output_file:
                with open(output_file, "w") as f:
                    f.write(mermaid_diagram)
                logger.info(f"Graph visualization saved to {output_file}")
            return mermaid_diagram
        except Exception as e:
            logger.error(f"Error generating graph visualization: {e}")
            return ""
    
    def run(
        self,
        user_query: str,
        conversation_history: List[Dict] = None
    ) -> Dict:
        """
        Run the agent workflow using LangGraph.
        
        Args:
            user_query: User's natural language query
            conversation_history: Previous conversation messages
        
        Returns:
            Dictionary with workflow results
        """
        # Initialize state
        initial_state: AgentState = {
            "user_query": user_query,
            "conversation_history": conversation_history or [],
            "retry_count": 0,
            "steps": [],
        }
        
        # Run the graph
        final_state = self.compiled_graph.invoke(initial_state)
        
        # Convert to regular dict for return (remove TypedDict typing)
        result = dict(final_state)
        return result
    
    def _classify_query(self, user_query: str) -> str:
        """Classify the query type (fallback method)."""
        query_lower = user_query.lower()
        
        greeting_words = ['hi', 'hello', 'hey', 'greetings', 'good morning', 'good afternoon', 'good evening']
        if any(word in query_lower for word in greeting_words):
            return "greeting"
        
        sql_keywords = ['show', 'list', 'display', 'find', 'get', 'count', 'how many', 'what are', 'which', 'select']
        if any(keyword in query_lower for keyword in sql_keywords):
            return "sql_query"
        
        return "general_question"
    
    def _fix_query(self, failed_query: str, error: str, user_query: str) -> Optional[str]:
        """Attempt to fix a failed SQL query."""
        try:
            fix_prompt = f"""The following SQL query failed with error: {error}

Failed Query:
{failed_query}

User's original question: {user_query}

Please generate a corrected SQL query that fixes the error. Only return the corrected SQL query, nothing else. Make sure it's a valid PostgreSQL SELECT query."""
            
            response = ollama.generate(
                model=self.sql_generator.model_name,
                prompt=fix_prompt,
                options={"temperature": 0.1, "num_predict": 512}
            )
            
            fixed_query = response['response'].strip()
            # Clean up markdown if present
            if fixed_query.startswith("```sql"):
                fixed_query = fixed_query[6:]
            elif fixed_query.startswith("```"):
                fixed_query = fixed_query[3:]
            if fixed_query.endswith("```"):
                fixed_query = fixed_query[:-3]
            fixed_query = fixed_query.strip()
            
            return fixed_query
            
        except Exception as e:
            logger.error(f"Error fixing query: {str(e)}")
            return None
