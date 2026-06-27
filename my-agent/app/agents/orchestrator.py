from ..llm_client import LLMClient
from ..prompts.system_prompts import ORCHESTRATOR_PROMPT

class Orchestrator:
    """Router agent that determines which sub-agent should handle a user request."""
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def route_request(self, user_request: str) -> str:
        """Routes to either 'lore_seeker' or 'editor_agent'."""
        route = self.llm.generate(prompt=user_request, system_instruction=ORCHESTRATOR_PROMPT)
        route = route.strip().lower()
        if "editor" in route or "draft" in route or "create" in route:
            return "editor_agent"
        return "lore_seeker"
