import difflib
import itertools
import re
from typing import Any

from .database import get_db_connection, get_metadata

def normalize_local_id(name: str) -> str:
    """Helper to normalize link targets to entity IDs."""
    return re.sub(r'\s+', '_', name.strip().lower())

def validate_link_integrity() -> list[dict[str, Any]]:
    """Checks for broken wiki links (links pointing to non-existent notes)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Select all links where target_id does not exist in entities table
    cursor.execute("""
        SELECT l.source_id, l.target_id, e.name as source_name 
        FROM links l
        LEFT JOIN entities e ON l.source_id = e.id
        WHERE l.target_id NOT IN (SELECT id FROM entities)
    """)
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for row in rows:
        results.append({
            "status": "warning",
            "type": "link_integrity",
            "entity_id": row["source_id"],
            "message": f"Note '{row['source_name']}' contains a broken link to [[{row['target_id'].replace('_', ' ').title()}]]"
        })
    return results

def validate_entity_schemas() -> list[dict[str, Any]]:
    """Checks that entities contain required template fields depending on their type, and cross-references relationships."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, type FROM entities")
    entities = [dict(row) for row in cursor.fetchall()]
    existing_ids = {ent["id"] for ent in entities}
    conn.close()
    
    results = []
    VALID_TYPES = {"character", "location", "item", "faction", "general"}
    for ent in entities:
        ent_id = ent["id"]
        ent_name = ent["name"]
        ent_type = ent["type"]
        meta = get_metadata(ent_id)
        
        if ent_type not in VALID_TYPES:
            results.append({
                "status": "warning",
                "type": "schema",
                "entity_id": ent_id,
                "message": f"Note '{ent_name}' has unrecognized type '{ent_type}'. Allowed types are: {', '.join(sorted(VALID_TYPES))}."
            })
            continue
            
        if ent_type == "character":
            # 1. Required fields
            required = ["status", "location", "age"]
            for field in required:
                if field not in meta or not meta[field].strip():
                    results.append({
                        "status": "warning",
                        "type": "schema",
                        "entity_id": ent_id,
                        "message": f"Character '{ent_name}' is missing required field '{field}' in frontmatter."
                    })
            
            # 2. Age format check
            age_str = meta.get("age", "").strip().lower()
            if age_str and age_str != "unknown":
                try:
                    age_val = int(age_str)
                    if age_val < 0:
                        results.append({
                            "status": "error",
                            "type": "schema",
                            "entity_id": ent_id,
                            "message": f"Character '{ent_name}' has negative age value: {age_str}."
                        })
                except ValueError:
                    results.append({
                        "status": "error",
                        "type": "schema",
                        "entity_id": ent_id,
                        "message": f"Character '{ent_name}' has invalid age format (must be integer or 'unknown'): {age_str}."
                    })
            
            # 3. Location relationship check
            loc_val = meta.get("location", "").strip()
            if loc_val and loc_val.lower() != "unknown":
                loc_id = normalize_local_id(loc_val)
                if loc_id not in existing_ids:
                    results.append({
                        "status": "warning",
                        "type": "relationship",
                        "entity_id": ent_id,
                        "message": f"Character '{ent_name}' references location '{loc_val}', but that Location note does not exist."
                    })

            # 4. Faction relationship check
            fac_val = meta.get("faction", "").strip()
            if fac_val and fac_val.lower() != "unknown":
                fac_id = normalize_local_id(fac_val)
                if fac_id not in existing_ids:
                    results.append({
                        "status": "warning",
                        "type": "relationship",
                        "entity_id": ent_id,
                        "message": f"Character '{ent_name}' references faction '{fac_val}', but that Faction note does not exist."
                    })

            # 5. Nested relationships check
            rel_str = meta.get("relationships", "")
            if rel_str:
                rel_links = re.findall(r"\[\[(.*?)\]\]", rel_str)
                for rel_target in rel_links:
                    rel_id = normalize_local_id(rel_target)
                    if rel_id not in existing_ids:
                        results.append({
                            "status": "warning",
                            "type": "relationship",
                            "entity_id": ent_id,
                            "message": f"Character '{ent_name}' has a relationship mapping to non-existent note [[{rel_target}]]."
                        })

        elif ent_type == "location":
            required = ["region", "place_type"]
            for field in required:
                if field not in meta or not meta[field].strip():
                    results.append({
                        "status": "warning",
                        "type": "schema",
                        "entity_id": ent_id,
                        "message": f"Location '{ent_name}' is missing required field '{field}' in frontmatter."
                    })

        elif ent_type == "item":
            required = ["rarity"]
            for field in required:
                if field not in meta or not meta[field].strip():
                    results.append({
                        "status": "warning",
                        "type": "schema",
                        "entity_id": ent_id,
                        "message": f"Item '{ent_name}' is missing required field '{field}' in frontmatter."
                    })
            
            # Check rarity values
            rarity_val = meta.get("rarity", "").strip().lower()
            if rarity_val and rarity_val not in ["common", "rare", "legendary", "unique"]:
                results.append({
                    "status": "warning",
                    "type": "schema",
                    "entity_id": ent_id,
                    "message": f"Item '{ent_name}' has atypical rarity category: '{rarity_val}'."
                })
            
            # Cross-reference owner, origin, location
            for field in ["owner", "origin", "location"]:
                val = meta.get(field, "").strip()
                if val and val.lower() != "unknown":
                    val_id = normalize_local_id(val)
                    if val_id not in existing_ids:
                        results.append({
                            "status": "warning",
                            "type": "relationship",
                            "entity_id": ent_id,
                            "message": f"Item '{ent_name}' references {field} '{val}', but that note does not exist."
                        })

        elif ent_type == "faction":
            required = ["headquarters", "leader"]
            for field in required:
                if field not in meta or not meta[field].strip():
                    results.append({
                        "status": "warning",
                        "type": "schema",
                        "entity_id": ent_id,
                        "message": f"Faction '{ent_name}' is missing required field '{field}' in frontmatter."
                    })
            
            # Headquarters and leader checks
            hq = meta.get("headquarters", "").strip()
            if hq and hq.lower() != "unknown" and normalize_local_id(hq) not in existing_ids:
                results.append({
                    "status": "warning",
                    "type": "relationship",
                    "entity_id": ent_id,
                    "message": f"Faction '{ent_name}' headquarters '{hq}' does not exist as a Location note."
                })
            
            ldr = meta.get("leader", "").strip()
            if ldr and ldr.lower() != "unknown" and normalize_local_id(ldr) not in existing_ids:
                results.append({
                    "status": "warning",
                    "type": "relationship",
                    "entity_id": ent_id,
                    "message": f"Faction '{ent_name}' leader '{ldr}' does not exist as a Character note."
                })

    return results

