from ..llm_client import LLMClient
from ..prompts.system_prompts import LINKER_AGENT_PROMPT
from ..database import get_all_entities

class LinkerAgent:
    """Agent responsible for inserting wikilinks around known entity names in raw text."""
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def insert_links(self, draft_text: str) -> str:
        # Get all known entity names to give the LLM as context
        entities = get_all_entities()
        known_names = [e["name"] for e in entities]
        
        prompt = f"Known Entities: {', '.join(known_names)}\n\nDraft Text:\n{draft_text}"
        return self.llm.generate(prompt=prompt, system_instruction=LINKER_AGENT_PROMPT)
