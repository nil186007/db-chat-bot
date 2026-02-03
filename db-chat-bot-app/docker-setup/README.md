# Docker Setup for Database ChatBot

This directory contains all Docker-related files for setting up:
- PostgreSQL database with sample e-commerce data
- Neo4j knowledge graph for storing database metadata and annotations
- MongoDB database with supply chain and inventory data
- pgAdmin web client for PostgreSQL
- Mongo Express web client for MongoDB

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
├── docker-compose.yml           # Docker Compose configuration
├── scripts/
│   ├── init.sql                 # PostgreSQL schema initialization
│   ├── load_data.sql            # PostgreSQL sample data loading
│   ├── load_mongodb_data.js     # MongoDB supply chain data (JavaScript)
│   ├── load_mongodb_data.py     # MongoDB supply chain data (Python)
│   └── load_mongodb_data.sh     # MongoDB data loading script
└── README.md                    # This file
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

### MongoDB (Supply Chain & Inventory)
- **Container:** `db-chat-bot-mongodb`
- **Port:** `27017`
- **Database:** `ecommerce_db`
- **Username:** `admin`
- **Password:** `adminpassword`
- **Purpose:** Stores supply chain and inventory data related to products
- **Collections:**
  - `vendors` - Vendor information
  - `product_vendor_mapping` - Product to vendor relationships
  - `inventory` - Inventory levels (in hand, in transit, ordered)
  - `purchase_orders` - Purchase order records
  - `shipments` - Shipment tracking information
  - `costs` - Production, shipping, storage, and handling costs
  - `warehouses` - Warehouse locations and details

### Mongo Express (Web Client)
- **Container:** `db-chat-bot-mongo-express`
- **URL:** http://localhost:8081
- **Username:** `admin`
- **Password:** `admin`
- **Purpose:** Web-based MongoDB administration interface

## Commands

```bash
# Start containers
docker-compose up -d

# Stop containers
docker-compose down

# View logs
docker-compose logs -f postgres
docker-compose logs -f neo4j
docker-compose logs -f mongodb

# Start only specific services
docker-compose up -d neo4j
docker-compose up -d mongodb

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

## Loading MongoDB Data

**MongoDB data is automatically loaded on first initialization!** 

When you start MongoDB for the first time, the `load_mongodb_data.js` script is automatically executed from the `/docker-entrypoint-initdb.d/` directory, similar to how PostgreSQL loads SQL scripts.

### Automatic Loading (Default Behavior)

The data loading script runs automatically when:
- MongoDB container is created for the first time
- MongoDB data volume is empty (fresh start)

**No manual action required!** Just start the containers:
```bash
docker-compose up -d mongodb
```

### Manual Loading (If Needed)

If you need to reload data manually (e.g., after clearing the database):

#### Option 1: Using the shell script
```bash
cd docker-setup/scripts
./load_mongodb_data.sh
```

#### Option 2: Using the JavaScript file directly
```bash
docker exec -i db-chat-bot-mongodb mongosh -u admin -p adminpassword --authenticationDatabase admin ecommerce_db < scripts/load_mongodb_data.js
```

#### Option 3: Using the Python script
```bash
cd docker-setup/scripts
python3 load_mongodb_data.py
```

### Resetting MongoDB Data

To reset MongoDB and trigger automatic data loading again:
```bash
# Stop MongoDB
docker-compose stop mongodb

# Remove the data volume
docker volume rm db-chat-bot-app_mongodb_data

# Start MongoDB again (will auto-load data)
docker-compose up -d mongodb
```

## MongoDB Collections

The MongoDB database contains the following collections:

1. **vendors** - Vendor information (5 vendors)
   - Vendor details, contact info, specializations, ratings

2. **product_vendor_mapping** - Links products to vendors
   - Maps all 25 products to their primary vendors
   - Includes lead time information

3. **inventory** - Current inventory status for all products
   - `quantity_in_hand` - Available stock
   - `quantity_in_transit` - Items being shipped
   - `quantity_ordered` - Items on order
   - `quantity_reserved` - Reserved stock
   - Reorder points and max stock levels
   - Warehouse locations

4. **purchase_orders** - Purchase order records
   - PO numbers, vendors, products
   - Order dates, delivery dates
   - Costs and payment status

5. **shipments** - Shipment tracking
   - Tracking numbers, carriers
   - Origin and destination
   - Shipping costs
   - Delivery status

6. **costs** - Various cost types
   - Production costs
   - Shipping costs
   - Storage costs
   - Handling costs

7. **warehouses** - Warehouse information
   - 5 warehouse locations
   - Capacity and utilization
   - Manager contacts

## Notes

- Data persists in Docker volumes even after stopping containers
- To reset the database, use `docker-compose down -v` and restart
- SQL scripts in `scripts/` are automatically executed in alphabetical order on first initialization
- Neo4j is optional - the app works with in-memory storage if Neo4j is not available
- MongoDB data must be loaded manually using the scripts provided

