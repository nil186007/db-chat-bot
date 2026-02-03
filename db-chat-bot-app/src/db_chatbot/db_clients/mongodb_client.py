"""
MongoDB database client tool for the agent.
"""
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from typing import Dict, List, Optional, Tuple, Any
from db_chatbot.config.settings import get_logger
import json

logger = get_logger(__name__)


class MongoDBClient:
    """MongoDB database client tool for agent use."""
    
    def __init__(self):
        """Initialize MongoDB client."""
        self.client = None
        self.database = None
        logger.info("MongoDBClient instance created")
    
    def connect(
        self,
        host: str,
        port: int,
        database: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        auth_source: str = "admin"
    ) -> Tuple[bool, str]:
        """
        Connect to MongoDB database.
        
        Args:
            host: MongoDB host
            port: MongoDB port
            database: Database name
            username: Username (optional)
            password: Password (optional)
            auth_source: Authentication database (default: admin)
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        logger.info(f"Attempting to connect to MongoDB: {host}:{port}/{database}")
        try:
            # Build connection URI
            if username and password:
                uri = f"mongodb://{username}:{password}@{host}:{port}/{database}?authSource={auth_source}"
            else:
                uri = f"mongodb://{host}:{port}/{database}"
            
            self.client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            # Test connection
            self.client.admin.command('ping')
            self.database = self.client[database]
            logger.info("MongoDB connection established successfully")
            return True, "Connection successful!"
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"MongoDB connection failed: {str(e)}")
            return False, f"Connection failed: {str(e)}"
        except Exception as e:
            logger.error(f"MongoDB connection error: {str(e)}")
            return False, f"Connection error: {str(e)}"
    
    def fetch_schema(self) -> Optional[Dict]:
        """
        Fetch all collection schemas from the database.
        
        Returns:
            Dictionary containing schema information
        """
        if self.database is None:
            logger.warning("Cannot fetch schema: not connected to database")
            return None
        
        logger.info("Starting MongoDB schema fetch process")
        schema_info = {
            "collections": [],
            "database_name": self.database.name
        }
        
        try:
            # Get all collection names
            collection_names = self.database.list_collection_names()
            logger.info(f"Found {len(collection_names)} collection(s) in database")
            
            for collection_name in collection_names:
                logger.debug(f"Processing collection: {collection_name}")
                collection = self.database[collection_name]
                
                # Get sample documents to infer schema
                sample_docs = list(collection.find().limit(10))
                
                # Infer schema from sample documents
                fields = self._infer_schema(sample_docs)
                
                # Get collection stats
                stats = self.database.command("collStats", collection_name)
                document_count = stats.get("count", 0)
                
                collection_info = {
                    "name": collection_name,
                    "fields": fields,
                    "document_count": document_count,
                    "indexes": self._get_indexes(collection)
                }
                
                schema_info["collections"].append(collection_info)
            
            logger.info(f"Schema fetch completed successfully. Loaded {len(schema_info['collections'])} collection(s)")
            return schema_info
            
        except Exception as e:
            logger.error(f"Error fetching MongoDB schema: {str(e)}")
            return None
    
    def _infer_schema(self, sample_docs: List[Dict]) -> List[Dict]:
        """
        Infer schema from sample documents.
        
        Args:
            sample_docs: List of sample documents
        
        Returns:
            List of field definitions
        """
        if not sample_docs:
            return []
        
        # Collect all unique fields and their types
        field_types = {}
        field_examples = {}
        
        for doc in sample_docs:
            for key, value in doc.items():
                if key not in field_types:
                    field_types[key] = set()
                    field_examples[key] = value
                
                # Determine type
                if value is None:
                    field_types[key].add("null")
                elif isinstance(value, bool):
                    field_types[key].add("boolean")
                elif isinstance(value, int):
                    field_types[key].add("integer")
                elif isinstance(value, float):
                    field_types[key].add("double")
                elif isinstance(value, str):
                    field_types[key].add("string")
                elif isinstance(value, list):
                    field_types[key].add("array")
                    # Check array element types
                    if value:
                        if isinstance(value[0], dict):
                            field_types[key].add("array_of_objects")
                        else:
                            field_types[key].add(f"array_of_{type(value[0]).__name__}")
                elif isinstance(value, dict):
                    field_types[key].add("object")
                else:
                    field_types[key].add(type(value).__name__)
        
        # Build field definitions
        fields = []
        for field_name, types in field_types.items():
            field_def = {
                "name": field_name,
                "types": sorted(list(types)),
                "nullable": "null" in types,
                "example": str(field_examples[field_name])[:100] if field_examples[field_name] is not None else None
            }
            fields.append(field_def)
        
        return sorted(fields, key=lambda x: x["name"])
    
    def _get_indexes(self, collection) -> List[Dict]:
        """Get indexes for a collection."""
        try:
            indexes = collection.list_indexes()
            index_list = []
            for index in indexes:
                index_info = {
                    "name": index.get("name", ""),
                    "keys": dict(index.get("key", {})),
                    "unique": index.get("unique", False)
                }
                index_list.append(index_info)
            return index_list
        except Exception as e:
            logger.warning(f"Error getting indexes: {str(e)}")
            return []
    
    def execute_query(self, query: Dict) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """
        Execute a MongoDB query.
        
        Args:
            query: MongoDB query dictionary with keys:
                - collection: Collection name
                - filter: Filter dictionary (find query)
                - projection: Projection dictionary (fields to return)
                - sort: Sort dictionary
                - limit: Limit number
                - aggregate: Aggregation pipeline (optional, if provided, uses aggregate instead of find)
        
        Returns:
            Tuple of (success: bool, results: Dict, error_message: str)
        """
        if self.database is None:
            logger.warning("Cannot execute query: not connected to database")
            return False, None, "Not connected to database"
        
        try:
            collection_name = query.get("collection")
            if not collection_name:
                return False, None, "Collection name is required"
            
            collection = self.database[collection_name]
            
            # Check if aggregation pipeline is provided
            if "aggregate" in query:
                pipeline = query["aggregate"]
                logger.info(f"Executing aggregation pipeline on {collection_name}")
                cursor = collection.aggregate(pipeline)
                results = list(cursor)
                
                return True, {
                    "collection": collection_name,
                    "operation": "aggregate",
                    "count": len(results),
                    "documents": results
                }, None
            
            # Otherwise use find
            filter_dict = query.get("filter", {})
            projection = query.get("projection")
            sort = query.get("sort")
            limit = query.get("limit")
            
            logger.info(f"Executing find query on {collection_name}: {filter_dict}")
            
            cursor = collection.find(filter_dict, projection)
            
            if sort:
                cursor = cursor.sort(list(sort.items()))
            
            if limit:
                cursor = cursor.limit(limit)
            
            results = list(cursor)
            
            logger.info(f"Query executed successfully. Returned {len(results)} document(s)")
            return True, {
                "collection": collection_name,
                "operation": "find",
                "count": len(results),
                "documents": results
            }, None
            
        except Exception as e:
            logger.error(f"MongoDB query execution failed: {str(e)}")
            return False, None, str(e)
    
    def close(self):
        """Close MongoDB connection."""
        if self.client:
            logger.info("Closing MongoDB connection")
            self.client.close()
            self.client = None
            self.database = None
