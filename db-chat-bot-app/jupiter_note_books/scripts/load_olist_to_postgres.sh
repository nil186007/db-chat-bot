#!/bin/bash
# Load complete olist.sqlite into customer_orders_and_reviews_db (existing DB)
# Creates schema "sql-e-commerce" only - no separate database
# Ensure PostgreSQL is running (e.g. docker-compose up -d postgres)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SQLITE_PATH="${SCRIPT_DIR}/olist.sqlite"

if [[ ! -f "$SQLITE_PATH" ]]; then
  echo "Error: olist.sqlite not found at $SQLITE_PATH"
  exit 1
fi

python "$SCRIPT_DIR/sqlite_to_postgres.py" "$SQLITE_PATH" \
  --pg-db "customer_orders_and_reviews_db" \
  --pg-schema "sql-e-commerce" \
  --recreate-tables \
  --fill-not-null
