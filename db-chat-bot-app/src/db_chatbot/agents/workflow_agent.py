"""
Workflow-based SQL query agent with retry logic and step-by-step execution.
Uses db_clients as tools, RAG for schema, and guardrails for validation.
"""
from typing import List, Optional, Dict
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


class WorkflowAgent:
    """Workflow-based agent for SQL query generation and execution with retry logic."""
    
    def __init__(
        self,
        sql_generator: SQLGenerator,
        db_client: PostgresClient,  # Database client as tool
        schema_rag: SchemaRAG,  # Schema RAG for schema retrieval
        response_generator: Optional[ResponseGenerator] = None,
        query_classifier: Optional[QueryClassifier] = None,
        max_retries: int = 3
    ):
        """
        Initialize workflow agent.
        
        Args:
            sql_generator: SQL generator instance
            db_client: Database client tool instance
            schema_rag: Schema RAG instance for schema retrieval
            response_generator: Response generator instance (optional)
            query_classifier: Query classifier instance (optional)
            max_retries: Maximum number of retry attempts
        """
        self.sql_generator = sql_generator
        self.db_client = db_client  # Database client as tool
        self.schema_rag = schema_rag  # Schema RAG for schema retrieval
        self.response_generator = response_generator
        self.query_classifier = query_classifier
        self.max_retries = max_retries
        logger.info(f"WorkflowAgent initialized with max_retries={max_retries}")
    
    def run(
        self,
        user_query: str,
        conversation_history: List[Dict] = None
    ) -> Dict:
        """
        Run the agent workflow.
        
        Args:
            user_query: User's natural language query
            conversation_history: Previous conversation messages
        
        Returns:
            Dictionary with workflow results
        """
        state = {
            "user_query": user_query,
            "query_type": None,
            "schema_info": None,
            "sql_query": None,
            "validation_error": None,
            "execution_error": None,
            "query_results": None,
            "retry_count": 0,
            "steps": [],
            "conversation_history": conversation_history or [],
            "final_response": None,
            "df": None
        }
        
        def _log_step(step_num: int, name: str, status: str, message: str):
            """Log a workflow step."""
            step_info = {
                "step": step_num,
                "name": name,
                "status": status,
                "message": message
            }
            state["steps"].append(step_info)
            logger.info(f"Step {step_num}: {name} - {status} - {message}")
        
        # Step 1: Validate input and classify query (using input guardrails and query intent)
        _log_step(1, "Input Validation & Classification", "in_progress", "Checking query type and guardrails...")
        
        # Use QueryClassifier if available, otherwise fallback to simple classification
        if self.query_classifier:
            try:
                # Get schema from RAG for classification context
                schema_info = self.schema_rag.get_schema()
                needs_sql, reasoning = self.query_classifier.classify_query(
                    user_query,
                    schema_info,
                    state["conversation_history"]
                )
                query_type = "sql_query" if needs_sql else "general_question"
                _log_step(1, "Input Validation & Classification", "completed", f"Query classified: {reasoning}")
            except Exception as e:
                logger.error(f"Error in QueryClassifier: {e}, falling back to simple classification")
                query_type = self._classify_query(user_query)
                _log_step(1, "Input Validation & Classification", "completed", f"Query classified as: {query_type}")
        else:
            query_type = self._classify_query(user_query)
            _log_step(1, "Input Validation & Classification", "completed", f"Query classified as: {query_type}")
        
        state["query_type"] = query_type
        
        if query_type == "greeting":
            state["final_response"] = "Hello! 👋 I'm your database assistant. How can I help you query your database today?"
            _log_step(1, "Input Validation & Classification", "completed", "Query classified as greeting")
            return state
        
        if query_type == "general_question":
            state["final_response"] = "I can help you query your database. Ask me questions like 'Show me all products' or 'How many orders are there?'"
            _log_step(1, "Input Validation & Classification", "completed", "Query classified as general question")
            return state
        
        _log_step(1, "Input Validation & Classification", "completed", "Query requires SQL generation")
        
        # Step 2: Get schema from RAG (database schema as RAG)
        _log_step(2, "Schema Retrieval (RAG)", "in_progress", "Retrieving database schema from RAG...")
        schema_info = self.schema_rag.get_schema()
        
        if schema_info:
            table_count = len(schema_info.get("tables", []))
            state["schema_info"] = schema_info
            _log_step(2, "Schema Retrieval (RAG)", "completed", f"Retrieved schema with {table_count} table(s) from RAG")
        else:
            # Try to fetch from database client tool if not in RAG
            _log_step(2, "Schema Retrieval (RAG)", "in_progress", "Schema not in RAG, fetching from database...")
            schema_info = self.db_client.fetch_schema()
            if schema_info:
                self.schema_rag.load_schema(schema_info)  # Store in RAG for future use
                table_count = len(schema_info.get("tables", []))
                state["schema_info"] = schema_info
                _log_step(2, "Schema Retrieval (RAG)", "completed", f"Fetched and stored schema with {table_count} table(s)")
            else:
                _log_step(2, "Schema Retrieval (RAG)", "error", "Failed to retrieve schema")
                state["final_response"] = "Failed to retrieve database schema. Please check your connection."
                return state
        
        # Step 3-N: Generate, validate, execute, retry loop
        retry_count = 0
        while retry_count <= self.max_retries:
            attempt_num = retry_count + 1
            
            # Step 3: Generate SQL query
            step_num = 3 + (retry_count * 3)
            if retry_count > 0:
                _log_step(step_num, f"SQL Generation (Retry {retry_count})", "in_progress", "Regenerating SQL query...")
            else:
                _log_step(step_num, "SQL Generation", "in_progress", "Generating SQL query from natural language...")
            
            sql_query = self.sql_generator.generate_sql(
                natural_language_query=user_query,
                schema_info=state["schema_info"],
                conversation_history=state["conversation_history"]
            )
            
            if not sql_query:
                _log_step(step_num, "SQL Generation", "error", "Failed to generate SQL query")
                state["final_response"] = "I couldn't generate a SQL query for your question. Please try rephrasing it."
                return state
            
            state["sql_query"] = sql_query
            _log_step(step_num, "SQL Generation", "completed", f"Generated SQL query: {sql_query[:60]}...")
            
            # Step 4: Validate SQL query (using input guardrails)
            _log_step(step_num + 1, "SQL Validation (Input Guardrails)", "in_progress", "Validating SQL query for security and syntax...")
            is_valid, validation_error = InputGuardrails.validate_query(sql_query)
            
            if not is_valid:
                _log_step(step_num + 1, "SQL Validation (Input Guardrails)", "error", f"Validation failed: {validation_error}")
                state["validation_error"] = validation_error
                if retry_count < self.max_retries:
                    retry_count += 1
                    state["retry_count"] = retry_count
                    continue
                else:
                    state["final_response"] = f"SQL validation failed after {self.max_retries} attempts: {validation_error}"
                    return state
            
            _log_step(step_num + 1, "SQL Validation (Input Guardrails)", "completed", "SQL query passed validation")
            
            # Step 5: Execute query (using db_client tool)
            _log_step(step_num + 2, "Query Execution (DB Client Tool)", "in_progress", "Executing SQL query...")
            success, results, error = self.db_client.execute_query(sql_query)
            
            if success and results and "columns" in results:
                row_count = len(results.get("rows", []))
                _log_step(step_num + 2, "Query Execution (DB Client Tool)", "completed", f"Query executed successfully. Returned {row_count} row(s)")
                state["query_results"] = results
                state["execution_error"] = None
                
                # Step 6: Generate response
                _log_step(step_num + 3, "Response Generation", "in_progress", "Generating natural language response...")
                df = pd.DataFrame(results["rows"], columns=results["columns"])
                state["df"] = df
                
                if self.response_generator:
                    try:
                        response = self.response_generator.generate_response(
                            user_query=user_query,
                            query_results=df,
                            sql_query=sql_query,
                            conversation_history=state["conversation_history"]
                        )
                        state["final_response"] = response
                    except Exception as e:
                        logger.error(f"Error generating response: {str(e)}")
                        state["final_response"] = f"I found {row_count} result(s) for your query."
                else:
                    state["final_response"] = f"I found {row_count} result(s) for your query."
                
                _log_step(step_num + 3, "Response Generation", "completed", "Response generated successfully")
                return state
            
            else:
                # Execution failed - try to fix
                _log_step(step_num + 2, "Query Execution (DB Client Tool)", "error", f"Execution failed: {error}")
                state["execution_error"] = error
                
                if retry_count < self.max_retries:
                    retry_count += 1
                    state["retry_count"] = retry_count
                    _log_step(step_num + 2, f"Query Fix (Attempt {retry_count}/{self.max_retries})", "in_progress", f"Attempting to fix SQL query...")
                    
                    # Fix the query
                    fixed_query = self._fix_query(sql_query, error, user_query)
                    if fixed_query and fixed_query != sql_query:
                        state["sql_query"] = fixed_query
                        _log_step(step_num + 2, f"Query Fix (Attempt {retry_count}/{self.max_retries})", "completed", f"Generated fixed query: {fixed_query[:60]}...")
                        continue
                    else:
                        _log_step(step_num + 2, f"Query Fix (Attempt {retry_count}/{self.max_retries})", "error", "Could not fix query")
                else:
                    state["final_response"] = f"Query execution failed after {self.max_retries} attempts. Error: {error}"
                    return state
        
        # Max retries reached
        state["final_response"] = f"Could not execute query after {self.max_retries} retry attempts."
        return state
    
    def _classify_query(self, user_query: str) -> str:
        """Classify the query type (fallback method)."""
        query_lower = user_query.lower()
        
        # Check for greetings
        greeting_words = ['hi', 'hello', 'hey', 'greetings', 'good morning', 'good afternoon', 'good evening']
        if any(word in query_lower for word in greeting_words):
            return "greeting"
        
        # Check if it needs SQL
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
