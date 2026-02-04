#!/usr/bin/env python3
"""
Python script to load MongoDB supply chain and inventory data.
Alternative to the JavaScript version for easier integration.
"""
import sys
from pathlib import Path

# Add parent directory to path for imports if needed
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from pymongo import MongoClient
from datetime import datetime
import json

# MongoDB connection settings (from docker-compose.yml)
MONGO_URI = "mongodb://admin:adminpassword@localhost:27017/"
DATABASE_NAME = "vendor_supply_chain_db"

def load_mongodb_data():
    """Load supply chain and inventory data into MongoDB."""
    print("Connecting to MongoDB...")
    client = MongoClient(MONGO_URI)
    db = client[DATABASE_NAME]
    
    print("Starting MongoDB data load for supply chain and inventory...")
    
    # ========== VENDORS COLLECTION ==========
    print("Creating vendors collection...")
    vendors = [
        {
            "vendor_id": "V001",
            "vendor_name": "TechCorp Manufacturing",
            "contact_person": "John Tech",
            "email": "john.tech@techcorp.com",
            "phone": "555-2001",
            "address": "123 Tech Park, San Francisco, CA 94101",
            "country": "USA",
            "rating": 4.8,
            "specializations": ["Electronics", "Computer Accessories"],
            "payment_terms": "Net 30",
            "created_at": datetime(2023, 1, 15)
        },
        {
            "vendor_id": "V002",
            "vendor_name": "Home Essentials Inc",
            "contact_person": "Sarah Home",
            "email": "sarah@homeessentials.com",
            "phone": "555-2002",
            "address": "456 Home Ave, Chicago, IL 60601",
            "country": "USA",
            "rating": 4.6,
            "specializations": ["Home & Kitchen"],
            "payment_terms": "Net 45",
            "created_at": datetime(2023, 2, 1)
        },
        {
            "vendor_id": "V003",
            "vendor_name": "Sports Gear Co",
            "contact_person": "Mike Sports",
            "email": "mike@sportsgear.com",
            "phone": "555-2003",
            "address": "789 Sports Blvd, Denver, CO 80201",
            "country": "USA",
            "rating": 4.7,
            "specializations": ["Sports & Outdoors"],
            "payment_terms": "Net 30",
            "created_at": datetime(2023, 2, 15)
        },
        {
            "vendor_id": "V004",
            "vendor_name": "Accessories Plus",
            "contact_person": "Lisa Accessories",
            "email": "lisa@accessoriesplus.com",
            "phone": "555-2004",
            "address": "321 Accessory St, New York, NY 10001",
            "country": "USA",
            "rating": 4.5,
            "specializations": ["Accessories"],
            "payment_terms": "Net 30",
            "created_at": datetime(2023, 3, 1)
        },
        {
            "vendor_id": "V005",
            "vendor_name": "Game World Suppliers",
            "contact_person": "Tom Games",
            "email": "tom@gamesuppliers.com",
            "phone": "555-2005",
            "address": "654 Game Lane, Seattle, WA 98101",
            "country": "USA",
            "rating": 4.4,
            "specializations": ["Toys & Games"],
            "payment_terms": "Net 30",
            "created_at": datetime(2023, 3, 15)
        }
    ]
    db.vendors.insert_many(vendors)
    
    # ========== PRODUCT VENDOR MAPPING ==========
    print("Creating product_vendor_mapping collection...")
    product_vendor_mapping = [
        # Electronics
        {"product_name": 'Laptop Pro 15"', "vendor_id": "V001", "is_primary_vendor": True, "lead_time_days": 14},
        {"product_name": "Wireless Mouse", "vendor_id": "V001", "is_primary_vendor": True, "lead_time_days": 7},
        {"product_name": "Mechanical Keyboard", "vendor_id": "V001", "is_primary_vendor": True, "lead_time_days": 10},
        {"product_name": 'Monitor 27" 4K', "vendor_id": "V001", "is_primary_vendor": True, "lead_time_days": 12},
        {"product_name": "USB-C Hub", "vendor_id": "V001", "is_primary_vendor": True, "lead_time_days": 5},
        {"product_name": "Smart Watch", "vendor_id": "V001", "is_primary_vendor": True, "lead_time_days": 10},
        {"product_name": "Bluetooth Headphones", "vendor_id": "V001", "is_primary_vendor": True, "lead_time_days": 8},
        # Home & Kitchen
        {"product_name": "Coffee Maker Deluxe", "vendor_id": "V002", "is_primary_vendor": True, "lead_time_days": 9},
        {"product_name": "Air Fryer XL", "vendor_id": "V002", "is_primary_vendor": True, "lead_time_days": 11},
        {"product_name": "Stand Mixer", "vendor_id": "V002", "is_primary_vendor": True, "lead_time_days": 15},
        {"product_name": "Desk Lamp LED", "vendor_id": "V002", "is_primary_vendor": True, "lead_time_days": 6},
        {"product_name": "Throw Pillow Set", "vendor_id": "V002", "is_primary_vendor": True, "lead_time_days": 7},
        # Sports & Outdoors
        {"product_name": "Yoga Mat Premium", "vendor_id": "V003", "is_primary_vendor": True, "lead_time_days": 5},
        {"product_name": "Running Shoes", "vendor_id": "V003", "is_primary_vendor": True, "lead_time_days": 12},
        {"product_name": "Backpack Travel", "vendor_id": "V003", "is_primary_vendor": True, "lead_time_days": 8},
        {"product_name": "Water Bottle Insulated", "vendor_id": "V003", "is_primary_vendor": True, "lead_time_days": 4},
        # Accessories
        {"product_name": "Leather Wallet", "vendor_id": "V004", "is_primary_vendor": True, "lead_time_days": 6},
        {"product_name": "Sunglasses Classic", "vendor_id": "V004", "is_primary_vendor": True, "lead_time_days": 7},
        # Toys & Games
        {"product_name": "Puzzle 1000 Pieces", "vendor_id": "V005", "is_primary_vendor": True, "lead_time_days": 5},
        {"product_name": "Board Game Strategy", "vendor_id": "V005", "is_primary_vendor": True, "lead_time_days": 6},
        # Out of stock products
        {"product_name": "Out of Stock Product A", "vendor_id": "V001", "is_primary_vendor": True, "lead_time_days": 14},
        {"product_name": "Out of Stock Product B", "vendor_id": "V002", "is_primary_vendor": True, "lead_time_days": 9},
        # Unordered products
        {"product_name": "Unordered Product X", "vendor_id": "V001", "is_primary_vendor": True, "lead_time_days": 10},
        {"product_name": "Unordered Product Y", "vendor_id": "V003", "is_primary_vendor": True, "lead_time_days": 8},
        {"product_name": "Unordered Product Z", "vendor_id": "V004", "is_primary_vendor": True, "lead_time_days": 6}
    ]
    db.product_vendor_mapping.insert_many(product_vendor_mapping)
    
    # ========== INVENTORY COLLECTION ==========
    print("Creating inventory collection...")
    # This is a large collection, so I'll create a helper function
    inventory_data = [
        # Electronics
        {"product_name": 'Laptop Pro 15"', "quantity_in_hand": 25, "quantity_in_transit": 15, "quantity_ordered": 10, "quantity_reserved": 5, "reorder_point": 20, "max_stock_level": 100, "warehouse_location": "WH-001", "last_restocked": datetime(2024, 1, 20), "status": "in_stock"},
        {"product_name": "Wireless Mouse", "quantity_in_hand": 150, "quantity_in_transit": 50, "quantity_ordered": 0, "quantity_reserved": 20, "reorder_point": 50, "max_stock_level": 300, "warehouse_location": "WH-001", "last_restocked": datetime(2024, 1, 25), "status": "in_stock"},
        {"product_name": "Mechanical Keyboard", "quantity_in_hand": 100, "quantity_in_transit": 30, "quantity_ordered": 20, "quantity_reserved": 10, "reorder_point": 40, "max_stock_level": 200, "warehouse_location": "WH-001", "last_restocked": datetime(2024, 1, 22), "status": "in_stock"},
        {"product_name": 'Monitor 27" 4K', "quantity_in_hand": 45, "quantity_in_transit": 20, "quantity_ordered": 10, "quantity_reserved": 5, "reorder_point": 30, "max_stock_level": 120, "warehouse_location": "WH-001", "last_restocked": datetime(2024, 1, 18), "status": "in_stock"},
        {"product_name": "USB-C Hub", "quantity_in_hand": 200, "quantity_in_transit": 50, "quantity_ordered": 50, "quantity_reserved": 30, "reorder_point": 100, "max_stock_level": 400, "warehouse_location": "WH-001", "last_restocked": datetime(2024, 1, 28), "status": "in_stock"},
        {"product_name": "Smart Watch", "quantity_in_hand": 60, "quantity_in_transit": 20, "quantity_ordered": 10, "quantity_reserved": 5, "reorder_point": 30, "max_stock_level": 150, "warehouse_location": "WH-001", "last_restocked": datetime(2024, 1, 24), "status": "in_stock"},
        {"product_name": "Bluetooth Headphones", "quantity_in_hand": 80, "quantity_in_transit": 20, "quantity_ordered": 10, "quantity_reserved": 8, "reorder_point": 40, "max_stock_level": 180, "warehouse_location": "WH-001", "last_restocked": datetime(2024, 1, 26), "status": "in_stock"},
        # Home & Kitchen
        {"product_name": "Coffee Maker Deluxe", "quantity_in_hand": 70, "quantity_in_transit": 20, "quantity_ordered": 10, "quantity_reserved": 5, "reorder_point": 30, "max_stock_level": 150, "warehouse_location": "WH-002", "last_restocked": datetime(2024, 1, 21), "status": "in_stock"},
        {"product_name": "Air Fryer XL", "quantity_in_hand": 50, "quantity_in_transit": 20, "quantity_ordered": 10, "quantity_reserved": 3, "reorder_point": 25, "max_stock_level": 120, "warehouse_location": "WH-002", "last_restocked": datetime(2024, 1, 19), "status": "in_stock"},
        {"product_name": "Stand Mixer", "quantity_in_hand": 40, "quantity_in_transit": 15, "quantity_ordered": 5, "quantity_reserved": 2, "reorder_point": 20, "max_stock_level": 100, "warehouse_location": "WH-002", "last_restocked": datetime(2024, 1, 17), "status": "in_stock"},
        {"product_name": "Desk Lamp LED", "quantity_in_hand": 120, "quantity_in_transit": 30, "quantity_ordered": 10, "quantity_reserved": 15, "reorder_point": 50, "max_stock_level": 250, "warehouse_location": "WH-002", "last_restocked": datetime(2024, 1, 27), "status": "in_stock"},
        {"product_name": "Throw Pillow Set", "quantity_in_hand": 150, "quantity_in_transit": 30, "quantity_ordered": 20, "quantity_reserved": 25, "reorder_point": 80, "max_stock_level": 300, "warehouse_location": "WH-002", "last_restocked": datetime(2024, 1, 29), "status": "in_stock"},
        # Sports & Outdoors
        {"product_name": "Yoga Mat Premium", "quantity_in_hand": 150, "quantity_in_transit": 30, "quantity_ordered": 20, "quantity_reserved": 20, "reorder_point": 80, "max_stock_level": 300, "warehouse_location": "WH-003", "last_restocked": datetime(2024, 1, 23), "status": "in_stock"},
        {"product_name": "Running Shoes", "quantity_in_hand": 100, "quantity_in_transit": 30, "quantity_ordered": 20, "quantity_reserved": 15, "reorder_point": 50, "max_stock_level": 200, "warehouse_location": "WH-003", "last_restocked": datetime(2024, 1, 20), "status": "in_stock"},
        {"product_name": "Backpack Travel", "quantity_in_hand": 80, "quantity_in_transit": 25, "quantity_ordered": 15, "quantity_reserved": 10, "reorder_point": 40, "max_stock_level": 180, "warehouse_location": "WH-003", "last_restocked": datetime(2024, 1, 25), "status": "in_stock"},
        {"product_name": "Water Bottle Insulated", "quantity_in_hand": 200, "quantity_in_transit": 30, "quantity_ordered": 20, "quantity_reserved": 30, "reorder_point": 100, "max_stock_level": 400, "warehouse_location": "WH-003", "last_restocked": datetime(2024, 1, 28), "status": "in_stock"},
        # Accessories
        {"product_name": "Leather Wallet", "quantity_in_hand": 130, "quantity_in_transit": 30, "quantity_ordered": 20, "quantity_reserved": 15, "reorder_point": 60, "max_stock_level": 250, "warehouse_location": "WH-004", "last_restocked": datetime(2024, 1, 24), "status": "in_stock"},
        {"product_name": "Sunglasses Classic", "quantity_in_hand": 100, "quantity_in_transit": 25, "quantity_ordered": 15, "quantity_reserved": 10, "reorder_point": 50, "max_stock_level": 200, "warehouse_location": "WH-004", "last_restocked": datetime(2024, 1, 22), "status": "in_stock"},
        # Toys & Games
        {"product_name": "Puzzle 1000 Pieces", "quantity_in_hand": 250, "quantity_in_transit": 30, "quantity_ordered": 20, "quantity_reserved": 40, "reorder_point": 120, "max_stock_level": 500, "warehouse_location": "WH-005", "last_restocked": datetime(2024, 1, 26), "status": "in_stock"},
        {"product_name": "Board Game Strategy", "quantity_in_hand": 70, "quantity_in_transit": 20, "quantity_ordered": 10, "quantity_reserved": 8, "reorder_point": 30, "max_stock_level": 150, "warehouse_location": "WH-005", "last_restocked": datetime(2024, 1, 21), "status": "in_stock"},
        # Out of stock products
        {"product_name": "Out of Stock Product A", "quantity_in_hand": 0, "quantity_in_transit": 0, "quantity_ordered": 50, "quantity_reserved": 0, "reorder_point": 20, "max_stock_level": 100, "warehouse_location": "WH-001", "last_restocked": datetime(2023, 12, 15), "status": "out_of_stock"},
        {"product_name": "Out of Stock Product B", "quantity_in_hand": 0, "quantity_in_transit": 0, "quantity_ordered": 30, "quantity_reserved": 0, "reorder_point": 15, "max_stock_level": 80, "warehouse_location": "WH-002", "last_restocked": datetime(2023, 12, 20), "status": "out_of_stock"},
        # Unordered products
        {"product_name": "Unordered Product X", "quantity_in_hand": 30, "quantity_in_transit": 0, "quantity_ordered": 0, "quantity_reserved": 0, "reorder_point": 20, "max_stock_level": 100, "warehouse_location": "WH-001", "last_restocked": datetime(2024, 1, 10), "status": "in_stock"},
        {"product_name": "Unordered Product Y", "quantity_in_hand": 50, "quantity_in_transit": 0, "quantity_ordered": 0, "quantity_reserved": 0, "reorder_point": 30, "max_stock_level": 120, "warehouse_location": "WH-003", "last_restocked": datetime(2024, 1, 12), "status": "in_stock"},
        {"product_name": "Unordered Product Z", "quantity_in_hand": 80, "quantity_in_transit": 0, "quantity_ordered": 0, "quantity_reserved": 0, "reorder_point": 40, "max_stock_level": 150, "warehouse_location": "WH-004", "last_restocked": datetime(2024, 1, 15), "status": "in_stock"}
    ]
    db.inventory.insert_many(inventory_data)
    
    # ========== PURCHASE ORDERS COLLECTION ==========
    print("Creating purchase_orders collection...")
    purchase_orders = [
        {
            "po_number": "PO-2024-001",
            "vendor_id": "V001",
            "product_name": 'Laptop Pro 15"',
            "order_date": datetime(2024, 1, 15),
            "expected_delivery_date": datetime(2024, 1, 29),
            "quantity_ordered": 10,
            "unit_cost": 900.00,
            "total_cost": 9000.00,
            "status": "ordered",
            "payment_status": "pending",
            "created_by": "admin",
            "notes": "Urgent order for high demand"
        },
        {
            "po_number": "PO-2024-002",
            "vendor_id": "V001",
            "product_name": "Wireless Mouse",
            "order_date": datetime(2024, 1, 20),
            "expected_delivery_date": datetime(2024, 1, 27),
            "quantity_ordered": 50,
            "unit_cost": 15.00,
            "total_cost": 750.00,
            "status": "in_transit",
            "payment_status": "paid",
            "created_by": "admin",
            "notes": "Regular restock"
        },
        {
            "po_number": "PO-2024-003",
            "vendor_id": "V002",
            "product_name": "Coffee Maker Deluxe",
            "order_date": datetime(2024, 1, 18),
            "expected_delivery_date": datetime(2024, 1, 27),
            "quantity_ordered": 20,
            "unit_cost": 50.00,
            "total_cost": 1000.00,
            "status": "in_transit",
            "payment_status": "paid",
            "created_by": "admin"
        },
        {
            "po_number": "PO-2024-004",
            "vendor_id": "V003",
            "product_name": "Running Shoes",
            "order_date": datetime(2024, 1, 22),
            "expected_delivery_date": datetime(2024, 2, 3),
            "quantity_ordered": 30,
            "unit_cost": 60.00,
            "total_cost": 1800.00,
            "status": "ordered",
            "payment_status": "pending",
            "created_by": "admin"
        },
        {
            "po_number": "PO-2024-005",
            "vendor_id": "V001",
            "product_name": "Out of Stock Product A",
            "order_date": datetime(2024, 1, 25),
            "expected_delivery_date": datetime(2024, 2, 8),
            "quantity_ordered": 50,
            "unit_cost": 70.00,
            "total_cost": 3500.00,
            "status": "ordered",
            "payment_status": "pending",
            "created_by": "admin",
            "notes": "Restocking out of stock item"
        }
    ]
    db.purchase_orders.insert_many(purchase_orders)
    
    # ========== SHIPMENTS COLLECTION ==========
    print("Creating shipments collection...")
    shipments = [
        {
            "shipment_id": "SH-2024-001",
            "po_number": "PO-2024-002",
            "vendor_id": "V001",
            "product_name": "Wireless Mouse",
            "quantity": 50,
            "shipped_date": datetime(2024, 1, 22),
            "expected_arrival_date": datetime(2024, 1, 27),
            "actual_arrival_date": None,
            "carrier": "FedEx",
            "tracking_number": "FX123456789",
            "shipping_cost": 45.00,
            "status": "in_transit",
            "origin": "San Francisco, CA",
            "destination": "WH-001"
        },
        {
            "shipment_id": "SH-2024-002",
            "po_number": "PO-2024-003",
            "vendor_id": "V002",
            "product_name": "Coffee Maker Deluxe",
            "quantity": 20,
            "shipped_date": datetime(2024, 1, 20),
            "expected_arrival_date": datetime(2024, 1, 27),
            "actual_arrival_date": None,
            "carrier": "UPS",
            "tracking_number": "UPS987654321",
            "shipping_cost": 60.00,
            "status": "in_transit",
            "origin": "Chicago, IL",
            "destination": "WH-002"
        },
        {
            "shipment_id": "SH-2024-003",
            "vendor_id": "V001",
            "product_name": "Mechanical Keyboard",
            "quantity": 30,
            "shipped_date": datetime(2024, 1, 18),
            "expected_arrival_date": datetime(2024, 1, 28),
            "actual_arrival_date": datetime(2024, 1, 27),
            "carrier": "FedEx",
            "tracking_number": "FX987654321",
            "shipping_cost": 55.00,
            "status": "delivered",
            "origin": "San Francisco, CA",
            "destination": "WH-001"
        },
        {
            "shipment_id": "SH-2024-004",
            "vendor_id": "V003",
            "product_name": "Yoga Mat Premium",
            "quantity": 30,
            "shipped_date": datetime(2024, 1, 19),
            "expected_arrival_date": datetime(2024, 1, 24),
            "actual_arrival_date": datetime(2024, 1, 23),
            "carrier": "DHL",
            "tracking_number": "DHL456789123",
            "shipping_cost": 40.00,
            "status": "delivered",
            "origin": "Denver, CO",
            "destination": "WH-003"
        }
    ]
    db.shipments.insert_many(shipments)
    
    # ========== COSTS COLLECTION ==========
    print("Creating costs collection...")
    costs = [
        # Production costs
        {"product_name": 'Laptop Pro 15"', "cost_type": "production", "unit_cost": 900.00, "quantity": 1, "total_cost": 900.00, "vendor_id": "V001", "date": datetime(2024, 1, 15), "notes": "Manufacturing cost per unit"},
        {"product_name": "Wireless Mouse", "cost_type": "production", "unit_cost": 15.00, "quantity": 1, "total_cost": 15.00, "vendor_id": "V001", "date": datetime(2024, 1, 20), "notes": "Manufacturing cost per unit"},
        {"product_name": "Coffee Maker Deluxe", "cost_type": "production", "unit_cost": 50.00, "quantity": 1, "total_cost": 50.00, "vendor_id": "V002", "date": datetime(2024, 1, 18), "notes": "Manufacturing cost per unit"},
        {"product_name": "Running Shoes", "cost_type": "production", "unit_cost": 60.00, "quantity": 1, "total_cost": 60.00, "vendor_id": "V003", "date": datetime(2024, 1, 22), "notes": "Manufacturing cost per unit"},
        # Shipping costs
        {"product_name": "Wireless Mouse", "cost_type": "shipping", "unit_cost": 0.90, "quantity": 50, "total_cost": 45.00, "vendor_id": "V001", "shipment_id": "SH-2024-001", "date": datetime(2024, 1, 22), "notes": "Shipping cost for 50 units"},
        {"product_name": "Coffee Maker Deluxe", "cost_type": "shipping", "unit_cost": 3.00, "quantity": 20, "total_cost": 60.00, "vendor_id": "V002", "shipment_id": "SH-2024-002", "date": datetime(2024, 1, 20), "notes": "Shipping cost for 20 units"},
        {"product_name": "Mechanical Keyboard", "cost_type": "shipping", "unit_cost": 1.83, "quantity": 30, "total_cost": 55.00, "vendor_id": "V001", "shipment_id": "SH-2024-003", "date": datetime(2024, 1, 18), "notes": "Shipping cost for 30 units"},
        # Storage costs
        {"product_name": 'Laptop Pro 15"', "cost_type": "storage", "unit_cost": 2.50, "quantity": 25, "total_cost": 62.50, "vendor_id": "V001", "date": datetime(2024, 1, 31), "notes": "Monthly storage cost"},
        {"product_name": "Wireless Mouse", "cost_type": "storage", "unit_cost": 0.20, "quantity": 150, "total_cost": 30.00, "vendor_id": "V001", "date": datetime(2024, 1, 31), "notes": "Monthly storage cost"},
        # Handling costs
        {"product_name": 'Laptop Pro 15"', "cost_type": "handling", "unit_cost": 5.00, "quantity": 25, "total_cost": 125.00, "vendor_id": "V001", "date": datetime(2024, 1, 31), "notes": "Monthly handling cost"}
    ]
    db.costs.insert_many(costs)
    
    # ========== WAREHOUSES COLLECTION ==========
    print("Creating warehouses collection...")
    warehouses = [
        {
            "warehouse_id": "WH-001",
            "warehouse_name": "Main Electronics Warehouse",
            "location": "San Francisco, CA",
            "address": "1000 Tech Park Dr, San Francisco, CA 94101",
            "capacity_sqft": 50000,
            "current_utilization": 75,
            "manager": "Alice Warehouse",
            "phone": "555-3001",
            "operating_hours": "Mon-Fri 8AM-6PM"
        },
        {
            "warehouse_id": "WH-002",
            "warehouse_name": "Home Goods Warehouse",
            "location": "Chicago, IL",
            "address": "2000 Home Ave, Chicago, IL 60601",
            "capacity_sqft": 40000,
            "current_utilization": 65,
            "manager": "Bob Storage",
            "phone": "555-3002",
            "operating_hours": "Mon-Fri 7AM-5PM"
        },
        {
            "warehouse_id": "WH-003",
            "warehouse_name": "Sports & Outdoors Warehouse",
            "location": "Denver, CO",
            "address": "3000 Sports Blvd, Denver, CO 80201",
            "capacity_sqft": 35000,
            "current_utilization": 70,
            "manager": "Charlie Sports",
            "phone": "555-3003",
            "operating_hours": "Mon-Fri 8AM-6PM"
        },
        {
            "warehouse_id": "WH-004",
            "warehouse_name": "Accessories Warehouse",
            "location": "New York, NY",
            "address": "4000 Accessory St, New York, NY 10001",
            "capacity_sqft": 30000,
            "current_utilization": 60,
            "manager": "Diana Accessories",
            "phone": "555-3004",
            "operating_hours": "Mon-Fri 9AM-5PM"
        },
        {
            "warehouse_id": "WH-005",
            "warehouse_name": "Toys & Games Warehouse",
            "location": "Seattle, WA",
            "address": "5000 Game Lane, Seattle, WA 98101",
            "capacity_sqft": 25000,
            "current_utilization": 55,
            "manager": "Eve Games",
            "phone": "555-3005",
            "operating_hours": "Mon-Fri 8AM-5PM"
        }
    ]
    db.warehouses.insert_many(warehouses)
    
    print("Creating indexes...")
    db.vendors.create_index("vendor_id", unique=True)
    db.vendors.create_index("vendor_name")
    
    db.product_vendor_mapping.create_index("product_name")
    db.product_vendor_mapping.create_index("vendor_id")
    
    db.inventory.create_index("product_name", unique=True)
    db.inventory.create_index("warehouse_location")
    db.inventory.create_index("status")
    
    db.purchase_orders.create_index("po_number", unique=True)
    db.purchase_orders.create_index("vendor_id")
    db.purchase_orders.create_index("product_name")
    db.purchase_orders.create_index("status")
    
    db.shipments.create_index("shipment_id", unique=True)
    db.shipments.create_index("po_number")
    db.shipments.create_index("tracking_number")
    db.shipments.create_index("status")
    
    db.costs.create_index("product_name")
    db.costs.create_index("cost_type")
    db.costs.create_index("vendor_id")
    db.costs.create_index("date")
    
    db.warehouses.create_index("warehouse_id", unique=True)
    
    print("✅ MongoDB data load completed successfully!")
    print("\nCollections created:")
    print("  - vendors")
    print("  - product_vendor_mapping")
    print("  - inventory")
    print("  - purchase_orders")
    print("  - shipments")
    print("  - costs")
    print("  - warehouses")
    
    client.close()

if __name__ == "__main__":
    try:
        load_mongodb_data()
    except Exception as e:
        print(f"❌ Error loading MongoDB data: {e}")
        sys.exit(1)
