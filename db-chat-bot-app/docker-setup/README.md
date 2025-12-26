# Docker Setup for Database ChatBot

This directory contains all Docker-related files for setting up:
- PostgreSQL database with sample e-commerce data
- Neo4j knowledge graph for storing database metadata and annotations
- pgAdmin web client for PostgreSQL

## Quick Start

1. **Start the database containers:**
   ```bash
   docker-compose up -d
   ```

2. **Verify containers are running:**
   ```bash
   docker-compose ps
   ```

3. **Connect to the database:**
   - Host: `localhost`
   - Port: `5432`
   - Database: `ecommerce_db`
   - Username: `postgres`
   - Password: `postgres`

## Directory Structure

```
docker-setup/
├── docker-compose.yml    # Docker Compose configuration
├── scripts/
│   ├── init.sql         # Database schema initialization
│   └── load_data.sql    # Sample data loading script
└── README.md            # This file
```

## Services

### PostgreSQL Database
- **Container:** `db-chat-bot-postgres`
- **Port:** `5432`
- **Database:** `ecommerce_db`
- **Auto-initialization:** Schema and data are automatically loaded on first start

### pgAdmin (Web Client)
- **Container:** `db-chat-bot-pgadmin`
- **URL:** http://localhost:5050
- **Email:** `admin@admin.com`
- **Password:** `admin`

### Neo4j (Knowledge Graph)
- **Container:** `db-chat-bot-neo4j`
- **Browser UI:** http://localhost:7474
- **Bolt Connection:** `bolt://localhost:7687`
- **Username:** `neo4j`
- **Password:** `neo4jpassword`
- **Purpose:** Stores database schema metadata and user annotations for enhanced SQL generation

## Commands

```bash
# Start containers
docker-compose up -d

# Stop containers
docker-compose down

# View logs
docker-compose logs -f postgres
docker-compose logs -f neo4j

# Start only Neo4j (if other services already running)
docker-compose up -d neo4j

# Stop and remove all data (volumes)
docker-compose down -v

# Restart containers
docker-compose restart

# Check Neo4j health
docker-compose ps neo4j
```

## Database Schema

The database includes the following tables:
- **products** - Product catalog
- **customers** - Customer information
- **orders** - Order records
- **order_items** - Order line items
- **reviews** - Product reviews

## Sample Data

The database is pre-populated with:
- 20 products across multiple categories
- 20 customers
- 15 orders
- Multiple order items
- 10 product reviews

## Neo4j Knowledge Graph

Neo4j is used to store:
- Database schema metadata (tables, columns, relationships)
- User annotations about database elements
- Enhanced context for SQL generation

### Accessing Neo4j

1. **Browser UI**: Open http://localhost:7474
   - Login with username: `neo4j`, password: `neo4jpassword`
   - Explore the graph structure and run Cypher queries

2. **In the Application**:
   - The app will auto-connect to Neo4j on startup if it's running
   - You can manually connect via the sidebar if needed
   - Connection URI: `bolt://localhost:7687`

### Neo4j Data Persistence

- All graph data is stored in the `neo4j_data` Docker volume
- Data persists across container restarts
- To reset the knowledge graph, stop Neo4j and remove the volume:
  ```bash
  docker-compose stop neo4j
  docker volume rm db-chat-bot-app_neo4j_data
  docker-compose up -d neo4j
  ```

## Notes

- Data persists in Docker volumes even after stopping containers
- To reset the database, use `docker-compose down -v` and restart
- SQL scripts in `scripts/` are automatically executed in alphabetical order on first initialization
- Neo4j is optional - the app works with in-memory storage if Neo4j is not available

