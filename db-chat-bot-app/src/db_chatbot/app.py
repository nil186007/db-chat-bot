"""
Streamlit-based PostgreSQL chatbot with natural language to SQL conversion.
"""
import sys
from pathlib import Path

# Add src directory to Python path
app_dir = Path(__file__).parent.parent
if str(app_dir) not in sys.path:
    sys.path.insert(0, str(app_dir))

import streamlit as st
import pandas as pd
from db_chatbot.core.database import DatabaseConnection
from db_chatbot.core.sql_generator import SQLGenerator
from db_chatbot.core.response_generator import ResponseGenerator
from db_chatbot.handlers.query_handler import QueryHandler
from db_chatbot.agents.workflow_agent import WorkflowAgent
from db_chatbot.config.settings import get_logger

logger = get_logger(__name__)

# Page configuration
st.set_page_config(
    page_title="Database ChatBot",
    page_icon="💬",
    layout="wide"
)

# Initialize session state
if "db_conn" not in st.session_state:
    st.session_state.db_conn = DatabaseConnection()
    st.session_state.connected = False
    st.session_state.schema_loaded = False
    st.session_state.sql_generator = None
    st.session_state.messages = []
    st.session_state.schema_info = None
    st.session_state.pending_query = None  # Store pending query awaiting confirmation
    logger.info("Session state initialized")

# Always ensure query_handler is initialized
if "query_handler" not in st.session_state:
    st.session_state.query_handler = QueryHandler()
    logger.debug("QueryHandler initialized in session state")

if "response_generator" not in st.session_state:
    st.session_state.response_generator = None
    logger.debug("ResponseGenerator placeholder initialized")

if "workflow_agent" not in st.session_state:
    st.session_state.workflow_agent = None
    logger.debug("WorkflowAgent placeholder initialized")


def reset_connection():
    """Reset database connection and related state."""
    logger.info("Resetting database connection")
    if st.session_state.db_conn:
        st.session_state.db_conn.close()
    st.session_state.connected = False
    st.session_state.schema_loaded = False
    st.session_state.schema_info = None
    st.session_state.messages = []
    st.session_state.pending_query = None
    # Note: query_handler is not reset as it's stateless


