"""
Handler for parsing and processing user annotations about database schema.
Uses LLM to understand natural language metadata update requests.
"""
import re
import json
import ollama
from typing import Optional, Dict, Tuple
from db_chatbot.config.settings import get_logger

logger = get_logger(__name__)


class AnnotationHandler:
    """Handles parsing and extraction of annotations from user chat messages using LLM."""
    
    def __init__(self, model_name: Optional[str] = None):
        """
        Initialize annotation handler.
        
        Args:
            model_name: Optional Ollama model name for LLM-based parsing
        """
        self.model_name = model_name
        logger.debug(f"AnnotationHandler initialized with model: {model_name}")
    
    def is_annotation(self, message: str) -> bool:
        """
        Check if a message appears to be an annotation using LLM if available, else use keyword matching.
        
        Args:
            message: User message
        
        Returns:
            True if message appears to be an annotation
        """
        if self.model_name:
            return self._llm_is_annotation(message)
        else:
            return self._keyword_is_annotation(message)
    
    def _llm_is_annotation(self, message: str) -> bool:
        """Use LLM to determine if message is an annotation request."""
        prompt = f"""You are a database assistant. A user has sent a message. Determine if this message is requesting to ADD, UPDATE, or DESCRIBE metadata/descriptions for database entities (databases, tables, columns, collections, fields).

User Message: {message}

Answer with ONLY one word: "YES" or "NO"

Answer "YES" if the message:
- Requests to add/update/describe metadata for a database, table, column, collection, or field
- Examples: "add description to table products", "update metadata for column product_id", "describe the vendors collection", "add description for database customer_orders_and_reviews_db that it contains..."
- Mentions adding descriptions, metadata, annotations, or information about schema entities

Answer "NO" if the message:
- Is asking a question about data (e.g., "show products", "how many orders")
- Is a greeting or general question
- Is requesting to query or retrieve data from the database

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
            is_annotation = "YES" in answer
            logger.debug(f"LLM annotation detection: {is_annotation}")
            return is_annotation
        except Exception as e:
            logger.warning(f"Error in LLM annotation detection: {e}, falling back to keyword matching")
            return self._keyword_is_annotation(message)
    
    def _keyword_is_annotation(self, message: str) -> bool:
        """Fallback keyword-based annotation detection."""
        message_lower = message.lower().strip()
        
        # Check for annotation keywords
        annotation_keywords = [
            "add description", "add metadata", "update description", "update metadata",
            "describe", "metadata for", "description for", "annotation",
            "the table", "the column", "the database", "the collection", "the field"
        ]
        
        has_keyword = any(keyword in message_lower for keyword in annotation_keywords)
        
        # Additional check: if message doesn't look like a query
        query_keywords = ["show", "list", "find", "get", "count", "how many", "what", "which", "select"]
        is_query = any(keyword in message_lower for keyword in query_keywords)
        
        return has_keyword and not is_query
    
    def parse_annotation(self, message: str) -> Optional[Dict[str, str]]:
        """
        Parse annotation from user message using LLM if available, else use regex fallback.
        
        Args:
            message: User message containing annotation
        
        Returns:
            Dictionary with annotation details or None if parsing fails
            {
                "entity_type": "database" | "table" | "column" | "collection" | "field",
                "entity_name": str,
                "table_name": str (for columns/fields, contains table/collection name),
                "content": str (description/metadata content)
            }
        """
        if self.model_name:
            result = self._llm_parse_annotation(message)
            if result:
                return result
        
        # Fallback to regex parsing
        return self._regex_parse_annotation(message)
    
    def _llm_parse_annotation(self, message: str) -> Optional[Dict[str, str]]:
        """Use LLM to parse annotation from natural language."""
        prompt = f"""You are a database assistant. A user wants to add or update metadata/description for a database entity. Parse the user's message and extract the information.

User Message: {message}

Extract the following information:
1. entity_type: One of "database", "table", "column", "collection", or "field"
2. entity_name: The name of the entity (database name, table name, column name, collection name, or field name)
3. table_name: If entity_type is "column", provide the table name. If entity_type is "field", provide the collection name. Otherwise, null.
4. content: The description/metadata content the user wants to add

