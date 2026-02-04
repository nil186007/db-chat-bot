"""
Database router to determine which database (PostgreSQL or MongoDB) to query based on user intent.
Uses knowledge graph RAG to find the most relevant database.
"""
from typing import Optional, Literal
from db_chatbot.config.settings import get_logger
from db_chatbot.rag.knowledge_graph_rag import KnowledgeGraphRAG
import ollama

logger = get_logger(__name__)


class DatabaseRouter:
    """Routes queries to appropriate database based on user intent using knowledge graph RAG."""
    
    def __init__(self, model_name: str = None, knowledge_graph_rag: Optional[KnowledgeGraphRAG] = None):
        """
        Initialize database router.
        
        Args:
            model_name: Name of the Ollama model to use. If None, uses first available model.
            knowledge_graph_rag: KnowledgeGraphRAG instance for relevance-based routing
        """
        self.model_name = model_name
        self.knowledge_graph_rag = knowledge_graph_rag
        if not self.model_name:
            self._auto_select_model()
        logger.info(f"DatabaseRouter initialized with model: {self.model_name}, RAG: {knowledge_graph_rag is not None}")
    
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
        conversation_history: list = None,
        postgres_db_name: Optional[str] = None,
        mongodb_db_name: Optional[str] = None
    ) -> Literal["postgresql", "mongodb", "both", "unknown"]:
        """
        Determine which database(s) to query based on user intent using knowledge graph RAG.
        
        Args:
            user_query: User's natural language query
            postgres_schema: PostgreSQL schema information (optional)
            mongodb_schema: MongoDB schema information (optional)
            conversation_history: Previous conversation messages (optional)
            postgres_db_name: PostgreSQL database name for RAG search
            mongodb_db_name: MongoDB database name for RAG search
        
        Returns:
            "postgresql", "mongodb", "both", or "unknown"
        """
        logger.info(f"Routing query: {user_query[:50]}...")
        
        # Use knowledge graph RAG for relevance-based routing if available
        if self.knowledge_graph_rag and (postgres_db_name or mongodb_db_name):
            return self._rag_based_routing(user_query, postgres_db_name, mongodb_db_name)
        
        # Fallback to LLM-based routing if RAG not available
        return self._llm_based_routing(user_query, postgres_schema, mongodb_schema, conversation_history)
    
    def _rag_based_routing(
        self,
        user_query: str,
        postgres_db_name: Optional[str] = None,
        mongodb_db_name: Optional[str] = None
    ) -> Literal["postgresql", "mongodb", "both", "unknown"]:
        """Route query based on knowledge graph RAG relevance scores."""
        logger.info("ROUTING METHOD: Knowledge Graph RAG-based routing")
        logger.info(f"  Query: {user_query}")
        
        postgres_score = 0
        mongodb_score = 0
        postgres_details = {}
        mongodb_details = {}
        
        # Get PostgreSQL relevance score
        if postgres_db_name:
            try:
                logger.info("  Calculating PostgreSQL relevance score...")
                postgres_details = self.knowledge_graph_rag.get_relevance_score(
                    user_query=user_query,
                    database_name=postgres_db_name,
                    db_type="postgresql"
                )
                postgres_score = postgres_details.get("score", 0)
                matched_entities = postgres_details.get("matched_entities", [])
                match_details = postgres_details.get("match_details", {})
                
                logger.info(f"  PostgreSQL Score: {postgres_score}")
                logger.info(f"  PostgreSQL Matches: {postgres_details.get('total_matches', 0)} entities")
                if matched_entities:
                    logger.info(f"  PostgreSQL Matched Entities:")
                    for entity in matched_entities[:5]:  # Log first 5
                        logger.info(f"    - {entity.get('type')}: {entity.get('name')} (score: {entity.get('score')})")
                if match_details.get("table_matches"):
                    logger.info(f"  PostgreSQL Table Matches: {match_details.get('table_matches', [])[:5]}")
                if match_details.get("column_matches"):
                    logger.info(f"  PostgreSQL Column Matches: {match_details.get('column_matches', [])[:5]}")
            except Exception as e:
                logger.warning(f"  Error getting PostgreSQL relevance score: {e}", exc_info=True)
        
        # Get MongoDB relevance score
        if mongodb_db_name:
            try:
                logger.info("  Calculating MongoDB relevance score...")
                mongodb_details = self.knowledge_graph_rag.get_relevance_score(
                    user_query=user_query,
                    database_name=mongodb_db_name,
                    db_type="mongodb"
                )
                mongodb_score = mongodb_details.get("score", 0)
                matched_entities = mongodb_details.get("matched_entities", [])
                match_details = mongodb_details.get("match_details", {})
                
                logger.info(f"  MongoDB Score: {mongodb_score}")
                logger.info(f"  MongoDB Matches: {mongodb_details.get('total_matches', 0)} entities")
                if matched_entities:
                    logger.info(f"  MongoDB Matched Entities:")
                    for entity in matched_entities[:5]:  # Log first 5
                        logger.info(f"    - {entity.get('type')}: {entity.get('name')} (score: {entity.get('score')})")
                if match_details.get("collection_matches"):
                    logger.info(f"  MongoDB Collection Matches: {match_details.get('collection_matches', [])[:5]}")
                if match_details.get("field_matches"):
                    logger.info(f"  MongoDB Field Matches: {match_details.get('field_matches', [])[:5]}")
            except Exception as e:
                logger.warning(f"  Error getting MongoDB relevance score: {e}", exc_info=True)
        
        # Determine routing based on scores
        logger.info("  SCORE COMPARISON:")
        logger.info(f"    PostgreSQL: {postgres_score}")
        logger.info(f"    MongoDB: {mongodb_score}")
        
        if postgres_score == 0 and mongodb_score == 0:
            logger.warning("  No relevance matches found in either database")
            return "unknown"
        elif postgres_score > 0 and mongodb_score > 0:
            # Both have matches - route to the one with higher score
            if postgres_score > mongodb_score:
                logger.info(f"  ROUTING DECISION: PostgreSQL (score: {postgres_score} > {mongodb_score})")
                return "postgresql"
            elif mongodb_score > postgres_score:
                logger.info(f"  ROUTING DECISION: MongoDB (score: {mongodb_score} > {postgres_score})")
                return "mongodb"
            else:
                # Equal scores - could route to both or use additional logic
                logger.info(f"  ROUTING DECISION: Both (equal scores: {postgres_score})")
                return "both"
        elif postgres_score > 0:
            logger.info(f"  ROUTING DECISION: PostgreSQL (score: {postgres_score}, MongoDB: 0)")
            return "postgresql"
        elif mongodb_score > 0:
            logger.info(f"  ROUTING DECISION: MongoDB (score: {mongodb_score}, PostgreSQL: 0)")
            return "mongodb"
        else:
            return "unknown"
    
    def _llm_based_routing(
        self,
        user_query: str,
        postgres_schema: Optional[dict] = None,
        mongodb_schema: Optional[dict] = None,
        conversation_history: list = None
    ) -> Literal["postgresql", "mongodb", "both", "unknown"]:
        """Fallback LLM-based routing when RAG is not available."""
        logger.info("Using LLM-based routing (RAG not available)")
        
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
- Table names suggest PostgreSQL (e.g., "products", "orders", "customers", "reviews", "order_items")
- Collection names suggest MongoDB (e.g., "vendors", "inventory", "supply_chain", "purchase_orders", "shipments")
- Field names in collections can help identify MongoDB queries
- Keywords like "vendor", "vendors", "inventory", "supply chain", "shipping", "purchase order", "warehouse" typically suggest MongoDB
- Keywords like "sold", "sales", "most sold", "best selling", "top selling", "order", "orders", "customer", "product", "review" suggest PostgreSQL
- If the query mentions concepts related to supply chain, inventory management, vendors, shipping logistics, purchase orders - it's likely MongoDB
- If the query mentions sales, orders (customer orders), products sold, customers, reviews, ratings - it's likely PostgreSQL

