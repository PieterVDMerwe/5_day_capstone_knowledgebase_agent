from ..llm_client import LLMClient
from ..prompts.system_prompts import TRUTH_KEEPER_PROMPT
from ..context_tools import get_entity_graph

class TruthKeeper:
    """Agent responsible for checking logical consistency of drafted lore against the graph."""
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def validate_logic(self, draft: dict, related_entities: list[str]) -> str:
        context = ""
        for name in related_entities:
            context += get_entity_graph(name) + "\n"
            
        prompt = f"Graph Context:\n{context}\n\nDraft to Review:\n{draft}"
        return self.llm.generate(prompt=prompt, system_instruction=TRUTH_KEEPER_PROMPT)
