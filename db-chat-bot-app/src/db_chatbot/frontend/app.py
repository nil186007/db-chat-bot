"""
Streamlit-based PostgreSQL chatbot with natural language to SQL conversion.
"""
import sys
from pathlib import Path

# Add src directory to Python path
app_dir = Path(__file__).parent.parent.parent
if str(app_dir) not in sys.path:
    sys.path.insert(0, str(app_dir))

import streamlit as st
import pandas as pd
from db_chatbot.db_clients.postgres_client import PostgresClient
from db_chatbot.db_clients.neo4j_client import Neo4jClient
from db_chatbot.query_generator.sql_generator import SQLGenerator
from db_chatbot.query_generator.response_generator import ResponseGenerator
from db_chatbot.query_intent.classifier import QueryClassifier
from db_chatbot.rag.schema_rag import SchemaRAG
from db_chatbot.rag.knowledge_graph_rag import KnowledgeGraphRAG
from db_chatbot.handlers.annotation_handler import AnnotationHandler
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
if "db_client" not in st.session_state:
    st.session_state.db_client = PostgresClient()
    st.session_state.neo4j_client = Neo4jClient()
    st.session_state.neo4j_connected = False
    st.session_state.neo4j_auto_connect_attempted = False
    st.session_state.connected = False
    st.session_state.schema_loaded = False
    st.session_state.sql_generator = None
    st.session_state.messages = []
    st.session_state.annotation_handler = AnnotationHandler()
    # Initialize SchemaRAG without KnowledgeGraphRAG initially
    st.session_state.schema_rag = SchemaRAG()
    st.session_state.current_database_name = None
    st.session_state.current_db_host = None
    st.session_state.current_db_port = None
    logger.info("Session state initialized")

if "response_generator" not in st.session_state:
    st.session_state.response_generator = None
    logger.debug("ResponseGenerator placeholder initialized")

if "query_classifier" not in st.session_state:
    st.session_state.query_classifier = None
    logger.debug("QueryClassifier placeholder initialized")

if "workflow_agent" not in st.session_state:
    st.session_state.workflow_agent = None
    logger.debug("WorkflowAgent placeholder initialized")


def reset_connection():
    """Reset database connection and related state."""
    logger.info("Resetting database connection")
    if st.session_state.db_client:
        st.session_state.db_client.close()
    st.session_state.connected = False
    st.session_state.schema_loaded = False
    if st.session_state.schema_rag and st.session_state.current_database_name:
        st.session_state.schema_rag.clear()
    st.session_state.current_database_name = None
    st.session_state.current_db_host = None
    st.session_state.current_db_port = None
    st.session_state.messages = []
    st.session_state.workflow_agent = None  # Reset workflow agent


