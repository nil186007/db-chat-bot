"""
Database router to determine which database (PostgreSQL or MongoDB) to query based on user intent.
"""
from typing import Optional, Literal
from db_chatbot.config.settings import get_logger
import ollama

logger = get_logger(__name__)


class DatabaseRouter:
    """Routes queries to appropriate database based on user intent."""
    
    def __init__(self, model_name: str = None):
        """
        Initialize database router.
        
        Args:
            model_name: Name of the Ollama model to use. If None, uses first available model.
        """
        self.model_name = model_name
        if not self.model_name:
            self._auto_select_model()
        logger.info(f"DatabaseRouter initialized with model: {self.model_name}")
    
    def _auto_select_model(self):
        """Auto-select the first available model."""
        try:
            response = ollama.list()
            models = response.get('models', [])
            if models:
                self.model_name = models[0].get('name', '')
                if self.model_name:
                    logger.info(f"Auto-selected model: {self.model_name}")
                else:
                    logger.warning("No valid model name found")
            else:
                logger.warning("No models available in Ollama")
        except Exception as e:
            logger.error(f"Error auto-selecting model: {str(e)}")
    
    def route_query(
        self,
        user_query: str,
        postgres_schema: Optional[dict] = None,
        mongodb_schema: Optional[dict] = None,
        conversation_history: list = None
    ) -> Literal["postgresql", "mongodb", "both", "unknown"]:
        """
        Determine which database(s) to query based on user intent.
        
        Args:
            user_query: User's natural language query
            postgres_schema: PostgreSQL schema information (optional)
            mongodb_schema: MongoDB schema information (optional)
            conversation_history: Previous conversation messages (optional)
        
        Returns:
            "postgresql", "mongodb", "both", or "unknown"
        """
        logger.info(f"Routing query: {user_query[:50]}...")
        
        # Build context about available databases
        available_dbs = []
        if postgres_schema:
            table_count = len(postgres_schema.get("tables", []))
            available_dbs.append(f"PostgreSQL with {table_count} table(s)")
        if mongodb_schema:
            collection_count = len(mongodb_schema.get("collections", []))
            available_dbs.append(f"MongoDB with {collection_count} collection(s)")
        
        if not available_dbs:
            logger.warning("No databases available for routing")
            return "unknown"
        
        # Build prompt for LLM-based routing
        schema_context = ""
        if postgres_schema:
            schema_context += "\nPostgreSQL Tables:\n"
            for table in postgres_schema.get("tables", []):
                schema_context += f"- {table['name']}\n"
        
        if mongodb_schema:
            schema_context += "\nMongoDB Collections:\n"
            for collection in mongodb_schema.get("collections", []):
                schema_context += f"- {collection['name']}\n"
                # Also include field names for better matching
                field_names = [f.get("name", "") for f in collection.get("fields", [])[:5]]
                if field_names:
                    schema_context += f"  Fields: {', '.join(field_names)}\n"
        
        prompt = f"""You are a database routing assistant. Determine which database(s) the user's query should be executed against.

Available databases:
{', '.join(available_dbs)}

{schema_context}

User Query: {user_query}

Based on the query, determine which database to use:
- "postgresql" if the query is about relational data, SQL tables, or traditional database concepts
- "mongodb" if the query mentions collections, documents, or NoSQL concepts
- "both" if the query requires data from both databases
- "unknown" if the query is unclear or doesn't require database access

Consider:
- Table names suggest PostgreSQL
- Collection names suggest MongoDB (e.g., "vendors", "inventory", "supply_chain")
- Field names in collections can help identify MongoDB queries
- Keywords like "vendor", "inventory", "supply chain", "shipping" typically suggest MongoDB
- Keywords like "table", "row", "join", "foreign key" suggest PostgreSQL
- If the query mentions concepts related to supply chain, inventory, vendors, shipping - it's likely MongoDB
- If the query mentions products, orders, customers, reviews - it's likely PostgreSQL

IMPORTANT: Pay attention to the collection names listed above. If the user asks about "vendor", "vendors", "inventory", or similar concepts that match MongoDB collection names, route to MongoDB.

Answer with ONLY one word: postgresql, mongodb, both, or unknown

Your answer:"""

        try:
            response = ollama.generate(
                model=self.model_name,
                prompt=prompt,
                options={
                    "temperature": 0.1,
                    "num_predict": 10
                }
            )
            
            answer = response['response'].strip().lower()
            
            # Parse answer
            if "postgresql" in answer or "postgres" in answer:
                result = "postgresql"
            elif "mongodb" in answer or "mongo" in answer:
                result = "mongodb"
            elif "both" in answer:
                result = "both"
            else:
                result = "unknown"
            
            logger.info(f"Query routed to: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error in database routing: {str(e)}")
            # Fallback to keyword-based routing
            return self._keyword_based_routing(user_query, postgres_schema, mongodb_schema)
    
    def _keyword_based_routing(
        self,
        user_query: str,
        postgres_schema: Optional[dict] = None,
        mongodb_schema: Optional[dict] = None
    ) -> Literal["postgresql", "mongodb", "both", "unknown"]:
        """Fallback keyword-based routing."""
        query_lower = user_query.lower()
        query_words = set(query_lower.split())
        
        # MongoDB keywords - expanded list
        mongo_keywords = ["collection", "document", "mongodb", "mongo", "nosql", 
                         "vendor", "vendors", "inventory", "supply", "supplychain",
                         "supply chain", "shipping", "transit", "ordered", "quantity"]
        # PostgreSQL keywords
        postgres_keywords = ["table", "row", "sql", "postgres", "postgresql", "join", "foreign key"]
        
        # Check for table/collection names in schemas (fuzzy matching)
        mongo_match = False
        postgres_match = False
        matched_collection = None
        
        if mongodb_schema:
            collections = mongodb_schema.get("collections", [])
            logger.debug(f"Checking {len(collections)} MongoDB collections against query: {query_lower}")
            for collection in collections:
                collection_name = collection["name"].lower()
                # Exact match
                if collection_name in query_lower:
                    mongo_match = True
                    matched_collection = collection_name
                    logger.debug(f"Exact match found: collection '{collection_name}' in query")
                    break
                # Singular/plural matching (e.g., "vendor" matches "vendors" collection)
                if collection_name in query_words or collection_name.rstrip('s') in query_words:
                    mongo_match = True
                    matched_collection = collection_name
                    logger.debug(f"Word match found: collection '{collection_name}' in query words")
                    break
                # Check if query contains singular form of collection name
                if collection_name.endswith('s') and collection_name[:-1] in query_words:
                    mongo_match = True
                    matched_collection = collection_name
                    logger.debug(f"Singular/plural match: '{collection_name[:-1]}' matches collection '{collection_name}'")
                    break
                # Check field names in collection
                for field in collection.get("fields", []):
                    field_name = field.get("name", "").lower()
                    if field_name in query_words:
                        mongo_match = True
                        matched_collection = collection_name
                        logger.debug(f"Field match found: field '{field_name}' in collection '{collection_name}'")
                        break
                if mongo_match:
                    break
        
        if postgres_schema:
            for table in postgres_schema.get("tables", []):
                table_name = table["name"].lower()
                if table_name in query_lower:
                    postgres_match = True
                    break
                # Check column names
                for col in table.get("columns", []):
                    if col.get("name", "").lower() in query_words:
                        postgres_match = True
                        break
                if postgres_match:
                    break
        
        # Check for MongoDB-specific keywords
        mongo_keyword_match = any(kw in query_lower for kw in mongo_keywords)
        if mongo_keyword_match:
            logger.debug(f"MongoDB keyword match: {[kw for kw in mongo_keywords if kw in query_lower]}")
        
        # Determine routing
        if mongo_match and postgres_match:
            logger.info(f"Both databases matched - mongo: {matched_collection}, postgres: {postgres_match}")
            return "both"
        elif mongo_match or mongo_keyword_match:
            logger.info(f"Routing to MongoDB - match: {matched_collection or 'keyword match'}")
            return "mongodb"
        elif postgres_match or any(kw in query_lower for kw in postgres_keywords):
            logger.info(f"Routing to PostgreSQL - match: {postgres_match}")
            return "postgresql"
        else:
            # Default to PostgreSQL if both are available, otherwise MongoDB
            if postgres_schema and mongodb_schema:
                logger.warning("No clear match - defaulting to PostgreSQL (both databases available)")
                return "postgresql"  # Default preference
            elif postgres_schema:
                logger.info("Routing to PostgreSQL (only PostgreSQL available)")
                return "postgresql"
            elif mongodb_schema:
                logger.info("Routing to MongoDB (only MongoDB available)")
                return "mongodb"
            else:
                logger.warning("No databases available for routing")
                return "unknown"
