from pydantic import BaseModel, Field
from typing import List, Literal, Optional

class EntityBase(BaseModel):
    """Base schema for all entities in the graph database."""
    name: str = Field(description="The unique name of the entity.")
    entity_type: str = Field(description="The type of the entity.")
    summary: str = Field(description="A 1-2 sentence summary of the entity.")
    aliases: List[str] = Field(default_factory=list, description="Alternative names or titles.")
    tags: List[str] = Field(default_factory=list, description="Tags for categorization.")

class CharacterModel(EntityBase):
    """Schema for Character entities."""
    entity_type: Literal["Character"] = "Character"
    age: Optional[str] = Field(None, description="Age of the character.")
    status: Optional[Literal["Alive", "Deceased", "Unknown"]] = Field("Unknown", description="Current living status.")
    faction_affiliations: List[str] = Field(default_factory=list, description="Factions this character belongs to.")
    current_location: Optional[str] = Field(None, description="Where the character is currently located.")
    physical_description: Optional[str] = Field(None, description="Appearance and physical traits.")
    personality_traits: List[str] = Field(default_factory=list, description="Core personality characteristics.")

class LocationModel(EntityBase):
    """Schema for Location entities."""
    entity_type: Literal["Location"] = "Location"
    region: Optional[str] = Field(None, description="The broader region this location is in.")
    climate: Optional[str] = Field(None, description="Typical weather and climate.")
    population: Optional[str] = Field(None, description="Population size or demographic makeup.")
    controlling_faction: Optional[str] = Field(None, description="The faction that controls this location.")

class ItemModel(EntityBase):
    """Schema for Item entities."""
    entity_type: Literal["Item"] = "Item"
    item_type: Optional[str] = Field(None, description="Type of item (e.g., Weapon, Artifact, Consumable).")
    creator: Optional[str] = Field(None, description="Who or what created this item.")
    current_owner: Optional[str] = Field(None, description="Who currently possesses this item.")
    materials: List[str] = Field(default_factory=list, description="Materials used to make the item.")

class FactionModel(EntityBase):
    """Schema for Faction entities."""
    entity_type: Literal["Faction"] = "Faction"
    leader: Optional[str] = Field(None, description="The current leader of the faction.")
    headquarters: Optional[str] = Field(None, description="The main base of operations.")
    goals: List[str] = Field(default_factory=list, description="Primary objectives of the faction.")
    allies: List[str] = Field(default_factory=list, description="Factions allied with this one.")
    enemies: List[str] = Field(default_factory=list, description="Factions opposed to this one.")

class EventModel(EntityBase):
    """Schema for Event entities."""
    entity_type: Literal["Event"] = "Event"
    date: Optional[str] = Field(None, description="When the event occurred.")
    participants: List[str] = Field(default_factory=list, description="Key characters or factions involved.")
    locations_involved: List[str] = Field(default_factory=list, description="Where the event took place.")
    outcome: Optional[str] = Field(None, description="The result or consequence of the event.")

class SpeciesModel(EntityBase):
    """Schema for Species entities."""
    entity_type: Literal["Species"] = "Species"
    lifespan: Optional[str] = Field(None, description="Average lifespan.")
    native_habitat: Optional[str] = Field(None, description="Where this species originates.")
    average_height: Optional[str] = Field(None, description="Typical physical stature.")
    distinctive_features: List[str] = Field(default_factory=list, description="Unique biological or cultural traits.")

class GeneralLoreModel(EntityBase):
    """Schema for General Lore, Magic Systems, Concepts, and Quests."""
    entity_type: Literal["General"] = "General"
    related_entities: List[str] = Field(default_factory=list, description="Entities related to this concept.")
    category: Optional[str] = Field(None, description="Category of lore (e.g., Magic System, Holiday, Concept, Quest).")
