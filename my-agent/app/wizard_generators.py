import random
from typing import Dict, Any, List
from app.database import get_db_connection

# Seed data lists
FANTASY_FIRST_NAMES = ["Liam", "Sarah", "Elara", "Garrick", "Thorne", "Zephyr", "Aria", "Kaelen", "Morrigan", "Lyra", "Orion", "Freya", "Baelor", "Vaelen", "Kael", "Eldrin", "Aurelia", "Sylas", "Dorian", "Isolde", "Valerius"]
FANTASY_LAST_NAMES = ["Whisperwind", "Stormbringer", "Blacksmith", "Ironheart", "Shadowmantle", "Sunstrider", "Oakenshield", "Dreadweaver", "Frostbrand", "Wyrmslayer", "Silverleaf", "Ravenclaw", "Brightflame", "Stonewright", "Goldweaver"]

FANTASY_SPECIES = ["Elves", "Dwarves", "Humans", "Orcs", "Goblins", "Halflings", "Gnomes", "Tieflings", "Dragonborn", "Centaurs"]
BIOMES = ["Forest", "Mountain", "Desert", "Swamp", "Cave", "Tundra", "Plains", "Jungle", "Coast", "Valley"]
CLIMATES = ["Temperate", "Arid", "Tropical", "Subarctic", "Mediterranean", "Polar", "Humid"]
ITEM_TYPES = ["Weapon", "Relic", "Armor", "Potion", "Book", "Ring", "Amulet", "Staff"]
MATERIALS = ["Mithril", "Adamantine", "Ironwood", "Star-Metal", "Obsidian", "Orichalcum", "Dragon-Glass"]
FACTION_TYPES = ["Guild", "Cult", "Empire", "Syndicate", "Order", "Alliance", "Cabal"]
EVENT_TYPES = ["Battle", "Coronation", "Treaty", "Discovery", "Catastrophe", "Rebellion"]
ANATOMY_TRAITS = ["Mammalian", "Reptilian", "Avian", "Insectoid", "Elemental", "Amphibious", "Ethereal"]
GENERAL_CATEGORIES = ["Magic System", "Holiday", "Concept", "Quest", "Mythology", "Historical Era"]
FANTASY_TAGS = ["Lore", "Magic", "History", "Artifact", "War", "Geography", "Legendary"]
PERSONALITY_TRAITS = ["Honorable", "Deceptive", "Brave", "Cunning", "Wise", "Reckless", "Loyal", "Ambitious", "Melancholy"]
PHYSICAL_DESCRIPTIONS = ["Tall and slender", "Stocky and muscular", "Scarred and weathered", "Elegant and poised", "Imposing stature", "Diminutive and quick"]

