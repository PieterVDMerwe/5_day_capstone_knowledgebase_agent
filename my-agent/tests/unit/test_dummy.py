from app.database import clear_db, init_db, insert_entity, insert_link, insert_metadata
from app.parser import extract_wiki_links, normalize_entity_id, parse_frontmatter
from app.validators import run_all_validators

def test_normalize_entity_id():
    assert normalize_entity_id("Garrett the Woodsman") == "garrett_the_woodsman"
    assert normalize_entity_id("Oakhaven Town.md") == "oakhaven_town"

def test_parse_frontmatter():
    content = """---
name: "Garrett the Woodsman"
type: "character"
birth_year: "1230"
---
Garrett is a weathered tracker who stops by [[The Rusty Anvil Tavern]]."""
    meta, body = parse_frontmatter(content)
    assert meta["name"] == "Garrett the Woodsman"
    assert meta["type"] == "character"
    assert meta["birth_year"] == "1230"
    assert "weathered tracker" in body

def test_extract_wiki_links():
    body = "He lives in [[Oakhaven Town]] and visits [[The Rusty Anvil Tavern|The Tavern]]."
    links = extract_wiki_links(body)
    assert "oakhaven_town" in links
    assert "the_rusty_anvil_tavern" in links

def test_static_validators_mocked():
    # Setup test DB
    init_db()
    clear_db()

    # Insert dummy location
    insert_entity("oakhaven_town", "Oakhaven Town", "location", "A quiet town", "Oakhaven is peaceful.", "test_path.md", 0.0)
    insert_metadata("oakhaven_town", "region", "The Wildlands")
    insert_metadata("oakhaven_town", "place_type", "town")

    # Insert character with timeline error (death before birth)
    insert_entity("bad_character", "Bad Character", "character", "A broken timeline", "He was a legend.", "test_path2.md", 0.0)
    insert_metadata("bad_character", "birth_year", "1250")
    insert_metadata("bad_character", "death_year", "1240") # Chronological error
    insert_metadata("bad_character", "status", "deceased")
    insert_metadata("bad_character", "location", "oakhaven_town")
    insert_metadata("bad_character", "age", "10")

    # Link pointing to non-existent note (broken link)
    insert_link("bad_character", "missing_entity")

    issues = run_all_validators()

    # We expect a timeline issue and a link integrity issue
    issue_types = {issue["type"] for issue in issues}
    assert "timeline" in issue_types
    assert "link_integrity" in issue_types

def test_fantasy_lifespans_and_item_schema():
    init_db()
    clear_db()

    # 1. Human character with long lifespan (800 years) -> Should trigger warning
    insert_entity("old_human", "Old Human", "character", "Very old", "He lived long.", "human.md", 0.0)
    insert_metadata("old_human", "status", "deceased")
    insert_metadata("old_human", "location", "unknown")
    insert_metadata("old_human", "age", "unknown")
    insert_metadata("old_human", "species", "human")
    insert_metadata("old_human", "birth_year", "1000")
    insert_metadata("old_human", "death_year", "1800") # 800 years lifespan

    # 2. Elf character with long lifespan (800 years) -> Should NOT trigger warning (allowed up to 1000)
    insert_entity("old_elf", "Old Elf", "character", "Elf lord", "He lived long.", "elf.md", 0.0)
    insert_metadata("old_elf", "status", "deceased")
    insert_metadata("old_elf", "location", "unknown")
    insert_metadata("old_elf", "age", "unknown")
    insert_metadata("old_elf", "species", "elf")
    insert_metadata("old_elf", "birth_year", "1000")
    insert_metadata("old_elf", "death_year", "1800")

    issues = run_all_validators()
    
    # We expect a warning for the old human, but not for the old elf
    human_warnings = [iss for iss in issues if iss["entity_id"] == "old_human" and iss["type"] == "timeline"]
    elf_warnings = [iss for iss in issues if iss["entity_id"] == "old_elf" and iss["type"] == "timeline"]
    
    assert len(human_warnings) > 0
    assert len(elf_warnings) == 0

def test_unrecognized_entity_type_and_negative_age():
    init_db()
    clear_db()

    # 1. Unrecognized type
    insert_entity("unknown_type", "Mysterious Orb", "relic", "An ancient relic", "Glowing orb.", "relic.md", 0.0)

    # 2. Negative age
    insert_entity("young_dwarf", "Gimli", "character", "Dwarf warrior", "Axeman.", "dwarf.md", 0.0)
    insert_metadata("young_dwarf", "status", "active")
    insert_metadata("young_dwarf", "location", "unknown")
    insert_metadata("young_dwarf", "age", "-5")

    issues = run_all_validators()
    issue_msgs = [iss["message"] for iss in issues]
    
    assert any("has unrecognized type 'relic'" in msg for msg in issue_msgs)
    assert any("has negative age value: -5" in msg for msg in issue_msgs)

def test_cross_references_validation():
    init_db()
    clear_db()

    # Character referencing missing location and faction
    insert_entity("bilbo", "Bilbo", "character", "Hobbit", "Adventurer.", "bilbo.md", 0.0)
    insert_metadata("bilbo", "status", "active")
    insert_metadata("bilbo", "age", "111")
    insert_metadata("bilbo", "location", "The Shire") # Missing Location note
    insert_metadata("bilbo", "faction", "Fellowship") # Missing Faction note

    # Faction referencing missing headquarters and leader
    insert_entity("guild", "Guild of Crafters", "faction", "Craft guild", "Builders.", "guild.md", 0.0)
    insert_metadata("guild", "headquarters", "Oakhaven Town") # Missing Location note
    insert_metadata("guild", "leader", "Liam the Blacksmith") # Missing Character note

    issues = run_all_validators()
    issue_msgs = [iss["message"] for iss in issues]

    assert any("references location 'The Shire', but that Location note does not exist." in msg for msg in issue_msgs)
    assert any("references faction 'Fellowship', but that Faction note does not exist." in msg for msg in issue_msgs)
    assert any("headquarters 'Oakhaven Town' does not exist as a Location note." in msg for msg in issue_msgs)
    assert any("leader 'Liam the Blacksmith' does not exist as a Character note." in msg for msg in issue_msgs)

def test_fuzzy_name_duplicates():
    init_db()
    clear_db()

    # Add two characters with highly similar names (typo scenario)
    insert_entity("eldrin_wise", "Eldrin the Wise", "character", "Wizard", "An old wizard.", "eldrin.md", 0.0)
    insert_entity("eldren_wise", "Eldren the Wise", "character", "Wizard typo", "An old wizard.", "eldren.md", 0.0)

    issues = run_all_validators()
    issue_types = {iss["type"] for iss in issues}
    assert "duplicate_name" in issue_types

def test_name_generator():
    from app.agent import generate_random_name
    
    char_names = generate_random_name("character", "elf")
    assert "Generated Character Names:" in char_names
    assert len(char_names.split(",")) == 5

    loc_names = generate_random_name("location", "dark")
    assert "Generated Location Names:" in loc_names

    item_names = generate_random_name("item")
    assert "Generated Item Names:" in item_names

    faction_names = generate_random_name("faction")
    assert "Generated Faction Names:" in faction_names

    error_msg = generate_random_name("invalid_type")
    assert "Error: Unknown entity_type" in error_msg
