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
import json
from db_chatbot.db_clients.postgres_client import PostgresClient
from db_chatbot.db_clients.mongodb_client import MongoDBClient
from db_chatbot.db_clients.neo4j_client import Neo4jClient
from db_chatbot.query_generator.sql_generator import SQLGenerator
from db_chatbot.query_generator.mongodb_query_generator import MongoDBQueryGenerator
from db_chatbot.query_generator.response_generator import ResponseGenerator
from db_chatbot.query_intent.classifier import QueryClassifier
from db_chatbot.rag.schema_rag import SchemaRAG
from db_chatbot.rag.knowledge_graph_rag import KnowledgeGraphRAG
from db_chatbot.handlers.annotation_handler import AnnotationHandler
from db_chatbot.handlers.query_example_handler import QueryExampleHandler
from db_chatbot.agents.workflow_agent import WorkflowAgent
from db_chatbot.agents.mongodb_workflow_agent import MongoDBWorkflowAgent
from db_chatbot.agents.orchestrator_agent import OrchestratorAgent
from db_chatbot.query_intent.database_router import DatabaseRouter
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
    st.session_state.mongodb_client = MongoDBClient()
    st.session_state.neo4j_client = Neo4jClient()
    st.session_state.neo4j_connected = False
    st.session_state.neo4j_auto_connect_attempted = False
    st.session_state.connected = False
    st.session_state.mongodb_connected = False
    st.session_state.schema_loaded = False
    st.session_state.mongodb_schema_loaded = False
    st.session_state.sql_generator = None
    st.session_state.mongodb_query_generator = None
    st.session_state.messages = []
    st.session_state.annotation_handler = AnnotationHandler()
    st.session_state.query_example_handler = QueryExampleHandler()
    # Initialize SchemaRAG without KnowledgeGraphRAG initially
    st.session_state.schema_rag = SchemaRAG()
    # PostgreSQL connection info
    st.session_state.postgres_db_name = None
    st.session_state.postgres_db_host = None
    st.session_state.postgres_db_port = None
    # MongoDB connection info
    st.session_state.mongodb_db_name = None
    st.session_state.mongodb_db_host = None
    st.session_state.mongodb_db_port = None
    logger.info("Session state initialized")

if "response_generator" not in st.session_state:
    st.session_state.response_generator = None
    logger.debug("ResponseGenerator placeholder initialized")

if "query_classifier" not in st.session_state:
    st.session_state.query_classifier = None
    logger.debug("QueryClassifier placeholder initialized")

if "workflow_agent" not in st.session_state:
    st.session_state.workflow_agent = None
    st.session_state.mongodb_workflow_agent = None
    st.session_state.orchestrator_agent = None
    st.session_state.database_router = None
    logger.debug("WorkflowAgent placeholder initialized")


def reset_postgres_connection():
    """Reset PostgreSQL connection and related state."""
    logger.info("Resetting PostgreSQL connection")
    if st.session_state.db_client:
        st.session_state.db_client.close()
    st.session_state.connected = False
    st.session_state.schema_loaded = False
    st.session_state.postgres_db_name = None
    st.session_state.postgres_db_host = None
    st.session_state.postgres_db_port = None
    st.session_state.workflow_agent = None

def reset_mongodb_connection():
    """Reset MongoDB connection and related state."""
    logger.info("Resetting MongoDB connection")
    if st.session_state.mongodb_client:
        st.session_state.mongodb_client.close()
    st.session_state.mongodb_connected = False
    st.session_state.mongodb_schema_loaded = False
    st.session_state.mongodb_db_name = None
    st.session_state.mongodb_db_host = None
    st.session_state.mongodb_db_port = None
    st.session_state.mongodb_workflow_agent = None


