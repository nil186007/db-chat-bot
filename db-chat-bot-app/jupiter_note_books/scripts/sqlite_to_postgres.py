#!/usr/bin/env python3
"""
Load data from SQLite database into PostgreSQL.

Usage:
  python sqlite_to_postgres.py path/to/database.db

  # With custom PostgreSQL connection:
  python sqlite_to_postgres.py data.db --pg-host localhost --pg-db mydb --pg-user postgres --pg-password secret

  # Drop and recreate tables before loading:
  python sqlite_to_postgres.py data.db --recreate-tables

  # Load only specific tables:
  python sqlite_to_postgres.py data.db --tables products,customers

  # Load into a new schema (e.g. sql-e-commerce):
  python sqlite_to_postgres.py olist.sqlite --pg-schema sql-e-commerce --recreate-tables
"""
import argparse
import sqlite3
import os
import sys
try:
    import psycopg2
except ImportError:
    print("Install psycopg2-binary: pip install psycopg2-binary")
    sys.exit(1)


# SQLite type -> PostgreSQL type mapping
SQLITE_TO_PG = {
    "INTEGER": "BIGINT",
    "INT": "INTEGER",
    "TINYINT": "SMALLINT",
    "SMALLINT": "SMALLINT",
    "BIGINT": "BIGINT",
    "REAL": "DOUBLE PRECISION",
    "FLOAT": "DOUBLE PRECISION",
    "DOUBLE": "DOUBLE PRECISION",
    "NUMERIC": "NUMERIC",
    "DECIMAL": "NUMERIC",
    "TEXT": "TEXT",
    "VARCHAR": "VARCHAR(255)",
    "CHAR": "CHAR(255)",
    "BLOB": "BYTEA",
    "DATE": "DATE",
    "DATETIME": "TIMESTAMP",
    "TIMESTAMP": "TIMESTAMP",
    "BOOLEAN": "BOOLEAN",
}


def map_sqlite_type(sqlite_type: str) -> str:
    """Map SQLite affinity/type to PostgreSQL."""
    t = (sqlite_type or "TEXT").upper().split("(")[0].strip()
    return SQLITE_TO_PG.get(t, "TEXT")


def get_tables(conn: sqlite3.Connection) -> list:
    """Return list of table names in SQLite."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    return [r[0] for r in cur.fetchall()]


def get_table_info(conn: sqlite3.Connection, table: str) -> list:
    """Return (name, type, notnull, pk) for each column."""
    cur = conn.execute(f"PRAGMA table_info({table})")
    return cur.fetchall()


def infer_fk_order(conn: sqlite3.Connection, tables: list) -> list:
    """Return tables in load order (parents before children) using PRAGMA foreign_key_list."""
    deps = {}  # table -> set of tables it depends on
    for t in tables:
        deps[t] = set()
        cur = conn.execute(f"PRAGMA foreign_key_list({t})")
        for row in cur.fetchall():
            # row: (id, seq, table, from, to)
            ref_table = row[2]
            if ref_table in tables and ref_table != t:
                deps[t].add(ref_table)
    # Topological sort (simple)
    order = []
    remaining = set(tables)
    while remaining:
        ready = [t for t in remaining if not (deps[t] & remaining)]
        if not ready:
            # Circular or unknown - use original order
            order.extend(remaining)
            break
        order.extend(ready)
        remaining -= set(ready)
    return order


def quote_schema_table(schema: str, table: str) -> str:
    """Return quoted schema.table for SQL (handles hyphens in schema names)."""
    return f'"{schema}"."{table}"'


def create_pg_schema(pg_conn, schema: str):
    """Create PostgreSQL schema if it does not exist."""
    with pg_conn.cursor() as cur:
        cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
    pg_conn.commit()


def create_pg_table(pg_conn, table: str, columns: list, schema: str = "public"):
    """Create PostgreSQL table from SQLite schema (simplified - no constraints)."""
    col_defs = []
    for c in columns:
        # PRAGMA table_info returns (cid, name, type, notnull, dflt_value, pk)
        cid, name, typ, notnull, dflt_value, pk = c
        pg_type = map_sqlite_type(typ)
        nn = " NOT NULL" if notnull else ""
        col_defs.append(f'  "{name}" {pg_type}{nn}')
    cols_sql = ",\n".join(col_defs)
    q = quote_schema_table(schema, table)
    with pg_conn.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS {q} CASCADE")
        cur.execute(f"CREATE TABLE {q} (\n{cols_sql}\n)")
    pg_conn.commit()


def get_pg_columns(pg_conn, table: str, schema: str = "public") -> list:
    """Return list of column names in PostgreSQL table (in ordinal order)."""
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
            """,
            (schema, table),
        )
        return [(r[0], r[1], r[2] == "NO") for r in cur.fetchall()]


