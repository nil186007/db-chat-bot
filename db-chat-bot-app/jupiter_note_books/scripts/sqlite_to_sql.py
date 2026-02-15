#!/usr/bin/env python3
"""
Export SQLite database to a PostgreSQL-compatible .sql file.
Use for Docker init: the generated file can be mounted to /docker-entrypoint-initdb.d/

Usage:
  python sqlite_to_sql.py path/to/database.db -o output.sql
  python sqlite_to_sql.py olist.sqlite -o ../../docker-setup/scripts/olist_load.sql --schema sql-e-commerce
"""
import argparse
import sqlite3
import os
import sys

# Reuse type mapping from sqlite_to_postgres logic
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
    t = (sqlite_type or "TEXT").upper().split("(")[0].strip()
    return SQLITE_TO_PG.get(t, "TEXT")


def get_tables(conn: sqlite3.Connection) -> list:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    return [r[0] for r in cur.fetchall()]


def get_table_info(conn: sqlite3.Connection, table: str) -> list:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return cur.fetchall()


def infer_fk_order(conn: sqlite3.Connection, tables: list) -> list:
    deps = {t: set() for t in tables}
    for t in tables:
        cur = conn.execute(f"PRAGMA foreign_key_list({t})")
        for row in cur.fetchall():
            ref_table = row[2]
            if ref_table in tables and ref_table != t:
                deps[t].add(ref_table)
    order = []
    remaining = set(tables)
    while remaining:
        ready = [t for t in remaining if not (deps[t] & remaining)]
        if not ready:
            order.extend(remaining)
            break
        order.extend(ready)
        remaining -= set(ready)
    return order


def pg_escape(val) -> str:
    """Escape value for PostgreSQL literal."""
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, bytes):
        val = val.decode("utf-8", errors="replace")
    s = str(val).replace("\\", "\\\\").replace("'", "''")
    return f"'{s}'"


def main():
    ap = argparse.ArgumentParser(description="Export SQLite to PostgreSQL .sql file")
    ap.add_argument("sqlite_path", type=str, help="Path to SQLite database")
    ap.add_argument("-o", "--output", type=str, required=True, help="Output .sql file path")
    ap.add_argument("--schema", default="sql-e-commerce", help="PostgreSQL schema name")
    args = ap.parse_args()

    if not os.path.exists(args.sqlite_path):
        print(f"Error: SQLite file not found: {args.sqlite_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(args.sqlite_path)
    conn.row_factory = sqlite3.Row

    tables = get_tables(conn)
    load_order = infer_fk_order(conn, tables)

    lines = [
        "-- Auto-generated from SQLite for PostgreSQL init",
        f"-- Schema: {args.schema}",
        "",
        f'CREATE SCHEMA IF NOT EXISTS "{args.schema}";',
        "",
    ]

    for table in load_order:
        cols = get_table_info(conn, table)
        col_names = [c[1] for c in cols]  # c[1] = name in (cid, name, type, notnull, dflt_value, pk)
        col_defs = []
        for c in cols:
            cid, name, typ, notnull, dflt_value, pk = c
            pg_type = map_sqlite_type(typ)
            nn = " NOT NULL" if notnull else ""
            col_defs.append(f'  "{name}" {pg_type}{nn}')
        q = f'"{args.schema}"."{table}"'
        lines.append(f'DROP TABLE IF EXISTS {q} CASCADE;')
        lines.append(f"CREATE TABLE {q} (")
        lines.append(",\n".join(col_defs))
        lines.append(");")
        lines.append("")

        cols_quoted = ", ".join(f'"{n}"' for n in col_names)
        cur = conn.execute(f'SELECT {cols_quoted} FROM "{table}"')
        rows = cur.fetchall()
        if rows:
            for row in rows:
                vals = ", ".join(pg_escape(v) for v in row)
                lines.append(f"INSERT INTO {q} ({cols_quoted}) VALUES ({vals});")
            lines.append("")

    conn.close()

    sql_content = "\n".join(lines)
    out_dir = os.path.dirname(os.path.abspath(args.output))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.output, "w") as f:
        f.write(sql_content)

    print(f"Wrote {args.output} ({len(load_order)} tables, {len(lines)} lines)")


if __name__ == "__main__":
    main()
