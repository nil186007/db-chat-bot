# Database ChatBot 🤖

A Streamlit-based chatbot that connects to PostgreSQL databases and allows you to query them using natural language. The chatbot uses a local LLM (via Ollama) to convert your questions into SQL queries.

## Features

- 🔌 **PostgreSQL Connection**: Easy connection to any PostgreSQL database
- 📊 **Schema Discovery**: Automatically fetches and loads all table schemas
- 💬 **Natural Language Queries**: Ask questions in plain English
- 🤖 **Local LLM**: Uses Ollama for local SQL generation (no API keys needed)
- 🚀 **Real-time Execution**: Execute generated SQL queries and view results
- 💾 **Conversation History**: Maintains context across multiple queries
- 🔒 **Security Guardrails**: Only SELECT queries allowed, SQL injection prevention
- 📝 **Comprehensive Logging**: Detailed logging for debugging and monitoring
- 🔍 **Auto Model Detection**: Automatically detects available Ollama models

## Prerequisites

1. **Python 3.10+**
2. **Poetry** for dependency management
   - Install from: https://python-poetry.org/docs/#installation
   - Or via pip: `pip install poetry`
3. **Ollama** installed and running
   - Download from: https://ollama.ai
   - Install and start the Ollama service
4. **PostgreSQL Database** (accessible from your machine)
   - Option 1: Use Docker Compose (recommended - see Docker Setup below)
   - Option 2: Install PostgreSQL locally

## Installation

1. **Clone or navigate to the project directory:**
   ```bash
   cd db-chat-bot-app
   ```

2. **Install Python dependencies using Poetry:**
   ```bash
   # Install Poetry (if not already installed)
   curl -sSL https://install.python-poetry.org | python3 -
   
   # Install project dependencies
   poetry install
   
   # Activate the virtual environment
   poetry shell
   ```

3. **Install and set up Ollama:**
   ```bash
   # On macOS/Linux
   curl -fsSL https://ollama.ai/install.sh | sh
   
   # Or download from https://ollama.ai
   ```

4. **Pull a language model:**
   ```bash
   # Recommended models for SQL generation:
   ollama pull llama3.2:3b      # Small, fast model
   ollama pull llama3.2:1b      # Even smaller
   ollama pull mistral          # Alternative option
   ollama pull codellama        # Code-specialized model
   ```

## Docker Setup (Recommended)

We've included a Docker Compose setup to quickly spin up a PostgreSQL database with sample e-commerce data.

### Quick Start with Docker

1. **Start the database containers:**
   ```bash
   cd db-chat-bot-app/docker-setup
   docker-compose up -d
   ```

2. **Verify containers are running:**
   ```bash
   cd docker-setup
   docker-compose ps
   ```

3. **Access pgAdmin (optional):**
   - Open http://localhost:5050 in your browser
   - Login with:
     - Email: `admin@admin.com`
     - Password: `admin`
   - Add a new server:
     - Host: `postgres`
     - Port: `5432`
     - Database: `ecommerce_db`
     - Username: `postgres`
     - Password: `postgres`

4. **Connect to the database in the chatbot:**
   - Host: `localhost`
   - Port: `5432`
   - Database: `ecommerce_db`
   - Username: `postgres`
   - Password: `postgres`

### Sample Database Schema

The Docker setup automatically creates an e-commerce database with the following tables:

- **products** - Product catalog with name, description, category, price, and stock
- **customers** - Customer information and contact details
- **orders** - Order records with status and totals
- **order_items** - Individual items in each order
- **reviews** - Product reviews and ratings

### Sample Data

The database is pre-populated with:
- 20 products across multiple categories (Electronics, Home & Kitchen, Sports & Outdoors, etc.)
- 20 customers with full contact information
- 15 orders with various statuses
- Multiple order items linking products to orders
- 10 product reviews with ratings

### Docker Commands

