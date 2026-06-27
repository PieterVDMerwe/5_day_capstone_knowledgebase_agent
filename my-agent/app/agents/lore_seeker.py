from ..llm_client import LLMClient
from ..prompts.system_prompts import LORE_SEEKER_PROMPT
from ..context_tools import get_entity_graph

class LoreSeeker:
    """Agent responsible for answering questions using the Tiny Footprint Relational DSL context."""
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def answer_query(self, query: str, context_entity: str = None) -> str:
        context = ""
        if context_entity:
            context = get_entity_graph(context_entity)
            
        prompt = f"Context:\n{context}\n\nUser Query: {query}"
        return self.llm.generate(prompt=prompt, system_instruction=LORE_SEEKER_PROMPT)
