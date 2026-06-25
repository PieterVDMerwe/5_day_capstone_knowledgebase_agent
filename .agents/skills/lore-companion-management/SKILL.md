---
name: lore-companion-management
description: Guidance on managing, validating, and extending the Obsidian Lore Companion vault schema and companion application.
---

# Lore Companion Management Skill

Use this skill when modifying, testing, or expanding the Obsidian Lore Companion workspace application, parser, schemas, or agents.

## Project Intention

The Obsidian Lore Companion is a specialized local agentic tool designed to act as a creative generator and a logical validator for worldbuilding note vaults (e.g., fantasy or mundane world settings). It indexes markdown notes to an SQLite database, verifies structural/semantic consistency, and assists the creator via two specialized agents.

## Sub-Agents

1. **Lore-seeker (Creative Generator)**
   - **Goal**: Research existing indexed wiki data to generate new characters, locations, items, or factions that integrate naturally.
   - **Constraint**: Must strictly output markdown content matching the designated schema templates (Character, Location, Item, Faction).
2. **Truth-keeper (Consistency Inspector)**
   - **Goal**: Perform logic checking on note drafts (or diffs of changed lines) to flag contradictions or broken connections against the database.
   - **Hierarchy**: Always run fast, non-LLM static checks first before executing the LLM-based agent.

## Note Schema Templates

Ensure all generated notes match these standard formats:

### Character Note
```yaml
---
name: "Character Name"
type: "character"
species: "human" # human | elf | dwarf | unknown (defines lifespan threshold)
summary: "High-level summary."
status: "active" # active | deceased | unknown
location: "Location Name" # Linked Location, or "unknown"
age: "unknown" # Integer or "unknown"
birth_year: "unknown" # Era/number, or "unknown"
death_year: "unknown" # Era/number, or "unknown"
faction: "Faction Name" # Linked Faction, or "unknown"
relationships:
  positive: []
  neutral: []
  negative: []
---
Prose content here...
```

### Location Note
```yaml
---
name: "Location Name"
type: "location"
summary: "High-level summary."
region: "Region Name" # String, or "unknown"
place_type: "town" # town | tavern | landmark | dungeon | etc.
---
Prose content here...
```

### Item Note
```yaml
---
name: "Item Name"
type: "item"
summary: "High-level summary."
owner: "Character Name" # Linked Character, or "unknown"
origin: "Location Name" # Linked Location, or "unknown"
location: "Location Name" # Linked Current Location, or "unknown"
rarity: "common" # common | rare | legendary | unique
---
Prose content here...
```

### Faction Note
```yaml
---
name: "Faction Name"
type: "faction"
summary: "High-level summary."
headquarters: "Location Name" # Linked Location, or "unknown"
leader: "Character Name" # Linked Character, or "unknown"
---
Prose content here...
```

## Validation & Testing
- Run unit tests after modifying schemas:
  `uv run pytest tests/unit/`
- Avoid running integration tests that connect to external LLM services in automated runs to conserve quota.