def validate_timelines() -> list[dict[str, Any]]:
    """Validates date consistency (birth_year, death_year) supporting fantasy calendar eras."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, type FROM entities WHERE type = 'character'")
    characters = cursor.fetchall()
    conn.close()
    
    results = []
    for char in characters:
        char_id = char["id"]
        char_name = char["name"]
        meta = get_metadata(char_id)
        
        species = meta.get("species", "human").strip().lower()
        
        # Determine lifespan limits by species/race (supports fantasy settings)
        max_lifespan = 150
        if species == "elf":
            max_lifespan = 1000
        elif species == "dwarf":
            max_lifespan = 350
        elif species == "orc":
            max_lifespan = 80
        elif species == "vampire" or species == "immortal":
            max_lifespan = 10000
            
        birth_str = meta.get("birth_year")
        death_str = meta.get("death_year")
        
        if birth_str and death_str and birth_str.lower() != "unknown" and death_str.lower() != "unknown":
            try:
                # Helper to extract the numeric components from era strings (e.g. 4E 201 -> 201)
                birth = int(''.join(filter(str.isdigit, birth_str)))
                death = int(''.join(filter(str.isdigit, death_str)))
                
                # Check negative values (BC calendar format support)
                if "-" in birth_str or "BC" in birth_str.upper():
                    birth = -birth
                if "-" in death_str or "BC" in death_str.upper():
                    death = -death
                
                if death < birth:
                    results.append({
                        "status": "error",
                        "type": "timeline",
                        "entity_id": char_id,
                        "message": f"Timeline conflict: Character '{char_name}' has death year ({death_str}) before birth year ({birth_str})."
                    })
                elif (death - birth) > max_lifespan:
                    results.append({
                        "status": "warning",
                        "type": "timeline",
                        "entity_id": char_id,
                        "message": f"Timeline warning: Character '{char_name}' ({species}) has a lifespan of {death - birth} years (born {birth_str}, died {death_str}), which exceeds the limits for species '{species}' ({max_lifespan} years)."
                    })
            except ValueError:
                pass
    return results

def validate_duplicates() -> list[dict[str, Any]]:
    """Identifies possible duplicate note names (typo/misspelled detection) or content similarity > 80%."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, content, type FROM entities")
    entities = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    results = []
    # Use combinations to check every unique pair of notes once
    for ent1, ent2 in itertools.combinations(entities, 2):
        # 1. Check Name Similarity (typo/misspelled checks)
        name_ratio = difflib.SequenceMatcher(None, ent1["name"].lower(), ent2["name"].lower()).ratio()
        if name_ratio >= 0.8:
            results.append({
                "status": "warning",
                "type": "duplicate_name",
                "entity_id": ent1["id"],
                "message": f"Fuzzy Duplicate Name: '{ent1['name']}' is {int(name_ratio * 100)}% similar to '{ent2['name']}'. Check for typos or misspellings."
            })
            
        # 2. Check Content Body Similarity
        if ent1["content"] and ent2["content"]:
            matcher = difflib.SequenceMatcher(None, ent1["content"], ent2["content"])
            if matcher.real_quick_ratio() >= 0.8 and matcher.ratio() >= 0.8:
                results.append({
                    "status": "error",
                    "type": "duplicate_content",
                    "entity_id": ent1["id"],
                    "message": f"High Content Similarity: Note '{ent1['name']}' has more than 80% identical text with note '{ent2['name']}'."
                })
                
    return results

def run_all_validators() -> list[dict[str, Any]]:
    """Runs all static validators and returns a consolidated list of issues."""
    issues = []
    issues.extend(validate_link_integrity())
    issues.extend(validate_entity_schemas())
    issues.extend(validate_timelines())
    issues.extend(validate_duplicates())
    return issues