def get_pg_columns_simple(pg_conn, table: str, schema: str = "public") -> list:
    """Return list of column names only."""
    return [c[0] for c in get_pg_columns(pg_conn, table, schema)]


def default_for_not_null(data_type: str):
    """Return a default value for NOT NULL column when source has NULL."""
    if not data_type:
        return ""
    t = data_type.upper()
    if "INT" in t or "NUMERIC" in t or "DECIMAL" in t or "SERIAL" in t:
        return 0
    if "BOOL" in t:
        return False
    if "DATE" in t or "TIME" in t or "STAMP" in t:
        return "1970-01-01 00:00:00"  # Sentinel for timestamp/date
    return ""  # TEXT, VARCHAR, CHAR, etc.


def copy_table(sq_conn: sqlite3.Connection, pg_conn, table: str, schema: str = "public", batch_size: int = 1000, fill_not_null: bool = False):
    """Copy all rows from SQLite table to PostgreSQL."""
    sq_columns = get_table_info(sq_conn, table)
    sq_col_names = [c[1] for c in sq_columns]
    sq_col_index = {name: i for i, name in enumerate(sq_col_names)}

    # Use only columns that exist in both SQLite and PostgreSQL
    pg_cols = get_pg_columns(pg_conn, table, schema)  # (name, data_type, is_not_null)
    pg_col_names = [c[0] for c in pg_cols]
    pg_notnull = {c[0]: (c[1], c[2]) for c in pg_cols}  # name -> (data_type, is_not_null)
    common_cols = [c for c in pg_col_names if c in sq_col_index]
    if not common_cols:
        raise ValueError(
            f"No common columns between SQLite and PostgreSQL for table {table}. "
            f"SQLite: {sq_col_names}, PostgreSQL: {pg_col_names}"
        )

    # When fill_not_null: include NOT NULL columns we don't have, with defaults
    if fill_not_null:
        insert_cols = [c for c in pg_col_names if c in common_cols or pg_notnull.get(c, (None, False))[1]]
    else:
        insert_cols = common_cols

    if set(common_cols) != set(pg_col_names):
        missing_in_sq = set(pg_col_names) - set(common_cols)
        extra_in_sq = set(sq_col_names) - set(common_cols)
        if missing_in_sq or extra_in_sq:
            print(f"    Note: Using {len(insert_cols)}/{len(pg_col_names)} columns (missing in SQLite: {missing_in_sq or 'none'}, extra in SQLite: {extra_in_sq or 'none'})")

    cols_quoted = ", ".join(f'"{c}"' for c in insert_cols)
    placeholders = ", ".join(["%s"] * len(insert_cols))
    q = quote_schema_table(schema, table)
    insert_sql = f"INSERT INTO {q} ({cols_quoted}) VALUES ({placeholders})"

    sq_cols_sel = ", ".join(f'"{c}"' for c in common_cols)
    sq_cur = sq_conn.execute(f'SELECT {sq_cols_sel} FROM "{table}"')
    rows = sq_cur.fetchall()
    if not rows:
        return 0

    with pg_conn.cursor() as pg_cur:
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            clean = []
            for row in batch:
                out = []
                for col in insert_cols:
                    if col in common_cols:
                        j = common_cols.index(col)
                        v = row[j] if j < len(row) else None
                    else:
                        v = None
                    if v is not None and isinstance(v, bytes):
                        v = v.decode("utf-8", errors="replace")
                    # Fill NULL for NOT NULL columns when fill_not_null is enabled
                    if v is None and (fill_not_null or col not in common_cols) and pg_notnull.get(col, (None, False))[1]:
                        v = default_for_not_null(pg_notnull[col][0])
                    out.append(v)
                clean.append(tuple(out))
            pg_cur.executemany(insert_sql, clean)
    pg_conn.commit()
    return len(rows)


