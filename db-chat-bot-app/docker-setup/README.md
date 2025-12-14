# Docker Setup for Database ChatBot

This directory contains all Docker-related files for setting up a PostgreSQL database with sample e-commerce data.

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

## Commands

```bash
# Start containers
docker-compose up -d

# Stop containers
docker-compose down

# View logs
docker-compose logs -f postgres

# Stop and remove all data (volumes)
docker-compose down -v

# Restart containers
docker-compose restart
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

## Notes

- Data persists in Docker volumes even after stopping containers
- To reset the database, use `docker-compose down -v` and restart
- SQL scripts in `scripts/` are automatically executed in alphabetical order on first initialization

