import os
import re
from typing import Any

from .database import get_db_connection


def normalize_entity_id(name: str) -> str:
    """Normalizes note name or path to a clean, lowercase id."""
    base = os.path.basename(name)
    if base.endswith(".md"):
        base = base[:-3]
    return re.sub(r'\s+', '_', base.strip().lower())

def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Parses frontmatter from a markdown string and returns (metadata_dict, body_content)."""
    meta = {}
    body = content

    # Matches starting frontmatter
    match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n(.*)$", content, re.DOTALL)
    if match:
        frontmatter_text = match.group(1)
        body = match.group(2)

        # Simple YAML key-value parser (supports strings, lists, numbers)
        for line in frontmatter_text.splitlines():
            if ":" not in line:
                continue
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip()

            # Parse list formats like [A, B] or simple lists
            if val.startswith("[") and val.endswith("]"):
                items = [item.strip().strip("'\"") for item in val[1:-1].split(",") if item.strip()]
                meta[key] = items
            # Parse quotes
            elif (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                meta[key] = val[1:-1]
            else:
                meta[key] = val

    return meta, body

def extract_wiki_links(body: str) -> list[str]:
    """Finds all standard wiki links [[Link Target]] in the body."""
    links = []
    # Matches [[Target]] or [[Target|Label]]
    pattern = r"\[\[(.*?)\]\]"
    for match in re.finditer(pattern, body):
        target = match.group(1).split("|")[0].strip()
        if target:
            links.append(normalize_entity_id(target))
    return links

def parse_markdown_file(filepath: str) -> dict[str, Any]:
    """Reads and parses a single markdown file into a structured dictionary."""
    filename = os.path.basename(filepath)
    entity_name = filename[:-3] if filename.endswith(".md") else filename
    entity_id = normalize_entity_id(entity_name)

    with open(filepath, encoding="utf-8") as f:
        content = f.read()

    meta, body = parse_frontmatter(content)
    links = extract_wiki_links(body)

    # Decouple facts from body text: Extract timeline details statically if not in frontmatter
    if "birth_year" not in meta:
        birth_match = re.search(r"born in the year (\d+)", body, re.IGNORECASE) or re.search(r"birth year:? (\d+)", body, re.IGNORECASE)
        if birth_match:
            meta["birth_year"] = birth_match.group(1)

    if "death_year" not in meta:
        death_match = re.search(r"died in the year (\d+)", body, re.IGNORECASE) or re.search(r"death year:? (\d+)", body, re.IGNORECASE)
        if death_match:
            meta["death_year"] = death_match.group(1)

    # Extract type or default to 'general'
    entity_type = "general"
    if "town" in entity_name.lower() or "city" in entity_name.lower() or "tavern" in entity_name.lower() or "location" in meta:
        entity_type = "location"
    elif "woodman" in entity_name.lower() or "barkeep" in entity_name.lower() or "character" in meta:
        entity_type = "character"
    entity_type = meta.get("type", entity_type).strip().lower()

    summary = meta.get("summary", body.split("\n")[0][:200].strip() if body else "")

    # If the file lacks frontmatter entirely, rewrite it formatted
    if not content.strip().startswith("---"):
        frontmatter = "---\n"
        frontmatter += f'name: "{entity_name}"\n'
        frontmatter += f'type: "{entity_type}"\n'
        frontmatter += f'summary: "{summary}"\n'
        if entity_type == "character":
            frontmatter += 'status: "active"\n'
            frontmatter += 'location: ""\n'
        elif entity_type == "location":
            frontmatter += 'region: ""\n'
        frontmatter += "---\n\n"

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(frontmatter + content.strip())

    return {
        "id": entity_id,
        "name": meta.get("name", entity_name),
        "type": entity_type,
        "summary": summary,
        "content": body,
        "path": filepath,
        "metadata": meta,
        "links": links
    }

def scan_and_sync_vault(vault_path: str):
    """Scans the vault directory and incrementally syncs changed files to the SQLite DB."""
    from .database import init_db, insert_entity, insert_link, insert_metadata

    init_db()

    if not os.path.exists(vault_path):
        return

    # Get current DB status
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, path, last_modified FROM entities")
    db_entities = {row["id"]: {"path": row["path"], "mtime": row["last_modified"]} for row in cursor.fetchall()}
    conn.close()

    found_paths = set()
    changed_or_new = []

    # Scan filesystem
    for root, _, files in os.walk(vault_path):
        for file in files:
            if file.endswith(".md") and not file.startswith("."):
                filepath = os.path.abspath(os.path.join(root, file))
                entity_id = normalize_entity_id(file)
                found_paths.add(entity_id)

                mtime = os.path.getmtime(filepath)
                # Parse if not in DB, or if file modified time is newer
                if entity_id not in db_entities or mtime > db_entities[entity_id]["mtime"]:
                    try:
                        entity = parse_markdown_file(filepath)
                        entity["mtime"] = mtime
                        changed_or_new.append(entity)
                    except Exception as e:
                        print(f"Error parsing {filepath}: {e}")

    # Clean up deleted files from the database
    conn = get_db_connection()
    cursor = conn.cursor()
    for db_id in list(db_entities.keys()):
        if db_id not in found_paths:
            cursor.execute("DELETE FROM links WHERE source_id = ? OR target_id = ?", (db_id, db_id))
            cursor.execute("DELETE FROM metadata WHERE entity_id = ?", (db_id,))
            cursor.execute("DELETE FROM entities WHERE id = ?", (db_id,))
    conn.commit()
    conn.close()

    # Save changed or new entities
    for ent in changed_or_new:
        insert_entity(
            id_=ent["id"],
            name=ent["name"],
            type_=ent["type"],
            summary=ent["summary"],
            content=ent["content"],
            path=ent["path"],
            last_modified=ent["mtime"]
        )

        # Reset metadata for this entity before inserting new ones
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM metadata WHERE entity_id = ?", (ent["id"],))
        cursor.execute("DELETE FROM links WHERE source_id = ?", (ent["id"],))
        conn.commit()
        conn.close()

        for k, v in ent["metadata"].items():
            v_str = str(v)
            insert_metadata(ent["id"], k, v_str)

        # Insert relationship links (only link to entities that exist in the vault or are being created)
        all_known_ids = found_paths
        for link_target in ent["links"]:
            if link_target in all_known_ids:
                insert_link(ent["id"], link_target)
