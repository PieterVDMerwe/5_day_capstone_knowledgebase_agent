import os
import sqlite3
from typing import Any
import json

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "lore_vault.db")

def get_db_connection():
    """
    Returns a connection to the SQLite database.
    Enforces WAL mode, Foreign Keys, and uses sqlite3.Row for dict-like rows.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    """Initializes the database schema with the new graph-relational tables."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Create entities table (name is PK)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS entities (
        name TEXT PRIMARY KEY,
        entity_type TEXT NOT NULL,
        summary TEXT,
        raw_markdown TEXT,
        metadata JSON
    )
    """)

    # Create edges table (directed graph)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS edges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_name TEXT NOT NULL,
        target_name TEXT NOT NULL,
        relation_type TEXT,
        weight INTEGER DEFAULT 1,
        FOREIGN KEY (source_name) REFERENCES entities(name) ON DELETE CASCADE,
        FOREIGN KEY (target_name) REFERENCES entities(name) ON DELETE CASCADE
    )
    """)

    # Create genealogy table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS genealogy (
        parent_name TEXT NOT NULL,
        child_name TEXT NOT NULL,
        PRIMARY KEY (parent_name, child_name),
        FOREIGN KEY (parent_name) REFERENCES entities(name) ON DELETE CASCADE,
        FOREIGN KEY (child_name) REFERENCES entities(name) ON DELETE CASCADE
    )
    """)

    # Create memberships table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS memberships (
        entity_name TEXT NOT NULL,
        faction_name TEXT NOT NULL,
        role TEXT,
        PRIMARY KEY (entity_name, faction_name),
        FOREIGN KEY (entity_name) REFERENCES entities(name) ON DELETE CASCADE,
        FOREIGN KEY (faction_name) REFERENCES entities(name) ON DELETE CASCADE
    )
    """)

    # Create containment table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS containment (
        item_name TEXT NOT NULL,
        location_name TEXT NOT NULL,
        PRIMARY KEY (item_name, location_name),
        FOREIGN KEY (item_name) REFERENCES entities(name) ON DELETE CASCADE,
        FOREIGN KEY (location_name) REFERENCES entities(name) ON DELETE CASCADE
    )
    """)

    # Create name_index table for typo detection
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS name_index (
        original_name TEXT PRIMARY KEY,
        phonetic_hash TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()

def clear_db():
    """Wipes all data from the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM name_index")
    cursor.execute("DELETE FROM containment")
    cursor.execute("DELETE FROM memberships")
    cursor.execute("DELETE FROM genealogy")
    cursor.execute("DELETE FROM edges")
    cursor.execute("DELETE FROM entities")
    conn.commit()
    conn.close()

# Basic CRUD Operations
def insert_entity(name: str, entity_type: str, summary: str, raw_markdown: str, metadata: dict):
    """Inserts or replaces an entity."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO entities (name, entity_type, summary, raw_markdown, metadata) VALUES (?, ?, ?, ?, ?)",
        (name, entity_type, summary, raw_markdown, json.dumps(metadata) if metadata else "{}")
    )
    conn.commit()
    conn.close()

def delete_entity(name: str):
    """Deletes an entity and its associated data."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM name_index WHERE original_name = ?", (name,))
    cursor.execute("DELETE FROM entities WHERE name = ?", (name,))
    conn.commit()
    conn.close()

def insert_edge(source_name: str, target_name: str, relation_type: str, weight: int = 1):
    """Inserts a directed edge between two entities."""
    conn = get_db_connection()
    cursor = conn.cursor()
    # Ensure foreign keys exist before inserting to avoid constraint failure
    # (In practice, parser will insert entities first)
    cursor.execute(
        "INSERT INTO edges (source_name, target_name, relation_type, weight) VALUES (?, ?, ?, ?)",
        (source_name, target_name, relation_type, weight)
    )
    conn.commit()
    conn.close()

def insert_name_index(original_name: str, phonetic_hash: str):
    """Inserts a phonetic hash into the name index."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO name_index (original_name, phonetic_hash) VALUES (?, ?)",
        (original_name, phonetic_hash)
    )
    conn.commit()
    conn.close()

def get_entity(name: str) -> dict[str, Any]:
    """Retrieves an entity by name."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM entities WHERE name = ?", (name,))
    row = cursor.fetchone()
    conn.close()
    if row:
        res = dict(row)
        if res.get("metadata"):
            res["metadata"] = json.loads(res["metadata"])
        return res
    return None

def get_all_entities() -> list[dict[str, Any]]:
    """Retrieves all entities."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM entities")
    rows = cursor.fetchall()
    conn.close()
    result = []
    for row in rows:
        d = dict(row)
        if d.get("metadata"):
            d["metadata"] = json.loads(d["metadata"])
        result.append(d)
    return result
