import json
from ..llm_client import LLMClient
from ..prompts.system_prompts import EDITOR_AGENT_PROMPT
from ..validators import validate_entity_data, MODEL_MAP

class EditorAgent:
    """Agent responsible for drafting structured JSON matching the flat Pydantic schemas."""
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def draft_entity(self, request: str, entity_type: str, current_draft: dict = None, context_graph: str = "") -> dict:
        if entity_type not in MODEL_MAP:
            entity_type = "General"
            
        model_class = MODEL_MAP[entity_type]
        prompt = f"Request: {request}\n"
        if context_graph:
            prompt += f"\nWorld Context:\n{context_graph}\n"
        if current_draft:
            prompt += f"\nCurrent Draft to modify:\n{json.dumps(current_draft, indent=2)}\n"
        
        # Enforce Pydantic schema constraints directly via LLM config (if supported by provider)
        raw_json_str = self.llm.generate(
            prompt=prompt, 
            system_instruction=EDITOR_AGENT_PROMPT, 
            response_schema=model_class
        )
        
        raw_json_str = raw_json_str.strip()
        import re
        
        # 1. Try extracting from markdown code block
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_json_str, re.DOTALL)
        if json_match:
            raw_json_str = json_match.group(1)
        else:
            # 2. Try aggressive curly brace extraction
            start = raw_json_str.find('{')
            end = raw_json_str.rfind('}')
            if start != -1 and end != -1:
                raw_json_str = raw_json_str[start:end+1]
                
        try:
            data = json.loads(raw_json_str)
        except json.JSONDecodeError:
            return {"error": f"LLM failed to output valid JSON. Raw output: {raw_json_str[:100]}..."}
            
        # Run through our static linter and fuzzy enum mapper
        is_valid, cleaned_data, msg = validate_entity_data(data)
        
        if not is_valid:
            # We use static recovery only. Let the user see the linter error.
            cleaned_data["_linter_error"] = msg
            
        return cleaned_data
