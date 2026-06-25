import os
import sqlite3
from typing import Any

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "lore_vault.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Create tables
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS entities (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        type TEXT NOT NULL,
        summary TEXT,
        content TEXT,
        path TEXT NOT NULL,
        last_modified REAL DEFAULT 0
    )
    """)

    # Run migration if table exists but last_modified column is missing
    cursor.execute("PRAGMA table_info(entities)")
    columns = [row["name"] for row in cursor.fetchall()]
    if "last_modified" not in columns:
        cursor.execute("ALTER TABLE entities ADD COLUMN last_modified REAL DEFAULT 0")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS metadata (
        entity_id TEXT,
        key TEXT,
        value TEXT,
        PRIMARY KEY (entity_id, key),
        FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS links (
        source_id TEXT,
        target_id TEXT,
        link_type TEXT,
        PRIMARY KEY (source_id, target_id),
        FOREIGN KEY (source_id) REFERENCES entities(id) ON DELETE CASCADE
    )
    """)

    conn.commit()
    conn.close()

def clear_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM links")
    cursor.execute("DELETE FROM metadata")
    cursor.execute("DELETE FROM entities")
    conn.commit()
    conn.close()

def insert_entity(id_: str, name: str, type_: str, summary: str, content: str, path: str, last_modified: float):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO entities (id, name, type, summary, content, path, last_modified) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (id_, name, type_, summary, content, path, last_modified)
    )
    conn.commit()
    conn.close()

def insert_metadata(entity_id: str, key: str, value: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO metadata (entity_id, key, value) VALUES (?, ?, ?)",
        (entity_id, key, value)
    )
    conn.commit()
    conn.close()

def insert_link(source_id: str, target_id: str, link_type: str = "wiki"):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO links (source_id, target_id, link_type) VALUES (?, ?, ?)",
        (source_id, target_id, link_type)
    )
    conn.commit()
    conn.close()

def get_all_entities() -> list[dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM entities")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_entity(entity_id: str) -> dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM entities WHERE id = ?", (entity_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_metadata(entity_id: str) -> dict[str, str]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM metadata WHERE entity_id = ?", (entity_id,))
    rows = cursor.fetchall()
    conn.close()
    return {row["key"]: row["value"] for row in rows}

def get_links() -> list[tuple[str, str, str]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT source_id, target_id, link_type FROM links")
    rows = cursor.fetchall()
    conn.close()
    return [(row["source_id"], row["target_id"], row["link_type"]) for row in rows]
