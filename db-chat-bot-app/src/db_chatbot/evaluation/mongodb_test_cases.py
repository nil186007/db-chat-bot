"""
Test cases for MongoDB query generation evaluation.
Contains natural language queries with expected MongoDB queries of varying complexity.
"""
from typing import Dict, List, Literal

# Complexity levels
Complexity = Literal["simple", "medium", "complex", "very_complex"]

class MongoDBTestCase:
    """Represents a single test case for MongoDB query generation."""
    
    def __init__(
        self,
        id: str,
        natural_language: str,
        expected_query: Dict,  # MongoDB query as JSON dict
        complexity: Complexity,
        description: str = "",
        category: str = ""
    ):
        self.id = id
        self.natural_language = natural_language
        self.expected_query = expected_query
        self.complexity = complexity
        self.description = description
        self.category = category
    
    def to_dict(self) -> Dict:
        """Convert test case to dictionary."""
        return {
            "id": self.id,
            "natural_language": self.natural_language,
            "expected_query": self.expected_query,
            "complexity": self.complexity,
            "description": self.description,
            "category": self.category
        }


# MongoDB test cases organized by complexity
MONGODB_TEST_CASES: List[MongoDBTestCase] = [
    # ========== SIMPLE QUERIES (Single collection, basic find) ==========
    MongoDBTestCase(
        id="mongo_simple_001",
        natural_language="Show me all vendors",
        expected_query={
            "collection": "vendors",
            "filter": {},
            "projection": None,
            "sort": None,
            "limit": None
        },
        complexity="simple",
        description="Basic find all from single collection",
        category="basic_find"
    ),
    MongoDBTestCase(
        id="mongo_simple_002",
        natural_language="List all vendor names",
        expected_query={
            "collection": "vendors",
            "filter": {},
            "projection": {"vendor_name": 1, "_id": 0},
            "sort": None,
            "limit": None
        },
        complexity="simple",
        description="Find with projection",
        category="basic_find"
    ),
    MongoDBTestCase(
        id="mongo_simple_003",
        natural_language="How many vendors are there?",
        expected_query={
            "collection": "vendors",
            "aggregate": [
                {"$count": "total"}
            ]
        },
        complexity="simple",
        description="Simple COUNT aggregation",
        category="aggregation"
    ),
    MongoDBTestCase(
        id="mongo_simple_004",
        natural_language="Find vendors from USA",
        expected_query={
            "collection": "vendors",
            "filter": {"country": "USA"},
            "projection": None,
            "sort": None,
            "limit": None
        },
        complexity="simple",
        description="Find with equality filter",
        category="filtering"
    ),
    MongoDBTestCase(
        id="mongo_simple_005",
        natural_language="Show vendors with rating above 4",
        expected_query={
            "collection": "vendors",
            "filter": {"rating": {"$gt": 4}},
            "projection": None,
            "sort": None,
            "limit": None
        },
        complexity="simple",
        description="Find with comparison operator",
        category="filtering"
    ),
    MongoDBTestCase(
        id="mongo_simple_006",
        natural_language="Show all inventory sorted by quantity",
        expected_query={
            "collection": "inventory",
            "filter": {},
            "projection": None,
            "sort": {"quantity_in_hand": 1},
            "limit": None
        },
        complexity="simple",
        description="Find with sort",
        category="sorting"
    ),
    MongoDBTestCase(
        id="mongo_simple_007",
        natural_language="List top 5 vendors by rating",
        expected_query={
            "collection": "vendors",
            "filter": {},
            "projection": None,
            "sort": {"rating": -1},
            "limit": 5
        },
        complexity="simple",
        description="Find with sort and limit",
        category="sorting"
    ),
    MongoDBTestCase(
        id="mongo_simple_008",
        natural_language="Show the first 10 inventory items",
        expected_query={
            "collection": "inventory",
            "filter": {},
            "projection": None,
            "sort": None,
            "limit": 10
        },
        complexity="simple",
        description="Find with limit",
        category="pagination"
    ),
    
    # ========== MEDIUM QUERIES (Multiple conditions, aggregations) ==========
    MongoDBTestCase(
        id="mongo_medium_001",
        natural_language="Find vendors from USA or Canada",
        expected_query={
            "collection": "vendors",
            "filter": {"country": {"$in": ["USA", "Canada"]}},
            "projection": None,
            "sort": None,
            "limit": None
        },
        complexity="medium",
        description="Find with $in operator",
        category="filtering"
    ),
    MongoDBTestCase(
        id="mongo_medium_002",
        natural_language="Show inventory items with low stock",
        expected_query={
            "collection": "inventory",
            "filter": {"status": "low_stock"},
            "projection": None,
            "sort": None,
            "limit": None
        },
        complexity="medium",
        description="Find with status filter",
        category="filtering"
    ),
    MongoDBTestCase(
        id="mongo_medium_003",
        natural_language="Count purchase orders by status",
        expected_query={
            "collection": "purchase_orders",
            "aggregate": [
                {"$group": {"_id": "$status", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}}
            ]
        },
        complexity="medium",
        description="GROUP BY with COUNT",
        category="aggregation"
    ),
    MongoDBTestCase(
        id="mongo_medium_004",
        natural_language="What is the total cost of all purchase orders?",
        expected_query={
            "collection": "purchase_orders",
            "aggregate": [
                {"$group": {"_id": None, "total_cost": {"$sum": "$total_cost"}}}
            ]
        },
        complexity="medium",
        description="SUM aggregation",
        category="aggregation"
    ),
    MongoDBTestCase(
        id="mongo_medium_005",
        natural_language="Find average rating of vendors",
        expected_query={
            "collection": "vendors",
            "aggregate": [
                {"$group": {"_id": None, "avg_rating": {"$avg": "$rating"}}}
            ]
        },
        complexity="medium",
        description="AVG aggregation",
        category="aggregation"
    ),
    MongoDBTestCase(
        id="mongo_medium_006",
        natural_language="Show inventory items with quantity between 10 and 100",
        expected_query={
            "collection": "inventory",
            "filter": {
                "quantity_in_hand": {"$gte": 10, "$lte": 100}
            },
            "projection": None,
            "sort": None,
            "limit": None
        },
        complexity="medium",
        description="Range filter with $gte and $lte",
        category="filtering"
    ),
    MongoDBTestCase(
        id="mongo_medium_007",
        natural_language="Find shipments that are in transit",
        expected_query={
            "collection": "shipments",
            "filter": {"status": "in_transit"},
            "projection": None,
            "sort": None,
            "limit": None
        },
        complexity="medium",
        description="Status filter",
        category="filtering"
    ),
    MongoDBTestCase(
        id="mongo_medium_008",
        natural_language="Show purchase orders ordered by date",
        expected_query={
            "collection": "purchase_orders",
            "filter": {},
            "projection": None,
            "sort": {"order_date": 1},
            "limit": None
        },
        complexity="medium",
        description="Sort by date",
        category="sorting"
    ),
    MongoDBTestCase(
        id="mongo_medium_009",
        natural_language="Find products with zero inventory",
        expected_query={
            "collection": "inventory",
            "filter": {"quantity_in_hand": 0},
            "projection": None,
            "sort": None,
            "limit": None
        },
        complexity="medium",
        description="Filter by zero value",
        category="filtering"
    ),
    MongoDBTestCase(
        id="mongo_medium_010",
        natural_language="Count shipments by carrier",
        expected_query={
            "collection": "shipments",
            "aggregate": [
                {"$group": {"_id": "$carrier", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}}
            ]
        },
        complexity="medium",
        description="GROUP BY with COUNT and SORT",
        category="aggregation"
    ),
    MongoDBTestCase(
        id="mongo_medium_011",
        natural_language="Show top 3 vendors by rating",
        expected_query={
            "collection": "vendors",
            "filter": {},
            "projection": None,
            "sort": {"rating": -1},
            "limit": 3
        },
        complexity="medium",
        description="Sort DESC with limit",
        category="sorting"
    ),
    MongoDBTestCase(
        id="mongo_medium_012",
        natural_language="Find purchase orders placed in January 2024",
        expected_query={
            "collection": "purchase_orders",
            "filter": {
                "order_date": {
                    "$gte": "2024-01-01",
                    "$lt": "2024-02-01"
                }
            },
            "projection": None,
            "sort": None,
            "limit": None
        },
        complexity="medium",
        description="Date range filtering",
        category="filtering"
    ),
    MongoDBTestCase(
        id="mongo_medium_013",
        natural_language="Show total quantity in hand for each product",
        expected_query={
            "collection": "inventory",
            "aggregate": [
                {"$group": {
                    "_id": "$product_name",
                    "total_quantity": {"$sum": "$quantity_in_hand"}
                }},
                {"$sort": {"total_quantity": -1}}
            ]
        },
        complexity="medium",
        description="GROUP BY with SUM",
        category="aggregation"
    ),
    MongoDBTestCase(
        id="mongo_medium_014",
        natural_language="Find vendors with email containing 'gmail'",
        expected_query={
            "collection": "vendors",
            "filter": {"email": {"$regex": "gmail", "$options": "i"}},
            "projection": None,
            "sort": None,
            "limit": None
        },
        complexity="medium",
        description="Regex filter",
        category="filtering"
    ),
    
    # ========== COMPLEX QUERIES (Multiple collections, complex aggregations) ==========
    MongoDBTestCase(
        id="mongo_complex_001",
        natural_language="Find products that have no inventory",
        expected_query={
            "collection": "inventory",
            "filter": {
                "$or": [
                    {"quantity_in_hand": 0},
                    {"quantity_in_hand": {"$exists": False}}
                ]
            },
            "projection": None,
            "sort": None,
            "limit": None
        },
        complexity="complex",
        description="Complex filter with $or",
        category="filtering"
    ),
    MongoDBTestCase(
        id="mongo_complex_002",
        natural_language="Find the vendor with the most purchase orders",
        expected_query={
            "collection": "purchase_orders",
            "aggregate": [
                {"$group": {"_id": "$vendor_id", "order_count": {"$sum": 1}}},
                {"$sort": {"order_count": -1}},
                {"$limit": 1},
                {"$lookup": {
                    "from": "vendors",
                    "localField": "_id",
                    "foreignField": "vendor_id",
                    "as": "vendor_info"
                }},
                {"$unwind": "$vendor_info"}
            ]
        },
        complexity="complex",
        description="Aggregation with $lookup",
        category="aggregation"
    ),
    MongoDBTestCase(
        id="mongo_complex_003",
        natural_language="Show inventory with product and vendor information",
        expected_query={
            "collection": "inventory",
            "aggregate": [
                {"$lookup": {
                    "from": "product_vendor_mapping",
                    "localField": "product_name",
                    "foreignField": "product_name",
                    "as": "vendor_mapping"
                }},
                {"$unwind": {"path": "$vendor_mapping", "preserveNullAndEmptyArrays": True}},
                {"$lookup": {
                    "from": "vendors",
                    "localField": "vendor_mapping.vendor_id",
                    "foreignField": "vendor_id",
                    "as": "vendor_info"
                }},
                {"$unwind": {"path": "$vendor_info", "preserveNullAndEmptyArrays": True}}
            ]
        },
        complexity="complex",
        description="Multiple $lookup operations",
        category="joins"
    ),
    MongoDBTestCase(
        id="mongo_complex_004",
        natural_language="Find vendors with average purchase order value above 1000",
        expected_query={
            "collection": "purchase_orders",
            "aggregate": [
                {"$group": {
                    "_id": "$vendor_id",
                    "avg_order_value": {"$avg": "$total_cost"}
                }},
                {"$match": {"avg_order_value": {"$gt": 1000}}},
                {"$lookup": {
                    "from": "vendors",
                    "localField": "_id",
                    "foreignField": "vendor_id",
                    "as": "vendor_info"
                }},
                {"$unwind": "$vendor_info"}
            ]
        },
        complexity="complex",
        description="Aggregation with $match and $lookup",
        category="aggregation"
    ),
    MongoDBTestCase(
        id="mongo_complex_005",
        natural_language="Show shipments with vendor details",
        expected_query={
            "collection": "shipments",
            "aggregate": [
                {"$lookup": {
                    "from": "vendors",
                    "localField": "vendor_id",
                    "foreignField": "vendor_id",
                    "as": "vendor_info"
                }},
                {"$unwind": "$vendor_info"}
            ]
        },
        complexity="complex",
        description="$lookup to join collections",
        category="joins"
    ),
    MongoDBTestCase(
        id="mongo_complex_006",
        natural_language="Find the product with highest inventory value",
        expected_query={
            "collection": "inventory",
            "aggregate": [
                {"$lookup": {
                    "from": "costs",
                    "localField": "product_name",
                    "foreignField": "product_name",
                    "as": "cost_info"
                }},
                {"$unwind": {"path": "$cost_info", "preserveNullAndEmptyArrays": True}},
                {"$match": {"cost_info.cost_type": "production"}},
                {"$project": {
                    "product_name": 1,
                    "quantity_in_hand": 1,
                    "unit_cost": "$cost_info.unit_cost",
                    "inventory_value": {
                        "$multiply": ["$quantity_in_hand", "$cost_info.unit_cost"]
                    }
                }},
                {"$sort": {"inventory_value": -1}},
                {"$limit": 1}
            ]
        },
        complexity="complex",
        description="Complex aggregation with calculations",
        category="aggregation"
    ),
    MongoDBTestCase(
        id="mongo_complex_007",
        natural_language="Show purchase orders with total cost above average",
        expected_query={
            "collection": "purchase_orders",
            "aggregate": [
                {"$group": {"_id": None, "avg_cost": {"$avg": "$total_cost"}}},
                {"$lookup": {
                    "from": "purchase_orders",
                    "pipeline": [],
                    "as": "all_orders"
                }},
                {"$unwind": "$all_orders"},
                {"$match": {"$expr": {"$gt": ["$all_orders.total_cost", "$avg_cost"]}}},
                {"$replaceRoot": {"newRoot": "$all_orders"}}
            ]
        },
        complexity="complex",
        description="Subquery-like aggregation",
        category="aggregation"
    ),
    MongoDBTestCase(
        id="mongo_complex_008",
        natural_language="List vendors with their total purchase order count and value",
        expected_query={
            "collection": "purchase_orders",
            "aggregate": [
                {"$group": {
                    "_id": "$vendor_id",
                    "order_count": {"$sum": 1},
                    "total_value": {"$sum": "$total_cost"}
                }},
                {"$lookup": {
                    "from": "vendors",
                    "localField": "_id",
                    "foreignField": "vendor_id",
                    "as": "vendor_info"
                }},
                {"$unwind": "$vendor_info"},
                {"$project": {
                    "vendor_name": "$vendor_info.vendor_name",
                    "order_count": 1,
                    "total_value": 1
                }}
            ]
        },
        complexity="complex",
        description="Multiple aggregations with $lookup",
        category="aggregation"
    ),
    MongoDBTestCase(
        id="mongo_complex_009",
        natural_language="Show inventory items with warehouse details",
        expected_query={
            "collection": "inventory",
            "aggregate": [
                {"$lookup": {
                    "from": "warehouses",
                    "localField": "warehouse_location",
                    "foreignField": "warehouse_id",
                    "as": "warehouse_info"
                }},
                {"$unwind": {"path": "$warehouse_info", "preserveNullAndEmptyArrays": True}}
            ]
        },
        complexity="complex",
        description="$lookup with warehouses",
        category="joins"
    ),
    MongoDBTestCase(
        id="mongo_complex_010",
        natural_language="Find products with inventory below reorder point",
        expected_query={
            "collection": "inventory",
            "filter": {
                "$expr": {"$lt": ["$quantity_in_hand", "$reorder_point"]}
            },
            "projection": None,
            "sort": None,
            "limit": None
        },
        complexity="complex",
        description="Filter with $expr for field comparison",
        category="filtering"
    ),
    MongoDBTestCase(
        id="mongo_complex_011",
        natural_language="Show shipments with delivery status and vendor",
        expected_query={
            "collection": "shipments",
            "aggregate": [
                {"$lookup": {
                    "from": "vendors",
                    "localField": "vendor_id",
                    "foreignField": "vendor_id",
                    "as": "vendor_info"
                }},
                {"$unwind": "$vendor_info"},
                {"$project": {
                    "shipment_id": 1,
                    "product_name": 1,
                    "status": 1,
                    "vendor_name": "$vendor_info.vendor_name",
                    "expected_arrival_date": 1,
                    "actual_arrival_date": 1
                }}
            ]
        },
        complexity="complex",
        description="$lookup with projection",
        category="joins"
    ),
    MongoDBTestCase(
        id="mongo_complex_012",
        natural_language="Count shipments by status and carrier",
        expected_query={
            "collection": "shipments",
            "aggregate": [
                {"$group": {
                    "_id": {
                        "status": "$status",
                        "carrier": "$carrier"
                    },
                    "count": {"$sum": 1}
                }},
                {"$sort": {"count": -1}}
            ]
        },
        complexity="complex",
        description="GROUP BY multiple fields",
        category="aggregation"
    ),
    
    # ========== VERY COMPLEX QUERIES (Nested aggregations, complex logic) ==========
    MongoDBTestCase(
        id="mongo_very_complex_001",
        natural_language="Show products with inventory value compared to category average",
        expected_query={
            "collection": "inventory",
            "aggregate": [
                {"$lookup": {
                    "from": "costs",
                    "localField": "product_name",
                    "foreignField": "product_name",
                    "as": "cost_info"
                }},
                {"$unwind": {"path": "$cost_info", "preserveNullAndEmptyArrays": True}},
                {"$match": {"cost_info.cost_type": "production"}},
                {"$project": {
                    "product_name": 1,
                    "quantity_in_hand": 1,
                    "unit_cost": "$cost_info.unit_cost",
                    "inventory_value": {
                        "$multiply": ["$quantity_in_hand", "$cost_info.unit_cost"]
                    }
                }},
                {"$group": {
                    "_id": None,
                    "avg_inventory_value": {"$avg": "$inventory_value"},
                    "products": {"$push": "$$ROOT"}
                }},
                {"$unwind": "$products"},
                {"$project": {
                    "product_name": "$products.product_name",
                    "inventory_value": "$products.inventory_value",
                    "avg_inventory_value": 1,
                    "difference": {
                        "$subtract": [
                            "$products.inventory_value",
                            "$avg_inventory_value"
                        ]
                    }
                }},
                {"$sort": {"difference": -1}}
            ]
        },
        complexity="very_complex",
        description="Complex nested aggregation with calculations",
        category="aggregation"
    ),
    MongoDBTestCase(
        id="mongo_very_complex_002",
        natural_language="Show complete supply chain view: products, vendors, inventory, and shipments",
        expected_query={
            "collection": "inventory",
            "aggregate": [
                {"$lookup": {
                    "from": "product_vendor_mapping",
                    "localField": "product_name",
                    "foreignField": "product_name",
                    "as": "vendor_mapping"
                }},
                {"$unwind": {"path": "$vendor_mapping", "preserveNullAndEmptyArrays": True}},
                {"$lookup": {
                    "from": "vendors",
                    "localField": "vendor_mapping.vendor_id",
                    "foreignField": "vendor_id",
                    "as": "vendor_info"
                }},
                {"$unwind": {"path": "$vendor_info", "preserveNullAndEmptyArrays": True}},
                {"$lookup": {
                    "from": "shipments",
                    "localField": "product_name",
                    "foreignField": "product_name",
                    "as": "shipment_info"
                }},
                {"$lookup": {
                    "from": "warehouses",
                    "localField": "warehouse_location",
                    "foreignField": "warehouse_id",
                    "as": "warehouse_info"
                }},
                {"$unwind": {"path": "$warehouse_info", "preserveNullAndEmptyArrays": True}}
            ]
        },
        complexity="very_complex",
        description="Multiple $lookup operations across 5 collections",
        category="joins"
    ),
    MongoDBTestCase(
        id="mongo_very_complex_003",
        natural_language="Find the second highest rated vendor",
        expected_query={
            "collection": "vendors",
            "aggregate": [
                {"$sort": {"rating": -1}},
                {"$skip": 1},
                {"$limit": 1}
            ]
        },
        complexity="very_complex",
        description="Ranking with $skip and $limit",
        category="sorting"
    ),
    MongoDBTestCase(
        id="mongo_very_complex_004",
        natural_language="Show total costs by type and vendor",
        expected_query={
            "collection": "costs",
            "aggregate": [
                {"$group": {
                    "_id": {
                        "cost_type": "$cost_type",
                        "vendor_id": "$vendor_id"
                    },
                    "total_cost": {"$sum": "$total_cost"},
                    "count": {"$sum": 1}
                }},
                {"$lookup": {
                    "from": "vendors",
                    "localField": "_id.vendor_id",
                    "foreignField": "vendor_id",
                    "as": "vendor_info"
                }},
                {"$unwind": {"path": "$vendor_info", "preserveNullAndEmptyArrays": True}},
                {"$project": {
                    "cost_type": "$_id.cost_type",
                    "vendor_name": "$vendor_info.vendor_name",
                    "total_cost": 1,
                    "count": 1
                }},
                {"$sort": {"total_cost": -1}}
            ]
        },
        complexity="very_complex",
        description="Complex grouping with multiple lookups",
        category="aggregation"
    ),
    MongoDBTestCase(
        id="mongo_very_complex_005",
        natural_language="Find vendors who have purchase orders from at least 2 different products",
        expected_query={
            "collection": "purchase_orders",
            "aggregate": [
                {"$group": {
                    "_id": "$vendor_id",
                    "unique_products": {"$addToSet": "$product_name"}
                }},
                {"$match": {
                    "$expr": {"$gte": [{"$size": "$unique_products"}, 2]}
                }},
                {"$lookup": {
                    "from": "vendors",
                    "localField": "_id",
                    "foreignField": "vendor_id",
                    "as": "vendor_info"
                }},
                {"$unwind": "$vendor_info"}
            ]
        },
        complexity="very_complex",
        description="Complex aggregation with set operations",
        category="aggregation"
    ),
    MongoDBTestCase(
        id="mongo_very_complex_006",
        natural_language="Show inventory status with reorder recommendations",
        expected_query={
            "collection": "inventory",
            "aggregate": [
                {"$project": {
                    "product_name": 1,
                    "quantity_in_hand": 1,
                    "reorder_point": 1,
                    "max_stock_level": 1,
                    "status": 1,
                    "needs_reorder": {
                        "$cond": {
                            "if": {"$lte": ["$quantity_in_hand", "$reorder_point"]},
                            "then": True,
                            "else": False
                        }
                    },
                    "reorder_quantity": {
                        "$cond": {
                            "if": {"$lte": ["$quantity_in_hand", "$reorder_point"]},
                            "then": {"$subtract": ["$max_stock_level", "$quantity_in_hand"]},
                            "else": 0
                        }
                    }
                }},
                {"$match": {"needs_reorder": True}},
                {"$sort": {"quantity_in_hand": 1}}
            ]
        },
        complexity="very_complex",
        description="Complex aggregation with conditional logic",
        category="aggregation"
    ),
]


def get_mongodb_test_cases_by_complexity(complexity: Complexity = None) -> List[MongoDBTestCase]:
    """Get MongoDB test cases filtered by complexity."""
    if complexity:
        return [tc for tc in MONGODB_TEST_CASES if tc.complexity == complexity]
    return MONGODB_TEST_CASES


def get_mongodb_test_cases_by_category(category: str = None) -> List[MongoDBTestCase]:
    """Get MongoDB test cases filtered by category."""
    if category:
        return [tc for tc in MONGODB_TEST_CASES if tc.category == category]
    return MONGODB_TEST_CASES


def get_mongodb_test_case_by_id(test_id: str) -> MongoDBTestCase:
    """Get a specific MongoDB test case by ID."""
    for tc in MONGODB_TEST_CASES:
        if tc.id == test_id:
            return tc
    raise ValueError(f"MongoDB test case with ID '{test_id}' not found")
