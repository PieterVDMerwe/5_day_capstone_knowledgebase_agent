import os
import json

VAULT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "Knowledgebase", "Obsidian")

def write_entity_to_vault(entity_data: dict) -> str:
    """
    Converts a flat dictionary into an Obsidian-compatible Markdown file.
    YAML frontmatter is used for all properties except 'content' or 'raw_markdown'.
    Returns the file path.
    """
    os.makedirs(VAULT_DIR, exist_ok=True)
    
    name = entity_data.get("name", "Untitled")
    # Clean filename to be safe for OS
    filename = "".join([c for c in name if c.isalpha() or c.isdigit() or c==' ']).rstrip() + ".md"
    filepath = os.path.join(VAULT_DIR, filename)
    
    # Separate body content from frontmatter
    body = entity_data.pop("content", "")
    if not body and "raw_markdown" in entity_data:
        # Fallback if no specific content is provided
        # But we strip frontmatter from raw_markdown if we can, to avoid duplication
        raw = entity_data.pop("raw_markdown")
        if "---" in raw:
            parts = raw.split("---")
            if len(parts) >= 3:
                body = "---".join(parts[2:]).strip()
            else:
                body = raw
                
    # Remove internal fields
    if "raw_markdown" in entity_data: del entity_data["raw_markdown"]
    
    yaml_lines = ["---"]
    for k, v in entity_data.items():
        if k.startswith("_"): continue # Skip internal fields like _linter_error
        
        if isinstance(v, list):
            # Format as JSON array for YAML
            yaml_lines.append(f"{k}: {json.dumps(v)}")
        elif v:
            # Wrap strings in quotes if they contain colons to prevent YAML errors
            v_str = str(v)
            if ":" in v_str:
                yaml_lines.append(f"{k}: \"{v_str}\"")
            else:
                yaml_lines.append(f"{k}: {v_str}")
    yaml_lines.append("---")
    
    full_text = "\n".join(yaml_lines) + "\n\n" + body
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(full_text)
        
    return filepath
