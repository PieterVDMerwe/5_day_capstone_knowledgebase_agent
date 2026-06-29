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

            if val.startswith("[") and val.endswith("]") and not (val.startswith("[[") and val.endswith("]]")):
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
    
    # Extract links from both body and metadata properties
    temp_draft = {
        "content": body,
        **meta
    }
    links = extract_all_wiki_links(temp_draft)
    
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
                clean_f = f[2:-2] if f.startswith("[[") and f.endswith("]]") else f
                if clean_f in known_entities:
                    cursor.execute("INSERT INTO memberships (entity_name, faction_name, role) VALUES (?, ?, ?)", (name, clean_f, "Member"))
    
    # 6. Insert Containment
    if parsed["entity_type"] == "Item" and "current_location" in meta:
        loc = meta["current_location"]
        if loc:
            clean_loc = loc[2:-2] if loc.startswith("[[") and loc.endswith("]]") else loc
            if clean_loc in known_entities:
                cursor.execute("INSERT INTO containment (item_name, location_name) VALUES (?, ?)", (name, clean_loc))
            
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
    
    # Pass 1.5: Identify missing links (stubs)
    cursor.execute("SELECT name FROM entities")
    known_entities = {row["name"] for row in cursor.fetchall()}
    
    all_extracted_links = set()
    for parsed in parsed_files:
        all_extracted_links.update(parsed["links"])
        
    from app.file_writer import write_entity_to_vault
    for link in all_extracted_links:
        if link.startswith("[["):
            continue
        if link not in known_entities:
            stub_draft = {
                "name": link,
                "entity_type": "General",
                "is_empty": True,
                "summary": f"Auto-generated empty stub for {link}."
            }
            stub_filepath = write_entity_to_vault(stub_draft)
            try:
                parsed_stub = parse_markdown_file(stub_filepath)
                insert_entity(
                    name=parsed_stub["name"],
                    entity_type=parsed_stub["entity_type"],
                    summary=parsed_stub["summary"],
                    raw_markdown=parsed_stub["raw_markdown"],
                    metadata=parsed_stub["metadata"]
                )
                insert_name_index(parsed_stub["name"], jellyfish.match_rating_codex(parsed_stub["name"]))
                parsed_files.append(parsed_stub)
                known_entities.add(link)
            except Exception as e:
                print(f"Error parsing stub {stub_filepath}: {e}")
    
    # Clear all relations
    cursor.execute("DELETE FROM edges")
    cursor.execute("DELETE FROM memberships")
    cursor.execute("DELETE FROM containment")
    cursor.execute("DELETE FROM genealogy")
    
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
                    clean_f = f[2:-2] if f.startswith("[[") and f.endswith("]]") else f
                    if clean_f in known_entities:
                        cursor.execute("INSERT INTO memberships (entity_name, faction_name, role) VALUES (?, ?, ?)", (name, clean_f, "Member"))
        
        # Containment
        if parsed["entity_type"] == "Item" and "current_location" in meta:
            loc = meta["current_location"]
            if loc:
                clean_loc = loc[2:-2] if loc.startswith("[[") and loc.endswith("]]") else loc
                if clean_loc in known_entities:
                    cursor.execute("INSERT INTO containment (item_name, location_name) VALUES (?, ?)", (name, clean_loc))
                
    conn.commit()
    conn.close()
