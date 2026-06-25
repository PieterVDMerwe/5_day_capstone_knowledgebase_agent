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

    # Insert character with timeline error (death before birth)
    insert_entity("bad_character", "Bad Character", "character", "A broken timeline", "He was a legend.", "test_path2.md", 0.0)
    insert_metadata("bad_character", "birth_year", "1250")
    insert_metadata("bad_character", "death_year", "1240") # Chronological error
    insert_metadata("bad_character", "status", "deceased")
    insert_metadata("bad_character", "location", "oakhaven_town")

    # Link pointing to non-existent note (broken link)
    insert_link("bad_character", "missing_entity")

    issues = run_all_validators()

    # We expect a timeline issue and a link integrity issue
    issue_types = {issue["type"] for issue in issues}
    assert "timeline" in issue_types
    assert "link_integrity" in issue_types
