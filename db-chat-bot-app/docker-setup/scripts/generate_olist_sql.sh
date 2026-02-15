#!/bin/bash
# Generate olist_load.sql from olist.sqlite for PostgreSQL init
# Run this before first 'docker-compose up' if olist.sqlite has changed

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OLIST_SQLITE="${SCRIPT_DIR}/../jupiter_note_books/scripts/olist.sqlite"
OUTPUT="${SCRIPT_DIR}/olist_load.sql"

if [[ ! -f "$OLIST_SQLITE" ]]; then
  echo "Error: olist.sqlite not found at $OLIST_SQLITE"
  exit 1
fi

python "${SCRIPT_DIR}/../jupiter_note_books/scripts/sqlite_to_sql.py" "$OLIST_SQLITE" -o "$OUTPUT" --schema sql-e-commerce
echo "Generated $OUTPUT - will be loaded on PostgreSQL first init"
