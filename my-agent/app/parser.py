import os
import re
import jellyfish
from typing import Any

from .database import (
    get_db_connection, init_db, insert_entity, insert_edge, insert_name_index
)

def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Parses frontmatter from a markdown string and returns (metadata_dict, body_content)."""
    meta = {}
    body = content

    match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n(.*)$", content, re.DOTALL)
    if match:
        frontmatter_text = match.group(1)
        body = match.group(2)

        for line in frontmatter_text.splitlines():
            if ":" not in line:
                continue
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip()

            if val.startswith("[") and val.endswith("]"):
                items = [item.strip().strip("'\"") for item in val[1:-1].split(",") if item.strip()]
                meta[key] = items
            elif (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                meta[key] = val[1:-1]
            else:
                meta[key] = val

    return meta, body

def extract_wiki_links(body: str) -> list[str]:
    """Finds all standard wiki links [[Link Target]] in the body."""
    links = []
    pattern = r"\[\[(.*?)\]\]"
    for match in re.finditer(pattern, body):
        target = match.group(1).split("|")[0].strip()
        if target:
            links.append(target)
    return links

def extract_all_wiki_links(draft: dict) -> list[str]:
    """Finds all standard wiki links across the body and all string metadata fields."""
    links = set()
    
    # Check body
    if "content" in draft and isinstance(draft["content"], str):
        links.update(extract_wiki_links(draft["content"]))
        
    # Check metadata fields
    for key, val in draft.items():
        if key in ("content", "raw_markdown"):
            continue
        if isinstance(val, str):
            links.update(extract_wiki_links(val))
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, str):
                    links.update(extract_wiki_links(item))
                    
    return list(links)

def parse_markdown_file(filepath: str) -> dict[str, Any]:
    filename = os.path.basename(filepath)
    entity_name = filename[:-3] if filename.endswith(".md") else filename

    with open(filepath, encoding="utf-8") as f:
        content = f.read()

    meta, body = parse_frontmatter(content)
    links = extract_wiki_links(body)
    
    # Name from metadata or filename
    name = meta.get("name", entity_name)
    entity_type = meta.get("entity_type", "General")
    summary = meta.get("summary", "")

    return {
        "name": name,
        "entity_type": entity_type,
        "summary": summary,
        "raw_markdown": content,
        "metadata": meta,
        "links": links
    }

def sync_single_file(filepath: str):
    """O(1) incremental sync for a single file."""
    if not os.path.exists(filepath):
        return

    parsed = parse_markdown_file(filepath)
    name = parsed["name"]
    meta = parsed["metadata"]
    
    # 1. Insert Entity
    insert_entity(
        name=name,
        entity_type=parsed["entity_type"],
        summary=parsed["summary"],
        raw_markdown=parsed["raw_markdown"],
        metadata=meta
    )
    
    # 2. Insert Name Index (Phonetic hash using match_rating_codex for typo detection)
    insert_name_index(name, jellyfish.match_rating_codex(name))
    
    # 3. Clear old relationships for this entity
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM edges WHERE source_name = ?", (name,))
    cursor.execute("DELETE FROM memberships WHERE entity_name = ?", (name,))
    cursor.execute("DELETE FROM containment WHERE item_name = ?", (name,))
    cursor.execute("DELETE FROM genealogy WHERE parent_name = ? OR child_name = ?", (name, name))
    conn.commit()
    
    # 4. Insert Edges (Wikilinks)
    # Get known entities to enforce FK constraints
    cursor.execute("SELECT name FROM entities")
    known_entities = {row["name"] for row in cursor.fetchall()}

    for target in parsed["links"]:
        if target in known_entities:
            cursor.execute("INSERT INTO edges (source_name, target_name, relation_type, weight) VALUES (?, ?, ?, ?)", (name, target, "wikilink", 1))
    
    # 5. Insert Memberships
    if parsed["entity_type"] == "Character" and "faction_affiliations" in meta:
        factions = meta["faction_affiliations"]
        if isinstance(factions, list):
            for f in factions:
                if f in known_entities:
                    cursor.execute("INSERT INTO memberships (entity_name, faction_name, role) VALUES (?, ?, ?)", (name, f, "Member"))
    
    # 6. Insert Containment
    if parsed["entity_type"] == "Item" and "current_location" in meta:
        loc = meta["current_location"]
        if loc and loc in known_entities:
            cursor.execute("INSERT INTO containment (item_name, location_name) VALUES (?, ?)", (name, loc))
            
    conn.commit()
    conn.close()

def scan_and_sync_vault(vault_path: str):
    """Full vault sync."""
    init_db()
    
    if not os.path.exists(vault_path):
        return

    # To avoid FK constraint failures when inserting edges to non-existent entities, 
    # we do a 2-pass sync. Pass 1: Entities. Pass 2: Relationships.
    
    all_files = []
    for root, _, files in os.walk(vault_path):
        for file in files:
            if file.endswith(".md") and not file.startswith("."):
                filepath = os.path.abspath(os.path.join(root, file))
                all_files.append(filepath)
                
    # Pass 1: Insert all entities
    parsed_files = []
    for filepath in all_files:
        try:
            parsed = parse_markdown_file(filepath)
            insert_entity(
                name=parsed["name"],
                entity_type=parsed["entity_type"],
                summary=parsed["summary"],
                raw_markdown=parsed["raw_markdown"],
                metadata=parsed["metadata"]
            )
            insert_name_index(parsed["name"], jellyfish.match_rating_codex(parsed["name"]))
            parsed_files.append(parsed)
        except Exception as e:
            print(f"Error parsing {filepath}: {e}")

    # Pass 2: Insert relationships
    conn = get_db_connection()
    cursor = conn.cursor()
    # Clear all relations
    cursor.execute("DELETE FROM edges")
    cursor.execute("DELETE FROM memberships")
    cursor.execute("DELETE FROM containment")
    cursor.execute("DELETE FROM genealogy")
    
    # We only insert edges if the target entity exists in DB
    cursor.execute("SELECT name FROM entities")
    known_entities = {row["name"] for row in cursor.fetchall()}
    
    for parsed in parsed_files:
        name = parsed["name"]
        meta = parsed["metadata"]
        
        # Edges
        for target in parsed["links"]:
            if target in known_entities:
                cursor.execute("INSERT INTO edges (source_name, target_name, relation_type, weight) VALUES (?, ?, ?, ?)", (name, target, "wikilink", 1))
        
        # Memberships
        if parsed["entity_type"] == "Character" and "faction_affiliations" in meta:
            factions = meta["faction_affiliations"]
            if isinstance(factions, list):
                for f in factions:
                    if f in known_entities:
                        cursor.execute("INSERT INTO memberships (entity_name, faction_name, role) VALUES (?, ?, ?)", (name, f, "Member"))
        
        # Containment
        if parsed["entity_type"] == "Item" and "current_location" in meta:
            loc = meta["current_location"]
            if loc and loc in known_entities:
                cursor.execute("INSERT INTO containment (item_name, location_name) VALUES (?, ?)", (name, loc))
                
    conn.commit()
    conn.close()
