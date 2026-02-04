# MongoDB Supply Chain & Inventory Data

This document describes the MongoDB collections containing supply chain and inventory data for the e-commerce database.

## Overview

The MongoDB database (`vendor_supply_chain_db`) contains supply chain and inventory data that complements the PostgreSQL product catalog. All products in MongoDB are linked to PostgreSQL products by `product_name`, ensuring data consistency.

## Collections

### 1. vendors
Stores vendor/supplier information.

**Schema:**
```javascript
{
  vendor_id: String (unique),
  vendor_name: String,
  contact_person: String,
  email: String,
  phone: String,
  address: String,
  country: String,
  rating: Number,
  specializations: [String],
  payment_terms: String,
  created_at: Date
}
```

**Sample Data:** 5 vendors covering different product categories

### 2. product_vendor_mapping
Maps products to their vendors.

**Schema:**
```javascript
{
  product_name: String,  // Links to PostgreSQL products.product_name
  vendor_id: String,     // Links to vendors.vendor_id
  is_primary_vendor: Boolean,
  lead_time_days: Number
}
```

**Sample Data:** All 25 products mapped to their vendors

### 3. inventory
Current inventory status for all products.

**Schema:**
```javascript
{
  product_name: String (unique),  // Links to PostgreSQL products.product_name
  quantity_in_hand: Number,        // Available stock
  quantity_in_transit: Number,     // Items being shipped
  quantity_ordered: Number,        // Items on order
  quantity_reserved: Number,       // Reserved stock
  reorder_point: Number,           // Minimum stock level before reordering
  max_stock_level: Number,         // Maximum stock capacity
  warehouse_location: String,     // Links to warehouses.warehouse_id
  last_restocked: Date,
  status: String                   // "in_stock", "out_of_stock", "low_stock"
}
```

**Sample Data:** Inventory records for all 25 products

### 4. purchase_orders
Purchase order records.

**Schema:**
```javascript
{
  po_number: String (unique),
  vendor_id: String,              // Links to vendors.vendor_id
  product_name: String,           // Links to PostgreSQL products.product_name
  order_date: Date,
  expected_delivery_date: Date,
  quantity_ordered: Number,
  unit_cost: Number,
  total_cost: Number,
  status: String,                 // "ordered", "in_transit", "delivered", "cancelled"
  payment_status: String,         // "pending", "paid", "partial"
  created_by: String,
  notes: String
}
```

**Sample Data:** 5 purchase orders

### 5. shipments
Shipment tracking information.

**Schema:**
```javascript
{
  shipment_id: String (unique),
  po_number: String,             // Links to purchase_orders.po_number (optional)
  vendor_id: String,              // Links to vendors.vendor_id
  product_name: String,           // Links to PostgreSQL products.product_name
  quantity: Number,
  shipped_date: Date,
  expected_arrival_date: Date,
  actual_arrival_date: Date,      // null if not yet arrived
  carrier: String,                // "FedEx", "UPS", "DHL", etc.
  tracking_number: String,
  shipping_cost: Number,
  status: String,                 // "in_transit", "delivered", "lost"
  origin: String,
  destination: String             // Warehouse ID
}
```

**Sample Data:** 4 shipments (some in transit, some delivered)

### 6. costs
Various cost types for products.

**Schema:**
```javascript
{
  product_name: String,           // Links to PostgreSQL products.product_name
  cost_type: String,              // "production", "shipping", "storage", "handling"
  unit_cost: Number,
  quantity: Number,
  total_cost: Number,
  vendor_id: String,              // Links to vendors.vendor_id
  shipment_id: String,           // Links to shipments.shipment_id (for shipping costs)
  date: Date,
  notes: String
}
```

**Sample Data:** 
- Production costs for multiple products
- Shipping costs for shipments
- Storage costs (monthly)
- Handling costs

### 7. warehouses
Warehouse locations and details.

**Schema:**
```javascript
{
  warehouse_id: String (unique),
  warehouse_name: String,
  location: String,
  address: String,
  capacity_sqft: Number,
  current_utilization: Number,    // Percentage
  manager: String,
  phone: String,
  operating_hours: String
}
```

**Sample Data:** 5 warehouses in different locations

## Data Relationships

```
PostgreSQL products.product_name
    ↓
MongoDB product_vendor_mapping.product_name
    ↓
MongoDB vendors.vendor_id
    ↓
MongoDB purchase_orders.vendor_id
    ↓
MongoDB shipments.po_number
    ↓
MongoDB costs (various types)
```

## Loading Data

### Method 1: Shell Script (Recommended)
```bash
cd docker-setup/scripts
./load_mongodb_data.sh
```

### Method 2: JavaScript File
```bash
docker exec -i db-chat-bot-mongodb mongosh -u admin -p adminpassword --authenticationDatabase admin vendor_supply_chain_db < docker-setup/scripts/load_mongodb_data.js
```

### Method 3: Python Script
```bash
cd docker-setup/scripts
python3 load_mongodb_data.py
```

## Example Queries

### Find inventory for a specific product
```javascript
db.inventory.findOne({ product_name: "Laptop Pro 15\"" })
```

### Find all products from a vendor
```javascript
db.product_vendor_mapping.find({ vendor_id: "V001" })
```

### Find all shipments in transit
```javascript
db.shipments.find({ status: "in_transit" })
```

### Calculate total inventory value
```javascript
db.inventory.aggregate([
  {
    $lookup: {
      from: "costs",
      localField: "product_name",
      foreignField: "product_name",
      as: "costs"
    }
  },
  {
    $project: {
      product_name: 1,
      quantity_in_hand: 1,
      unit_cost: { $arrayElemAt: ["$costs.unit_cost", 0] },
      total_value: { $multiply: ["$quantity_in_hand", { $arrayElemAt: ["$costs.unit_cost", 0] }] }
    }
  }
])
```

### Find products below reorder point
```javascript
db.inventory.find({
  $expr: { $lt: ["$quantity_in_hand", "$reorder_point"] }
})
```

## Integration with PostgreSQL

The MongoDB collections are designed to complement PostgreSQL data:

- **PostgreSQL** stores: Products, Customers, Orders, Order Items, Reviews
- **MongoDB** stores: Vendors, Inventory, Purchase Orders, Shipments, Costs, Warehouses

Products are linked between systems using `product_name` as the common identifier.

## Accessing MongoDB

### Via Mongo Express (Web UI)
- URL: http://localhost:8081
- Username: `admin`
- Password: `admin`

### Via Command Line
```bash
docker exec -it db-chat-bot-mongodb mongosh -u admin -p adminpassword --authenticationDatabase admin
```

### Connection String
```
mongodb://admin:adminpassword@localhost:27017/vendor_supply_chain_db?authSource=admin
```
