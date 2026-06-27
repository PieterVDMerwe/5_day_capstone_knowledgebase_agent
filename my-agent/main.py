from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Any, Optional, Dict, List
import os

from app.llm_client import LLMClient
from app.agents.orchestrator import Orchestrator
from app.agents.lore_seeker import LoreSeeker
from app.agents.editor_agent import EditorAgent
from app.agents.linker_agent import LinkerAgent
from app.agents.truth_keeper import TruthKeeper
from app.database import get_db_connection
from app.file_writer import write_entity_to_vault
from app.parser import sync_single_file

app = FastAPI(title="Lore Vault API")

# Universal Protocol Envelope ensuring UI consistency
class ApiResponse(BaseModel):
    status: str
    current_step: str
    data: Any
    message: str

class ChatRequest(BaseModel):
    user_message: str
    draft_state: Optional[Dict[str, Any]] = None
    chat_history: Optional[List[Dict[str, str]]] = None

class SaveRequest(BaseModel):
    draft_state: Dict[str, Any]

# Initialize LLM and Agents
llm_client = LLMClient(provider="gemini")
orchestrator = Orchestrator(llm_client)
lore_seeker = LoreSeeker(llm_client)
editor_agent = EditorAgent(llm_client)
linker_agent = LinkerAgent(llm_client)
truth_keeper = TruthKeeper(llm_client)

@app.post("/api/chat", response_model=ApiResponse)
async def chat_endpoint(req: ChatRequest):
    """Stateless chat endpoint wrapping requests in the Universal Protocol Envelope."""
    try:
        route = orchestrator.route_request(req.user_message)
        
        if route == "editor_agent":
            # Heuristic for demo purposes
            entity_type = "General" 
            low_msg = req.user_message.lower()
            if "location" in low_msg or "town" in low_msg: entity_type = "Location"
            elif "item" in low_msg or "weapon" in low_msg: entity_type = "Item"
            elif "faction" in low_msg: entity_type = "Faction"
            elif "character" in low_msg or "npc" in low_msg: entity_type = "Character"
            elif "event" in low_msg: entity_type = "Event"
            elif "species" in low_msg: entity_type = "Species"
            
            draft = editor_agent.draft_entity(req.user_message, entity_type=entity_type)
            
            msg = "Draft generated successfully."
            status = "success"
            if "_linter_error" in draft:
                msg = f"Draft generated with linter warnings: {draft.pop('_linter_error')}"
                status = "warning"
                
            return ApiResponse(
                status=status,
                current_step="Drafting Complete",
                data={"draft": draft, "route": route},
                message=msg
            )
            
        else: # lore_seeker
            context_entity = None
            if req.draft_state and "name" in req.draft_state:
                context_entity = req.draft_state["name"]
                
            answer = lore_seeker.answer_query(req.user_message, context_entity)
            return ApiResponse(
                status="success",
                current_step="Query Answered",
                data={"answer": answer, "route": route},
                message="Successfully queried the lore."
            )
            
    except Exception as e:
        return ApiResponse(status="error", current_step="Processing Error", data=None, message=str(e))


@app.post("/api/save", response_model=ApiResponse)
async def save_endpoint(req: SaveRequest):
    """Full Pipeline: Validate Logic -> Insert Links -> Save File -> Sync to DB"""
    try:
        draft = req.draft_state
        name = draft.get("name", "Unknown")
        
        # 1. Truth Keeper validation
        related = []
        if "faction_affiliations" in draft and isinstance(draft["faction_affiliations"], list):
            related.extend(draft["faction_affiliations"])
            
        logic_report = truth_keeper.validate_logic(draft, related_entities=related)
        if "valid" not in logic_report.lower() and "no" not in logic_report.lower():
            return ApiResponse(
                status="warning",
                current_step="Validation Failed",
                data={"logic_report": logic_report, "draft": draft},
                message=f"Truth Keeper found inconsistencies: {logic_report}"
            )
            
        # 2. Linker Integration
        if "content" in draft and draft["content"].strip():
            linked_content = linker_agent.insert_links(draft["content"])
            draft["content"] = linked_content
            
        # 3. Write to file
        filepath = write_entity_to_vault(draft)
        
        # 4. Trigger O(1) Sync
        sync_single_file(filepath)
        
        return ApiResponse(
            status="success",
            current_step="Saved and Synced",
            data={"filepath": filepath},
            message=f"Entity '{name}' successfully saved to vault and synced to graph."
        )
    except Exception as e:
        return ApiResponse(status="error", current_step="Save Error", data=None, message=str(e))

@app.get("/api/graph", response_model=ApiResponse)
async def get_graph(entity_id: Optional[str] = None):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name, entity_type FROM entities")
        nodes = [dict(r) for r in cursor.fetchall()]
        cursor.execute("SELECT source_name, target_name, relation_type FROM edges")
        edges = [dict(r) for r in cursor.fetchall()]
        conn.close()
        
        graph_data = {
            "nodes": [{"id": n["name"], "label": n["name"], "group": n["entity_type"]} for n in nodes],
            "links": [{"source": e["source_name"], "target": e["target_name"], "label": e["relation_type"]} for e in edges]
        }
        return ApiResponse(status="success", current_step="Graph Retrieved", data=graph_data, message=f"Retrieved {len(nodes)} nodes.")
    except Exception as e:
        return ApiResponse(status="error", current_step="Database Error", data=None, message=str(e))

STATIC_DIR = os.path.join(os.path.dirname(__file__), "app", "static")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
