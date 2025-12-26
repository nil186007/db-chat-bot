"""
Script to visualize the LangGraph workflow.
"""
import sys
from pathlib import Path

# Add src directory to Python path
src_dir = Path(__file__).parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from db_chatbot.agents.workflow_agent import WorkflowAgent
from db_chatbot.query_generator.sql_generator import SQLGenerator
from db_chatbot.db_clients.postgres_client import PostgresClient
from db_chatbot.rag.schema_rag import SchemaRAG

# Create a minimal agent instance to access the graph
# We need the dependencies but won't actually run queries
sql_generator = SQLGenerator()
db_client = PostgresClient()
schema_rag = SchemaRAG()

# Initialize agent to build the graph
agent = WorkflowAgent(
    sql_generator=sql_generator,
    db_client=db_client,
    schema_rag=schema_rag,
    max_retries=3
)

# Get the compiled graph and visualize it
compiled_graph = agent.compiled_graph

print("=" * 80)
print("LangGraph Workflow Visualization")
print("=" * 80)
print()

# Method 1: Mermaid diagram (can be used in markdown or online tools)
print("Mermaid Diagram (copy this to https://mermaid.live/):")
print("-" * 80)
try:
    mermaid_diagram = compiled_graph.get_graph().draw_mermaid()
    print(mermaid_diagram)
    print()
    print("📊 You can paste this diagram at: https://mermaid.live/")
    print("   Or use it in Markdown files, GitHub, or documentation tools")
except Exception as e:
    print(f"Mermaid diagram not available: {e}")
    # Try alternative method
    try:
        mermaid_diagram = compiled_graph.get_graph().draw_ascii()
        print(mermaid_diagram)
    except:
        pass

print()
print("-" * 80)
print()

# Method 2: Print graph structure
print("Graph Structure:")
print("-" * 80)
try:
    graph_structure = compiled_graph.get_graph()
    print(f"Nodes: {list(graph_structure.nodes.keys())}")
    print(f"Edges: {graph_structure.edges}")
    print(f"First node: {graph_structure.first}")
except Exception as e:
    print(f"Error getting graph structure: {e}")

print()
print("-" * 80)
print()

# Method 3: Save to file
try:
    mermaid_diagram = compiled_graph.get_graph().draw_mermaid()
    with open("workflow_graph.mmd", "w") as f:
        f.write(mermaid_diagram)
    print("✅ Graph saved to workflow_graph.mmd")
    print("   You can open it in Mermaid Live Editor or any Mermaid-compatible viewer")
except Exception as e:
    print(f"Could not save graph: {e}")

print()
print("=" * 80)

