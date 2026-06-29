import pytest
from app.wizard_generators import generate_suggested_fields

def test_generate_suggested_fields_character():
    fields = generate_suggested_fields("Character")
    
    assert fields["entity_type"] == "Character"
    assert fields["name"] != ""
    assert fields["age"] != ""
    assert fields["status"] in ("Alive", "Deceased", "Unknown")
    assert fields["species"].startswith("[[") and fields["species"].endswith("]]")
    assert isinstance(fields["faction_affiliations"], list)
    if fields["current_location"] is not None:
        assert fields["current_location"].startswith("[[") and fields["current_location"].endswith("]]")

def test_generate_suggested_fields_location():
    fields = generate_suggested_fields("Location")
    
    assert fields["entity_type"] == "Location"
    assert fields["name"] != ""
    if fields["region"] is not None:
        assert fields["region"].startswith("[[") and fields["region"].endswith("]]")
    if fields["controlling_faction"] is not None:
        assert fields["controlling_faction"].startswith("[[") and fields["controlling_faction"].endswith("]]")

def test_generate_suggested_fields_item():
    fields = generate_suggested_fields("Item")
    
    assert fields["entity_type"] == "Item"
    assert fields["name"] != ""
    if fields["creator"] is not None:
        assert fields["creator"].startswith("[[") and fields["creator"].endswith("]]")
    if fields["current_owner"] is not None:
        assert fields["current_owner"].startswith("[[") and fields["current_owner"].endswith("]]")

def test_generate_suggested_fields_invalid_type():
    with pytest.raises(ValueError):
        generate_suggested_fields("Spaceship")
