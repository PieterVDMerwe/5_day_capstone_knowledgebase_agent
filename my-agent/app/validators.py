import jellyfish
from typing import Any, Dict
from pydantic import ValidationError
from . import models

# Mapping string types to Pydantic models
MODEL_MAP = {
    "Character": models.CharacterModel,
    "Location": models.LocationModel,
    "Item": models.ItemModel,
    "Faction": models.FactionModel,
    "Event": models.EventModel,
    "Species": models.SpeciesModel,
    "General": models.GeneralLoreModel
}

def fuzzy_match_enum(value: str, options: list[str]) -> str:
    """
    Finds the closest match for a string within a list of options using Jaro-Winkler.
    Used as the Static Recovery Control Strategy to prevent LLM loop retries.
    """
    if not value or not isinstance(value, str):
        return options[-1] if options else ""
    
    best_match = None
    best_score = 0.0
    val_lower = value.lower()
    
    for opt in options:
        if val_lower == opt.lower():
            return opt
            
        score = jellyfish.jaro_winkler_similarity(val_lower, opt.lower())
        if score > best_score:
            best_score = score
            best_match = opt
            
    # If the score is decent (>0.7), return the fuzzy match
    if best_score > 0.7 and best_match:
        return best_match
    
    return options[-1] # fallback (often "Unknown" or last option)

def validate_entity_data(data: Dict[str, Any]) -> tuple[bool, Dict[str, Any], str]:
    """
    Validates a raw dictionary against the flat Pydantic models.
    Applies the Static Fuzzy Enum Mapper to automatically correct minor deviations.
    Returns (is_valid, cleaned_data, error_message).
    """
    entity_type = data.get("entity_type")
    
    # Fuzzy match entity type first if it's slightly off
    if entity_type not in MODEL_MAP:
        entity_type = fuzzy_match_enum(str(entity_type), list(MODEL_MAP.keys()))
        data["entity_type"] = entity_type

    model_class = MODEL_MAP.get(entity_type, models.GeneralLoreModel)
    
    try:
        # First attempt: strict validation
        instance = model_class(**data)
        return True, instance.model_dump(), ""
    except ValidationError as e:
        # Apply Static Fuzzy Enum Mapper for known Literals
        # We manually map the known Literals from Phase 0 to ensure high reliability
        
        for error in e.errors():
            loc = error.get("loc", [])
            if not loc:
                continue
            field_name = loc[0]
            
            if field_name == "status" and entity_type == "Character":
                bad_val = data.get("status", "")
                data["status"] = fuzzy_match_enum(str(bad_val), ["Alive", "Deceased", "Unknown"])

        # Second attempt after fuzzy correction
        try:
            instance = model_class(**data)
            return True, instance.model_dump(), "Data was fuzzy corrected."
        except ValidationError as e2:
            # If it still fails, it's a hard error (e.g. expected string got dict due to LLM nesting)
            # In our Flat Model Rule, nested dicts are illegal.
            # We can aggressively flatten them to strings as a last resort.
            for key, val in data.items():
                if isinstance(val, dict):
                    data[key] = str(val)
                elif isinstance(val, list):
                    # Ensure lists are strictly lists of strings
                    data[key] = [str(i) for i in val]
            
            # Third attempt after aggressive flattening
            try:
                instance = model_class(**data)
                return True, instance.model_dump(), "Data was aggressively flattened and fuzzy corrected."
            except ValidationError as e3:
                return False, data, str(e3)
