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
from db_chatbot.utils.validators import SQLValidator
from db_chatbot.handlers.query_handler import QueryHandler
from db_chatbot.utils.result_processor import ResultProcessor
from db_chatbot.config.settings import get_logger
import json

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

# Always ensure query_handler and result_processor are initialized
if "query_handler" not in st.session_state:
    st.session_state.query_handler = QueryHandler()
    logger.debug("QueryHandler initialized in session state")

if "result_processor" not in st.session_state:
    st.session_state.result_processor = ResultProcessor()
    logger.debug("ResultProcessor initialized in session state")

if "response_generator" not in st.session_state:
    st.session_state.response_generator = None
    logger.debug("ResponseGenerator placeholder initialized")


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
    # Note: query_handler and result_processor are not reset as they're stateless


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
            
            # Handle SQL queries
            elif query_type == 'sql_query':
                if st.session_state.sql_generator is None:
                    st.warning("⚠️ Please load an LLM model from the sidebar first.")
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": "⚠️ Please load an LLM model from the sidebar to generate SQL queries."
                    })
                    st.rerun()
                
                with st.spinner("Analyzing your question and generating SQL query..."):
                    logger.info("Starting SQL generation process")
                    # Get conversation history for context
                    conversation_history = [
                        {k: v for k, v in msg.items() if k not in ["query_results", "pending_query"]}
                        for msg in st.session_state.messages
                    ]
                    
                    # Generate SQL query
                    sql_query = st.session_state.sql_generator.generate_sql(
                        natural_language_query=prompt,
                        schema_info=st.session_state.schema_info,
                        conversation_history=conversation_history
                    )
                    
                    if sql_query:
                        logger.info(f"SQL query generated: {sql_query[:50]}...")
                        
                        # Validate SQL query
                        logger.info("Validating SQL query")
                        is_valid, validation_error = SQLValidator.validate_query(sql_query)
                        
                        if not is_valid:
                            error_msg = f"⚠️ Security validation failed: {validation_error}"
                            st.error(error_msg)
                            logger.warning(f"SQL validation failed: {validation_error}")
                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": error_msg,
                                "sql_query": sql_query
                            })
                            st.rerun()
                        
                        # Show the generated query and ask for confirmation
                        st.markdown("**I've generated the following SQL query for your question:**")
                        st.code(sql_query, language="sql")
                        
                        # Store pending query
                        st.session_state.pending_query = {
                            "sql": sql_query,
                            "user_query": prompt
                        }
                        
                        # Store in messages first
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": f"I've generated a SQL query for: '{prompt}'. Please review and confirm to execute it.",
                            "sql_query": sql_query,
                            "pending_query": True
                        })
                        
                        # Confirmation buttons
                        st.markdown("**Would you like to execute this query?**")
                        col1, col2 = st.columns(2)
                        with col1:
                            execute_btn = st.button("✅ Execute Query", key=f"execute_{len(st.session_state.messages)}", use_container_width=True, type="primary")
                        
                        with col2:
                            cancel_btn = st.button("❌ Cancel", key=f"cancel_{len(st.session_state.messages)}", use_container_width=True)
                        
                        if execute_btn:
                            logger.info("User confirmed query execution")
                            # Execute the query
                            with st.spinner("Executing query..."):
                                success, results, error = st.session_state.db_conn.execute_query(sql_query)
                                
                                if success and isinstance(results, dict) and "columns" in results:
                                    # Process results to DataFrame
                                    df = pd.DataFrame(results['rows'], columns=results['columns'])
                                    
                                    # Generate natural language response using LLM
                                    conversation_history = [
                                        {k: v for k, v in msg.items() if k not in ["query_results", "pending_query"]}
                                        for msg in st.session_state.messages
                                    ]
                                    
                                    if st.session_state.response_generator:
                                        logger.info("Generating natural language response from query results")
                                        nl_response = st.session_state.response_generator.generate_response(
                                            user_query=prompt,
                                            query_results=df,
                                            sql_query=sql_query,
                                            conversation_history=conversation_history
                                        )
                                    else:
                                        # Fallback if response generator not available
                                        nl_response = f"I found {len(df)} result(s) for your query."
                                    
                                    # Update the last message with LLM-generated response
                                    st.session_state.messages[-1].update({
                                        "content": nl_response,
                                        "query_results": df,
                                        "sql_query": sql_query,
                                        "pending_query": False
                                    })
                                    st.session_state.pending_query = None
                                    st.rerun()
                                elif success:
                                    st.session_state.messages[-1].update({
                                        "content": "Query executed successfully.",
                                        "pending_query": False
                                    })
                                    st.rerun()
                                else:
                                    st.error(f"Query execution failed: {error}")
                                    st.session_state.messages[-1].update({
                                        "content": f"Query execution failed: {error}",
                                        "pending_query": False
                                    })
                                    st.rerun()
                        
                        if cancel_btn:
                            logger.info("User cancelled query execution")
                            st.session_state.pending_query = None
                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": "Query cancelled. Feel free to ask another question!"
                            })
                            st.rerun()
                    else:
                        error_msg = "I couldn't generate a valid SQL query for your question. Please try rephrasing it or be more specific."
                        st.error(error_msg)
                        logger.warning("Failed to generate SQL query")
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": error_msg
                        })




if __name__ == "__main__":
    main()

