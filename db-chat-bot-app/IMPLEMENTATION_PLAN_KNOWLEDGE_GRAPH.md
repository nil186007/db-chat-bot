# Implementation Plan: Knowledge Graph-Based RAG for DB Metadata

## Overview
Transform the current in-memory schema storage to a Neo4j knowledge graph-based RAG system that:
1. Stores database metadata (tables, columns, relationships) as graph nodes
2. Allows users to add annotations/descriptions about database elements via chat
3. Retrieves relevant schema context using graph-based queries
4. Enhances SQL generation with rich metadata from the knowledge graph

## Architecture

### Knowledge Graph Schema

**Nodes:**
- `Database` - Represents a database instance
  - Properties: `name`, `host`, `port`, `created_at`
- `Table` - Represents a database table
  - Properties: `name`, `description`, `created_at`, `updated_at`
- `Column` - Represents a table column
  - Properties: `name`, `type`, `nullable`, `default_value`, `description`, `created_at`, `updated_at`
- `UserAnnotation` - User-provided information
  - Properties: `content`, `entity_type` (table/column/database), `entity_name`, `created_at`, `updated_at`

**Relationships:**
- `HAS_TABLE` - Database → Table
- `HAS_COLUMN` - Table → Column
- `HAS_PRIMARY_KEY` - Table → Column (with property `is_primary: true`)
- `HAS_FOREIGN_KEY` - Table → Table (with properties: `from_column`, `to_column`)
- `DESCRIBES` - UserAnnotation → (Table|Column|Database)
- `RELATES_TO` - Table → Table (general relationships, e.g., "orders relate to customers")

## Components to Create

### 1. Neo4j Client (`db_clients/neo4j_client.py`)
- Connection management
- Basic CRUD operations
- Query execution
- Health checks

### 2. Knowledge Graph RAG (`rag/knowledge_graph_rag.py`)
- Build graph from PostgreSQL schema
- Store user annotations
- Retrieve relevant schema context using Cypher queries
- Support semantic search (future: vector embeddings)

### 3. Enhanced Schema RAG (`rag/schema_rag.py`)
- Keep existing interface for backward compatibility
- Internally use KnowledgeGraphRAG
- Bridge between old and new implementations

### 4. Annotation Handler (`handlers/annotation_handler.py`)
- Parse user annotations from chat
- Extract entity type (table/column/database)
- Store annotations in knowledge graph
- Validate annotation format

### 5. Frontend Integration (`frontend/app.py`)
- Add annotation input/parsing
- Display annotation options in chat
- Show graph statistics

## Implementation Steps

### Phase 1: Neo4j Client & Knowledge Graph Infrastructure
1. ✅ Add neo4j Python driver to dependencies
2. ✅ Create Neo4jClient class
3. ✅ Create KnowledgeGraphRAG class with basic CRUD
4. ✅ Implement graph building from PostgreSQL schema
5. ✅ Test graph creation and queries

### Phase 2: Annotation System
6. ✅ Create AnnotationHandler
7. ✅ Parse annotations from user chat
8. ✅ Store annotations in graph
9. ✅ Retrieve annotations with schema queries

### Phase 3: Enhanced Retrieval
10. ✅ Implement context retrieval with Cypher queries
11. ✅ Support keyword-based table/column search
12. ✅ Include annotations in retrieved context
13. ✅ Format enhanced context for LLM prompts

### Phase 4: Integration
14. ✅ Update SchemaRAG to use KnowledgeGraphRAG
15. ✅ Update workflow agent to use enhanced RAG
16. ✅ Update frontend for annotation input
17. ✅ Add graph visualization/statistics

### Phase 5: Testing & Optimization
18. ✅ Test full workflow
19. ✅ Optimize Cypher queries
20. ✅ Add error handling and logging

## Example User Interactions

**User adds annotation:**
```
User: "The 'orders' table contains customer purchase records. Each order has a status that can be: pending, processing, shipped, delivered, or cancelled."
```
→ System extracts: Table="orders", description="..."
→ Stores in graph as UserAnnotation → DESCRIBES → Table

**User adds column annotation:**
```
User: "The 'products.price' column stores prices in USD currency"
```
→ System extracts: Table="products", Column="price", description="..."
→ Stores in graph

**Query with enhanced context:**
```
User: "Show me all pending orders"
```
→ Knowledge graph retrieves:
  - Table structure for 'orders'
  - User annotation about order status values
  - Related tables (customers via foreign keys)
→ Enhanced context sent to LLM for better SQL generation

## Technical Details

### Cypher Query Examples

**Build graph from schema:**
```cypher
// Create database node
CREATE (db:Database {name: $db_name, host: $host, port: $port})

// Create table node
CREATE (t:Table {name: $table_name})
CREATE (db)-[:HAS_TABLE]->(t)

// Create column node
CREATE (c:Column {name: $col_name, type: $col_type, nullable: $nullable})
CREATE (t)-[:HAS_COLUMN]->(c)

// Create foreign key relationship
MATCH (t1:Table {name: $table1}), (t2:Table {name: $table2})
CREATE (t1)-[:HAS_FOREIGN_KEY {from_column: $col1, to_column: $col2}]->(t2)
```

**Retrieve context for query:**
```cypher
// Find relevant tables and columns
MATCH (t:Table)
WHERE t.name CONTAINS $keyword OR $keyword IN t.description
OPTIONAL MATCH (t)-[:HAS_COLUMN]->(c:Column)
OPTIONAL MATCH (ann:UserAnnotation)-[:DESCRIBES]->(t)
RETURN t, collect(DISTINCT c) as columns, collect(DISTINCT ann.content) as annotations
```

## Benefits

1. **Persistent Storage**: Metadata persists across sessions
2. **Rich Context**: User annotations provide domain knowledge
3. **Graph Relationships**: Better understanding of table relationships
4. **Extensible**: Easy to add more metadata types
5. **Searchable**: Graph queries enable intelligent context retrieval
6. **Scalable**: Neo4j handles large schemas efficiently

## Future Enhancements

- Vector embeddings for semantic search
- Auto-learn from query patterns
- Suggest annotations based on queries
- Visual graph explorer in UI
- Multi-database support with namespaces