def main():
    logger.info("Starting main application")
    st.title("🗄️ Database ChatBot")
    st.markdown("Connect to PostgreSQL and query your database using natural language!")
    
    # Sidebar for connection settings
    with st.sidebar:
        st.header("⚙️ Settings")
        
        # Database connection form
        st.subheader("Database Connection")
        
        with st.form("db_connection_form"):
            db_host = st.text_input("Host", value="localhost")
            db_port = st.number_input("Port", value=5432, min_value=1, max_value=65535)
            db_name = st.text_input("Database", value="ecommerce_db")
            db_user = st.text_input("Username", value="postgres")
            db_password = st.text_input("Password", type="password")
            
            connect_button = st.form_submit_button("Connect to Database", use_container_width=True)
        
        if connect_button:
            logger.info(f"Connection attempt initiated for {db_host}:{db_port}/{db_name}")
            with st.spinner("Connecting to database..."):
                success, message = st.session_state.db_conn.connect(
                    host=db_host,
                    port=int(db_port),
                    database=db_name,
                    user=db_user,
                    password=db_password
                )
                
                if success:
                    st.session_state.connected = True
                    st.success(message)
                    logger.info("Database connection successful")
                    
                    # Fetch schema
                    with st.spinner("Loading database schema..."):
                        logger.info("Starting schema fetch")
                        schema = st.session_state.db_conn.fetch_schema()
                        if schema:
                            st.session_state.schema_info = schema
                            st.session_state.schema_loaded = True
                            st.success(f"Loaded {len(schema['tables'])} table(s)")
                            logger.info(f"Schema loaded successfully: {len(schema['tables'])} tables")
                        else:
                            st.error("Failed to load schema")
                            logger.error("Schema loading failed")
                else:
                    st.error(message)
                    st.session_state.connected = False
                    logger.error(f"Connection failed: {message}")
        
        # Disconnect button
        if st.session_state.connected:
            if st.button("Disconnect", use_container_width=True):
                reset_connection()
                st.rerun()
        
        st.divider()
        
        # LLM Model selection
        st.subheader("LLM Settings")
        
        # Auto-detect available models
        try:
            available_models = SQLGenerator.get_available_models()
            if available_models:
                logger.info(f"Found {len(available_models)} available model(s) for selection")
                selected_model = st.selectbox(
                    "Select Model",
                    options=available_models,
                    index=0,
                    help="Available Ollama models on your system"
                )
            else:
                st.warning("No Ollama models found. Please install a model first.")
                logger.warning("No Ollama models available")
                selected_model = None
        except Exception as e:
            st.error(f"Error fetching models: {str(e)}")
            logger.error(f"Error fetching available models: {str(e)}")
            selected_model = None
            available_models = []
        
        if st.button("Load Model", use_container_width=True, disabled=not available_models):
            try:
                logger.info(f"Loading model: {selected_model}")
                st.session_state.sql_generator = SQLGenerator(model_name=selected_model)
                # Initialize response generator with the same model
                st.session_state.response_generator = ResponseGenerator(model_name=selected_model)
                # Update query handler to use LLM classification
                st.session_state.query_handler = QueryHandler(model_name=selected_model)
                # Initialize workflow agent
                # Workflow agent will be initialized when needed
                # (requires db_conn to be connected first)
                st.success(f"Loaded model: {selected_model}")
                logger.info(f"Model {selected_model} loaded successfully")
            except Exception as e:
                st.error(f"Failed to load model: {str(e)}")
                logger.error(f"Model loading failed: {str(e)}")
        
        # Show current model
        if st.session_state.sql_generator:
            st.info(f"📌 Current model: {st.session_state.sql_generator.model_name}")
        
        # Show schema info
        if st.session_state.schema_loaded and st.session_state.schema_info:
            st.divider()
            st.subheader("📊 Database Schema")
            with st.expander("View Schema", expanded=False):
                for table in st.session_state.schema_info["tables"]:
                    st.markdown(f"**{table['name']}**")
                    for col in table["columns"]:
                        st.text(f"  • {col['name']}: {col['type']}")
    
    # Main chat interface
    if not st.session_state.connected:
        st.info("👈 Please connect to a database using the sidebar to get started.")
        st.markdown("""
        ### How to use:
        1. Enter your PostgreSQL connection details in the sidebar
        2. Click "Connect to Database"
        3. Wait for the schema to load
        4. Select and load an LLM model
        5. Start asking questions about your database!
        """)
        return
    
    if not st.session_state.schema_loaded:
        st.warning("⚠️ Schema not loaded. Please check your connection.")
        return
    
    if st.session_state.sql_generator is None:
        st.warning("⚠️ Please load an LLM model from the sidebar to generate SQL queries.")
    
    # Display chat messages
    for idx, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            
            # Show SQL query if available
            if message.get("sql_query"):
                with st.expander("🔍 View SQL Query"):
                    st.code(message["sql_query"], language="sql")
                
                # Show execute button if pending
                if message.get("pending_query"):
                    if st.button("✅ Execute Query", key=f"exec_msg_{idx}", type="primary"):
                        logger.info(f"Executing query from message {idx}")
                        sql_query = message["sql_query"]
                        user_query = message.get("user_query", "")
                        # Update message to remove pending flag
                        message["pending_query"] = False
                        # Execute the query
                        with st.spinner("Executing query..."):
                            success, results, error = st.session_state.db_conn.execute_query(sql_query)
                            
                            if success and isinstance(results, dict) and "columns" in results:
                                # Process results to DataFrame
                                df = pd.DataFrame(results['rows'], columns=results['columns'])
                                
                                # Generate natural language response using LLM
                                conversation_history = [
                                    {k: v for k, v in msg.items() if k not in ["query_results", "pending_query"]}
                                    for msg in st.session_state.messages[:idx+1]
                                ]
                                
                                if st.session_state.response_generator:
                                    logger.info("Generating natural language response from query results")
                                    nl_response = st.session_state.response_generator.generate_response(
                                        user_query=user_query or prompt,
                                        query_results=df,
                                        sql_query=sql_query,
                                        conversation_history=conversation_history
                                    )
                                else:
                                    # Fallback if response generator not available
                                    nl_response = f"I found {len(df)} result(s) for your query."
                                
                                # Update message with LLM-generated response
                                message["content"] = nl_response
                                message["query_results"] = df
                                message["sql_query"] = sql_query
                                st.session_state.pending_query = None
                                st.rerun()
                            elif success:
                                message["pending_query"] = False
                                message["content"] = "Query executed successfully."
                                st.session_state.pending_query = None
                                st.rerun()
                            else:
                                st.error(f"Query execution failed: {error}")
                                message["pending_query"] = False
                                message["content"] = f"Query execution failed: {error}"
                                st.rerun()
            
            # Show workflow steps if available
            if message.get("steps"):
                with st.expander("🔄 View Workflow Steps", expanded=False):
                    for step in message["steps"]:
                        step_status = step.get("status", "pending")
                        step_icon = "✅" if step_status == "completed" else "❌" if step_status == "error" else "⏳"
                        status_color = "green" if step_status == "completed" else "red" if step_status == "error" else "blue"
                        st.markdown(f"{step_icon} **Step {step.get('step')}: {step.get('name')}**")
                        st.markdown(f"  Status: :{status_color}[{step_status}] - {step.get('message', '')}")
            
            # Show query results if available
            if message.get("query_results") is not None:
                df = message.get("query_results")
                if isinstance(df, pd.DataFrame) and len(df) > 0:
                    st.dataframe(df, use_container_width=True)
    
    # Chat input
    if prompt := st.chat_input("Ask a question about your database..."):
        logger.info(f"User query received: {prompt[:50]}...")
        # Add user message to chat
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Use query handler to classify and route the query (with schema info for LLM classification)
        query_type, handler_response = st.session_state.query_handler.handle_query(
            prompt, 
            schema_info=st.session_state.schema_info if st.session_state.schema_loaded else None
        )
        
        with st.chat_message("assistant"):
            # Handle greetings and general questions
            if query_type in ['greeting', 'general_question']:
                st.markdown(handler_response)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": handler_response
                })
                st.rerun()
            
            # Handle SQL queries using workflow agent
            elif query_type == 'sql_query':
                if st.session_state.sql_generator is None:
                    st.warning("⚠️ Please load an LLM model from the sidebar first.")
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": "⚠️ Please load an LLM model from the sidebar to generate SQL queries."
                    })
                    st.rerun()
                
                # Initialize workflow agent if needed
                if st.session_state.workflow_agent is None:
                    st.session_state.workflow_agent = WorkflowAgent(
                        sql_generator=st.session_state.sql_generator,
                        db_connection=st.session_state.db_conn,
                        response_generator=st.session_state.response_generator,
                        query_classifier=st.session_state.query_classifier if hasattr(st.session_state, 'query_classifier') else None,
                        max_retries=3
                    )
                
                # Get conversation history
                conversation_history = [
                    {k: v for k, v in msg.items() if k not in ["query_results", "pending_query", "steps"]}
                    for msg in st.session_state.messages
                ]
                
                # Container for step-by-step progress
                steps_container = st.container()
                
                # Run workflow agent
                logger.info("Starting workflow agent")
                with st.spinner("Processing your query through workflow..."):
                    result = st.session_state.workflow_agent.run(
                        user_query=prompt,
                        schema_info=st.session_state.schema_info,
                        conversation_history=conversation_history
                    )
                
                # Display workflow steps
                if result.get("steps"):
                    with steps_container:
                        st.markdown("### 🔄 Workflow Steps")
                        for step in result["steps"]:
                            step_status = step.get("status", "pending")
                            step_icon = "⏳" if step_status == "in_progress" else "✅" if step_status == "completed" else "❌"
                            status_color = "blue" if step_status == "in_progress" else "green" if step_status == "completed" else "red"
                            
                            with st.expander(f"{step_icon} Step {step.get('step')}: {step.get('name')}", expanded=True):
                                st.markdown(f"**Status:** :{status_color}[{step_status}]")
                                st.markdown(f"**Details:** {step.get('message', '')}")
                
                # Show SQL query if generated
                if result.get("sql_query"):
                    with st.expander("🔍 View Generated SQL Query", expanded=False):
                        st.code(result["sql_query"], language="sql")
                
                # Display final response
                final_response = result.get("final_response", "No response generated.")
                st.markdown(f"**Response:** {final_response}")
                
                # Display results if available
                if result.get("df") is not None:
                    df = result["df"]
                    if len(df) > 0:
                        st.dataframe(df, use_container_width=True)
                
                # Store in messages
                message_entry = {
                    "role": "assistant",
                    "content": final_response,
                    "sql_query": result.get("sql_query"),
                    "steps": result.get("steps", []),
                    "query_results": result.get("df")
                }
                
                st.session_state.messages.append(message_entry)
                st.rerun()




if __name__ == "__main__":
    main()

