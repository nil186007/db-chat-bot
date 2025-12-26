# Neo4j Knowledge Graph Quick Start

## Starting Neo4j

### Start Neo4j with Docker Compose

```bash
cd docker-setup

# Start all services (PostgreSQL, pgAdmin, Neo4j)
docker-compose up -d

# Or start only Neo4j
docker-compose up -d neo4j
```

### Verify Neo4j is Running

```bash
# Check container status
docker-compose ps neo4j

# View logs
docker-compose logs -f neo4j

# Test connection
curl http://localhost:7474
```

## Connection Details

- **Browser UI**: http://localhost:7474
- **Bolt URI**: `bolt://localhost:7687`
- **Username**: `neo4j`
- **Password**: `neo4jpassword`

## Using Neo4j in the Application

### Automatic Connection

The Streamlit app will automatically attempt to connect to Neo4j when it starts:
- Connection URI: `bolt://localhost:7687`
- Credentials: `neo4j` / `neo4jpassword`

If Neo4j is running, it will connect automatically. If not, the app will fall back to in-memory storage.

### Manual Connection

1. Open the app sidebar
2. Under "Knowledge Graph (Neo4j)" section
3. Enter connection details (if different from defaults)
4. Click "Connect to Neo4j"

## What Gets Stored in Neo4j

When you connect to a PostgreSQL database, the schema is automatically stored in Neo4j:

- **Database nodes** - Database instances
- **Table nodes** - All tables with their properties
- **Column nodes** - All columns with data types, constraints
- **Relationships**:
  - Database → Tables (`HAS_TABLE`)
  - Table → Columns (`HAS_COLUMN`)
  - Table → Table (`HAS_FOREIGN_KEY`)
  - Table → Column (`HAS_PRIMARY_KEY`)

When you add annotations in chat, they're stored as:
- **UserAnnotation nodes** with `DESCRIBES` relationships to tables/columns

## Exploring the Graph in Neo4j Browser

1. Open http://localhost:7474
2. Login with `neo4j` / `neo4jpassword`
3. Run Cypher queries to explore:

```cypher
// See all databases
MATCH (db:Database) RETURN db

// See all tables
MATCH (t:Table) RETURN t.name

// See all tables with their columns
MATCH (t:Table)-[:HAS_COLUMN]->(c:Column)
RETURN t.name, collect(c.name) as columns

// See all user annotations
MATCH (ann:UserAnnotation)-[:DESCRIBES]->(e)
RETURN ann.entity_type, ann.entity_name, ann.content

// See table relationships (foreign keys)
MATCH (t1:Table)-[r:HAS_FOREIGN_KEY]->(t2:Table)
RETURN t1.name, r.from_column, t2.name, r.to_column
```

## Stopping Neo4j

```bash
# Stop Neo4j
docker-compose stop neo4j

# Stop and remove container (data persists in volume)
docker-compose rm neo4j

# Remove all data (⚠️ deletes all graph data)
docker-compose down -v neo4j
```

## Troubleshooting

### Neo4j won't start
```bash
# Check logs
docker-compose logs neo4j

# Check if port is already in use
lsof -i :7687
lsof -i :7474
```

### Connection refused
- Make sure Neo4j container is running: `docker-compose ps neo4j`
- Check if ports are accessible: `curl http://localhost:7474`
- Verify credentials match docker-compose.yml

### Reset Neo4j data
```bash
# Stop Neo4j
docker-compose stop neo4j

# Remove volume
docker volume rm db-chat-bot-app_neo4j_data

# Start again
docker-compose up -d neo4j
```