Examples:
- "add description to table products that it contains product information" → {{"entity_type": "table", "entity_name": "products", "table_name": null, "content": "it contains product information"}}
- "update metadata for column product_id in products table that it is unique identifier" → {{"entity_type": "column", "entity_name": "product_id", "table_name": "products", "content": "it is unique identifier"}}
- "add description for database customer_orders_and_reviews_db that it contains all orders and reviews" → {{"entity_type": "database", "entity_name": "customer_orders_and_reviews_db", "table_name": null, "content": "it contains all orders and reviews"}}
- "describe the vendors collection as storing supplier information" → {{"entity_type": "collection", "entity_name": "vendors", "table_name": null, "content": "storing supplier information"}}
- "add metadata for vendor_name field in vendors collection that it contains supplier name" → {{"entity_type": "field", "entity_name": "vendor_name", "table_name": "vendors", "content": "it contains supplier name"}}

Return ONLY a valid JSON object with keys: entity_type, entity_name, table_name, content. Do not include any explanation or additional text.

JSON:"""

        try:
            response = ollama.generate(
                model=self.model_name,
                prompt=prompt,
                options={
                    "temperature": 0.1,
                    "num_predict": 200
                }
            )
            
            response_text = response['response'].strip()
            
            # Try to extract JSON from response
            # Remove markdown code blocks if present
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            # Parse JSON
            try:
                result = json.loads(response_text)
                
                # Validate required fields
                if "entity_type" in result and "content" in result:
                    # Ensure entity_name is present
                    if "entity_name" not in result or not result["entity_name"]:
                        # Try to extract from message if missing
                        logger.warning("LLM did not provide entity_name, attempting extraction")
                        return None
                    
                    # Normalize entity_type
                    entity_type = result["entity_type"].lower()
                    valid_types = ["database", "table", "column", "collection", "field"]
                    if entity_type not in valid_types:
                        logger.warning(f"Invalid entity_type from LLM: {entity_type}")
                        return None
                    
                    result["entity_type"] = entity_type
                    result["table_name"] = result.get("table_name")  # Can be None
                    result["content"] = result["content"].strip()
                    
                    logger.info(f"LLM parsed annotation: {result}")
                    return result
                else:
                    logger.warning(f"LLM response missing required fields: {result}")
                    return None
                    
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse LLM response as JSON: {e}, response: {response_text[:100]}")
                return None
                
        except Exception as e:
            logger.warning(f"Error in LLM annotation parsing: {e}, falling back to regex")
            return None
    
    def _regex_parse_annotation(self, message: str) -> Optional[Dict[str, str]]:
        """Fallback regex-based annotation parsing."""
        message_lower = message.lower().strip()
        
        # Try to parse table annotation
        table_match = re.search(r"the\s+['\"]?(\w+)['\"]?\s+table\s+(?:contains|stores|has|is|represents|describes|means)\s+(.+)", message_lower)
        if table_match:
            table_name = table_match.group(1)
            content = message[message_lower.find(table_match.group(2)):].strip()
            return {
                "entity_type": "table",
                "entity_name": table_name,
                "table_name": None,
                "content": content
            }
        
        # Try to parse column annotation with table.table format
        col_dot_match = re.search(r"the\s+['\"]?(\w+)\.(\w+)['\"]?\s+column\s+(?:stores|contains|is|represents)\s+(.+)", message_lower)
        if col_dot_match:
            table_name = col_dot_match.group(1)
            col_name = col_dot_match.group(2)
            content = message[message_lower.find(col_dot_match.group(3)):].strip()
            return {
                "entity_type": "column",
                "entity_name": col_name,
                "table_name": table_name,
                "content": content
            }
        
        # Try to parse column annotation with "column in table" format
        col_in_table_match = re.search(r"the\s+['\"]?(\w+)['\"]?\s+column\s+(?:in|of|for)\s+(?:the\s+)?['\"]?(\w+)['\"]?\s+table\s+(?:stores|contains|is|represents)\s+(.+)", message_lower)
        if col_in_table_match:
            col_name = col_in_table_match.group(1)
            table_name = col_in_table_match.group(2)
            content = message[message_lower.find(col_in_table_match.group(3)):].strip()
            return {
                "entity_type": "column",
                "entity_name": col_name,
                "table_name": table_name,
                "content": content
            }
        
        # Try to parse collection annotation (MongoDB)
        coll_match = re.search(r"the\s+['\"]?(\w+)['\"]?\s+collection\s+(?:contains|stores|has|is|represents|describes|means)\s+(.+)", message_lower)
        if coll_match:
            collection_name = coll_match.group(1)
            content = message[message_lower.find(coll_match.group(2)):].strip()
            return {
                "entity_type": "collection",
                "entity_name": collection_name,
                "table_name": None,
                "content": content
            }
        
        # Try to parse field annotation with collection.field format
        field_dot_match = re.search(r"the\s+['\"]?(\w+)\.(\w+)['\"]?\s+field\s+(?:stores|contains|is|represents)\s+(.+)", message_lower)
        if field_dot_match:
            collection_name = field_dot_match.group(1)
            field_name = field_dot_match.group(2)
            content = message[message_lower.find(field_dot_match.group(3)):].strip()
            return {
                "entity_type": "field",
                "entity_name": field_name,
                "table_name": collection_name,  # Reuse table_name for collection_name
                "content": content
            }
        
        # Try to parse field annotation with "field in collection" format
        field_in_coll_match = re.search(r"the\s+['\"]?(\w+)['\"]?\s+field\s+(?:in|of|for)\s+(?:the\s+)?['\"]?(\w+)['\"]?\s+collection\s+(?:stores|contains|is|represents)\s+(.+)", message_lower)
        if field_in_coll_match:
            field_name = field_in_coll_match.group(1)
            collection_name = field_in_coll_match.group(2)
            content = message[message_lower.find(field_in_coll_match.group(3)):].strip()
            return {
                "entity_type": "field",
                "entity_name": field_name,
                "table_name": collection_name,  # Reuse table_name for collection_name
                "content": content
            }
        
        # Try to parse attribute annotation (alternative to field)
        attr_match = re.search(r"the\s+['\"]?(\w+)['\"]?\s+attribute\s+(?:in|of|for)\s+(?:the\s+)?['\"]?(\w+)['\"]?\s+collection\s+(?:stores|contains|is|represents)\s+(.+)", message_lower)
        if attr_match:
            attr_name = attr_match.group(1)
            collection_name = attr_match.group(2)
            content = message[message_lower.find(attr_match.group(3)):].strip()
            return {
                "entity_type": "field",
                "entity_name": attr_name,
                "table_name": collection_name,  # Reuse table_name for collection_name
                "content": content
            }
        
        # Try to parse database annotation with explicit database name
        # Pattern: "add metadata description for [database_name] that it contains..."
        # Pattern: "add description for [database_name] that..."
        # Pattern: "metadata for [database_name] that..."
        db_explicit_match = re.search(
            r"(?:add\s+)?(?:metadata\s+)?(?:description\s+)?for\s+['\"]?([a-zA-Z_][a-zA-Z0-9_]*)['\"]?\s+(?:that\s+)?(?:it\s+)?(?:contains|stores|has|is|represents|means)\s+(.+)",
            message_lower
        )
        if db_explicit_match:
            database_name = db_explicit_match.group(1)
            content = message[message_lower.find(db_explicit_match.group(2)):].strip()
            return {
                "entity_type": "database",
                "entity_name": database_name,
                "table_name": None,
                "content": content
            }
        
        # Try to parse database annotation with "add description for [database_name]: ..."
        db_colon_match = re.search(
            r"(?:add\s+)?(?:metadata\s+)?(?:description\s+)?for\s+['\"]?([a-zA-Z_][a-zA-Z0-9_]*)['\"]?\s*[:]\s*(.+)",
            message
        )
        if db_colon_match:
            database_name = db_colon_match.group(1)
            content = db_colon_match.group(2).strip()
            return {
                "entity_type": "database",
                "entity_name": database_name,
                "table_name": None,
                "content": content
            }
        
        # Try to parse database annotation (generic)
        db_match = re.search(r"the\s+database\s+(?:contains|stores|has|is|represents)\s+(.+)", message_lower)
        if db_match:
            content = message[message_lower.find(db_match.group(1)):].strip()
            return {
                "entity_type": "database",
                "entity_name": "",  # Will be filled from context
                "table_name": None,
                "content": content
            }
        
        # Fallback: try to extract using LLM if available (future enhancement)
        logger.warning(f"Could not parse annotation from message: {message[:50]}...")
        return None
    
    def extract_annotation_content(self, message: str, entity_type: str, entity_name: str) -> str:
        """
        Extract the descriptive content from an annotation message.
        
        Args:
            message: Full annotation message
            entity_type: Type of entity
            entity_name: Name of entity
        
        Returns:
            Extracted content/description
        """
        message_lower = message.lower()
        entity_lower = entity_name.lower()
        
        # Try to find content after entity mention
        patterns = [
            f"the {entity_lower} {entity_type} (?:contains|stores|has|is|represents|describes|means) (.+)",
            f"the {entity_lower} (?:contains|stores|has|is|represents) (.+)",
            f"{entity_lower} (?:contains|stores|has|is|represents) (.+)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message_lower)
            if match:
                content_start = message_lower.find(match.group(1))
                if content_start > 0:
                    return message[content_start:].strip()
        
        # Fallback: return message as-is
        return message.strip()

