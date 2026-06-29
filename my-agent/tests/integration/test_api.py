import json
import pytest
from fastapi.testclient import TestClient
from main import app
from app.database import get_entity, get_db_connection

client = TestClient(app)

def test_api_chat_direct_llm(mock_llm_client):
    mock_llm_client.return_value = "This is a direct response."
    
    payload = {
        "user_message": "Hello LLM",
        "chat_mode": "direct_llm"
    }
    
    res = client.post("/api/chat", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["data"]["answer"] == "This is a direct response."
    assert data["data"]["route"] == "direct_llm"

def test_api_chat_lore_base(mock_llm_client):
    mock_llm_client.return_value = "This is a RAG response."
    
    payload = {
        "user_message": "Tell me about Oakhaven",
        "chat_mode": "lore_base"
    }
    
    res = client.post("/api/chat", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["data"]["answer"] == "This is a RAG response."
    assert data["data"]["route"] == "lore_base"

def test_api_save_endpoint_success(mock_llm_client):
    # Mock Truth Keeper validation to succeed (must return string containing "valid" or "no inconsistencies")
    mock_llm_client.return_value = "The draft is logically valid."
    
    payload = {
        "draft_state": {
            "name": "Sarah the Rogue",
            "entity_type": "Character",
            "summary": "A friendly rogue.",
            "age": "25",
            "status": "Alive",
            "species": "[[Elves]]",
            "faction_affiliations": ["[[The Bloodrunners]]"],
            "current_location": "[[Oakhaven Town]]"
        }
    }
    
    res = client.post("/api/save", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "successfully saved" in data["message"]
    
    # Verify entity is in the test database
    entity = get_entity("Sarah the Rogue")
    assert entity is not None
    assert entity["entity_type"] == "Character"

def test_api_save_endpoint_with_incoming_connection_removal(mock_llm_client):
    # Mock Truth Keeper
    mock_llm_client.return_value = "Valid"
    
    # 1. Save Liam to create base node
    client.post("/api/save", json={
        "draft_state": {
            "name": "Liam the Blacksmith",
            "entity_type": "Character",
            "summary": "Blacksmith",
            "species": "[[Human]]"
        }
    })
    
    # 2. Save Sarah linking to Liam
    client.post("/api/save", json={
        "draft_state": {
            "name": "Sarah",
            "entity_type": "Character",
            "summary": "Rogue",
            "species": "[[Elves]]",
            "faction_affiliations": ["[[The Bloodrunners]]"]
        }
    })
    
    # Create relationship manually in DB
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO edges (source_name, target_name, relation_type, weight) VALUES ('Sarah', 'Liam the Blacksmith', 'wikilink', 1)")
    conn.commit()
    
    # Verify connection exists
    cursor.execute("SELECT count(*) FROM edges WHERE source_name = 'Sarah' AND target_name = 'Liam the Blacksmith'")
    assert cursor.fetchone()[0] == 1
    
    # 3. Save Liam requesting to remove connection from Sarah
    payload = {
        "draft_state": {
            "name": "Liam the Blacksmith",
            "entity_type": "Character",
            "summary": "Blacksmith",
            "species": "[[Human]]"
        },
        "connections_to_remove": ["Sarah"]
    }
    
    res = client.post("/api/save", json=payload)
    assert res.status_code == 200
    
    # Verify connection is deleted
    cursor.execute("SELECT count(*) FROM edges WHERE source_name = 'Sarah' AND target_name = 'Liam the Blacksmith'")
    count = cursor.fetchone()[0]
    conn.close()
    
    assert count == 0

def test_api_wizard_suggest():
    res = client.get("/api/wizard/suggest?entity_type=Character")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "age" in data["data"]
    assert "species" in data["data"]

def test_api_wizard_generate_content(mock_llm_client):
    mock_llm_client.return_value = '{"summary": "A local faction.", "content": "The guild represents woodcutters."}'
    
    payload = {
        "draft_state": {
            "name": "Woodcutters Guild",
            "entity_type": "Faction",
            "goals": ["Timber harvesting"]
        }
    }
    
    res = client.post("/api/wizard/generate-content", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["data"]["summary"] == "A local faction."
    assert "woodcutters" in data["data"]["content"]

def test_api_delete_entity(mock_llm_client):
    mock_llm_client.return_value = "Valid"
    
    # 1. Save an entity to create the file and DB entry
    client.post("/api/save", json={
        "draft_state": {
            "name": "TargetToDelete",
            "entity_type": "Character",
            "summary": "Target"
        }
    })
    
    assert get_entity("TargetToDelete") is not None
    
    # Verify file is created
    from app.file_writer import VAULT_DIR
    import os
    filepath = os.path.join(VAULT_DIR, "TargetToDelete.md")
    assert os.path.exists(filepath)
    
    # 2. Delete it via the API
    res = client.delete("/api/entity/TargetToDelete")
    assert res.status_code == 200
    assert res.json()["status"] == "success"
    
    # 3. Verify it is deleted from both DB and file system
    assert get_entity("TargetToDelete") is None
    assert not os.path.exists(filepath)