def main():
    ap = argparse.ArgumentParser(description="Load SQLite data into PostgreSQL")
    ap.add_argument("sqlite_path", type=str, help="Path to SQLite database file")
    ap.add_argument("--pg-host", default=os.getenv("PG_HOST", "localhost"), help="PostgreSQL host")
    ap.add_argument("--pg-port", type=int, default=int(os.getenv("PG_PORT", "5432")), help="PostgreSQL port")
    ap.add_argument("--pg-db", default=os.getenv("PG_DB", "customer_orders_and_reviews_db"), help="PostgreSQL database")
    ap.add_argument("--pg-user", default=os.getenv("PG_USER", "postgres"), help="PostgreSQL user")
    ap.add_argument("--pg-password", default=os.getenv("PG_PASS", "postgres"), help="PostgreSQL password")
    ap.add_argument("--pg-schema", default="public", help="PostgreSQL schema")
    ap.add_argument("--recreate-tables", action="store_true", help="Drop and create tables (uses SQLite schema, not init.sql)")
    ap.add_argument("--tables", type=str, default="", help="Comma-separated table names to load only (default: all)")
    ap.add_argument("--skip-create", action="store_true", help="Skip table creation; assume tables exist (e.g. from init.sql)")
    ap.add_argument("--fill-not-null", action="store_true", help="Fill NOT NULL columns with defaults when source has NULL (for schema mismatch)")
    args = ap.parse_args()

    if not os.path.exists(args.sqlite_path):
        print(f"Error: SQLite file not found: {args.sqlite_path}")
        sys.exit(1)

    print(f"Connecting to SQLite: {args.sqlite_path}")
    sq_conn = sqlite3.connect(args.sqlite_path)
    sq_conn.row_factory = sqlite3.Row

    print(f"Connecting to PostgreSQL: {args.pg_host}:{args.pg_port}/{args.pg_db}")
    try:
        pg_conn = psycopg2.connect(
            host=args.pg_host,
            port=args.pg_port,
            dbname=args.pg_db,
            user=args.pg_user,
            password=args.pg_password,
        )
        pg_conn.autocommit = False
    except Exception as e:
        print(f"PostgreSQL connection failed: {e}")
        sys.exit(1)

    tables = get_tables(sq_conn)
    if args.tables:
        want = {t.strip() for t in args.tables.split(",") if t.strip()}
        tables = [t for t in tables if t in want]
        missing = want - set(tables)
        if missing:
            print(f"Warning: Tables not found in SQLite: {missing}")

    if not tables:
        print("No tables to load.")
        sq_conn.close()
        pg_conn.close()
        return

    # Create schema if not public (handles names with hyphens like sql-e-commerce)
    if args.pg_schema != "public":
        print(f"Creating schema '{args.pg_schema}' if not exists...")
        create_pg_schema(pg_conn, args.pg_schema)

    # Load in FK order to satisfy references
    load_order = infer_fk_order(sq_conn, tables)
    print(f"Tables to load (in order): {load_order}")

    for table in load_order:
        cols = get_table_info(sq_conn, table)
        if args.recreate_tables:
            print(f"  Creating table {table}...")
            create_pg_table(pg_conn, table, cols, args.pg_schema)
        elif not args.skip_create:
            # Check if table exists
            with pg_conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = %s AND table_name = %s
                    """,
                    (args.pg_schema, table),
                )
                if not cur.fetchone():
                    print(f"  Table {table} does not exist. Creating...")
                    create_pg_table(pg_conn, table, cols, args.pg_schema)

        n = copy_table(sq_conn, pg_conn, table, args.pg_schema, fill_not_null=args.fill_not_null)
        print(f"  Loaded {table}: {n} rows")

    sq_conn.close()
    pg_conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
