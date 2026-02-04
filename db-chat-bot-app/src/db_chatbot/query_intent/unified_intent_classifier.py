"""
Unified Intent Classifier that determines query intent and routes to appropriate handler.
This is the most critical component that classifies user queries into:
1. DB_QUERY - Execute database query (PostgreSQL or MongoDB)
2. METADATA_UPDATE - Update metadata/annotations in RAG
3. SCHEMA_QUERY - Answer from RAG schema information
4. GENERAL_QUESTION - General conversation/greeting
"""
import json
import ollama
from typing import Optional, Dict, Any
from db_chatbot.config.settings import get_logger

logger = get_logger(__name__)


class UnifiedIntentClassifier:
    """
    Unified intent classifier that determines the user's intent and extracts relevant information.
    This is the most important component for routing queries correctly.
    """
    
    def __init__(self, model_name: str):
        """
        Initialize unified intent classifier.
        
        Args:
            model_name: Name of the Ollama model to use
        """
        self.model_name = model_name
        logger.info(f"UnifiedIntentClassifier initialized with model: {model_name}")
    
    def classify_intent(self, user_query: str) -> Dict[str, Any]:
        """
        Classify user query intent and extract relevant information.
        
        Args:
            user_query: User's natural language query
        
        Returns:
            Dictionary with classification results:
            {
                "intent": "DB_QUERY" | "METADATA_UPDATE" | "SCHEMA_QUERY" | "GENERAL_QUESTION",
                "confidence": float (0.0-1.0),
                "details": {
                    # For DB_QUERY:
                    "target_db": "postgresql" | "mongodb" | "both" | "unknown",
                    
                    # For METADATA_UPDATE:
                    "entity_type": "database" | "table" | "column" | "collection" | "field",
                    "entity_name": str,
                    "table_name": str (for columns/fields),
                    "content": str (description/metadata),
                    
                    # For SCHEMA_QUERY:
                    "query_type": "databases" | "tables" | "columns" | "collections" | "fields",
                    "database_name": str (optional),
                    "table_name": str (optional, for columns),
                    "collection_name": str (optional, for fields)
                }
            }
        """
        logger.info(f"Classifying intent for query: {user_query[:100]}...")
        
        prompt = self._build_classification_prompt(user_query)
        
        try:
            response = ollama.generate(
                model=self.model_name,
                prompt=prompt,
                options={
                    "temperature": 0.1,  # Low temperature for consistent classification
                    "num_predict": 300   # Enough tokens for detailed JSON response
                }
            )
            
            response_text = response['response'].strip()
            
            # Extract JSON from response
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            # Parse JSON
            try:
                result = json.loads(response_text)
                
                # Validate and normalize result
                intent = result.get("intent", "").upper()
                valid_intents = ["DB_QUERY", "METADATA_UPDATE", "SCHEMA_QUERY", "GENERAL_QUESTION"]
                
                if intent not in valid_intents:
                    logger.warning(f"Invalid intent from LLM: {intent}, defaulting to DB_QUERY")
                    intent = "DB_QUERY"
                
                result["intent"] = intent
                result["confidence"] = float(result.get("confidence", 0.8))
                
                logger.info(f"Intent classified as: {intent} (confidence: {result['confidence']:.2f})")
                logger.debug(f"Classification details: {result.get('details', {})}")
                
                return result
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse LLM response as JSON: {e}")
                logger.error(f"Response text: {response_text[:200]}")
                # Fallback to DB_QUERY
                return {
                    "intent": "DB_QUERY",
                    "confidence": 0.5,
                    "details": {"target_db": "unknown"}
                }
                
        except Exception as e:
            logger.error(f"Error in intent classification: {e}")
            # Fallback to DB_QUERY
            return {
                "intent": "DB_QUERY",
                "confidence": 0.5,
                "details": {"target_db": "unknown"}
            }
    
    def _build_classification_prompt(self, user_query: str) -> str:
        """Build comprehensive prompt for intent classification."""
        return f"""You are an intelligent database assistant that classifies user queries into one of four categories. This is a CRITICAL classification step that determines how the system responds.

User Query: {user_query}

Analyze the query and classify it into ONE of these categories:

1. **DB_QUERY**: The user wants to query/retrieve actual DATA from the database
   - Examples: "show all vendors", "list products", "how many orders", "show product name and total quantity", "find customers who ordered more than 5 items", "get vendor details for product X"
   - Keywords: actual data values, records, filtering, aggregations, calculations, counts, sums, joins
   - Action: Execute SQL or MongoDB query to retrieve data
   - For DB_QUERY, also determine target_db: "postgresql" (for products, orders, customers, reviews), "mongodb" (for vendors, inventory, shipments, purchase orders), "both" (if needs data from both), or "unknown"

2. **METADATA_UPDATE**: The user wants to ADD, UPDATE, or DESCRIBE metadata/annotations for database entities
   - Examples: "add description to table products that it contains product information", "update metadata for column product_id that it is unique identifier", "add description for database customer_orders_and_reviews_db that it contains all orders and reviews", "describe the vendors collection as storing supplier information", "PostgreSQL stores: products, orders, customers, sales data", "MongoDB contains: vendors, inventory, shipments, purchase orders"
   - Keywords: "add description", "update metadata", "describe", "annotation", "metadata for", "description for", "[database_type] stores:", "[database_type] contains:"
   - Action: Store/update metadata in knowledge graph (RAG)
   - For METADATA_UPDATE, extract: entity_type (database/table/column/collection/field), entity_name, table_name (if column/field), content (description)
   - Special case: If query is like "PostgreSQL stores: ..." or "MongoDB contains: ...", entity_type should be "database", entity_name should be the database name (if specified) or null, content should be the description after the colon

3. **SCHEMA_QUERY**: The user wants to see SCHEMA STRUCTURE/METADATA, not actual data
   - Examples: "show all databases", "what databases are available", "list tables", "show columns in products table", "show collections", "show fields in vendors collection"
   - Keywords: schema structure, what tables/columns/collections/fields exist, database structure
   - Action: Retrieve and display schema information from knowledge graph (RAG)
   - For SCHEMA_QUERY, extract: query_type (databases/tables/columns/collections/fields), database_name (optional), table_name (optional), collection_name (optional)

4. **GENERAL_QUESTION**: Greeting, help request, or general conversation
   - Examples: "hello", "hi", "what can you do", "help", "how does this work"
   - Action: Provide general response or help information

CRITICAL DISTINCTIONS:

**DB_QUERY vs SCHEMA_QUERY:**
- "show all vendors" = DB_QUERY (retrieving vendor records/data)
- "show vendors collection" or "show fields in vendors collection" = SCHEMA_QUERY (showing collection structure)
- "list products" = DB_QUERY (retrieving product data)
- "list tables" = SCHEMA_QUERY (showing table names/structure)
- "show product name" = DB_QUERY (retrieving product names)
- "show columns in products table" = SCHEMA_QUERY (showing column structure)

**DB_QUERY vs METADATA_UPDATE:**
- "show products" = DB_QUERY (retrieving product data)
- "add description to products table" = METADATA_UPDATE (updating metadata)
- "describe products" = Could be either - if asking what products exist = DB_QUERY, if adding description = METADATA_UPDATE (check for "add", "update", "description for" keywords)

**METADATA_UPDATE vs SCHEMA_QUERY:**
- "add description for database X" = METADATA_UPDATE (updating metadata)
- "show all databases" = SCHEMA_QUERY (showing database list)
- "describe the vendors collection" (if adding description) = METADATA_UPDATE
- "show vendors collection" (if showing structure) = SCHEMA_QUERY

Return a JSON object with this exact structure:
{{
    "intent": "DB_QUERY" | "METADATA_UPDATE" | "SCHEMA_QUERY" | "GENERAL_QUESTION",
    "confidence": 0.0-1.0,
    "details": {{
        // For DB_QUERY:
        "target_db": "postgresql" | "mongodb" | "both" | "unknown",
        
        // For METADATA_UPDATE:
        "entity_type": "database" | "table" | "column" | "collection" | "field" | null,
        "entity_name": "string" | null,
        "table_name": "string" | null,  // For columns/fields
        "content": "string" | null,  // Description/metadata content
        
        // For SCHEMA_QUERY:
        "query_type": "databases" | "tables" | "columns" | "collections" | "fields" | null,
        "database_name": "string" | null,
        "table_name": "string" | null,  // For columns
        "collection_name": "string" | null  // For fields
    }}
}}

Only include fields in "details" that are relevant to the classified intent. Use null for irrelevant fields.

Your JSON response:"""