def get_random_entities_by_type(entity_type: str, limit: int = 3) -> List[str]:
    """Helper to query the DB and fetch a list of random entity names of a given type."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM entities WHERE entity_type = ? ORDER BY RANDOM() LIMIT ?", (entity_type, limit))
        rows = cursor.fetchall()
        conn.close()
        return [row["name"] for row in rows]
    except Exception:
        return []

def get_random_all_entities(limit: int = 3) -> List[str]:
    """Helper to query the DB and fetch a list of random entity names of any type."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM entities ORDER BY RANDOM() LIMIT ?", (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [row["name"] for row in rows]
    except Exception:
        return []

def generate_suggested_fields(entity_type: str) -> Dict[str, Any]:
    """Generates suggested fields for the given entity type."""
    if entity_type not in ("Character", "Location", "Item", "Faction", "Event", "Species", "General"):
        raise ValueError(f"Unknown entity type: {entity_type}")
        
    first_name = random.choice(FANTASY_FIRST_NAMES)
    last_name = random.choice(FANTASY_LAST_NAMES)
    name = f"{first_name} {last_name}"
    
    # Base fields
    base = {
        "name": name,
        "entity_type": entity_type,
        "summary": "",
        "aliases": [],
        "tags": [random.choice(FANTASY_TAGS)],
        "is_empty": False
    }
    
    if entity_type == "Character":
        species_name = random.choice(FANTASY_SPECIES)
        existing_species = get_random_entities_by_type("Species", 1)
        species_val = f"[[{existing_species[0]}]]" if existing_species else f"[[{species_name}]]"
        
        existing_locations = get_random_entities_by_type("Location", 1)
        location_val = f"[[{existing_locations[0]}]]" if existing_locations else None
        
        existing_factions = get_random_entities_by_type("Faction", 2)
        factions_val = [f"[[{f}]]" for f in existing_factions] if existing_factions else []
        
        base.update({
            "species": species_val,
            "age": str(random.randint(18, 150)),
            "status": "Alive",
            "faction_affiliations": factions_val,
            "current_location": location_val,
            "physical_description": random.choice(PHYSICAL_DESCRIPTIONS),
            "personality_traits": random.sample(PERSONALITY_TRAITS, min(3, len(PERSONALITY_TRAITS)))
        })
        
    elif entity_type == "Location":
        biome = random.choice(BIOMES)
        base["name"] = f"The {biome} of {first_name}"
        
        existing_regions = get_random_entities_by_type("Location", 1)
        region_val = f"[[{existing_regions[0]}]]" if existing_regions else None
        
        existing_factions = get_random_entities_by_type("Faction", 1)
        faction_val = f"[[{existing_factions[0]}]]" if existing_factions else None
        
        base.update({
            "region": region_val,
            "climate": random.choice(CLIMATES),
            "population": f"{random.randint(1, 50)}k",
            "controlling_faction": faction_val
        })
        
    elif entity_type == "Item":
        item_type = random.choice(ITEM_TYPES)
        base["name"] = f"{first_name}'s {item_type}"
        
        existing_creators = get_random_entities_by_type("Character", 1)
        creator_val = f"[[{existing_creators[0]}]]" if existing_creators else None
        
        existing_owners = get_random_entities_by_type("Character", 1)
        owner_val = f"[[{existing_owners[0]}]]" if existing_owners else None
        
        base.update({
            "item_type": item_type,
            "creator": creator_val,
            "current_owner": owner_val,
            "materials": random.sample(MATERIALS, min(2, len(MATERIALS)))
        })
        
    elif entity_type == "Faction":
        faction_type = random.choice(FACTION_TYPES)
        base["name"] = f"The {faction_type} of the {random.choice(BIOMES)}"
        
        existing_leaders = get_random_entities_by_type("Character", 1)
        leader_val = f"[[{existing_leaders[0]}]]" if existing_leaders else None
        
        existing_hqs = get_random_entities_by_type("Location", 1)
        hq_val = f"[[{existing_hqs[0]}]]" if existing_hqs else None
        
        base.update({
            "leader": leader_val,
            "headquarters": hq_val,
            "goals": ["Achieve supreme control", "Protect the ancient lore", "Find the lost artifacts"],
            "allies": [],
            "enemies": []
        })
        
    elif entity_type == "Event":
        event_type = random.choice(EVENT_TYPES)
        base["name"] = f"The {event_type} of {first_name}"
        
        chars = get_random_entities_by_type("Character", 2)
        factions = get_random_entities_by_type("Faction", 1)
        participants_val = [f"[[{c}]]" for c in chars] + [f"[[{f}]]" for f in factions]
        
        locs = get_random_entities_by_type("Location", 1)
        locs_val = [f"[[{l}]]" for l in locs]
        
        base.update({
            "date": f"{random.randint(100, 2000)} A.D.",
            "participants": participants_val,
            "locations_involved": locs_val,
            "outcome": "A massive power shift in the realm."
        })
        
    elif entity_type == "Species":
        species_name = random.choice(FANTASY_SPECIES)
        base["name"] = species_name
        
        existing_locs = get_random_entities_by_type("Location", 1)
        habitat_val = f"[[{existing_locs[0]}]]" if existing_locs else None
        
        base.update({
            "lifespan": f"{random.randint(50, 500)} years",
            "native_habitat": habitat_val,
            "average_height": f"{random.randint(100, 250)} cm",
            "distinctive_features": [random.choice(ANATOMY_TRAITS), "Intelligent and magical"]
        })
        
    elif entity_type == "General":
        base["name"] = f"The Secret of {first_name}"
        
        related = get_random_all_entities(2)
        related_val = [f"[[{r}]]" for r in related]
        
        base.update({
            "related_entities": related_val,
            "category": random.choice(GENERAL_CATEGORIES)
        })
        
    return base