def main():
    logger.info("Starting main application")
    st.title("🗄️ Database ChatBot")
    st.markdown("Connect to PostgreSQL or MongoDB and query your database using natural language!")
    
    # Auto-connect to Neo4j on startup (silent, no UI)
    if not st.session_state.neo4j_connected and not st.session_state.neo4j_auto_connect_attempted:
        st.session_state.neo4j_auto_connect_attempted = True
        # Use default connection parameters from docker-compose.yml
        try:
            # Initialize with default Neo4j connection parameters
            st.session_state.neo4j_client = Neo4jClient(
                uri="bolt://localhost:7687",
                user="neo4j",
                password="neo4jpassword"
            )
            success = st.session_state.neo4j_client.connect()
            if success:
                st.session_state.neo4j_connected = True
                # Initialize KnowledgeGraphRAG and update SchemaRAG
                kg_rag = KnowledgeGraphRAG(st.session_state.neo4j_client)
                st.session_state.schema_rag = SchemaRAG(knowledge_graph_rag=kg_rag)
                logger.info("Neo4j auto-connected and KnowledgeGraphRAG initialized")
            else:
                logger.warning("Auto-connect to Neo4j failed (Neo4j may not be running)")
                st.session_state.neo4j_connected = False
        except Exception as e:
            logger.warning(f"Auto-connect to Neo4j failed: {e}")
            st.session_state.neo4j_connected = False
    
    # Sidebar for connection settings
    with st.sidebar:
        st.header("⚙️ Settings")
        
        st.divider()
        
        # PostgreSQL connection section
        st.subheader("🐘 PostgreSQL Connection")
        
        # Show connection status
        if st.session_state.connected:
            st.success(f"✅ Connected to {st.session_state.postgres_db_name or 'PostgreSQL'}")
            if st.button("Disconnect PostgreSQL", use_container_width=True, key="disconnect_pg"):
                reset_postgres_connection()
                st.rerun()
        else:
            with st.form("postgres_connection_form"):
                pg_host = st.text_input("Host", value="localhost", key="pg_host")
                pg_port = st.number_input("Port", value=5432, min_value=1, max_value=65535, key="pg_port")
                pg_name = st.text_input("Database", value="ecommerce_db", key="pg_db")
                pg_user = st.text_input("Username", value="postgres", key="pg_user")
                pg_password = st.text_input("Password", type="password", key="pg_password")
                
                connect_button = st.form_submit_button("Connect to PostgreSQL", use_container_width=True)
            
            if connect_button:
                logger.info(f"PostgreSQL connection attempt: {pg_host}:{pg_port}/{pg_name}")
                with st.spinner("Connecting to PostgreSQL..."):
                    success, message = st.session_state.db_client.connect(
                        host=pg_host,
                        port=int(pg_port),
                        database=pg_name,
                        user=pg_user,
                        password=pg_password
                    )
                    
                    if success:
                        st.session_state.connected = True
                        st.success(message)
                        logger.info("PostgreSQL connection successful")
                        
                        # Store connection info
                        st.session_state.postgres_db_name = pg_name
                        st.session_state.postgres_db_host = pg_host
                        st.session_state.postgres_db_port = int(pg_port)
                        
                        # Fetch schema and load into RAG
                        with st.spinner("Loading database schema into RAG..."):
                            logger.info("Starting PostgreSQL schema fetch")
                            schema = st.session_state.db_client.fetch_schema()
                            if schema:
                                # Load into RAG (with knowledge graph if connected)
                                st.session_state.schema_rag.load_schema(
                                    schema,
                                    database_name=pg_name,
                                    host=pg_host,
                                    port=int(pg_port)
                                )
                                st.session_state.schema_loaded = True
                                storage_type = "Knowledge Graph" if st.session_state.neo4j_connected else "Memory"
                                st.success(f"Loaded {len(schema['tables'])} table(s) into {storage_type}")
                                logger.info(f"PostgreSQL schema loaded: {len(schema['tables'])} tables")
                            else:
                                st.error("Failed to load schema")
                                logger.error("PostgreSQL schema loading failed")
                    else:
                        st.error(message)
                        st.session_state.connected = False
                        logger.error(f"PostgreSQL connection failed: {message}")
        
        st.divider()
        
        # MongoDB connection section
        st.subheader("🍃 MongoDB Connection")
        
        # Show connection status
        if st.session_state.mongodb_connected:
            st.success(f"✅ Connected to {st.session_state.mongodb_db_name or 'MongoDB'}")
            if st.button("Disconnect MongoDB", use_container_width=True, key="disconnect_mongo"):
                reset_mongodb_connection()
                st.rerun()
        else:
            with st.form("mongodb_connection_form"):
                mongo_host = st.text_input("Host", value="localhost", key="mongo_host")
                mongo_port = st.number_input("Port", value=27017, min_value=1, max_value=65535, key="mongo_port")
                mongo_db = st.text_input("Database", value="ecommerce_db", key="mongo_db")
                mongo_user = st.text_input("Username (optional)", value="", key="mongo_user")
                mongo_password = st.text_input("Password (optional)", type="password", value="", key="mongo_password")
                
                connect_button = st.form_submit_button("Connect to MongoDB", use_container_width=True)
            
            if connect_button:
                logger.info(f"MongoDB connection attempt: {mongo_host}:{mongo_port}/{mongo_db}")
                with st.spinner("Connecting to MongoDB..."):
                    success, message = st.session_state.mongodb_client.connect(
                        host=mongo_host,
                        port=int(mongo_port),
                        database=mongo_db,
                        username=mongo_user if mongo_user else None,
                        password=mongo_password if mongo_password else None
                    )
                    
                    if success:
                        st.session_state.mongodb_connected = True
                        st.success(message)
                        logger.info("MongoDB connection successful")
                        
                        # Store connection info
                        st.session_state.mongodb_db_name = mongo_db
                        st.session_state.mongodb_db_host = mongo_host
                        st.session_state.mongodb_db_port = int(mongo_port)
                        
                        # Fetch schema and load into knowledge graph
                        with st.spinner("Loading MongoDB schema into knowledge graph..."):
                            logger.info("Starting MongoDB schema fetch")
                            schema = st.session_state.mongodb_client.fetch_schema()
                            if schema:
                                # Build knowledge graph from MongoDB schema
                                if st.session_state.neo4j_connected and st.session_state.schema_rag.knowledge_graph_rag:
                                    st.session_state.schema_rag.knowledge_graph_rag.build_graph_from_schema(
                                        schema,
                                        database_name=mongo_db,
                                        host=mongo_host,
                                        port=int(mongo_port),
                                        db_type="mongodb"
                                    )
                                    st.success(f"Loaded {len(schema['collections'])} collection(s) into Knowledge Graph")
                                    logger.info(f"MongoDB schema loaded into knowledge graph: {len(schema['collections'])} collections")
                                else:
                                    st.warning("Neo4j not connected. Schema will not be stored in knowledge graph.")
                                    logger.warning("MongoDB schema fetched but not stored (Neo4j not connected)")
                                
                                st.session_state.mongodb_schema_loaded = True
                            else:
                                st.error("Failed to load MongoDB schema")
                                logger.error("MongoDB schema loading failed")
                    else:
                        st.error(message)
                        st.session_state.mongodb_connected = False
                        logger.error(f"MongoDB connection failed: {message}")
        
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
                st.session_state.mongodb_query_generator = MongoDBQueryGenerator(model_name=selected_model)
                # Initialize response generator with the same model
                st.session_state.response_generator = ResponseGenerator(model_name=selected_model)
                # Initialize query classifier with the same model
                st.session_state.query_classifier = QueryClassifier(model_name=selected_model)
                # Initialize database router
                st.session_state.database_router = DatabaseRouter(model_name=selected_model)
                # Reset workflow agents and orchestrator - will be initialized when needed
                st.session_state.workflow_agent = None
                st.session_state.mongodb_workflow_agent = None
                st.session_state.orchestrator_agent = None
                st.success(f"Loaded model: {selected_model}")
                logger.info(f"Model {selected_model} loaded successfully")
            except Exception as e:
                st.error(f"Failed to load model: {str(e)}")
                logger.error(f"Model loading failed: {str(e)}")
        
        # Show current model
        if st.session_state.sql_generator:
            st.info(f"📌 Current model: {st.session_state.sql_generator.model_name}")
        elif st.session_state.mongodb_query_generator:
            st.info(f"📌 Current model: {st.session_state.mongodb_query_generator.model_name}")
        
        # Metadata Management Section
        if (st.session_state.schema_loaded or st.session_state.mongodb_schema_loaded) and st.session_state.neo4j_connected:
            st.divider()
            st.subheader("📝 Metadata Management")
            st.caption("Manage descriptions for database, tables, and columns. These descriptions enhance query generation context.")
            
            # Database Description - handle both PostgreSQL and MongoDB
            with st.expander("🗄️ Database Description", expanded=False):
                db_options = []
                if st.session_state.connected and st.session_state.postgres_db_name:
                    db_options.append(("PostgreSQL", st.session_state.postgres_db_name))
                if st.session_state.mongodb_connected and st.session_state.mongodb_db_name:
                    db_options.append(("MongoDB", st.session_state.mongodb_db_name))
                
                if db_options:
                    selected_db_type, selected_db_name = st.selectbox(
                        "Select Database",
                        options=db_options,
                        format_func=lambda x: f"{x[0]}: {x[1]}",
                        key="metadata_db_select"
                    )
                    
                    current_db_desc = st.session_state.schema_rag.get_annotation(
                        "database",
                        selected_db_name
                    ) if st.session_state.schema_rag else "" or ""
                    
                    db_description = st.text_area(
                        f"Description for {selected_db_type} database '{selected_db_name}'",
                        value=current_db_desc,
                        height=100,
                        key="db_description",
                        help="Describe what this database stores and its purpose"
                    )
                    if st.button("💾 Save Database Description", key="save_db_desc", use_container_width=True):
                        if st.session_state.schema_rag:
                            st.session_state.schema_rag.add_annotation(
                                entity_type="database",
                                entity_name=selected_db_name,
                                content=db_description,
                                table_name=None
                            )
                            st.success(f"✅ Database description saved for {selected_db_type}!")
                            st.rerun()
                else:
                    st.info("No databases connected for metadata management.")
            
            # Table Descriptions (PostgreSQL only)
            schema_info = st.session_state.schema_rag.get_schema() if st.session_state.schema_rag else None
            if schema_info and schema_info.get("tables"):
                
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
        
        # Show schema info for all connected databases
        st.divider()
        st.subheader("📊 Database Schema")
        
        # PostgreSQL Tables
        if st.session_state.connected and st.session_state.schema_loaded:
            schema_info = st.session_state.schema_rag.get_schema()
            if schema_info and schema_info.get("tables"):
                with st.expander(f"🐘 PostgreSQL: {st.session_state.postgres_db_name} ({len(schema_info['tables'])} table(s))", expanded=True):
                    for table in schema_info["tables"]:
                        col_count = len(table.get("columns", []))
                        st.markdown(f"**📋 {table['name']}** ({col_count} column(s))")
                        with st.expander(f"View columns in {table['name']}", expanded=False):
                            for col in table.get("columns", []):
                                nullable = " (nullable)" if col.get("nullable") else ""
                                st.text(f"  • {col['name']}: {col['type']}{nullable}")
        
        # MongoDB Collections
        if st.session_state.mongodb_connected and st.session_state.mongodb_schema_loaded:
            try:
                mongodb_schema = st.session_state.mongodb_client.fetch_schema()
                if mongodb_schema and mongodb_schema.get("collections"):
                    with st.expander(f"🍃 MongoDB: {st.session_state.mongodb_db_name} ({len(mongodb_schema['collections'])} collection(s))", expanded=True):
                        for collection in mongodb_schema["collections"]:
                            doc_count = collection.get("document_count", 0)
                            field_count = len(collection.get("fields", []))
                            st.markdown(f"**📦 {collection['name']}** ({doc_count} document(s), {field_count} field(s))")
                            with st.expander(f"View fields in {collection['name']}", expanded=False):
                                for field in collection.get("fields", []):
                                    types_str = ", ".join(field.get("types", []))
                                    nullable = " (nullable)" if field.get("nullable") else ""
                                    example = f" (example: {field.get('example')})" if field.get("example") else ""
                                    st.text(f"  • {field['name']}: {types_str}{nullable}{example}")
            except Exception as e:
                logger.error(f"Error fetching MongoDB schema for display: {e}")
                st.warning(f"Could not load MongoDB schema: {str(e)}")
        
        # Show message if no databases connected
        if not st.session_state.connected and not st.session_state.mongodb_connected:
            st.info("👈 Connect to a database to see schema information here.")
    
    # Main chat interface
    if not st.session_state.connected and not st.session_state.mongodb_connected:
        st.info("👈 Please connect to at least one database (PostgreSQL or MongoDB) using the sidebar to get started.")
        st.markdown("""
        ### How to use:
        1. Enter your database connection details in the sidebar (PostgreSQL and/or MongoDB)
        2. Click "Connect" for each database you want to use
        3. Wait for the schema(s) to load
        4. Select and load an LLM model
        5. Start asking questions about your database(s)!
        
        **Note:** You can connect to both PostgreSQL and MongoDB simultaneously. The system will automatically route your queries to the appropriate database.
        """)
        return
    
    if (st.session_state.connected and not st.session_state.schema_loaded) or \
       (st.session_state.mongodb_connected and not st.session_state.mongodb_schema_loaded):
        st.warning("⚠️ Schema not fully loaded. Please check your connection(s).")
        return
    
    if st.session_state.sql_generator is None and st.session_state.mongodb_query_generator is None:
        st.warning("⚠️ Please load an LLM model from the sidebar to generate queries.")
    
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
                        
                        step_name = step.get('name', '')
                        is_retry = 'retry' in step_name.lower() or 'fix' in step_name.lower() or 'fixed' in step_name.lower()
                        is_sql_gen = 'sql generation' in step_name.lower()
                        is_fix_attempt = 'query fix' in step_name.lower() and step_status == "in_progress"
                        is_fixed = 'query fixed' in step_name.lower()
                        
                        st.markdown(f"{step_icon} **Step {step.get('step')}: {step_name}**")
                        st.markdown(f"  Status: :{status_color}[{step_status}] - {step.get('message', '')}")
                        
                        # Show error if present
                        if step.get('error'):
                            st.error(f"  **Error:** {step.get('error')}")
                        
                        # Show SQL query if present
                        if step.get('sql_query'):
                            if is_fix_attempt:
                                st.warning("  **Failed SQL Query (being fixed):**")
                                st.code(step.get('sql_query'), language="sql")
                            elif is_fixed:
                                st.success("  **Fixed SQL Query (new):**")
                                st.code(step.get('sql_query'), language="sql")
                            elif is_retry:
                                st.markdown("  **SQL Query (Retry):**")
                                st.code(step.get('sql_query'), language="sql")
                            else:
                                st.markdown("  **SQL Query:**")
                                st.code(step.get('sql_query'), language="sql")
            
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
            # Check for DB summary request
            if any(keyword in prompt.lower() for keyword in ["database summary", "db summary", "show database", "list tables", "database details", "schema summary"]):
                logger.info("Detected database summary request")
                try:
                    summary_parts = []
                    
                    # PostgreSQL summary
                    if st.session_state.connected and st.session_state.schema_loaded and st.session_state.schema_rag.knowledge_graph_rag:
                        pg_summary = st.session_state.schema_rag.knowledge_graph_rag.get_database_summary(
                            database_name=st.session_state.postgres_db_name
                        )
                        summary_parts.append(f"## 🐘 PostgreSQL Database: {st.session_state.postgres_db_name}\n\n{pg_summary}")
                        
                        # Check for entities without descriptions
                        missing = st.session_state.schema_rag.knowledge_graph_rag.find_entities_without_descriptions(
                            database_name=st.session_state.postgres_db_name
                        )
                        
                        if missing["tables"] or missing["columns"]:
                            summary_parts.append("\n💡 **Tip:** Some PostgreSQL tables and columns don't have descriptions.")
                    
                    # MongoDB summary
                    if st.session_state.mongodb_connected and st.session_state.mongodb_schema_loaded and st.session_state.schema_rag.knowledge_graph_rag:
                        mongo_schema = st.session_state.mongodb_client.fetch_schema()
                        if mongo_schema:
                            mongo_summary = f"## 🍃 MongoDB Database: {st.session_state.mongodb_db_name}\n\n"
                            mongo_summary += f"**Collections:** {len(mongo_schema.get('collections', []))}\n\n"
                            for collection in mongo_schema.get("collections", []):
                                mongo_summary += f"### Collection: {collection['name']}\n"
                                mongo_summary += f"- Document Count: {collection.get('document_count', 0)}\n"
                                mongo_summary += f"- Fields: {len(collection.get('fields', []))}\n\n"
                            summary_parts.append(mongo_summary)
                    
                    if summary_parts:
                        full_summary = "\n\n---\n\n".join(summary_parts)
                        st.markdown(full_summary)
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": full_summary
                        })
                    else:
                        st.warning("No databases connected or schema not loaded.")
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": "No databases connected or schema not loaded."
                        })
                    st.rerun()
                except Exception as e:
                    logger.error(f"Error generating database summary: {e}")
                    st.error(f"Error generating database summary: {str(e)}")
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": f"Error generating database summary: {str(e)}"
                    })
                    st.rerun()
            
            # Check if this is a query example
            elif st.session_state.query_example_handler.is_query_example(prompt):
                logger.info("Detected query example in user message")
                query_example = st.session_state.query_example_handler.parse_query_example(prompt)
                
                if query_example and (st.session_state.schema_loaded or st.session_state.mongodb_schema_loaded):
                    try:
                        # Store query example in knowledge graph
                        if st.session_state.schema_rag.knowledge_graph_rag:
                            # Determine which database to use based on entity type
                            database_name = None
                            if query_example.get("table_name"):
                                # PostgreSQL table/column
                                database_name = st.session_state.postgres_db_name
                            elif query_example["entity_type"] == "collection":
                                # MongoDB collection
                                database_name = st.session_state.mongodb_db_name
                            else:
                                # Default to PostgreSQL if available, else MongoDB
                                database_name = st.session_state.postgres_db_name or st.session_state.mongodb_db_name
                            
                            st.session_state.schema_rag.knowledge_graph_rag.add_query_example(
                                entity_type=query_example["entity_type"],
                                entity_name=query_example["entity_name"],
                                query=query_example["query"],
                                description=query_example.get("description", ""),
                                table_name=query_example.get("table_name"),
                                database_name=database_name
                            )
                            
                            entity_desc = f"{query_example['entity_type']} '{query_example['entity_name']}'"
                            if query_example.get("table_name"):
                                entity_desc = f"column '{query_example['entity_name']}' in table '{query_example['table_name']}'"
                            
                            st.success(f"✅ Query example saved for {entity_desc}!")
                            st.code(query_example["query"], language="sql")
                            
                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": f"Query example saved for {entity_desc}!"
                            })
                            st.rerun()
                        else:
                            st.warning("Knowledge graph not connected. Query examples can only be saved when Neo4j is connected.")
                    except Exception as e:
                        logger.error(f"Error saving query example: {e}")
                        st.error(f"Error saving query example: {str(e)}")
                else:
                    st.warning("Could not parse query example. Please format it as: 'Example query for table_name: SELECT ...'")
            
            # Check if this is an annotation
            elif st.session_state.annotation_handler.is_annotation(prompt):
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
            
            # Check if any database is connected
            if not st.session_state.connected and not st.session_state.mongodb_connected:
                st.warning("⚠️ Please connect to at least one database (PostgreSQL or MongoDB).")
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": "⚠️ Please connect to at least one database (PostgreSQL or MongoDB)."
                })
                st.rerun()
                return
            
            # Check if model is loaded
            if st.session_state.sql_generator is None and st.session_state.mongodb_query_generator is None:
                st.warning("⚠️ Please load an LLM model from the sidebar first.")
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": "⚠️ Please load an LLM model from the sidebar to generate queries."
                })
                st.rerun()
                return
            
            # Initialize workflow agents if needed (for orchestrator)
            if st.session_state.connected and st.session_state.workflow_agent is None:
                st.session_state.workflow_agent = WorkflowAgent(
                    sql_generator=st.session_state.sql_generator,
                    db_client=st.session_state.db_client,
                    schema_rag=st.session_state.schema_rag,
                    response_generator=st.session_state.response_generator,
                    query_classifier=st.session_state.query_classifier,
                    max_retries=3
                )
            
            if st.session_state.mongodb_connected and st.session_state.mongodb_workflow_agent is None:
                st.session_state.mongodb_workflow_agent = MongoDBWorkflowAgent(
                    mongodb_query_generator=st.session_state.mongodb_query_generator,
                    mongodb_client=st.session_state.mongodb_client,
                    knowledge_graph_rag=st.session_state.schema_rag.knowledge_graph_rag if st.session_state.schema_rag.knowledge_graph_rag else None,
                    response_generator=st.session_state.response_generator,
                    max_retries=3
                )
            
            # Initialize orchestrator agent if needed
            if st.session_state.orchestrator_agent is None:
                st.session_state.orchestrator_agent = OrchestratorAgent(
                    postgres_workflow_agent=st.session_state.workflow_agent,
                    mongodb_workflow_agent=st.session_state.mongodb_workflow_agent,
                    database_router=st.session_state.database_router,
                    postgres_client=st.session_state.db_client,
                    mongodb_client=st.session_state.mongodb_client,
                    schema_rag=st.session_state.schema_rag
                )
            
            # Get conversation history
            conversation_history = [
                {k: v for k, v in msg.items() if k not in ["query_results", "steps"]}
                for msg in st.session_state.messages
            ]
            
            # Container for step-by-step progress
            steps_container = st.container()
            
            # Run orchestrator agent
            logger.info("Starting orchestrator agent")
            with st.spinner("Processing your query..."):
                result = st.session_state.orchestrator_agent.run(
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
                        
                        # Check if this is a MongoDB query step
                        is_mongodb = "mongodb_query" in step or "MongoDB" in step.get('name', '')
                        is_postgres = "sql_query" in step or "PostgreSQL" in step.get('name', '')
                        is_orchestrator = "Orchestrator" in step.get('name', '') or "Query Classification" in step.get('name', '') or "Database Routing" in step.get('name', '')
                        
                        query_key = "mongodb_query" if is_mongodb else "sql_query"
                        
                        step_name = step.get('name', '')
                        is_retry = 'retry' in step_name.lower() or 'fix' in step_name.lower() or 'fixed' in step_name.lower()
                        is_sql_gen = 'sql generation' in step_name.lower() or 'query generation' in step_name.lower()
                        is_fix_attempt = 'query fix' in step_name.lower() and step_status == "in_progress"
                        is_fixed = 'query fixed' in step_name.lower()
                        
                        # Expand orchestrator steps, retries, errors, and query generation by default
                        expanded = True if (is_orchestrator or is_retry or step_status == "error" or is_sql_gen) else False
                        
                        with st.expander(f"{step_icon} Step {step.get('step')}: {step_name}", expanded=expanded):
                            st.markdown(f"**Status:** :{status_color}[{step_status}]")
                            st.markdown(f"**Details:** {step.get('message', '')}")
                            
                            # Show error if present
                            if step.get('error'):
                                st.error(f"**Error:** {step.get('error')}")
                            
                            # Show query (SQL or MongoDB) if present
                            query = step.get('sql_query') or step.get('mongodb_query')
                            if query:
                                if is_mongodb:
                                    # MongoDB query display
                                    if isinstance(query, dict):
                                        query_str = json.dumps(query, indent=2)
                                    else:
                                        query_str = str(query)
                                    
                                    if is_fix_attempt:
                                        st.warning("**Failed MongoDB Query (being fixed):**")
                                        st.code(query_str, language="json")
                                    elif is_fixed:
                                        st.success("**Fixed MongoDB Query (new):**")
                                        st.code(query_str, language="json")
                                    elif is_retry:
                                        st.markdown("**MongoDB Query (Retry):**")
                                        st.code(query_str, language="json")
                                    else:
                                        st.markdown("**MongoDB Query:**")
                                        st.code(query_str, language="json")
                                else:
                                    # SQL query display
                                    if is_fix_attempt:
                                        st.warning("**Failed SQL Query (being fixed):**")
                                        st.code(query, language="sql")
                                    elif is_fixed:
                                        st.success("**Fixed SQL Query (new):**")
                                        st.code(query, language="sql")
                                    elif is_retry:
                                        st.markdown("**SQL Query (Retry):**")
                                        st.code(query, language="sql")
                                    else:
                                        st.markdown("**SQL Query:**")
                                        st.code(query, language="sql")
            
            # Show generated queries if available (from sub-workflows or direct)
            queries_shown = False
            if result.get("postgres_result") and result["postgres_result"].get("sql_query"):
                with st.expander("🔍 View Generated PostgreSQL SQL Query", expanded=False):
                    st.code(result["postgres_result"]["sql_query"], language="sql")
                queries_shown = True
            
            if result.get("mongodb_result") and result["mongodb_result"].get("mongodb_query"):
                with st.expander("🔍 View Generated MongoDB Query", expanded=False):
                    query = result["mongodb_result"]["mongodb_query"]
                    if isinstance(query, dict):
                        st.code(json.dumps(query, indent=2), language="json")
                    else:
                        st.code(str(query), language="json")
                queries_shown = True
            
            # Fallback to direct query fields if sub-results not available
            if not queries_shown:
                if result.get("sql_query"):
                    with st.expander("🔍 View Generated SQL Query", expanded=False):
                        st.code(result["sql_query"], language="sql")
                elif result.get("mongodb_query"):
                    with st.expander("🔍 View Generated MongoDB Query", expanded=False):
                        query = result["mongodb_query"]
                        if isinstance(query, dict):
                            st.code(json.dumps(query, indent=2), language="json")
                        else:
                            st.code(str(query), language="json")
            
            # Display final response
            final_response = result.get("final_response", "No response generated.")
            st.markdown(final_response)
            
            # Display results if available
            if result.get("df") is not None:
                df = result["df"]
                if len(df) > 0:
                    st.dataframe(df, use_container_width=True)
            
            # Store in messages
            # Extract queries from sub-results if available
            sql_query = result.get("sql_query")
            mongodb_query = result.get("mongodb_query")
            
            if result.get("postgres_result"):
                sql_query = result["postgres_result"].get("sql_query") or sql_query
            if result.get("mongodb_result"):
                mongodb_query = result["mongodb_result"].get("mongodb_query") or mongodb_query
            
            message_entry = {
                "role": "assistant",
                "content": final_response,
                "sql_query": sql_query,
                "mongodb_query": mongodb_query,
                "steps": result.get("steps", []),
                "query_results": result.get("df")
            }
            
            st.session_state.messages.append(message_entry)
            st.rerun()


if __name__ == "__main__":
    main()

