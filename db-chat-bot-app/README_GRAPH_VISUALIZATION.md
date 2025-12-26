# LangGraph Workflow Visualization

This document explains how to visualize the LangGraph workflow used by the Database ChatBot agent.

## Quick Start

Run the visualization script:

```bash
poetry run python visualize_graph.py
```

This will:
1. Generate a Mermaid diagram
2. Save it to `workflow_graph.mmd`
3. Display it in the console

## Viewing the Graph

### Option 1: Mermaid Live Editor (Recommended)

1. Copy the Mermaid diagram from the console output or from `workflow_graph.mmd`
2. Go to https://mermaid.live/
3. Paste the diagram
4. You'll see an interactive visualization

### Option 2: GitHub/GitLab

If you commit `workflow_graph.mmd` to your repository, GitHub and GitLab will automatically render it in markdown files:

```markdown
```mermaid
[paste diagram content here]
```
```

### Option 3: VS Code

Install the "Markdown Preview Mermaid Support" extension to view Mermaid diagrams directly in VS Code.

### Option 4: Programmatically

You can also generate the diagram from code:

```python
from db_chatbot.agents.workflow_agent import WorkflowAgent
# ... initialize agent ...

# Generate and save diagram
diagram = agent.visualize_graph("my_graph.mmd")
print(diagram)
```

## Workflow Structure

The workflow consists of the following nodes:

1. **classify_query** - Classifies user queries (greeting, general, or SQL)
2. **retrieve_schema** - Retrieves database schema from RAG
3. **generate_sql** - Generates SQL query from natural language
4. **validate_sql** - Validates SQL using input guardrails
5. **execute_query** - Executes query using db_client tool
6. **fix_query** - Attempts to fix failed queries
7. **generate_response** - Generates natural language response

## Conditional Routing

- **classify_query** → Routes to `retrieve_schema` for SQL queries, or `END` for greetings/general questions
- **validate_sql** → Routes to `fix_query` if validation fails (with retries), or `execute_query` if valid
- **execute_query** → Routes to `fix_query` on error (with retries), `generate_response` on success, or `END` if max retries reached
- **fix_query** → Always routes back to `validate_sql` to re-validate the fixed query

## Graph Flow

```
START → classify_query → [SQL?] → retrieve_schema → generate_sql → validate_sql
                                                           ↓           ↓
                                                      [valid?]    [invalid?]
                                                           ↓           ↓
                                                      execute_query  fix_query
                                                           ↓           ↓
                                                      [success?]      ↓
                                                           ↓          ↓
                                                      generate_response
                                                           ↓
                                                          END
```

