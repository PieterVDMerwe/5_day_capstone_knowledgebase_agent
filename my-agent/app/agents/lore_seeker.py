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
        else:
            # Fallback: scan query for mentioned entity names in the DB to build relevant context
            from ..database import get_all_entities
            try:
                entities = get_all_entities()
                for ent in entities:
                    if ent["name"].lower() in query.lower():
                        context += get_entity_graph(ent["name"]) + "\n"
            except Exception:
                pass
            
        prompt = f"Context:\n{context}\n\nUser Query: {query}"
        return self.llm.generate(prompt=prompt, system_instruction=LORE_SEEKER_PROMPT)
