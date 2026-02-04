#!/bin/bash
# Script to load MongoDB supply chain data
# Usage: ./load_mongodb_data.sh

echo "Loading MongoDB supply chain and inventory data..."

# Check if MongoDB is running
if ! docker ps | grep -q db-chat-bot-mongodb; then
    echo "Error: MongoDB container is not running."
    echo "Please start it with: cd docker-setup && docker-compose up -d mongodb"
    exit 1
fi

# Load the data
docker exec -i db-chat-bot-mongodb mongosh -u admin -p adminpassword --authenticationDatabase admin vendor_supply_chain_db < load_mongodb_data.js

if [ $? -eq 0 ]; then
    echo "✅ MongoDB data loaded successfully!"
    echo ""
    echo "Collections created:"
    echo "  - vendors"
    echo "  - product_vendor_mapping"
    echo "  - inventory"
    echo "  - purchase_orders"
    echo "  - shipments"
    echo "  - costs"
    echo "  - warehouses"
else
    echo "❌ Error loading MongoDB data"
    exit 1
fi
