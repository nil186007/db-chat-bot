"""
Handler for detecting and parsing schema information queries.
Uses LLM for flexible natural language understanding.
"""
import re
import json
import ollama
from typing import Optional, Dict
from db_chatbot.config.settings import get_logger

logger = get_logger(__name__)


class SchemaQueryHandler:
    """Handles parsing of schema information queries using LLM."""
    
    def __init__(self, model_name: Optional[str] = None):
        """
        Initialize schema query handler.
        
        Args:
            model_name: Optional Ollama model name for LLM-based parsing
        """
        self.model_name = model_name
        logger.debug(f"SchemaQueryHandler initialized with model: {model_name}")
    
    def is_schema_query(self, message: str) -> bool:
        """
        Check if a message is a schema information query using LLM if available, else use regex.
        
        Examples:
        - "show all databases"
        - "list connected databases"
        - "what all databases are available"
        - "show tables"
        - "show columns in products table"
        - "show collections"
        - "show fields in vendors collection"
        """
        if self.model_name:
            return self._llm_is_schema_query(message)
        else:
            return self._regex_is_schema_query(message)
    
    def _llm_is_schema_query(self, message: str) -> bool:
        """Use LLM to determine if message is a schema information query."""
        prompt = f"""You are a database assistant. A user has sent a message. Determine if this message is asking to SHOW, LIST, or DISPLAY schema information (databases, tables, columns, collections, fields) rather than querying actual data.

User Message: {message}

Answer with ONLY one word: "YES" or "NO"

Answer "YES" if the message:
- Asks to show/list/display databases, tables, columns, collections, or fields (the structure/metadata)
- Examples: "show all databases", "what databases are available", "list tables", "show columns in products table", "what tables are there", "show fields in vendors collection"
- Is asking about schema structure/metadata, not actual data values
- Keywords: "show tables", "list databases", "what columns", "show fields"

Answer "NO" if the message:
- Asks to query/retrieve actual DATA VALUES (e.g., "show products", "show product name", "how many orders", "list customers", "total quantity ordered", "show all vendors")
- Is asking about data values, counts, aggregations, calculations, filtering data, or retrieving records
- Contains words like "name", "quantity", "total", "ordered", "customers", "for each", "vendors", "products" - these indicate data queries
- Examples: "Show product name and total quantity", "list all customers", "how many orders", "show products with price > 100", "show all the vendors", "list vendors"
- Is a greeting or general question

IMPORTANT: 
- If the message asks to "show" or "list" actual DATA (like product names, quantities, customer names, order details, vendors, products), it's a DATA QUERY, not a schema query.
- Schema queries only ask about the structure (what tables/columns/collections/fields exist), not the data in them.
- "show all vendors" = DATA QUERY (retrieving vendor records)
- "show vendors collection" or "show fields in vendors collection" = SCHEMA QUERY (showing collection structure)

Your answer (YES or NO):"""

        try:
            response = ollama.generate(
                model=self.model_name,
                prompt=prompt,
                options={
                    "temperature": 0.1,
                    "num_predict": 10
                }
            )
            answer = response['response'].strip().upper()
            is_schema_query = "YES" in answer
            logger.debug(f"LLM schema query detection: {is_schema_query}")
            return is_schema_query
        except Exception as e:
            logger.warning(f"Error in LLM schema query detection: {e}, falling back to regex")
            return self._regex_is_schema_query(message)
    
    def _regex_is_schema_query(self, message: str) -> bool:
        """Fallback regex-based schema query detection."""
        message_lower = message.lower().strip()
        
        # First, check if it's clearly a data query (has data-related keywords or entity names)
        data_query_indicators = [
            "product name", "customer name", "order", "quantity", "total", "count",
            "price", "amount", "for each", "group by", "where", "having",
            "sum", "avg", "max", "min", "aggregate"
        ]
        
        # Entity names that indicate data queries (not schema queries)
        # "show all vendors" = data query, "show vendors collection" = schema query
        data_entity_names = [
            "vendors", "products", "customers", "orders", "reviews", "inventory",
            "shipments", "purchase orders", "warehouses", "costs"
        ]
        
        # Check if query contains entity names after "show all" or "list" - this is a data query
        # Pattern: "show all [entity]" or "list [entity]" where entity is a data entity name
        for entity in data_entity_names:
            if re.search(rf"(show|list|display|get|find)\s+(all\s+)?(the\s+)?{entity}", message_lower):
                return False
        
        # If it contains data query indicators, it's NOT a schema query
        if any(indicator in message_lower for indicator in data_query_indicators):
            return False
        
        # Patterns for schema queries (updated to handle "all" and variations)
        # These patterns are more specific to avoid false positives
        patterns = [
            r"show\s+(all\s+)?(databases|dbs?|database\s+details)$",  # End of string to avoid matching "show products"
            r"list\s+(all\s+)?(databases|dbs?|connected\s+databases)$",
            r"what\s+(all\s+)?(databases|dbs?|tables?|columns?|collections?|fields?|attributes?)\s+(are\s+)?(available|connected|in|there)",
            r"which\s+(databases|tables?|columns?|collections?|fields?|attributes?)(\s+are|\s+exist|\s+available)?$",
            r"show\s+(all\s+)?tables?$",  # End of string
            r"list\s+(all\s+)?tables?$",
            r"show\s+columns?\s+(in|of|for)\s+",  # Must have "in/of/for" to be schema query
            r"list\s+columns?\s+(in|of|for)\s+",
            r"show\s+(all\s+)?collections?$",
            r"list\s+(all\s+)?collections?$",
            r"show\s+fields?\s+(in|of|for)\s+",  # Must have "in/of/for" to be schema query
            r"list\s+fields?\s+(in|of|for)\s+",
            r"show\s+attributes?\s+(in|of|for)\s+",
            r"list\s+attributes?\s+(in|of|for)\s+",
        ]
        
        return any(re.search(pattern, message_lower) for pattern in patterns)
    
    def parse_schema_query(self, message: str) -> Optional[Dict[str, str]]:
        """
        Parse schema query to determine what information to retrieve using LLM if available.
        
        Returns:
            Dictionary with query type and parameters:
            {
                "query_type": "databases" | "tables" | "columns" | "collections" | "fields",
                "database_name": str (optional),
                "table_name": str (optional, for columns),
                "collection_name": str (optional, for fields)
            }
        """
        if self.model_name:
            result = self._llm_parse_schema_query(message)
            if result:
                return result
        
        # Fallback to regex parsing
        return self._regex_parse_schema_query(message)
    
    def _llm_parse_schema_query(self, message: str) -> Optional[Dict[str, str]]:
        """Use LLM to parse schema query."""
        prompt = f"""You are a database assistant. A user wants to see schema information. Parse the user's message and extract what they want to see.

User Message: {message}

Extract the following information:
1. query_type: One of "databases", "tables", "columns", "collections", or "fields"
2. database_name: The database name if specified (optional, can be null)
3. table_name: The table name if query_type is "columns" (optional, can be null)
4. collection_name: The collection name if query_type is "fields" (optional, can be null)

Examples:
- "show all databases" → {{"query_type": "databases", "database_name": null, "table_name": null, "collection_name": null}}
- "what all databases are available" → {{"query_type": "databases", "database_name": null, "table_name": null, "collection_name": null}}
- "show tables" → {{"query_type": "tables", "database_name": null, "table_name": null, "collection_name": null}}
- "show columns in products table" → {{"query_type": "columns", "database_name": null, "table_name": "products", "collection_name": null}}
- "show collections" → {{"query_type": "collections", "database_name": null, "table_name": null, "collection_name": null}}
- "show fields in vendors collection" → {{"query_type": "fields", "database_name": null, "table_name": null, "collection_name": "vendors"}}

Return ONLY a valid JSON object with keys: query_type, database_name, table_name, collection_name. Use null for optional fields that are not specified.

JSON:"""

        try:
            response = ollama.generate(
                model=self.model_name,
                prompt=prompt,
                options={
                    "temperature": 0.1,
                    "num_predict": 100
                }
            )
            
            response_text = response['response'].strip()
            
            # Try to extract JSON from response
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            # Parse JSON
            try:
                result = json.loads(response_text)
                
                # Validate required fields
                if "query_type" in result:
                    query_type = result["query_type"].lower()
                    valid_types = ["databases", "tables", "columns", "collections", "fields"]
                    if query_type in valid_types:
                        result["query_type"] = query_type
                        result["database_name"] = result.get("database_name") if result.get("database_name") else None
                        result["table_name"] = result.get("table_name") if result.get("table_name") else None
                        result["collection_name"] = result.get("collection_name") if result.get("collection_name") else None
                        
                        logger.info(f"LLM parsed schema query: {result}")
                        return result
                    else:
                        logger.warning(f"Invalid query_type from LLM: {query_type}")
                        return None
                else:
                    logger.warning(f"LLM response missing query_type: {result}")
                    return None
                    
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse LLM response as JSON: {e}, response: {response_text[:100]}")
                return None
                
        except Exception as e:
            logger.warning(f"Error in LLM schema query parsing: {e}, falling back to regex")
            return None
    
    def _regex_parse_schema_query(self, message: str) -> Optional[Dict[str, str]]:
        """Fallback regex-based schema query parsing."""
        message_lower = message.lower().strip()
        
        # Check for database queries (updated to handle "all")
        if re.search(r"(show|list|what|which)\s+(all\s+)?(databases?|dbs?)", message_lower):
            return {"query_type": "databases"}
        
        # Check for table queries
        if re.search(r"(show|list|what|which)\s+(all\s+)?tables?", message_lower):
            # Try to extract database name
            db_match = re.search(r"(?:in|for|of)\s+(?:the\s+)?['\"]?(\w+)['\"]?\s+(?:database|db)", message_lower)
            database_name = db_match.group(1) if db_match else None
            return {
                "query_type": "tables",
                "database_name": database_name
            }
        
        # Check for column queries
        col_match = re.search(r"(show|list|what|which)\s+columns?\s+(?:in|of|for)\s+(?:the\s+)?['\"]?(\w+)['\"]?\s+table", message_lower)
        if col_match:
            table_name = col_match.group(2)
            # Try to extract database name
            db_match = re.search(r"(?:in|for|of)\s+(?:the\s+)?['\"]?(\w+)['\"]?\s+(?:database|db)", message_lower)
            database_name = db_match.group(1) if db_match else None
            return {
                "query_type": "columns",
                "table_name": table_name,
                "database_name": database_name
            }
        
        # Check for collection queries
        if re.search(r"(show|list|what|which)\s+(all\s+)?collections?", message_lower):
            # Try to extract database name
            db_match = re.search(r"(?:in|for|of)\s+(?:the\s+)?['\"]?(\w+)['\"]?\s+(?:database|db)", message_lower)
            database_name = db_match.group(1) if db_match else None
            return {
                "query_type": "collections",
                "database_name": database_name
            }
        
        # Check for field/attribute queries
        field_match = re.search(r"(show|list|what|which)\s+(fields?|attributes?)\s+(?:in|of|for)\s+(?:the\s+)?['\"]?(\w+)['\"]?\s+collection", message_lower)
        if field_match:
            collection_name = field_match.group(2)
            # Try to extract database name
            db_match = re.search(r"(?:in|for|of)\s+(?:the\s+)?['\"]?(\w+)['\"]?\s+(?:database|db)", message_lower)
            database_name = db_match.group(1) if db_match else None
            return {
                "query_type": "fields",
                "collection_name": collection_name,
                "database_name": database_name
            }
        
        logger.warning(f"Could not parse schema query from message: {message[:50]}...")
        return None
