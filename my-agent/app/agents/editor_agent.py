import json
from ..llm_client import LLMClient
from ..prompts.system_prompts import EDITOR_AGENT_PROMPT
from ..validators import validate_entity_data, MODEL_MAP

class EditorAgent:
    """Agent responsible for drafting structured JSON matching the flat Pydantic schemas."""
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def draft_entity(self, request: str, entity_type: str) -> dict:
        if entity_type not in MODEL_MAP:
            entity_type = "General"
            
        model_class = MODEL_MAP[entity_type]
        prompt = f"Draft an entity of type {entity_type} based on this request: {request}"
        
        # Enforce Pydantic schema constraints directly via LLM config (if supported by provider)
        raw_json_str = self.llm.generate(
            prompt=prompt, 
            system_instruction=EDITOR_AGENT_PROMPT, 
            response_schema=model_class
        )
        
        try:
            # Some providers return markdown fenced json
            if raw_json_str.startswith("```json"):
                raw_json_str = raw_json_str[7:-3].strip()
            data = json.loads(raw_json_str)
        except json.JSONDecodeError:
            return {"error": "LLM failed to output valid JSON"}
            
        # Run through our static linter and fuzzy enum mapper
        is_valid, cleaned_data, msg = validate_entity_data(data)
        
        if not is_valid:
            # We use static recovery only. Let the user see the linter error.
            cleaned_data["_linter_error"] = msg
            
        return cleaned_data
