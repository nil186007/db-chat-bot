"""
Test cases for SQL query generation evaluation.
Contains natural language queries with expected SQL queries of varying complexity.
"""
from typing import Dict, List, Literal

# Complexity levels
Complexity = Literal["simple", "medium", "complex", "very_complex"]

class TestCase:
    """Represents a single test case for SQL generation."""
    
    def __init__(
        self,
        id: str,
        natural_language: str,
        expected_sql: str,
        complexity: Complexity,
        description: str = "",
        category: str = ""
    ):
        self.id = id
        self.natural_language = natural_language
        self.expected_sql = expected_sql
        self.complexity = complexity
        self.description = description
        self.category = category
    
    def to_dict(self) -> Dict:
        """Convert test case to dictionary."""
        return {
            "id": self.id,
            "natural_language": self.natural_language,
            "expected_sql": self.expected_sql,
            "complexity": self.complexity,
            "description": self.description,
            "category": self.category
        }


# Test cases organized by complexity
TEST_CASES: List[TestCase] = [
    # ========== SIMPLE QUERIES (Single table, basic SELECT) ==========
    TestCase(
        id="simple_001",
        natural_language="Show me all products",
        expected_sql="SELECT product_name FROM products;",
        complexity="simple",
        description="Basic SELECT all from single table",
        category="basic_select"
    ),
    TestCase(
        id="simple_002",
        natural_language="List all customer names",
        expected_sql="SELECT first_name, last_name FROM customers;",
        complexity="simple",
        description="SELECT specific columns",
        category="basic_select"
    ),
    TestCase(
        id="simple_003",
        natural_language="How many products are there?",
        expected_sql="SELECT COUNT(*) FROM products;",
        complexity="simple",
        description="Simple COUNT aggregation",
        category="aggregation"
    ),
    TestCase(
        id="simple_004",
        natural_language="Show products in the Electronics category",
        expected_sql="SELECT * FROM products WHERE category = 'Electronics';",
        complexity="simple",
        description="WHERE clause with equality",
        category="filtering"
    ),
    TestCase(
        id="simple_005",
        natural_language="Find products with price greater than 100",
        expected_sql="SELECT * FROM products WHERE price > 100;",
        complexity="simple",
        description="WHERE clause with comparison operator",
        category="filtering"
    ),
    TestCase(
        id="simple_006",
        natural_language="Show all orders sorted by order date",
        expected_sql="SELECT * FROM orders ORDER BY order_date;",
        complexity="simple",
        description="ORDER BY clause",
        category="sorting"
    ),
    TestCase(
        id="simple_007",
        natural_language="List products ordered by price from highest to lowest",
        expected_sql="SELECT * FROM products ORDER BY price DESC;",
        complexity="simple",
        description="ORDER BY DESC",
        category="sorting"
    ),
    TestCase(
        id="simple_008",
        natural_language="Show the first 10 products",
        expected_sql="SELECT * FROM products LIMIT 10;",
        complexity="simple",
        description="LIMIT clause",
        category="pagination"
    ),
    
    # ========== MEDIUM QUERIES (JOINs, multiple conditions, aggregations) ==========
    TestCase(
        id="medium_001",
        natural_language="Show all orders with customer names",
        expected_sql="""SELECT o.*, c.first_name, c.last_name 
FROM orders o 
INNER JOIN customers c ON o.customer_id = c.customer_id;""",
        complexity="medium",
        description="INNER JOIN between two tables",
        category="joins"
    ),
    TestCase(
        id="medium_002",
        natural_language="Find products that have been reviewed",
        expected_sql="""SELECT DISTINCT p.* 
FROM products p 
INNER JOIN reviews r ON p.product_id = r.product_id;""",
        complexity="medium",
        description="INNER JOIN with DISTINCT",
        category="joins"
    ),
    TestCase(
        id="medium_003",
        natural_language="Show order details with product names",
        expected_sql="""SELECT oi.*, p.product_name, o.order_date 
FROM order_items oi 
INNER JOIN products p ON oi.product_id = p.product_id 
INNER JOIN orders o ON oi.order_id = o.order_id;""",
        complexity="medium",
        description="Multiple INNER JOINs",
        category="joins"
    ),
    TestCase(
        id="medium_004",
        natural_language="Count orders for each customer",
        expected_sql="""SELECT c.customer_id, c.first_name, c.last_name, COUNT(o.order_id) as order_count 
FROM customers c 
LEFT JOIN orders o ON c.customer_id = o.customer_id 
GROUP BY c.customer_id, c.first_name, c.last_name;""",
        complexity="medium",
        description="LEFT JOIN with GROUP BY and COUNT",
        category="aggregation"
    ),
    TestCase(
        id="medium_005",
        natural_language="What is the total revenue from all orders?",
        expected_sql="SELECT SUM(total_amount) as total_revenue FROM orders;",
        complexity="medium",
        description="SUM aggregation",
        category="aggregation"
    ),
    TestCase(
        id="medium_006",
        natural_language="Find the average price of products in each category",
        expected_sql="""SELECT category, AVG(price) as avg_price 
FROM products 
GROUP BY category;""",
        complexity="medium",
        description="GROUP BY with AVG",
        category="aggregation"
    ),
    TestCase(
        id="medium_007",
        natural_language="Show products with price between 50 and 200",
        expected_sql="SELECT * FROM products WHERE price BETWEEN 50 AND 200;",
        complexity="medium",
        description="BETWEEN operator",
        category="filtering"
    ),
    TestCase(
        id="medium_008",
        natural_language="Find customers from New York or Los Angeles",
        expected_sql="SELECT * FROM customers WHERE city IN ('New York', 'Los Angeles');",
        complexity="medium",
        description="IN operator with multiple values",
        category="filtering"
    ),
    TestCase(
        id="medium_009",
        natural_language="Show products that are out of stock",
        expected_sql="SELECT * FROM products WHERE stock_quantity = 0;",
        complexity="medium",
        description="Filter by zero value",
        category="filtering"
    ),
    TestCase(
        id="medium_010",
        natural_language="List customers who have placed more than 1 order",
        expected_sql="""SELECT c.*, COUNT(o.order_id) as order_count 
FROM customers c 
INNER JOIN orders o ON c.customer_id = o.customer_id 
GROUP BY c.customer_id 
HAVING COUNT(o.order_id) > 1;""",
        complexity="medium",
        description="GROUP BY with HAVING clause",
        category="aggregation"
    ),
    TestCase(
        id="medium_011",
        natural_language="Show the top 5 most expensive products",
        expected_sql="SELECT * FROM products ORDER BY price DESC LIMIT 5;",
        complexity="medium",
        description="ORDER BY with LIMIT",
        category="sorting"
    ),
    TestCase(
        id="medium_012",
        natural_language="Find all orders placed in January 2024",
        expected_sql="""SELECT * FROM orders 
WHERE order_date >= '2024-01-01' AND order_date < '2024-02-01';""",
        complexity="medium",
        description="Date range filtering",
        category="filtering"
    ),
    TestCase(
        id="medium_013",
        natural_language="Show product name and total quantity ordered for each product",
        expected_sql="""SELECT p.product_name, SUM(oi.quantity) as total_quantity 
FROM products p 
LEFT JOIN order_items oi ON p.product_id = oi.product_id 
GROUP BY p.product_id, p.product_name;""",
        complexity="medium",
        description="LEFT JOIN with GROUP BY and SUM",
        category="aggregation"
    ),
    TestCase(
        id="medium_014",
        natural_language="Find customers with email containing 'gmail'",
        expected_sql="SELECT * FROM customers WHERE email LIKE '%gmail%';",
        complexity="medium",
        description="LIKE operator with wildcard",
        category="filtering"
    ),
    
    # ========== COMPLEX QUERIES (Subqueries, multiple JOINs, complex aggregations) ==========
    TestCase(
        id="complex_001",
        natural_language="Show products that have never been ordered",
        expected_sql="""SELECT * FROM products p 
WHERE p.product_id NOT IN (
    SELECT DISTINCT product_id FROM order_items
);""",
        complexity="complex",
        description="Subquery with NOT IN",
        category="subqueries"
    ),
    TestCase(
        id="complex_002",
        natural_language="Find the customer who has placed the most orders",
        expected_sql="""SELECT c.*, COUNT(o.order_id) as order_count 
FROM customers c 
INNER JOIN orders o ON c.customer_id = o.customer_id 
GROUP BY c.customer_id 
ORDER BY order_count DESC 
LIMIT 1;""",
        complexity="complex",
        description="JOIN with GROUP BY and ORDER BY LIMIT",
        category="aggregation"
    ),
    TestCase(
        id="complex_003",
        natural_language="Show orders with customer details and total order value",
        expected_sql="""SELECT o.*, c.first_name, c.last_name, c.email, 
       COALESCE(SUM(oi.subtotal), 0) as calculated_total 
FROM orders o 
INNER JOIN customers c ON o.customer_id = c.customer_id 
LEFT JOIN order_items oi ON o.order_id = oi.order_id 
GROUP BY o.order_id, c.first_name, c.last_name, c.email;""",
        complexity="complex",
        description="Multiple JOINs with GROUP BY and COALESCE",
        category="joins"
    ),
    TestCase(
        id="complex_004",
        natural_language="Find products with average rating above 4",
        expected_sql="""SELECT p.*, AVG(r.rating) as avg_rating 
FROM products p 
INNER JOIN reviews r ON p.product_id = r.product_id 
GROUP BY p.product_id 
HAVING AVG(r.rating) > 4;""",
        complexity="complex",
        description="JOIN with GROUP BY and HAVING",
        category="aggregation"
    ),
    TestCase(
        id="complex_005",
        natural_language="Show customers who have ordered products from Electronics category",
        expected_sql="""SELECT DISTINCT c.* 
FROM customers c 
INNER JOIN orders o ON c.customer_id = o.customer_id 
INNER JOIN order_items oi ON o.order_id = oi.order_id 
INNER JOIN products p ON oi.product_id = p.product_id 
WHERE p.category = 'Electronics';""",
        complexity="complex",
        description="Multiple JOINs with WHERE filter",
        category="joins"
    ),
    TestCase(
        id="complex_006",
        natural_language="Find the product with the highest total sales revenue",
        expected_sql="""SELECT p.product_id, p.product_name, SUM(oi.subtotal) as total_revenue 
FROM products p 
INNER JOIN order_items oi ON p.product_id = oi.product_id 
GROUP BY p.product_id, p.product_name 
ORDER BY total_revenue DESC 
LIMIT 1;""",
        complexity="complex",
        description="JOIN with SUM aggregation and ORDER BY",
        category="aggregation"
    ),
    TestCase(
        id="complex_007",
        natural_language="Show products that cost more than the average product price",
        expected_sql="""SELECT * FROM products 
WHERE price > (SELECT AVG(price) FROM products);""",
        complexity="complex",
        description="Subquery in WHERE clause",
        category="subqueries"
    ),
    TestCase(
        id="complex_008",
        natural_language="List customers with their total spending",
        expected_sql="""SELECT c.*, COALESCE(SUM(o.total_amount), 0) as total_spending 
FROM customers c 
LEFT JOIN orders o ON c.customer_id = o.customer_id 
GROUP BY c.customer_id;""",
        complexity="complex",
        description="LEFT JOIN with COALESCE and SUM",
        category="aggregation"
    ),
    TestCase(
        id="complex_009",
        natural_language="Show order items with product details and customer information",
        expected_sql="""SELECT oi.*, p.product_name, p.category, c.first_name, c.last_name, o.order_date 
FROM order_items oi 
INNER JOIN products p ON oi.product_id = p.product_id 
INNER JOIN orders o ON oi.order_id = o.order_id 
INNER JOIN customers c ON o.customer_id = c.customer_id;""",
        complexity="complex",
        description="Multiple JOINs across 4 tables",
        category="joins"
    ),
    TestCase(
        id="complex_010",
        natural_language="Find categories with more than 3 products",
        expected_sql="""SELECT category, COUNT(*) as product_count 
FROM products 
GROUP BY category 
HAVING COUNT(*) > 3;""",
        complexity="complex",
        description="GROUP BY with HAVING COUNT",
        category="aggregation"
    ),
    TestCase(
        id="complex_011",
        natural_language="Show products with their review count and average rating",
        expected_sql="""SELECT p.*, COUNT(r.review_id) as review_count, 
       AVG(r.rating) as avg_rating 
FROM products p 
LEFT JOIN reviews r ON p.product_id = r.product_id 
GROUP BY p.product_id;""",
        complexity="complex",
        description="LEFT JOIN with multiple aggregations",
        category="aggregation"
    ),
    TestCase(
        id="complex_012",
        natural_language="Find orders that contain products from multiple categories",
        expected_sql="""SELECT o.order_id, COUNT(DISTINCT p.category) as category_count 
FROM orders o 
INNER JOIN order_items oi ON o.order_id = oi.order_id 
INNER JOIN products p ON oi.product_id = p.product_id 
GROUP BY o.order_id 
HAVING COUNT(DISTINCT p.category) > 1;""",
        complexity="complex",
        description="Multiple JOINs with COUNT DISTINCT and HAVING",
        category="aggregation"
    ),
    
    # ========== VERY COMPLEX QUERIES (Nested subqueries, complex logic) ==========
    TestCase(
        id="very_complex_001",
        natural_language="Show customers who have ordered all products in the Electronics category",
        expected_sql="""SELECT c.* 
FROM customers c 
WHERE NOT EXISTS (
    SELECT p.product_id 
    FROM products p 
    WHERE p.category = 'Electronics' 
    AND NOT EXISTS (
        SELECT oi.order_id 
        FROM order_items oi 
        INNER JOIN orders o ON oi.order_id = o.order_id 
        WHERE oi.product_id = p.product_id 
        AND o.customer_id = c.customer_id
    )
);""",
        complexity="very_complex",
        description="Nested NOT EXISTS subqueries (division query)",
        category="subqueries"
    ),
    TestCase(
        id="very_complex_002",
        natural_language="Find products that are more expensive than at least 3 other products",
        expected_sql="""SELECT p1.* 
FROM products p1 
WHERE (
    SELECT COUNT(*) 
    FROM products p2 
    WHERE p2.price < p1.price
) >= 3;""",
        complexity="very_complex",
        description="Correlated subquery with COUNT",
        category="subqueries"
    ),
    TestCase(
        id="very_complex_003",
        natural_language="Show customers with their order history including product details and totals",
        expected_sql="""SELECT c.customer_id, c.first_name, c.last_name, 
       o.order_id, o.order_date, o.status,
       p.product_name, oi.quantity, oi.unit_price, oi.subtotal,
       o.total_amount as order_total
FROM customers c 
INNER JOIN orders o ON c.customer_id = o.customer_id 
INNER JOIN order_items oi ON o.order_id = oi.order_id 
INNER JOIN products p ON oi.product_id = p.product_id 
ORDER BY c.customer_id, o.order_date DESC, p.product_name;""",
        complexity="very_complex",
        description="Multiple JOINs with complex ORDER BY",
        category="joins"
    ),
    TestCase(
        id="very_complex_004",
        natural_language="Find the second most expensive product in each category",
        expected_sql="""SELECT p1.* 
FROM products p1 
WHERE (
    SELECT COUNT(DISTINCT p2.price) 
    FROM products p2 
    WHERE p2.category = p1.category 
    AND p2.price > p1.price
) = 1;""",
        complexity="very_complex",
        description="Correlated subquery for ranking",
        category="subqueries"
    ),
    TestCase(
        id="very_complex_005",
        natural_language="Show products with their sales performance compared to category average",
        expected_sql="""SELECT p.product_id, p.product_name, p.category, p.price,
       COALESCE(SUM(oi.subtotal), 0) as total_sales,
       (SELECT AVG(subquery.total_sales) 
        FROM (
            SELECT p2.product_id, COALESCE(SUM(oi2.subtotal), 0) as total_sales 
            FROM products p2 
            LEFT JOIN order_items oi2 ON p2.product_id = oi2.product_id 
            WHERE p2.category = p.category 
            GROUP BY p2.product_id
        ) subquery
       ) as category_avg_sales
FROM products p 
LEFT JOIN order_items oi ON p.product_id = oi.product_id 
GROUP BY p.product_id, p.product_name, p.category, p.price;""",
        complexity="very_complex",
        description="Complex nested subquery with aggregations",
        category="subqueries"
    ),
    TestCase(
        id="very_complex_006",
        natural_language="Find customers who have purchased products from at least 2 different categories",
        expected_sql="""SELECT c.*, COUNT(DISTINCT p.category) as categories_purchased 
FROM customers c 
INNER JOIN orders o ON c.customer_id = o.customer_id 
INNER JOIN order_items oi ON o.order_id = oi.order_id 
INNER JOIN products p ON oi.product_id = p.product_id 
GROUP BY c.customer_id 
HAVING COUNT(DISTINCT p.category) >= 2;""",
        complexity="very_complex",
        description="Multiple JOINs with COUNT DISTINCT and HAVING",
        category="aggregation"
    ),
    
    # ========== ADDITIONAL TEST CASES TO REACH 50 TOTAL ==========
    # Simple queries (2 more)
    TestCase(
        id="simple_009",
        natural_language="Show all products with their prices",
        expected_sql="SELECT product_name, price FROM products;",
        complexity="simple",
        description="SELECT specific columns from single table",
        category="basic_select"
    ),
    TestCase(
        id="simple_010",
        natural_language="How many customers do we have?",
        expected_sql="SELECT COUNT(*) FROM customers;",
        complexity="simple",
        description="Simple COUNT on customers table",
        category="aggregation"
    ),
    
    # Medium queries (3 more)
    TestCase(
        id="medium_015",
        natural_language="Show all reviews with product names",
        expected_sql="""SELECT r.*, p.product_name 
FROM reviews r 
INNER JOIN products p ON r.product_id = p.product_id;""",
        complexity="medium",
        description="INNER JOIN to get product names for reviews",
        category="joins"
    ),
    TestCase(
        id="medium_016",
        natural_language="Find the maximum price of products",
        expected_sql="SELECT MAX(price) as max_price FROM products;",
        complexity="medium",
        description="MAX aggregation function",
        category="aggregation"
    ),
    TestCase(
        id="medium_017",
        natural_language="Show orders placed after 2024-01-01",
        expected_sql="SELECT * FROM orders WHERE order_date > '2024-01-01';",
        complexity="medium",
        description="Date comparison with greater than",
        category="filtering"
    ),
    
    # Complex queries (3 more)
    TestCase(
        id="complex_013",
        natural_language="Find products that have been reviewed but never ordered",
        expected_sql="""SELECT DISTINCT p.* 
FROM products p 
INNER JOIN reviews r ON p.product_id = r.product_id 
WHERE p.product_id NOT IN (
    SELECT DISTINCT product_id FROM order_items
);""",
        complexity="complex",
        description="JOIN with subquery using NOT IN",
        category="subqueries"
    ),
    TestCase(
        id="complex_014",
        natural_language="Show customers with their first order date",
        expected_sql="""SELECT c.*, MIN(o.order_date) as first_order_date 
FROM customers c 
LEFT JOIN orders o ON c.customer_id = o.customer_id 
GROUP BY c.customer_id;""",
        complexity="complex",
        description="LEFT JOIN with MIN aggregation",
        category="aggregation"
    ),
    TestCase(
        id="complex_015",
        natural_language="Find the total number of items sold for each product",
        expected_sql="""SELECT p.product_id, p.product_name, 
       COALESCE(SUM(oi.quantity), 0) as total_items_sold 
FROM products p 
LEFT JOIN order_items oi ON p.product_id = oi.product_id 
GROUP BY p.product_id, p.product_name;""",
        complexity="complex",
        description="LEFT JOIN with SUM and COALESCE",
        category="aggregation"
    ),
    
    # Very complex queries (2 more)
    TestCase(
        id="very_complex_007",
        natural_language="Show products that have sold more units than the average units sold across all products",
        expected_sql="""SELECT p.product_id, p.product_name, SUM(oi.quantity) as units_sold 
FROM products p 
INNER JOIN order_items oi ON p.product_id = oi.product_id 
GROUP BY p.product_id, p.product_name 
HAVING SUM(oi.quantity) > (
    SELECT AVG(total_units) 
    FROM (
        SELECT SUM(oi2.quantity) as total_units 
        FROM order_items oi2 
        GROUP BY oi2.product_id
    ) subquery
);""",
        complexity="very_complex",
        description="Nested subquery with HAVING and aggregation comparison",
        category="subqueries"
    ),
    TestCase(
        id="very_complex_008",
        natural_language="Find customers who have placed orders in all months where orders exist",
        expected_sql="""SELECT c.* 
FROM customers c 
WHERE NOT EXISTS (
    SELECT DISTINCT DATE_TRUNC('month', o1.order_date) as order_month 
    FROM orders o1 
    WHERE NOT EXISTS (
        SELECT 1 
        FROM orders o2 
        WHERE o2.customer_id = c.customer_id 
        AND DATE_TRUNC('month', o2.order_date) = DATE_TRUNC('month', o1.order_date)
    )
);""",
        complexity="very_complex",
        description="Complex nested NOT EXISTS with date functions",
        category="subqueries"
    ),
]


def get_test_cases_by_complexity(complexity: Complexity = None) -> List[TestCase]:
    """Get test cases filtered by complexity."""
    if complexity:
        return [tc for tc in TEST_CASES if tc.complexity == complexity]
    return TEST_CASES


def get_test_cases_by_category(category: str = None) -> List[TestCase]:
    """Get test cases filtered by category."""
    if category:
        return [tc for tc in TEST_CASES if tc.category == category]
    return TEST_CASES


def get_test_case_by_id(test_id: str) -> TestCase:
    """Get a specific test case by ID."""
    for tc in TEST_CASES:
        if tc.id == test_id:
            return tc
    raise ValueError(f"Test case with ID '{test_id}' not found")
