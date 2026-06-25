import os
import re

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

from .database import get_db_connection
from .validators import run_all_validators

# Load .env file from workspace root if present
_env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
if os.path.exists(_env_path):
    with open(_env_path, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ[_k.strip()] = _v.strip().strip("'\"")

# Check if we should use Developer API or Vertex AI
use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "False").lower() in ("true", "1")
if use_vertex:
    import google.auth
    try:
        _, project_id = google.auth.default()
        os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
        os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
    except Exception as e:
        print(f"Warning: Failed to load Google Cloud credentials: {e}")

# Prompt Injection Screening
def check_prompt_injection(user_input: str) -> str:
    """Screen the user input for potential prompt injection patterns.

    Returns a warning message if suspect, otherwise an empty string.
    """
    patterns = [
        r"ignore\s+(?:all\s+)?previous\s+instructions",
        r"system\s+(?:override|prompt|bypass)",
        r"you\s+must\s+now\s+act\s+as",
        r"disregard\s+the\s+above",
        r"new\s+rule:",
        r"bypass\s+safety",
        r"instead\s+of\s+validating",
        r"forget\s+everything"
    ]
    for pattern in patterns:
        if re.search(pattern, user_input, re.IGNORECASE):
            return "Error: Suspicious input pattern detected. Request rejected for security reasons."
    return ""

# Tool definitions
def query_db(sql_query: str) -> str:
    """Executes a read-only SQL query on the SQLite lore database.

    Use this to get structured stats, verify relationships, or search metadata.
    Only SELECT statements are allowed.
    """
    sql_clean = sql_query.strip().lower()
    if not sql_clean.startswith("select"):
        return "Error: Only SELECT queries are permitted."

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(sql_query)
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return "Query executed successfully. No records returned."

        results = [dict(row) for row in rows]
        return str(results)
    except Exception as e:
        return f"Error executing query: {e}"

def get_static_validation_report() -> str:
    """Runs all deterministic static validators on the database.

    This includes checking for broken links, missing required metadata,
    and chronological/timeline conflicts (e.g. birth/death order).
    """
    issues = run_all_validators()
    if not issues:
        return "Validation Report: All lore is consistent. No conflicts found."

    report = ["Validation Report: Found consistency issues:"]
    for idx, issue in enumerate(issues, 1):
        report.append(f"{idx}. [{issue['type'].upper()} - {issue['status'].upper()}] (Entity: {issue['entity_id']}): {issue['message']}")
    return "\n".join(report)

