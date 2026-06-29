import os
import pytest
from app.parser import parse_frontmatter, extract_wiki_links, extract_all_wiki_links, parse_markdown_file

def test_parse_frontmatter_single_wikilink():
    content = """---
name: Orion
species: [[Elves]]
current_location: [[Oakhaven Town]]
---
Orion lives in [[Oakhaven Town]]."""
    meta, body = parse_frontmatter(content)
    
    assert meta["name"] == "Orion"
    assert meta["species"] == "[[Elves]]"
    assert meta["current_location"] == "[[Oakhaven Town]]"
    assert "lives in" in body

def test_parse_frontmatter_list():
    content = """---
name: Liam
faction_affiliations: ["[[The Bloodrunners]]", "[[Iron Guild]]"]
aliases: ["Liam", "The Bear"]
---
A blacksmith."""
    meta, body = parse_frontmatter(content)
    
    assert meta["name"] == "Liam"
    assert isinstance(meta["faction_affiliations"], list)
    assert meta["faction_affiliations"] == ["[[The Bloodrunners]]", "[[Iron Guild]]"]
    assert meta["aliases"] == ["Liam", "The Bear"]

def test_extract_wiki_links():
    body = "Orion met [[Liam the Blacksmith]] at [[The Rusty Anvil Tavern|The Tavern]]."
    links = extract_wiki_links(body)
    
    assert "Liam the Blacksmith" in links
    assert "The Rusty Anvil Tavern" in links
    assert len(links) == 2

def test_extract_all_wiki_links():
    draft = {
        "name": "Orion",
        "entity_type": "Character",
        "species": "[[Elves]]",
        "faction_affiliations": ["[[The Bloodrunners]]"],
        "content": "Lives in [[Oakhaven Town]] with [[Sarah]]."
    }
    
    links = extract_all_wiki_links(draft)
    assert "Elves" in links
    assert "The Bloodrunners" in links
    assert "Oakhaven Town" in links
    assert "Sarah" in links
    assert len(links) == 4

def test_parse_markdown_file(tmp_path):
    vault_dir = tmp_path / "Obsidian"
    vault_dir.mkdir()
    file_path = vault_dir / "Orion.md"
    
    markdown_content = """---
name: Orion
entity_type: Character
species: [[Elves]]
faction_affiliations: ["[[The Bloodrunners]]"]
summary: An elven sorcerer.
---
Orion is learning [[Aetheric Magic]]."""
    
    file_path.write_text(markdown_content, encoding="utf-8")
    
    parsed = parse_markdown_file(str(file_path))
    assert parsed["name"] == "Orion"
    assert parsed["entity_type"] == "Character"
    assert parsed["summary"] == "An elven sorcerer."
    assert "Elves" in parsed["links"]
    assert "The Bloodrunners" in parsed["links"]
    assert "Aetheric Magic" in parsed["links"]
    assert len(parsed["links"]) == 3
