import os
import shutil

VAULT_DIR = r"E:\Projects\5_day_capstone_knowledgebase_agent\Knowledgebase\Obsidian"
DB_PATH = r"E:\Projects\5_day_capstone_knowledgebase_agent\my-agent\lore_vault.db"

DUMMY_FILES = {
    "Liam the Blacksmith.md": """---
name: Liam the Blacksmith
entity_type: Character
summary: A burly blacksmith who secretly crafts weapons for the Bloodrunners.
aliases: ["Liam", "The Iron Bear"]
tags: ["npc", "blacksmith", "secret"]
age: "42"
status: Alive
faction_affiliations: ["The Bloodrunners", "Iron Guild"]
current_location: Oakhaven Town
physical_description: Tall, muscular, with soot-stained hands and a thick beard.
personality_traits: ["Gruff", "Loyal", "Secretive"]
---
Liam spends most of his time at [[The Rusty Anvil Tavern]] after a long day of forging. He was once approached by [[Drakath]], asking for a custom weapon, which resulted in the creation of the [[Bloodlust Warhammer]]. He is currently located in [[Oakhaven Town]].
""",

    "Oakhaven Town.md": """---
name: Oakhaven Town
entity_type: Location
summary: A quiet logging town bordering the Whispering Woods.
aliases: ["Oakhaven", "The Logging Capital"]
tags: ["location", "town"]
region: The Northern Reaches
climate: Temperate, rainy
population: "1200"
controlling_faction: The Crown
---
[[Oakhaven Town]] is known for its timber. The most popular spot is [[The Rusty Anvil Tavern]]. It was the site of the [[Battle of Oakhaven]].
""",

    "Bloodlust Warhammer.md": """---
name: Bloodlust Warhammer
entity_type: Item
summary: A cursed warhammer that drains the life of its victims.
aliases: ["The Sanguine Smasher"]
tags: ["weapon", "cursed", "artifact"]
item_type: Weapon
creator: Liam the Blacksmith
current_owner: Drakath
materials: ["Dark Iron", "Vampiric Crystal"]
---
Forged by [[Liam the Blacksmith]], this terrifying weapon is wielded by [[Drakath]]. It is rumored to have been used during the [[Battle of Oakhaven]].
""",

    "The Bloodrunners.md": """---
name: The Bloodrunners
entity_type: Faction
summary: A ruthless band of mercenaries and assassins.
aliases: ["Blood Guild", "The Red Shadows"]
tags: ["faction", "mercenaries", "villains"]
leader: Drakath
headquarters: Unknown
goals: ["Wealth", "Chaos", "Control of the Northern Reaches"]
allies: ["Shadow Syndicate"]
enemies: ["The Crown", "Iron Guild"]
---
Led by the fearsome [[Drakath]], the Bloodrunners operate in the shadows of [[Oakhaven Town]]. They employ secret members like [[Liam the Blacksmith]].
""",

    "The Great Sundering.md": """---
name: The Great Sundering
entity_type: Event
summary: A cataclysmic magical event that split the continent in two.
aliases: ["The Breaking"]
tags: ["event", "history", "cataclysm"]
date: 1000 Years Ago
participants: ["The Ancient Magi", "The Dragons"]
locations_involved: ["The Northern Reaches"]
outcome: Creation of the Chasm of Souls
---
The Great Sundering changed the world forever. It wiped out many of the ancient [[Elves]], and altered the landscape near [[Oakhaven Town]].
""",

    "Elves.md": """---
name: Elves
entity_type: Species
summary: A long-lived, magically attuned race of humanoids.
aliases: ["The Firstborn"]
tags: ["species", "fey"]
lifespan: 1000 years
native_habitat: The Whispering Woods
average_height: 6 feet
distinctive_features: ["Pointed ears", "Glowing eyes", "Slender build"]
---
The Elves are a proud race, many of whom died during [[The Great Sundering]]. They are rarely seen in human settlements like [[Oakhaven Town]].
""",

    "Aetheric Magic.md": """---
name: Aetheric Magic
entity_type: General
summary: The fundamental system of magic relying on drawing energy from the leylines.
aliases: ["Ley-Magic", "The Weave"]
tags: ["magic", "concept"]
category: Magic System
related_entities: ["The Ancient Magi", "Elves"]
---
Aetheric magic is heavily utilized by [[Elves]]. The flow of magic was permanently disrupted during [[The Great Sundering]]. Objects like the [[Bloodlust Warhammer]] are immune to its effects.
"""
}

def seed_vault():
    print("Wiping existing DB...")
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        
    print("Wiping existing markdown files in vault...")
    for filename in os.listdir(VAULT_DIR):
        if filename.endswith(".md"):
            os.remove(os.path.join(VAULT_DIR, filename))
            
    print("Writing new dummy files...")
    for filename, content in DUMMY_FILES.items():
        filepath = os.path.join(VAULT_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
            
    print("Vault seeded successfully.")

if __name__ == "__main__":
    seed_vault()