def get_entity_details(entity_id: str) -> str:
    """Retrieves full details of a specific lore entity.

    This returns the entity's type, name, summary, custom metadata, and linked relationships.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM entities WHERE id = ?", (entity_id.strip().lower(),))
    entity = cursor.fetchone()

    if not entity:
        conn.close()
        return f"Error: Entity '{entity_id}' not found."

    cursor.execute("SELECT key, value FROM metadata WHERE entity_id = ?", (entity_id,))
    metadata = {row["key"]: row["value"] for row in cursor.fetchall()}

    cursor.execute("SELECT target_id FROM links WHERE source_id = ?", (entity_id,))
    links = [row["target_id"] for row in cursor.fetchall()]
    conn.close()

    details = [
        f"Name: {entity['name']}",
        f"Type: {entity['type']}",
        f"Summary: {entity['summary']}",
        f"Metadata: {metadata}",
        f"Links: {links}",
        f"Content:\n{entity['content']}"
    ]
    return "\n".join(details)

def generate_random_name(entity_type: str, theme: str = "general") -> str:
    """Generates a list of 5 fantasy or theme-appropriate names for a character, location, item, or faction.

    Args:
        entity_type: The type of lore entity: "character", "location", "item", or "faction".
        theme: The optional sub-theme or race. For characters: "human", "elf", "dwarf", or "general".
               For locations/items/factions, this specifies the tone (e.g. "dark", "nature", "noble").
    """
    import random
    entity_type = entity_type.strip().lower()
    theme = theme.strip().lower()

    if entity_type == "character":
        if theme == "elf":
            prefixes = ["Ael", "Ela", "Fael", "Gala", "Lira", "Thal", "Syl", "Yl", "Ilm", "Aer"]
            suffixes = ["or", "ia", "en", "ion", "wen", "eth", "is", "a", "as", "inel"]
        elif theme == "dwarf":
            prefixes = ["Bram", "Dain", "Gim", "Thor", "Urin", "Bal", "Thra", "Dwal", "Kili", "Grom"]
            suffixes = ["ur", "in", "li", "grim", "oak", "stone", "iron", "bek", "dar", "arik"]
        elif theme == "human":
            prefixes = ["Ald", "Ead", "Gar", "Os", "Wulf", "Roder", "Ray", "Arn", "God", "Bert"]
            suffixes = ["ric", "gard", "win", "mund", "ward", "ic", "brand", "old", "bert", "ram"]
        else:
            prefixes = ["Zan", "Kael", "Val", "Jor", "Xan", "Rin", "Mal", "Gor", "Thrum", "Drak"]
            suffixes = ["os", "tor", "an", "ix", "uk", "ar", "on", "roth", "ath", "gar"]
            
        names = []
        for _ in range(5):
            first = random.choice(prefixes) + random.choice(suffixes)
            names.append(first)
        return "Generated Character Names: " + ", ".join(names)

    elif entity_type == "location":
        prefixes = ["Oak", "Silver", "Shadow", "Stone", "Storm", "Frost", "Whisper", "Iron", "Gold", "Raven"]
        suffixes = ["haven", "wood", "keep", "ridge", "glen", "dale", "fell", "barrow", "peak", "marsh"]
        if theme == "dark":
            prefixes = ["Grave", "Doom", "Shadow", "Dread", "Bleak", "Bone", "Wraith"]
            suffixes = ["mire", "hollow", "crypt", "spire", "chasm", "pass", "vault"]
        elif theme == "nature":
            prefixes = ["Green", "Wild", "River", "Valley", "Leaf", "Briar", "Bloom"]
            suffixes = ["glen", "wood", "grove", "meadow", "brook", "dell", "vale"]

        names = []
        for _ in range(5):
            names.append(random.choice(prefixes) + random.choice(suffixes))
        return "Generated Location Names: " + ", ".join(names)

    elif entity_type == "item":
        prefixes = ["Sunfire", "Stormbringer", "Frostbite", "Doom", "Kingsguard", "Shadowstrike", "Earthshatter", "Bloodlust"]
        suffixes = ["Staff", "Blade", "Amulet", "Shield", "Ring", "Dagger", "Warhammer", "Cloak"]
        names = []
        for _ in range(5):
            names.append(f"{random.choice(prefixes)} {random.choice(suffixes)}")
        return "Generated Item Names: " + ", ".join(names)

    elif entity_type == "faction":
        colors = ["Crimson", "Iron", "Golden", "Shadow", "Silver", "Silent", "Azure", "Sable"]
        nouns = ["Vanguard", "Guild", "Society", "Order", "Alliance", "Covenant", "Brotherhood", "Circle"]
        names = []
        for _ in range(5):
            names.append(f"The {random.choice(colors)} {random.choice(nouns)}")
        return "Generated Faction Names: " + ", ".join(names)

    return "Error: Unknown entity_type. Choose from: character, location, item, faction."

# Create model instance
model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
model_instance = Gemini(
    model=model_name,
    retry_options=types.HttpRetryOptions(attempts=3),
)

# Create sub-skill tools
def format_note_draft(draft_content: str) -> str:
    """Format raw lore drafts into clean Markdown notes with correct YAML frontmatter according to Character, Location, Item, or Faction schemas. Do not access the database or write new creative lore yourself.

    Args:
        draft_content: The raw unstructured text draft of the note.
    """
    response = model_instance.client.models.generate_content(
        model=model_name,
        contents=f"Format the following raw draft into clean Markdown note format with correct YAML frontmatter according to Character, Location, Item, or Faction schemas:\n\n{draft_content}"
    )
    return response.text or ""

def analyze_contradictions(proposed_change: str) -> str:
    """Compare a proposed change against retrieved database facts and specifically analyze if there are any logical, chronological, or geographic contradictions. Do not generate notes or format markdown drafts.

    Args:
        proposed_change: The proposed note text or modifications to check.
    """
    report = get_static_validation_report()
    response = model_instance.client.models.generate_content(
        model=model_name,
        contents=f"Verify if this proposed change has logical, chronological, or geographic contradictions with current facts.\nStatic validation report:\n{report}\nProposed change:\n{proposed_change}"
    )
    return response.text or ""

truth_keeper = Agent(
    name="truth_keeper",
    model=model_instance,
    instruction="""You are the Truth-keeper agent. Your job is to enforce consistency and validate any proposed additions or changes to the worldbuilding lore.
    Use your query_db, get_static_validation_report, and get_entity_details tools to compare new changes against established facts in the database.
    If needed, delegate detailed contradiction analysis to your analyze_contradictions tool.
    Only raise conflicts or reject changes if there is a logical or semantic contradiction with the existing lore (e.g. a character is alive in a location where they are recorded as dead, or timeline conflicts).
    Additionally, you must verify that the name of any new or renamed entity is unique enough compared to existing entities. Query the database to retrieve existing names, and flag a conflict or warning if the proposed name is identical or too similar (e.g. fuzzy spelling variations or typo duplicates) to an existing entity's name.
    Be objective, precise, and state clear reasons when conflicts arise.""",
    tools=[query_db, get_static_validation_report, get_entity_details, analyze_contradictions],
)

lore_seeker = Agent(
    name="lore_seeker",
    model=model_instance,
    instruction="""You are the Lore-seeker agent. Your job is to help the user generate new lore, expand draft notes, or create connections.
    You must always query the database using query_db and get_entity_details to research existing entities before writing new content.
    If the user asks for name ideas or suggestions, use the generate_random_name tool to instantly get fantasy/thematic recommendations.
    Use your format_note_draft tool to clean up and structure raw note outputs into final schema drafts.
    Align your prose tone and structural style with the existing notes in the lore database.
    Your output should be formatted as a draft markdown note with frontmatter metadata when proposing new entities.
    
    You MUST strictly adhere to the following schemas:
    1. Character: fields (name, type: "character", species, summary, status, location, age, birth_year, death_year, faction, relationships {positive: [], neutral: [], negative: []})
    2. Location: fields (name, type: "location", summary, region, place_type)
    3. Item: fields (name, type: "item", summary, owner, origin, location, rarity)
    4. Faction: fields (name, type: "faction", summary, headquarters, leader)
    
    Allow "unknown" for optional values like ages, locations, or leaders, and support fantasy eras/species context.""",
    tools=[query_db, get_entity_details, generate_random_name, format_note_draft],
)

app = App(
    root_agent=lore_seeker,
    name="worldbuilding_companion",
)