IMPORTANT DISTINCTION:
- "orders" or "order" in the context of SALES/CUSTOMER PURCHASES = PostgreSQL (orders table)
- "purchase orders" or "purchase order" in the context of SUPPLY CHAIN = MongoDB (purchase_orders collection)
- "sold", "sales", "most sold", "best selling" = PostgreSQL (order_items table)
- "vendor", "inventory", "shipping" = MongoDB

Pay attention to the collection names listed above. If the user asks about "vendor", "vendors", "inventory", "purchase order", or similar concepts that match MongoDB collection names, route to MongoDB.

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
        
        # MongoDB keywords - supply chain and inventory related
        mongo_keywords = ["collection", "document", "mongodb", "mongo", "nosql", 
                         "vendor", "vendors", "inventory", "supply", "supplychain",
                         "supply chain", "shipping", "transit", "purchase order", "purchase orders",
                         "warehouse", "warehouses", "shipment", "shipments", "carrier"]
        # PostgreSQL keywords - sales and e-commerce related
        postgres_keywords = ["table", "row", "sql", "postgres", "postgresql", "join", "foreign key",
                           "sold", "sales", "order", "orders", "customer", "customers", "product", "products",
                           "review", "reviews", "rating", "ratings", "most sold", "best selling", "top selling",
                           "purchase", "buy", "bought", "transaction", "transactions"]
        
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
        
        # Check for PostgreSQL-specific keywords (sales, orders, etc.)
        postgres_keyword_match = any(kw in query_lower for kw in postgres_keywords)
        if postgres_keyword_match:
            logger.debug(f"PostgreSQL keyword match: {[kw for kw in postgres_keywords if kw in query_lower]}")
        
        # Determine routing - prioritize PostgreSQL for sales/orders queries
        # Check for sales-related keywords first
        sales_keywords = ["sold", "sales", "most sold", "best selling", "top selling", "customer", "order", "orders"]
        has_sales_keywords = any(kw in query_lower for kw in sales_keywords)
        
        if mongo_match and postgres_match:
            # If both match, check for sales-related keywords to prioritize PostgreSQL
            if has_sales_keywords:
                logger.info(f"Both databases matched but sales keywords detected - routing to PostgreSQL")
                return "postgresql"
            logger.info(f"Both databases matched - mongo: {matched_collection}, postgres: {postgres_match}")
            return "both"
        elif has_sales_keywords or (postgres_match and not mongo_match):
            # Prioritize PostgreSQL for sales/orders queries
            logger.info(f"Routing to PostgreSQL - sales/orders keyword or table match")
            return "postgresql"
        elif mongo_match or mongo_keyword_match:
            logger.info(f"Routing to MongoDB - match: {matched_collection or 'keyword match'}")
            return "mongodb"
        elif postgres_match or postgres_keyword_match:
            logger.info(f"Routing to PostgreSQL - match: {postgres_match or 'keyword match'}")
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