def main():
    logger.info("Starting main application")
    st.title("🗄️ Database ChatBot")
    st.markdown("Connect to PostgreSQL and query your database using natural language!")
    
    # Sidebar for connection settings
    with st.sidebar:
        st.header("⚙️ Settings")
        
        # Neo4j connection (for knowledge graph)
        st.subheader("Knowledge Graph (Neo4j)")
        
        # Auto-connect to Neo4j on first load
        if not st.session_state.neo4j_connected and not st.session_state.neo4j_auto_connect_attempted:
            st.session_state.neo4j_auto_connect_attempted = True
            with st.spinner("Attempting to connect to Neo4j..."):
                try:
                    success = st.session_state.neo4j_client.connect()
                    if success:
                        st.session_state.neo4j_connected = True
                        # Initialize KnowledgeGraphRAG and update SchemaRAG
                        kg_rag = KnowledgeGraphRAG(st.session_state.neo4j_client)
                        st.session_state.schema_rag = SchemaRAG(knowledge_graph_rag=kg_rag)
                        logger.info("Neo4j auto-connected and KnowledgeGraphRAG initialized")
                except Exception as e:
                    logger.warning(f"Auto-connect to Neo4j failed: {e}")
                    st.session_state.neo4j_connected = False
        
        with st.form("neo4j_connection_form"):
            neo4j_uri = st.text_input("Neo4j URI", value="bolt://localhost:7687", help="Neo4j connection URI (default: bolt://localhost:7687)")
            neo4j_user = st.text_input("Neo4j User", value="neo4j")
            neo4j_password = st.text_input("Neo4j Password", type="password", value="neo4jpassword", help="Default password: neo4jpassword (from docker-compose)")
            neo4j_connect_button = st.form_submit_button("Connect to Neo4j", use_container_width=True)
        
        if neo4j_connect_button:
            # Update client connection details
            st.session_state.neo4j_client = Neo4jClient(uri=neo4j_uri, user=neo4j_user, password=neo4j_password)
            with st.spinner("Connecting to Neo4j..."):
                success = st.session_state.neo4j_client.connect()
                if success:
                    st.session_state.neo4j_connected = True
                    st.success("✅ Neo4j connected!")
                    # Initialize KnowledgeGraphRAG and update SchemaRAG
                    kg_rag = KnowledgeGraphRAG(st.session_state.neo4j_client)
                    st.session_state.schema_rag = SchemaRAG(knowledge_graph_rag=kg_rag)
                    logger.info("Neo4j connected and KnowledgeGraphRAG initialized")
                else:
                    st.error("❌ Failed to connect to Neo4j. Make sure Neo4j is running (docker-compose up -d neo4j)")
                    st.session_state.neo4j_connected = False
        
        if st.session_state.neo4j_connected:
            st.success("🟢 Knowledge Graph: Active")
            if st.button("Disconnect Neo4j", use_container_width=True):
                st.session_state.neo4j_client.close()
                st.session_state.neo4j_connected = False
                st.session_state.schema_rag = SchemaRAG()  # Reset to in-memory
                st.rerun()
        else:
            st.warning("🟡 Knowledge Graph: Not connected (using in-memory storage)")
            st.caption("💡 Tip: Start Neo4j with: `cd docker-setup && docker-compose up -d neo4j`")
        
        st.divider()
        
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
                success, message = st.session_state.db_client.connect(
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
                    
                    # Fetch schema and load into RAG
                    with st.spinner("Loading database schema into RAG..."):
                        logger.info("Starting schema fetch")
                        schema = st.session_state.db_client.fetch_schema()
                        if schema:
                            # Store database connection info for knowledge graph
                            st.session_state.current_database_name = db_name
                            st.session_state.current_db_host = db_host
                            st.session_state.current_db_port = int(db_port)
                            
                            # Load into RAG (with knowledge graph if connected)
                            st.session_state.schema_rag.load_schema(
                                schema,
                                database_name=db_name,
                                host=db_host,
                                port=int(db_port)
                            )
                            st.session_state.schema_loaded = True
                            storage_type = "Knowledge Graph" if st.session_state.neo4j_connected else "Memory"
                            st.success(f"Loaded {len(schema['tables'])} table(s) into {storage_type}")
                            logger.info(f"Schema loaded successfully into {storage_type}: {len(schema['tables'])} tables")
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
                # Initialize query classifier with the same model
                st.session_state.query_classifier = QueryClassifier(model_name=selected_model)
                # Reset workflow agent - will be initialized when needed
                st.session_state.workflow_agent = None
                st.success(f"Loaded model: {selected_model}")
                logger.info(f"Model {selected_model} loaded successfully")
            except Exception as e:
                st.error(f"Failed to load model: {str(e)}")
                logger.error(f"Model loading failed: {str(e)}")
        
        # Show current model
        if st.session_state.sql_generator:
            st.info(f"📌 Current model: {st.session_state.sql_generator.model_name}")
        
        # Metadata Management Section
        if st.session_state.schema_loaded and st.session_state.neo4j_connected:
            st.divider()
            st.subheader("📝 Metadata Management")
            st.caption("Manage descriptions for database, tables, and columns. These descriptions enhance SQL generation context.")
            
            schema_info = st.session_state.schema_rag.get_schema()
            if schema_info:
                # Database Description
                with st.expander("🗄️ Database Description", expanded=False):
                    current_db_desc = st.session_state.schema_rag.get_annotation(
                        "database",
                        st.session_state.current_database_name or ""
                    ) or ""
                    
                    db_description = st.text_area(
                        "Database Description",
                        value=current_db_desc,
                        height=100,
                        key="db_description",
                        help="Describe what this database stores and its purpose"
                    )
                    if st.button("💾 Save Database Description", key="save_db_desc", use_container_width=True):
                        st.session_state.schema_rag.add_annotation(
                            entity_type="database",
                            entity_name=st.session_state.current_database_name or "",
                            content=db_description,
                            table_name=None
                        )
                        st.success("✅ Database description saved!")
                        st.rerun()
                
                # Table Descriptions
                with st.expander("📋 Table Descriptions", expanded=False):
                    table_options = [t["name"] for t in schema_info["tables"]]
                    selected_table = st.selectbox(
                        "Select Table",
                        options=table_options,
                        key="metadata_table_select"
                    )
                    
                    if selected_table:
                        # Get current annotation for selected table
                        current_table_desc = st.session_state.schema_rag.get_annotation(
                            "table",
                            selected_table
                        ) or ""
                        
                        table_description = st.text_area(
                            f"Description for '{selected_table}' table",
                            value=current_table_desc,
                            height=150,
                            key=f"table_desc_{selected_table}",
                            help="Describe what this table stores, its purpose, and key information"
                        )
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button("💾 Save Table Description", key=f"save_table_{selected_table}", use_container_width=True):
                                st.session_state.schema_rag.add_annotation(
                                    entity_type="table",
                                    entity_name=selected_table,
                                    content=table_description,
                                    table_name=None
                                )
                                st.success(f"✅ Description saved for table '{selected_table}'!")
                                st.rerun()
                        with col2:
                            if st.button("🔄 View Columns", key=f"view_cols_{selected_table}", use_container_width=True):
                                st.session_state[f"show_cols_{selected_table}"] = not st.session_state.get(f"show_cols_{selected_table}", False)
                        
                        # Show columns for selected table
                        if st.session_state.get(f"show_cols_{selected_table}", False):
                            selected_table_info = next((t for t in schema_info["tables"] if t["name"] == selected_table), None)
                            if selected_table_info:
                                st.markdown("**Columns:**")
                                for col in selected_table_info["columns"]:
                                    col_name = col["name"]
                                    # Get current column annotation
                                    current_col_desc = st.session_state.schema_rag.get_annotation(
                                        "column",
                                        col_name,
                                        table_name=selected_table
                                    ) or ""
                                    
                                    with st.expander(f"📌 {col_name} ({col['type']})", expanded=False):
                                        col_description = st.text_area(
                                            f"Description for column '{col_name}'",
                                            value=current_col_desc,
                                            height=100,
                                            key=f"col_desc_{selected_table}_{col_name}",
                                            help=f"Describe what this column stores (type: {col['type']})"
                                        )
                                        if st.button("💾 Save", key=f"save_col_{selected_table}_{col_name}", use_container_width=True):
                                            st.session_state.schema_rag.add_annotation(
                                                entity_type="column",
                                                entity_name=col_name,
                                                content=col_description,
                                                table_name=selected_table
                                            )
                                            st.success(f"✅ Description saved for column '{col_name}'!")
                                            st.rerun()
        elif st.session_state.schema_loaded and not st.session_state.neo4j_connected:
            st.divider()
            st.info("💡 Connect to Neo4j to enable metadata management features")
        
        # Show schema info from RAG
        if st.session_state.schema_loaded:
            schema_info = st.session_state.schema_rag.get_schema()
            if schema_info:
                st.divider()
                st.subheader("📊 Database Schema (RAG)")
                with st.expander("View Schema", expanded=False):
                    for table in schema_info["tables"]:
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
        3. Wait for the schema to load into RAG
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
        
        with st.chat_message("assistant"):
            # Check if this is an annotation
            if st.session_state.annotation_handler.is_annotation(prompt):
                logger.info("Detected annotation in user message")
                annotation = st.session_state.annotation_handler.parse_annotation(prompt)
                
                if annotation and st.session_state.schema_loaded:
                    # Store annotation in knowledge graph
                    try:
                        st.session_state.schema_rag.add_annotation(
                            entity_type=annotation["entity_type"],
                            entity_name=annotation["entity_name"],
                            content=annotation["content"],
                            table_name=annotation.get("table_name")
                        )
                        entity_desc = f"{annotation['entity_type']} '{annotation['entity_name']}'"
                        if annotation.get("table_name"):
                            entity_desc = f"column '{annotation['entity_name']}' in table '{annotation['table_name']}'"
                        
                        response = f"✅ Annotation saved for {entity_desc}:\n\n{annotation['content']}"
                        st.success(response)
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": response
                        })
                        logger.info(f"Annotation stored: {entity_desc}")
                    except Exception as e:
                        error_msg = f"❌ Failed to save annotation: {str(e)}"
                        st.error(error_msg)
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": error_msg
                        })
                        logger.error(f"Failed to store annotation: {e}")
                elif not st.session_state.schema_loaded:
                    st.warning("⚠️ Please connect to a database first before adding annotations.")
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": "⚠️ Please connect to a database first before adding annotations."
                    })
                else:
                    st.warning("⚠️ Could not parse annotation. Please use format like:\n- 'The orders table contains customer purchase records'\n- 'The orders.status column stores order status values'")
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": "⚠️ Could not parse annotation. Please use format like:\n- 'The orders table contains customer purchase records'\n- 'The orders.status column stores order status values'"
                    })
                st.rerun()
                return
            
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
                    db_client=st.session_state.db_client,  # Database client as tool
                    schema_rag=st.session_state.schema_rag,  # Schema RAG
                    response_generator=st.session_state.response_generator,
                    query_classifier=st.session_state.query_classifier,
                    max_retries=3
                )
            
            # Get conversation history
            conversation_history = [
                {k: v for k, v in msg.items() if k not in ["query_results", "steps"]}
                for msg in st.session_state.messages
            ]
            
            # Container for step-by-step progress
            steps_container = st.container()
            
            # Run workflow agent
            logger.info("Starting workflow agent")
            with st.spinner("Processing your query through workflow..."):
                result = st.session_state.workflow_agent.run(
                    user_query=prompt,
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
            st.markdown(final_response)
            
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

