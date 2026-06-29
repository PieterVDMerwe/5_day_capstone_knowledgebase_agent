import pytest
from app.validators import validate_entity_data, ensure_wikilinks_in_metadata

def test_validate_entity_data_valid_character():
    data = {
        "name": "Liam the Blacksmith",
        "entity_type": "Character",
        "summary": "A gruff blacksmith.",
        "age": "42",
        "status": "Alive",
        "species": "[[Human]]",
        "faction_affiliations": ["[[Iron Guild]]"],
        "current_location": "[[Oakhaven Town]]",
        "physical_description": "Strong build.",
        "personality_traits": ["Gruff", "Loyal"]
    }
    
    is_valid, cleaned, msg = validate_entity_data(data)
    assert is_valid
    assert cleaned["name"] == "Liam the Blacksmith"
    assert cleaned["age"] == "42"
    assert cleaned["status"] == "Alive"

def test_validate_entity_data_fuzzy_enum_correction():
    data = {
        "name": "Sarah",
        "entity_type": "Character",
        "summary": "A rogue.",
        "status": "Alivee", # Typos in enum
        "species": "[[Elves]]"
    }
    
    is_valid, cleaned, msg = validate_entity_data(data)
    assert is_valid
    assert cleaned["status"] == "Alive", "Fuzzy enum mapping failed to correct 'Alivee' to 'Alive'"

def test_validate_entity_data_type_mismatch_correction():
    data = {
        "name": "Drakath",
        "entity_type": "Character",
        "summary": "Leader.",
        "species": ["[[Human]]"], # List instead of string
        "faction_affiliations": "[[The Bloodrunners]]", # String instead of list
    }
    
    is_valid, cleaned, msg = validate_entity_data(data)
    assert is_valid
    assert cleaned["species"] == "[[Human]]"
    assert cleaned["faction_affiliations"] == ["[[The Bloodrunners]]"]

def test_ensure_wikilinks_in_metadata_auto_wrapping():
    # 1. Plain text -> Wrapped
    data = {
        "entity_type": "Character",
        "species": "Elves",
        "faction_affiliations": ["The Bloodrunners", "[[Iron Guild]]"],
        "current_location": "[[Oakhaven Town]" # Malformed
    }
    
    cleaned = ensure_wikilinks_in_metadata(data)
    assert cleaned["species"] == "[[Elves]]"
    assert cleaned["faction_affiliations"] == ["[[The Bloodrunners]]", "[[Iron Guild]]"]
    assert cleaned["current_location"] == "[[Oakhaven Town]]"

def test_ensure_wikilinks_in_metadata_non_relationships():
    data = {
        "entity_type": "Character",
        "name": "Liam the Blacksmith",
        "summary": "A friendly blacksmith.",
        "physical_description": "Big arms.",
        "personality_traits": ["Kind", "Strong"]
    }
    
    cleaned = ensure_wikilinks_in_metadata(data)
    # Ensure they are NOT wrapped!
    assert cleaned["name"] == "Liam the Blacksmith"
    assert cleaned["summary"] == "A friendly blacksmith."
    assert cleaned["physical_description"] == "Big arms."
    assert cleaned["personality_traits"] == ["Kind", "Strong"]
