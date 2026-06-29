import pytest
import sqlite3
from app.database import (
    get_db_connection, init_db, insert_entity, insert_edge, 
    insert_name_index, get_entity, get_all_entities, delete_entity
)

def test_database_init():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r["name"] for r in cursor.fetchall()]
    conn.close()
    
    assert "entities" in tables
    assert "edges" in tables
    assert "name_index" in tables
    assert "memberships" in tables
    assert "containment" in tables

def test_insert_and_get_entity():
    insert_entity(
        name="Sarah",
        entity_type="Character",
        summary="A rogue elf.",
        raw_markdown="---\nname: Sarah\n---",
        metadata={"age": 120}
    )
    
    entity = get_entity("Sarah")
    assert entity is not None
    assert entity["name"] == "Sarah"
    assert entity["entity_type"] == "Character"
    assert entity["summary"] == "A rogue elf."
    assert entity["metadata"]["age"] == 120

def test_insert_entity_on_conflict_update():
    # Insert initially
    insert_entity(
        name="Elves",
        entity_type="Species",
        summary="Long lived species.",
        raw_markdown="",
        metadata={"lifespan": 1000}
    )
    
    # Save a character linking to Elves to create an incoming edge
    insert_entity("Orion", "Character", "An elven wizard.", "", {"species": "[[Elves]]"})
    insert_edge("Orion", "Elves", "wikilink", 1)
    
    # Verify edge exists
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM edges WHERE target_name = 'Elves'")
    assert cursor.fetchone()[0] == 1
    
    # Update Elves (triggering insert_entity again)
    insert_entity(
        name="Elves",
        entity_type="Species",
        summary="Long lived fey species.",
        raw_markdown="Updated markdown",
        metadata={"lifespan": 1200}
    )
    
    # Verify Elves updated correctly
    entity = get_entity("Elves")
    assert entity["summary"] == "Long lived fey species."
    assert entity["metadata"]["lifespan"] == 1200
    
    # CRITICAL: Verify incoming connection was NOT deleted by cascade!
    cursor.execute("SELECT count(*) FROM edges WHERE target_name = 'Elves'")
    count = cursor.fetchone()[0]
    conn.close()
    
    assert count == 1, "Incoming link was deleted due to INSERT OR REPLACE cascade bug!"

def test_delete_entity():
    insert_entity("Drakath", "Character", "Mercenary leader.", "", {})
    assert get_entity("Drakath") is not None
    
    delete_entity("Drakath")
    assert get_entity("Drakath") is None

def test_memberships_and_containment():
    # Insert required foreign keys
    insert_entity("Sarah", "Character", "", "", {})
    insert_entity("The Bloodrunners", "Faction", "", "", {})
    insert_entity("Bloodlust Warhammer", "Item", "", "", {})
    insert_entity("Oakhaven Town", "Location", "", "", {})
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Insert Membership
    cursor.execute("INSERT INTO memberships (entity_name, faction_name, role) VALUES (?, ?, ?)", ("Sarah", "The Bloodrunners", "Member"))
    
    # Insert Containment
    cursor.execute("INSERT INTO containment (item_name, location_name) VALUES (?, ?)", ("Bloodlust Warhammer", "Oakhaven Town"))
    conn.commit()
    
    # Query membership
    cursor.execute("SELECT faction_name FROM memberships WHERE entity_name = ?", ("Sarah",))
    faction = cursor.fetchone()["faction_name"]
    assert faction == "The Bloodrunners"
    
    # Query containment
    cursor.execute("SELECT location_name FROM containment WHERE item_name = ?", ("Bloodlust Warhammer",))
    location = cursor.fetchone()["location_name"]
    assert location == "Oakhaven Town"
    
    conn.close()