```bash
# Navigate to docker-setup directory
cd docker-setup

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

### Example Queries for Sample Database

Once connected to the `ecommerce_db`, try these natural language queries:

- "Show me all products in the Electronics category"
- "What are the top 5 most expensive products?"
- "List all customers who placed orders"
- "How many orders are in 'delivered' status?"
- "Show me the total revenue by product category"
- "Which products have reviews with 5-star ratings?"
- "List all orders placed in January 2024"
- "Find customers who haven't placed any orders"
- "What is the average order value?"
- "Show me products with low stock (less than 100 units)"

## Usage

1. **Start the Streamlit app:**
   ```bash
   # Using the run script (recommended)
   poetry run python run.py
   
   # Or run directly
   poetry run streamlit run src/db_chatbot/app.py
   ```

2. **Connect to your database:**
   - The app will open in your browser
   - Use the sidebar to enter your PostgreSQL connection details:
     - Host (default: localhost)
     - Port (default: 5432)
     - Database name
     - Username
     - Password
   - Click "Connect to Database"

3. **Load an LLM model:**
   - Select a model from the dropdown in the sidebar
   - Click "Load Model"

4. **Start querying:**
   - Type your questions in natural language
   - The chatbot will generate SQL queries
   - Review and execute the generated queries
   - View results directly in the chat interface

## Example Queries

### General Examples
- "Show me all users"
- "How many orders were placed last month?"
- "What are the top 5 products by sales?"
- "Find all customers who haven't placed an order"
- "Show me the total revenue by product category"

### Examples for Sample E-commerce Database
See the [Docker Setup](#docker-setup-recommended) section for database-specific examples.

## Project Structure

```
db-chat-bot-app/
├── src/
│   └── db_chatbot/           # Main application package
│       ├── __init__.py
│       ├── app.py            # Main Streamlit application
│       ├── config/           # Configuration module
│       │   ├── __init__.py
│       │   └── settings.py   # Logging and configuration settings
│       ├── core/             # Core functionality modules
│       │   ├── __init__.py
│       │   ├── database.py   # Database connection and schema fetching
│       │   └── sql_generator.py  # LLM integration for SQL generation
│       ├── handlers/         # Query handling modules
│       │   ├── __init__.py
│       │   └── query_handler.py  # Query classification and routing
│       └── utils/            # Utility modules
│           ├── __init__.py
│           ├── validators.py     # SQL validation and security guardrails
│           └── result_processor.py  # Result formatting and summarization
├── run.py                    # Application entry point
├── logs/                     # Application logs (auto-created)
├── pyproject.toml            # Poetry configuration and dependencies
├── poetry.lock               # Locked dependency versions (auto-generated)
├── docker-setup/             # Docker setup and database scripts
│   ├── docker-compose.yml    # Docker Compose configuration
│   └── scripts/
│       ├── init.sql          # Database schema initialization
│       └── load_data.sql     # Sample data loading script
└── README.md                 # This file
```

## How It Works

1. **Connection**: The app connects to your PostgreSQL database using psycopg2
2. **Schema Loading**: It queries the `information_schema` to fetch all table structures, columns, data types, primary keys, and foreign keys
3. **SQL Generation**: When you ask a question, the LLM receives:
   - The complete database schema
   - Your natural language question
   - Previous conversation context
4. **Query Validation**: All generated SQL queries are validated:
   - Only SELECT queries are allowed (no data manipulation)
   - SQL injection patterns are detected and blocked
   - Query syntax is verified
5. **Query Execution**: Validated SQL queries can be reviewed and executed
6. **Results Display**: Query results are displayed as interactive DataFrames
7. **Logging**: All operations are logged to `logs/db_chatbot.log` for debugging and monitoring

## Security Features

- **SELECT-only queries**: Only SELECT statements are allowed. INSERT, UPDATE, DELETE, DROP, and other data manipulation operations are blocked.
- **SQL Injection Prevention**: Detection and blocking of common SQL injection patterns
- **Query Validation**: All queries are parsed and validated before execution
- **Input Sanitization**: Natural language queries are processed safely

## Supported Models

The app supports any Ollama model, but these are recommended for SQL generation:
- `llama3.2:3b` - Balanced performance and accuracy
- `llama3.2:1b` - Faster, lighter option
- `mistral` - Alternative language model
- `codellama` - Optimized for code generation

## Troubleshooting

### Ollama not connecting
- Make sure Ollama is running: `ollama serve` or check if the service is running
- Verify installation: `ollama list`

### Model not found
- Pull the model: `ollama pull <model_name>`
- Check available models: `ollama list`

### Database connection issues
- Verify PostgreSQL is running
- Check connection credentials
- Ensure the database is accessible from your network
- Check firewall settings

### Schema loading fails
- Verify you have proper permissions on the database
- The app currently loads tables from the `public` schema only
- Check database logs for specific errors

## Dependency Management

This project uses **Poetry** for dependency management. Common commands:

```bash
# Install dependencies
poetry install

# Add a new dependency
poetry add <package-name>

# Add a development dependency
poetry add --group dev <package-name>

# Update dependencies
poetry update

# Show dependency tree
poetry show --tree

# Activate virtual environment
poetry shell

# Run commands in virtual environment
poetry run <command>
```

## Security Notes

- Database credentials are stored only in session state (cleared when app restarts)
- Never commit credentials to version control
- Consider using environment variables or Streamlit secrets for production use

## License

This project is open source and available for personal and commercial use.

