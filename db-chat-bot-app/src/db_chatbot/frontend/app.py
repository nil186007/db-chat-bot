"""
Streamlit-based SQL database chatbot with natural language to SQL conversion.
Supports PostgreSQL and other SQL database flavors (MongoDB removed).
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
from db_chatbot.db_clients.neo4j_client import Neo4jClient
from db_chatbot.query_generator.sql_generator import SQLGenerator
from db_chatbot.query_generator.response_generator import ResponseGenerator
from db_chatbot.query_intent.classifier import QueryClassifier
from db_chatbot.rag.schema_rag import SchemaRAG
from db_chatbot.rag.knowledge_graph_rag import KnowledgeGraphRAG
from db_chatbot.handlers.annotation_handler import AnnotationHandler
from db_chatbot.handlers.query_example_handler import QueryExampleHandler
from db_chatbot.handlers.database_type_handler import DatabaseTypeHandler
from db_chatbot.handlers.schema_query_handler import SchemaQueryHandler
from db_chatbot.agents.workflow_agent import WorkflowAgent
from db_chatbot.agents.orchestrator_agent import OrchestratorAgent
from db_chatbot.guardrails.input_guardrails import InputGuardrails
from db_chatbot.guardrails.output_guardrails import OutputGuardrails
from db_chatbot.query_intent.database_router import DatabaseRouter
from db_chatbot.query_intent.unified_intent_classifier import UnifiedIntentClassifier
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
    # Initialize handlers without model initially (will be updated when model loads)
    st.session_state.annotation_handler = AnnotationHandler(model_name=None)
    st.session_state.query_example_handler = QueryExampleHandler()
    st.session_state.database_type_handler = DatabaseTypeHandler()
    st.session_state.schema_query_handler = SchemaQueryHandler(model_name=None)
    st.session_state.unified_intent_classifier = None  # Will be initialized when model loads
    # Initialize SchemaRAG without KnowledgeGraphRAG initially
    st.session_state.schema_rag = SchemaRAG()
    # Last 3 user queries (DB_QUERY type only) for quick reference
    st.session_state.recent_user_queries = []
    # PostgreSQL connection info
    st.session_state.postgres_db_name = None
    st.session_state.postgres_db_host = None
    st.session_state.postgres_db_port = None
    logger.info("Session state initialized")

if "response_generator" not in st.session_state:
    st.session_state.response_generator = None
    logger.debug("ResponseGenerator placeholder initialized")

if "query_classifier" not in st.session_state:
    st.session_state.query_classifier = None
    logger.debug("QueryClassifier placeholder initialized")

if "workflow_agent" not in st.session_state:
    st.session_state.workflow_agent = None
    st.session_state.orchestrator_agent = None
    st.session_state.database_router = None
    logger.debug("WorkflowAgent placeholder initialized")


def _normalize_workflow_steps(steps: list) -> list:
    """
    Deduplicate and renumber workflow steps for proper display.
    - Removes duplicate entries (same step num + name; keeps last/final state)
    - Assigns sequential display numbers 1, 2, 3...
    """
    if not steps:
        return []
    seen = {}
    last_index = {}
    for i, s in enumerate(steps):
        key = (s.get("step"), s.get("name", ""))
        seen[key] = dict(s)
        last_index[key] = i
    ordered = sorted(seen.items(), key=lambda x: last_index.get(x[0], 0))
    result = []
    for i, (_, s) in enumerate(ordered, 1):
        s["_display_num"] = i
        result.append(s)
    return result


def _render_result_with_chart_option(df: pd.DataFrame, key_prefix: str = ""):
    """Display dataframe with Table/Chart view toggle. Masks sensitive data before display."""
    if df is None or not isinstance(df, pd.DataFrame) or len(df) == 0:
        return
    df = OutputGuardrails.mask_sensitive_dataframe(df.copy())
    view_mode = st.radio(
        "View as",
        options=["Table", "Chart"],
        key=f"view_mode_{key_prefix}",
        horizontal=True,
        label_visibility="collapsed"
    )
    if view_mode == "Table":
        st.dataframe(df, use_container_width=True)
    else:
        numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
        all_cols = list(df.columns)
        if not numeric_cols:
            st.info("No numeric columns to chart. Showing table instead.")
            st.dataframe(df, use_container_width=True)
            return
        chart_type = st.selectbox(
            "Chart type",
            ["Bar", "Line", "Area", "Pie"],
            key=f"chart_type_{key_prefix}",
            label_visibility="collapsed"
        )
        x_options = ["(First column)"] + all_cols
        x_col = st.selectbox(
            "X-axis / Labels",
            options=x_options,
            key=f"x_col_{key_prefix}",
            index=0
        )
        y_col = st.selectbox(
            "Y-axis / Values",
            options=numeric_cols,
            key=f"y_col_{key_prefix}",
            index=0
        )
        chart_df = df.head(50).copy()
        x_use = chart_df.columns[0] if x_col == "(First column)" else x_col
        try:
            if chart_type in ("Bar", "Line", "Area"):
                plot_df = chart_df[[x_use, y_col]].set_index(x_use)
                if chart_type == "Bar":
                    st.bar_chart(plot_df)
                elif chart_type == "Line":
                    st.line_chart(plot_df)
                else:
                    st.area_chart(plot_df)
            else:  # Pie
                import matplotlib.pyplot as plt
                fig, ax = plt.subplots(figsize=(8, 6))
                pie_data = chart_df.head(20)
                labels = [str(v)[:30] for v in pie_data[x_use]]  # Truncate long labels
                vals = pie_data[y_col]
                ax.pie(vals, labels=labels, autopct="%1.1f%%", startangle=90)
                ax.axis("equal")
                st.pyplot(fig)
                plt.close()
        except Exception as e:
            st.warning(f"Could not render chart: {e}")
            st.dataframe(df, use_container_width=True)


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

def main():
    logger.info("Starting main application")
    st.title("🗄️ Database ChatBot")
    st.markdown("Connect to your SQL database (PostgreSQL) and query using natural language!")
    
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
        
        # Recent queries section
        recent = getattr(st.session_state, "recent_user_queries", [])
        if recent:
            with st.expander("📝 Last 3 Queries", expanded=False):
                for i, q in enumerate(reversed(recent), 1):
                    st.caption(f"{i}. {q[:60]}{'...' if len(q) > 60 else ''}")
                    st.code(q, language=None)
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
                pg_name = st.text_input("Database", value="customer_orders_and_reviews_db", key="pg_db")
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
                # Initialize unified intent classifier (most important component)
                st.session_state.unified_intent_classifier = UnifiedIntentClassifier(model_name=selected_model)
                # Initialize query classifier with the same model (for backward compatibility)
                st.session_state.query_classifier = QueryClassifier(model_name=selected_model)
                # Initialize database router with knowledge graph RAG if available
                kg_rag = None
                if st.session_state.schema_rag and st.session_state.schema_rag.knowledge_graph_rag:
                    kg_rag = st.session_state.schema_rag.knowledge_graph_rag
                st.session_state.database_router = DatabaseRouter(
                    model_name=selected_model,
                    knowledge_graph_rag=kg_rag
                )
                # Update annotation handler with model for LLM-based parsing (fallback)
                st.session_state.annotation_handler = AnnotationHandler(model_name=selected_model)
                # Update schema query handler with model for LLM-based parsing (fallback)
                st.session_state.schema_query_handler = SchemaQueryHandler(model_name=selected_model)
                # Reset workflow agents and orchestrator - will be initialized when needed
                st.session_state.workflow_agent = None
                st.session_state.orchestrator_agent = None
                st.success(f"Loaded model: {selected_model}")
                logger.info(f"Model {selected_model} loaded successfully")
            except Exception as e:
                st.error(f"Failed to load model: {str(e)}")
                logger.error(f"Model loading failed: {str(e)}")
        
        # Show current model
        if st.session_state.sql_generator:
            st.info(f"📌 Current model: {st.session_state.sql_generator.model_name}")
        
        # Schema Explorer & Query Examples (when connected and schema loaded)
        if st.session_state.connected and st.session_state.schema_loaded and st.session_state.schema_rag.knowledge_graph_rag:
            st.divider()
            with st.expander("📋 Schema & Examples", expanded=False):
                kg = st.session_state.schema_rag.knowledge_graph_rag
                db_name = st.session_state.postgres_db_name
                tables = kg.get_tables_for_database(db_name) if db_name else []
                
                if tables:
                    for tbl in tables:
                        schema_name = tbl.get("schema_name", "public")
                        table_label = f'"{schema_name}".{tbl["name"]}' if schema_name != "public" else tbl["name"]
                        with st.expander(f"📁 {table_label}", expanded=False):
                            # Table description/context
                            existing_desc = kg.get_annotation("table", tbl["name"], database_name=db_name, schema_name=schema_name)
                            new_desc = st.text_area(
                                "Table context/description",
                                value=existing_desc or "",
                                key=f"tbl_desc_{tbl['name']}_{schema_name}",
                                placeholder="e.g., Contains product catalog with name, price, category"
                            )
                            if st.button("Save table context", key=f"save_tbl_{tbl['name']}"):
                                kg.add_annotation("table", tbl["name"], content=new_desc, database_name=db_name, schema_name=schema_name)
                                st.success("Saved!")
                                st.rerun()
                            
                            # Columns with context
                            columns = kg.get_columns_for_table(tbl["name"], db_name, schema_name)
                            for col in columns:
                                col_ann = kg.get_annotation("column", col["name"], table_name=tbl["name"], database_name=db_name, schema_name=schema_name)
                                with st.expander(f"  📌 {col['name']} ({col.get('type', '')})", expanded=False):
                                    col_ctx = st.text_area("Column context", value=col_ann or "", key=f"col_{tbl['name']}_{col['name']}", placeholder="e.g., Unique product identifier")
                                    if st.button("Save", key=f"save_col_{tbl['name']}_{col['name']}"):
                                        kg.add_annotation("column", col["name"], col_ctx, table_name=tbl["name"], database_name=db_name, schema_name=schema_name)
                                        st.rerun()
                            
                            # Query examples for this table
                            examples = kg.get_query_examples_for_table(tbl["name"], db_name, schema_name)
                            if examples:
                                st.caption("Query examples:")
                                for ex in examples[:3]:
                                    st.code(ex.get("sql_query", ""), language="sql")
                            
                            # Add query example form
                            st.divider()
                            with st.form(f"add_example_{tbl['name']}"):
                                st.caption("Add query example")
                                ex_nl = st.text_input("Natural language (what does this query do?)", key=f"ex_nl_{tbl['name']}", placeholder="e.g., show all products")
                                ex_sql = st.text_area("SQL query", key=f"ex_sql_{tbl['name']}", placeholder="SELECT * FROM ...")
                                if st.form_submit_button("Save example"):
                                    if ex_sql.strip() and ex_nl.strip():
                                        try:
                                            kg.add_query_example(
                                                entity_type="table",
                                                entity_name=tbl["name"],
                                                query=ex_sql.strip(),
                                                natural_language=ex_nl.strip(),
                                                table_name=tbl["name"],
                                                schema_name=schema_name,
                                                database_name=db_name
                                            )
                                            st.success("Example saved!")
                                            st.rerun()
                                        except Exception as e:
                                            st.error(str(e))
                                    else:
                                        st.warning("Enter both natural language and SQL")
                else:
                    st.caption("No tables in graph. Load schema first.")
        
        # Info about metadata management via chat
        st.divider()
        st.info("💡 **Tip:** Provide metadata by chatting with the bot:\n\n"
                "**Database descriptions:**\n"
                "- 'PostgreSQL stores: products, orders, customers, sales data'\n\n"
                "**Table descriptions:**\n"
                "- 'The products table contains: product information, pricing, inventory levels'\n\n"
                "**Column descriptions:**\n"
                "- 'The product_id column is: unique identifier for each product'")
    
    # Main chat interface
    if not st.session_state.connected:
        st.info("👈 Please connect to your SQL database (PostgreSQL) using the sidebar to get started.")
        st.markdown("""
        ### How to use:
        1. Enter your database connection details in the sidebar
        2. Click "Connect to PostgreSQL"
        3. Wait for the schema to load
        4. Select and load an LLM model
        5. Start asking questions about your database!
        """)
        return
    
    if st.session_state.connected and not st.session_state.schema_loaded:
        st.warning("⚠️ Schema not fully loaded. Please check your connection.")
        return
    
    if st.session_state.sql_generator is None:
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
                    for step in _normalize_workflow_steps(message["steps"]):
                        step_status = step.get("status", "pending")
                        step_icon = "✅" if step_status == "completed" else "❌" if step_status == "error" else "⏳"
                        status_color = "green" if step_status == "completed" else "red" if step_status == "error" else "blue"
                        
                        step_name = step.get('name', '')
                        display_num = step.get("_display_num", step.get("step", 0))
                        is_retry = 'retry' in step_name.lower() or 'fix' in step_name.lower() or 'fixed' in step_name.lower()
                        is_sql_gen = 'sql generation' in step_name.lower()
                        is_fix_attempt = 'query fix' in step_name.lower() and step_status == "in_progress"
                        is_fixed = 'query fixed' in step_name.lower()
                        
                        st.markdown(f"{step_icon} **Step {display_num}: {step_name}**")
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
            
            # Show query results if available (with chart option)
            if message.get("query_results") is not None:
                df = message.get("query_results")
                if isinstance(df, pd.DataFrame) and len(df) > 0:
                    _render_result_with_chart_option(df, key_prefix=f"msg_{idx}")
    
    # Chat input
    if prompt := st.chat_input("Ask a question about your database..."):
        logger.info("=" * 80)
        logger.info("FRONTEND: User query received")
        logger.info(f"USER QUERY: {prompt}")
        logger.info("=" * 80)
        logger.info(f"User query received: {prompt[:50]}...")
        # Add user message to chat
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            # Early guardrail: reject dangerous intents and SQL injection in user input
            is_safe, guardrail_error = InputGuardrails.validate_user_input(prompt)
            if not is_safe:
                st.error(f"⛔ **Not allowed**\n\n{guardrail_error}")
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"⛔ **Not allowed**\n\n{guardrail_error}"
                })
                st.rerun()
                return

            # Use unified intent classifier if available (most important step)
            if st.session_state.unified_intent_classifier:
                logger.info("Using unified intent classifier")
                classification = st.session_state.unified_intent_classifier.classify_intent(prompt)
                intent = classification.get("intent")
                details = classification.get("details", {})
                confidence = classification.get("confidence", 0.0)
                
                logger.info(f"Intent classified: {intent} (confidence: {confidence:.2f})")
                logger.debug(f"Classification details: {details}")
                
                # Route based on intent
                if intent == "SCHEMA_QUERY":
                    logger.info("Routing to SCHEMA_QUERY handler")
                    # Handle schema query from RAG
                    if st.session_state.schema_rag.knowledge_graph_rag:
                        try:
                            response_parts = []
                            kg_rag = st.session_state.schema_rag.knowledge_graph_rag
                            query_type = details.get("query_type")
                            
                            if query_type == "databases":
                                databases = kg_rag.get_all_databases()
                                if databases:
                                    response_parts.append("## 📊 Connected Databases\n\n")
                                    for db in databases:
                                        db_type_icon = "🐘" if db["type"] == "postgresql" else "💾"
                                        response_parts.append(f"### {db_type_icon} {db['name']} ({db['type'].upper()})")
                                        response_parts.append(f"- **Host:** {db.get('host', 'N/A')}")
                                        response_parts.append(f"- **Port:** {db.get('port', 'N/A')}")
                                        if db.get("description"):
                                            response_parts.append(f"- **Description:** {db['description']}")
                                        response_parts.append("")
                                else:
                                    response_parts.append("No databases found in knowledge graph.")
                            
                            elif query_type == "tables":
                                database_name = details.get("database_name")
                                if not database_name:
                                    databases = [db for db in kg_rag.get_all_databases() if db["type"] == "postgresql"]
                                    if databases:
                                        for db in databases:
                                            tables = kg_rag.get_tables_for_database(db["name"])
                                            if tables:
                                                response_parts.append(f"## 📋 Tables in {db['name']} (PostgreSQL)\n\n")
                                                for table in tables:
                                                    schema_name = table.get("schema_name", "public")
                                                    table_label = f'"{schema_name}".{table["name"]}' if schema_name != "public" else table["name"]
                                                    response_parts.append(f"### {table_label}")
                                                    response_parts.append(f"- **Columns:** {table['column_count']}")
                                                    if table.get("description"):
                                                        response_parts.append(f"- **Description:** {table['description']}")
                                                    response_parts.append("")
                                else:
                                    tables = kg_rag.get_tables_for_database(database_name)
                                    if tables:
                                        response_parts.append(f"## 📋 Tables in {database_name}\n\n")
                                        for table in tables:
                                            schema_name = table.get("schema_name", "public")
                                            table_label = f'"{schema_name}".{table["name"]}' if schema_name != "public" else table["name"]
                                            response_parts.append(f"### {table_label}")
                                            response_parts.append(f"- **Columns:** {table['column_count']}")
                                            if table.get("description"):
                                                response_parts.append(f"- **Description:** {table['description']}")
                                            response_parts.append("")
                            
                            elif query_type == "columns":
                                table_name = details.get("table_name")
                                database_name = details.get("database_name") or st.session_state.postgres_db_name
                                if table_name and database_name:
                                    columns = kg_rag.get_columns_for_table(table_name, database_name)
                                    if columns:
                                        response_parts.append(f"## 📊 Columns in {table_name} table\n\n")
                                        for col in columns:
                                            nullable_str = " (nullable)" if col.get("nullable") else " (not null)"
                                            response_parts.append(f"### {col['name']}")
                                            response_parts.append(f"- **Type:** {col.get('type', 'N/A')}{nullable_str}")
                                            if col.get("description"):
                                                response_parts.append(f"- **Description:** {col['description']}")
                                            response_parts.append("")
                            
                            if response_parts:
                                full_response = "\n".join(response_parts)
                                st.markdown(full_response)
                                st.session_state.messages.append({
                                    "role": "assistant",
                                    "content": full_response
                                })
                            else:
                                st.warning("Could not retrieve schema information.")
                                st.session_state.messages.append({
                                    "role": "assistant",
                                    "content": "Could not retrieve schema information."
                                })
                            st.rerun()
                        except Exception as e:
                            logger.error(f"Error handling schema query: {e}")
                            st.error(f"Error retrieving schema information: {str(e)}")
                            st.rerun()
                
                elif intent == "METADATA_UPDATE":
                    logger.info("Routing to METADATA_UPDATE handler")
                    # Handle metadata update
                    if st.session_state.schema_rag.knowledge_graph_rag:
                        try:
                            entity_type = details.get("entity_type")
                            entity_name = details.get("entity_name")
                            table_name = details.get("table_name")
                            content = details.get("content")
                            
                            if entity_type and content:
                                # Handle database type descriptions (e.g., "PostgreSQL stores: ...")
                                if entity_type == "database" and not entity_name:
                                    # Check if it's a database type description
                                    query_lower = prompt.lower()
                                    if "postgresql" in query_lower or "postgres" in query_lower:
                                        db_type = "postgresql"
                                        database_name = st.session_state.postgres_db_name
                                        if database_name:
                                            st.session_state.schema_rag.knowledge_graph_rag.update_database_type_description(
                                                db_type=db_type,
                                                description=content
                                            )
                                            response = f"✅ Database description saved for PostgreSQL:\n\n{content}"
                                        else:
                                            response = "⚠️ PostgreSQL database not connected. Please connect first."
                                    else:
                                        response = "⚠️ Could not determine database type. Please specify PostgreSQL."
                                    
                                    st.success(response)
                                    st.session_state.messages.append({
                                        "role": "assistant",
                                        "content": response
                                    })
                                    st.rerun()
                                    return
                                
                                # Handle regular metadata updates (tables, columns, collections, fields, specific databases)
                                if entity_name:
                                    database_name = None
                                    if entity_type in ["table", "column"]:
                                        database_name = st.session_state.postgres_db_name
                                    elif entity_type == "database":
                                        database_name = entity_name if entity_name else st.session_state.postgres_db_name
                                    
                                    st.session_state.schema_rag.add_annotation(
                                        entity_type=entity_type,
                                        entity_name=entity_name,
                                        content=content,
                                        table_name=table_name,
                                        database_name=database_name
                                    )
                                    
                                    entity_desc = f"{entity_type} '{entity_name}'"
                                    if table_name and entity_type == "column":
                                        entity_desc = f"column '{entity_name}' in table '{table_name}'"
                                    
                                    response = f"✅ Metadata saved for {entity_desc}:\n\n{content}"
                                    st.success(response)
                                    st.session_state.messages.append({
                                        "role": "assistant",
                                        "content": response
                                    })
                                    logger.info(f"Metadata stored: {entity_desc}")
                                else:
                                    st.warning("Could not extract entity name from query.")
                                    st.session_state.messages.append({
                                        "role": "assistant",
                                        "content": "Could not extract entity name. Please specify the entity (table, column, or database name)."
                                    })
                            else:
                                st.warning("Could not extract metadata information from query.")
                                st.session_state.messages.append({
                                    "role": "assistant",
                                    "content": "Could not extract metadata information. Please try: 'add description to table products that it contains product information'"
                                })
                            st.rerun()
                        except Exception as e:
                            logger.error(f"Error saving metadata: {e}")
                            st.error(f"Error saving metadata: {str(e)}")
                            st.rerun()
                
                elif intent == "GENERAL_QUESTION":
                    logger.info("Routing to GENERAL_QUESTION handler")
                    greeting_responses = {
                        "hello": "Hello! 👋 I'm your SQL database assistant. How can I help you query your database today?",
                        "hi": "Hi! 👋 I can help you query your SQL database, manage metadata, and explore schema information.",
                        "help": "I can help you:\n- Query data from your SQL database\n- Add/update metadata for databases, tables, and columns\n- Explore schema information\n- Show connected databases and their structure\n\nTry asking: 'show all products', 'list tables', or 'add description to products table'"
                    }
                    
                    query_lower = prompt.lower().strip()
                    response = greeting_responses.get(query_lower, 
                        "Hello! 👋 I'm your SQL database assistant. I can help you:\n"
                        "- Query data from your database\n"
                        "- Manage metadata and descriptions\n"
                        "- Explore schema information\n\n"
                        "What would you like to do?")
                    
                    st.markdown(response)
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": response
                    })
                    st.rerun()
                
                elif intent == "DB_QUERY":
                    logger.info("Routing to DB_QUERY handler - will proceed to orchestrator")
                    # Continue to orchestrator for DB query execution
                    # (fall through to orchestrator code below)
            
            # Fallback: Check for schema information queries (if unified classifier not available)
            elif st.session_state.schema_query_handler.is_schema_query(prompt):
                logger.info("Detected schema query request")
                schema_query = st.session_state.schema_query_handler.parse_schema_query(prompt)
                
                if schema_query and st.session_state.schema_rag.knowledge_graph_rag:
                    try:
                        response_parts = []
                        kg_rag = st.session_state.schema_rag.knowledge_graph_rag
                        
                        if schema_query["query_type"] == "databases":
                            # Show all databases
                            databases = kg_rag.get_all_databases()
                            if databases:
                                response_parts.append("## 📊 Connected Databases\n\n")
                                for db in databases:
                                    db_type_icon = "🐘" if db["type"] == "postgresql" else "💾"
                                    response_parts.append(f"### {db_type_icon} {db['name']} ({db['type'].upper()})")
                                    response_parts.append(f"- **Host:** {db.get('host', 'N/A')}")
                                    response_parts.append(f"- **Port:** {db.get('port', 'N/A')}")
                                    if db.get("description"):
                                        response_parts.append(f"- **Description:** {db['description']}")
                                    response_parts.append("")
                            else:
                                response_parts.append("No databases found in knowledge graph.")
                        
                        elif schema_query["query_type"] == "tables":
                            # Show tables for database(s)
                            database_name = schema_query.get("database_name")
                            
                            # If database name not specified, show tables for all connected PostgreSQL databases
                            if not database_name:
                                databases = [db for db in kg_rag.get_all_databases() if db["type"] == "postgresql"]
                                if databases:
                                    for db in databases:
                                        tables = kg_rag.get_tables_for_database(db["name"])
                                        if tables:
                                            response_parts.append(f"## 📋 Tables in {db['name']} (PostgreSQL)\n\n")
                                            for table in tables:
                                                response_parts.append(f"### {table['name']}")
                                                response_parts.append(f"- **Columns:** {table['column_count']}")
                                                if table.get("description"):
                                                    response_parts.append(f"- **Description:** {table['description']}")
                                                response_parts.append("")
                                else:
                                    response_parts.append("No PostgreSQL databases found.")
                            else:
                                tables = kg_rag.get_tables_for_database(database_name)
                                if tables:
                                    response_parts.append(f"## 📋 Tables in {database_name}\n\n")
                                    for table in tables:
                                        response_parts.append(f"### {table['name']}")
                                        response_parts.append(f"- **Columns:** {table['column_count']}")
                                        if table.get("description"):
                                            response_parts.append(f"- **Description:** {table['description']}")
                                        response_parts.append("")
                                else:
                                    response_parts.append(f"No tables found for database '{database_name}'.")
                        
                        elif schema_query["query_type"] == "columns":
                            # Show columns for a table
                            table_name = schema_query.get("table_name")
                            database_name = schema_query.get("database_name") or st.session_state.postgres_db_name
                            
                            if table_name and database_name:
                                columns = kg_rag.get_columns_for_table(table_name, database_name)
                                if columns:
                                    response_parts.append(f"## 📊 Columns in {table_name} table\n\n")
                                    for col in columns:
                                        nullable_str = " (nullable)" if col.get("nullable") else " (not null)"
                                        response_parts.append(f"### {col['name']}")
                                        response_parts.append(f"- **Type:** {col.get('type', 'N/A')}{nullable_str}")
                                        if col.get("description"):
                                            response_parts.append(f"- **Description:** {col['description']}")
                                        response_parts.append("")
                                else:
                                    response_parts.append(f"No columns found for table '{table_name}' in database '{database_name}'.")
                            else:
                                response_parts.append("Please specify a table name. Example: 'show columns in products table'")
                        
                        if response_parts:
                            full_response = "\n".join(response_parts)
                            st.markdown(full_response)
                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": full_response
                            })
                        else:
                            st.warning("Could not retrieve schema information. Please ensure databases are connected and schema is loaded.")
                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": "Could not retrieve schema information. Please ensure databases are connected and schema is loaded."
                            })
                        st.rerun()
                    except Exception as e:
                        logger.error(f"Error retrieving schema information: {e}")
                        st.error(f"Error retrieving schema information: {str(e)}")
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": f"Error retrieving schema information: {str(e)}"
                        })
                        st.rerun()
                else:
                    st.warning("Could not parse schema query. Please try: 'show all databases', 'show tables', 'show columns in products table', etc.")
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": "Could not parse schema query. Please try: 'show all databases', 'show tables', 'show columns in products table', etc."
                    })
                    st.rerun()
            
            # Check for DB summary request (legacy support)
            elif any(keyword in prompt.lower() for keyword in ["database summary", "db summary", "show database", "list tables", "database details", "schema summary"]):
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
                
                if query_example and st.session_state.schema_loaded:
                    try:
                        # Store query example in knowledge graph
                        if st.session_state.schema_rag.knowledge_graph_rag:
                            database_name = st.session_state.postgres_db_name
                            
                            st.session_state.schema_rag.knowledge_graph_rag.add_query_example(
                                entity_type=query_example["entity_type"],
                                entity_name=query_example["entity_name"],
                                query=query_example["query"],
                                natural_language=query_example.get("description") or prompt[:200],
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
            
            # Note: Database type description handling is now done by unified intent classifier above
            # This section is kept for fallback if unified classifier is not available
            
            # Note: Annotation handling is now done by unified intent classifier above
            # This section is kept for fallback if unified classifier is not available
            
            if not st.session_state.connected:
                st.warning("⚠️ Please connect to a SQL database (PostgreSQL).")
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": "⚠️ Please connect to a SQL database (PostgreSQL)."
                })
                st.rerun()
                return
            
            if st.session_state.sql_generator is None:
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
                    max_retries=2
                )
            
            # Initialize orchestrator agent if needed
            if st.session_state.orchestrator_agent is None:
                # Update database router with knowledge graph RAG if available
                if st.session_state.database_router and st.session_state.schema_rag and st.session_state.schema_rag.knowledge_graph_rag:
                    st.session_state.database_router.knowledge_graph_rag = st.session_state.schema_rag.knowledge_graph_rag
                
                st.session_state.orchestrator_agent = OrchestratorAgent(
                    postgres_workflow_agent=st.session_state.workflow_agent,
                    database_router=st.session_state.database_router,
                    postgres_client=st.session_state.db_client,
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
                    for step in _normalize_workflow_steps(result["steps"]):
                        step_status = step.get("status", "pending")
                        step_icon = "⏳" if step_status == "in_progress" else "✅" if step_status == "completed" else "❌"
                        status_color = "blue" if step_status == "in_progress" else "green" if step_status == "completed" else "red"
                        
                        is_orchestrator = "Orchestrator" in step.get('name', '') or "Query Classification" in step.get('name', '') or "Database Routing" in step.get('name', '')
                        
                        step_name = step.get('name', '')
                        display_num = step.get("_display_num", step.get("step", 0))
                        is_retry = 'retry' in step_name.lower() or 'fix' in step_name.lower() or 'fixed' in step_name.lower()
                        is_sql_gen = 'sql generation' in step_name.lower() or 'query generation' in step_name.lower()
                        is_fix_attempt = 'query fix' in step_name.lower() and step_status == "in_progress"
                        is_fixed = 'query fixed' in step_name.lower()
                        
                        # Expand orchestrator steps, retries, errors, and query generation by default
                        expanded = True if (is_orchestrator or is_retry or step_status == "error" or is_sql_gen) else False
                        
                        with st.expander(f"{step_icon} Step {display_num}: {step_name}", expanded=expanded):
                            st.markdown(f"**Status:** :{status_color}[{step_status}]")
                            st.markdown(f"**Details:** {step.get('message', '')}")
                            
                            # Show error if present
                            if step.get('error'):
                                st.error(f"**Error:** {step.get('error')}")
                            
                            # Show SQL query if present
                            query = step.get('sql_query')
                            if query:
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
            
            if not queries_shown and result.get("sql_query"):
                with st.expander("🔍 View Generated SQL Query", expanded=False):
                    st.code(result["sql_query"], language="sql")
            
            # Display final response
            final_response = result.get("final_response", "No response generated.")
            st.markdown(final_response)
            
            # Display results if available - check both direct df and from sub-results
            df = result.get("df")
            
            if df is None and result.get("postgres_result"):
                df = result["postgres_result"].get("df")

            if df is not None and isinstance(df, pd.DataFrame) and len(df) > 0:
                _render_result_with_chart_option(df, key_prefix="result")
            
            sql_query = result.get("sql_query")
            query_results_df = df
            if result.get("postgres_result"):
                sql_query = result["postgres_result"].get("sql_query") or sql_query
                if query_results_df is None:
                    query_results_df = result["postgres_result"].get("df")

            # Store last 3 user queries (for DB_QUERY that reached orchestrator)
            if prompt and (query_results_df is not None or result.get("postgres_result")):
                recent = getattr(st.session_state, "recent_user_queries", [])
                if prompt not in recent:
                    recent = [prompt] + [q for q in recent if q != prompt][:2]
                    st.session_state.recent_user_queries = recent[:3]

            message_entry = {
                "role": "assistant",
                "content": final_response,
                "sql_query": sql_query,
                "steps": result.get("steps", []),
                "query_results": query_results_df
            }
            
            st.session_state.messages.append(message_entry)
            st.rerun()


if __name__ == "__main__":
    main()

