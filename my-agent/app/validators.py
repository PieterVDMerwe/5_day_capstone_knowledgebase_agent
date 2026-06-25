import difflib
import itertools
from typing import Any

from .database import get_db_connection, get_metadata


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
    """Checks that entities contain required template fields depending on their type."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, type FROM entities")
    entities = cursor.fetchall()
    conn.close()

    results = []
    for ent in entities:
        ent_id = ent["id"]
        ent_name = ent["name"]
        ent_type = ent["type"]
        meta = get_metadata(ent_id)

        if ent_type == "character":
            # Required fields for characters
            required = ["status", "location"]
            for field in required:
                if field not in meta or not meta[field].strip():
                    results.append({
                        "status": "warning",
                        "type": "schema",
                        "entity_id": ent_id,
                        "message": f"Character '{ent_name}' is missing required field '{field}' in frontmatter."
                    })
        elif ent_type == "location":
            required = ["region"]
            for field in required:
                if field not in meta or not meta[field].strip():
                    results.append({
                        "status": "warning",
                        "type": "schema",
                        "entity_id": ent_id,
                        "message": f"Location '{ent_name}' is missing required field '{field}' in frontmatter."
                    })
    return results

def validate_timelines() -> list[dict[str, Any]]:
    """Validates date consistency (birth_year, death_year, timeline chronologies)."""
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

        birth_str = meta.get("birth_year")
        death_str = meta.get("death_year")

        if birth_str and death_str:
            try:
                # Strip out any non-numeric chars for simple fantasy calendars or standard ones
                birth = int(''.join(filter(str.isdigit, birth_str)))
                death = int(''.join(filter(str.isdigit, death_str)))

                # Check for negative signs if represented
                if "-" in birth_str:
                    birth = -birth
                if "-" in death_str:
                    death = -death

                if death < birth:
                    results.append({
                        "status": "error",
                        "type": "timeline",
                        "entity_id": char_id,
                        "message": f"Timeline conflict: Character '{char_name}' has death year ({death_str}) before birth year ({birth_str})."
                    })
                elif (death - birth) > 150:
                    results.append({
                        "status": "warning",
                        "type": "timeline",
                        "entity_id": char_id,
                        "message": f"Timeline warning: Character '{char_name}' has a lifespan of {death - birth} years (born {birth_str}, died {death_str}), which exceeds the typical limit of 150 years."
                    })
            except ValueError:
                # Ignore fields that aren't numeric
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
            # Use quick_ratio for performance on large content first
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
