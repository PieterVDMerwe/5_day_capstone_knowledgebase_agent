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

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # Shutdown hook: unload Ollama model to free VRAM
    if llm_client.provider == "ollama" and llm_client.model_name:
        try:
            import ollama
            print(f"Unloading Ollama model: {llm_client.model_name}")
            ollama.generate(model=llm_client.model_name, prompt="", keep_alive=0)
            print("Ollama model unloaded successfully.")
        except Exception as e:
            print(f"Failed to unload Ollama model on shutdown: {e}")

app = FastAPI(title="Lore Vault API", lifespan=lifespan)

from app.wizard_generators import generate_suggested_fields

# Universal Protocol Envelope ensuring UI consistency
class ApiResponse(BaseModel):
    status: str
    current_step: str
    data: Any
    message: str

class ChatRequest(BaseModel):
    user_message: str
    chat_mode: Optional[str] = "lore_base" # "lore_base" or "direct_llm"
    draft_state: Optional[Dict[str, Any]] = None
    chat_history: Optional[List[Dict[str, str]]] = None
    provider: Optional[str] = "gemini"
    model: Optional[str] = "gemini-2.5-flash"

class SaveRequest(BaseModel):
    draft_state: Dict[str, Any]
    connections_to_remove: Optional[List[str]] = None
    provider: Optional[str] = "gemini"
    model: Optional[str] = "gemini-2.5-flash"

class WizardContentRequest(BaseModel):
    draft_state: Dict[str, Any]
    instruction: Optional[str] = ""
    provider: Optional[str] = "gemini"
    model: Optional[str] = "gemini-2.5-flash"

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
        if req.provider:
            llm_client.provider = req.provider
        if req.model:
            llm_client.model_name = req.model
            
        if req.chat_mode == "direct_llm":
            # Simple text prompt without RAG/context
            answer = llm_client.generate(prompt=req.user_message)
            return ApiResponse(
                status="success",
                current_step="Direct LLM Answered",
                data={"answer": answer, "route": "direct_llm"},
                message="LLM responded directly."
            )
        else: # lore_base
            context_entity = None
            if req.draft_state and "name" in req.draft_state:
                context_entity = req.draft_state["name"]
                
            answer = lore_seeker.answer_query(req.user_message, context_entity)
            return ApiResponse(
                status="success",
                current_step="Query Answered",
                data={"answer": answer, "route": "lore_base"},
                message="Successfully queried the lore base."
            )
            
    except Exception as e:
        return ApiResponse(status="error", current_step="Processing Error", data=None, message=str(e))


@app.post("/api/save", response_model=ApiResponse)
async def save_endpoint(req: SaveRequest):
    """Full Pipeline: Validate Schema -> Validate Logic -> Insert Links -> Save File -> Sync to DB"""
    try:
        from app.validators import validate_entity_data
        
        if req.provider:
            llm_client.provider = req.provider
        if req.model:
            llm_client.model_name = req.model
            
        draft = req.draft_state
        
        # 0. Schema Validation
        # Any draft saved through this endpoint is now populated
        draft["is_empty"] = False
        
        is_valid, cleaned_draft, linter_msg = validate_entity_data(draft)
        if not is_valid:
            return ApiResponse(
                status="error",
                current_step="Schema Validation Failed",
                data={"linter_report": linter_msg, "draft": draft},
                message=f"Schema validation failed: {linter_msg}"
            )
        draft = cleaned_draft
        name = draft.get("name", "Unknown")
        
        # 1. Truth Keeper validation
        from app.parser import extract_all_wiki_links
        related = extract_all_wiki_links(draft)
            
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
            
        # 2.5 Generate stubs for missing wikilinks
        from app.parser import extract_all_wiki_links
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM entities")
        known_entities = {row["name"] for row in cursor.fetchall()}
        conn.close()
        
        all_links = extract_all_wiki_links(draft)
        for link in all_links:
            if link not in known_entities and link != name:
                stub_draft = {
                    "name": link,
                    "entity_type": "General",
                    "is_empty": True,
                    "summary": f"Auto-generated empty stub for {link}."
                }
                stub_filepath = write_entity_to_vault(stub_draft)
                sync_single_file(stub_filepath)
                known_entities.add(link)

        # 3. Write to file
        filepath = write_entity_to_vault(draft)
        
        # 4. Trigger O(1) Sync
        sync_single_file(filepath)
        
        # Remove selected connections if requested
        if req.connections_to_remove:
            from app.database import get_db_connection
            conn = get_db_connection()
            cursor = conn.cursor()
            for source in req.connections_to_remove:
                cursor.execute("DELETE FROM edges WHERE source_name = ? AND target_name = ?", (source, name))
                cursor.execute("DELETE FROM memberships WHERE entity_name = ? AND faction_name = ?", (source, name))
                cursor.execute("DELETE FROM containment WHERE item_name = ? AND location_name = ?", (source, name))
            conn.commit()
            conn.close()
        
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
        cursor.execute("SELECT name, entity_type, metadata FROM entities")
        import json
        nodes = []
        for r in cursor.fetchall():
            d = dict(r)
            meta = json.loads(d["metadata"]) if d.get("metadata") else {}
            d["is_empty"] = meta.get("is_empty", False)
            if "metadata" in d:
                del d["metadata"]
            nodes.append(d)
            
        cursor.execute("SELECT source_name, target_name, relation_type FROM edges")
        edges = [dict(r) for r in cursor.fetchall()]
        conn.close()
        
        graph_data = {
            "nodes": [{"id": n["name"], "label": n["name"], "group": n["entity_type"], "is_empty": n.get("is_empty", False)} for n in nodes],
            "links": [{"source": e["source_name"], "target": e["target_name"], "label": e["relation_type"]} for e in edges]
        }
        return ApiResponse(status="success", current_step="Graph Retrieved", data=graph_data, message=f"Retrieved {len(nodes)} nodes.")
    except Exception as e:
        return ApiResponse(status="error", current_step="Database Error", data=None, message=str(e))

@app.get("/api/entity/{name}", response_model=ApiResponse)
async def get_entity_endpoint(name: str):
    try:
        from app.database import get_entity
        from app.parser import parse_frontmatter
        
        entity = get_entity(name)
        if not entity:
            return ApiResponse(status="error", current_step="Fetch Entity", data=None, message="Entity not found")
            
        draft = {"name": entity["name"], "entity_type": entity["entity_type"]}
        if entity.get("metadata"):
            draft.update(entity["metadata"])
            
        _, body = parse_frontmatter(entity["raw_markdown"])
        draft["content"] = body
        
        return ApiResponse(status="success", current_step="Entity Fetched", data=draft, message="Loaded entity")
    except Exception as e:
        return ApiResponse(status="error", current_step="Fetch Error", data=None, message=str(e))

@app.get("/api/entity/{name}/incoming", response_model=ApiResponse)
async def get_incoming_connections(name: str):
    try:
        from app.database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. Standard wikilinks (edges)
        cursor.execute("SELECT source_name FROM edges WHERE target_name = ? AND relation_type = 'wikilink'", (name,))
        edges = [row["source_name"] for row in cursor.fetchall()]
        
        # 2. Memberships
        cursor.execute("SELECT entity_name FROM memberships WHERE faction_name = ?", (name,))
        memberships = [row["entity_name"] for row in cursor.fetchall()]
        
        # 3. Containments
        cursor.execute("SELECT item_name FROM containment WHERE location_name = ?", (name,))
        containments = [row["item_name"] for row in cursor.fetchall()]
        
        conn.close()
        
        # Combine and remove duplicates
        all_incoming = []
        for src in set(edges + memberships + containments):
            all_incoming.append({
                "source": src,
                "type": "membership" if src in memberships else ("containment" if src in containments else "wikilink")
            })
            
        return ApiResponse(
            status="success",
            current_step="Get Incoming Connections",
            data=all_incoming,
            message="Retrieved incoming connections successfully."
        )
    except Exception as e:
        return ApiResponse(status="error", current_step="Get Incoming Error", data=None, message=str(e))

@app.delete("/api/entity/{name}", response_model=ApiResponse)
async def delete_entity_endpoint(name: str):
    try:
        from app.database import delete_entity
        import os
        
        # Delete from DB
        delete_entity(name)
        
        # Delete file
        vault_dir = r"E:\Projects\5_day_capstone_knowledgebase_agent\Knowledgebase\Obsidian"
        file_path = os.path.join(vault_dir, f"{name}.md")
        if os.path.exists(file_path):
            os.remove(file_path)
            
        return ApiResponse(status="success", current_step="Entity Deleted", data=None, message=f"Deleted entity '{name}'")
    except Exception as e:
        return ApiResponse(status="error", current_step="Delete Error", data=None, message=str(e))

@app.get("/api/schemas", response_model=ApiResponse)
async def get_schemas():
    try:
        from app.validators import MODEL_MAP
        schemas = {}
        for name, model in MODEL_MAP.items():
            empty_dict = {}
            for field_name, field_info in model.model_fields.items():
                if field_name == "entity_type":
                    empty_dict[field_name] = name
                    continue
                if field_name == "is_empty":
                    continue
                    
                # Use simple types for frontend rendering
                if "list" in str(field_info.annotation).lower():
                    empty_dict[field_name] = []
                else:
                    empty_dict[field_name] = ""
                    
            schemas[name] = empty_dict
            
        return ApiResponse(status="success", current_step="Schemas Fetched", data=schemas, message="Loaded schemas")
    except Exception as e:
        return ApiResponse(status="error", current_step="Fetch Error", data=None, message=str(e))

@app.get("/api/wizard/suggest", response_model=ApiResponse)
async def wizard_suggest_endpoint(entity_type: str):
    try:
        data = generate_suggested_fields(entity_type)
        return ApiResponse(
            status="success",
            current_step="Wizard Suggestion",
            data=data,
            message="Suggested fields generated procedurally."
        )
    except Exception as e:
        return ApiResponse(status="error", current_step="Wizard Error", data=None, message=str(e))

@app.post("/api/wizard/generate-content", response_model=ApiResponse)
async def wizard_generate_content_endpoint(req: WizardContentRequest):
    try:
        import json
        if req.provider:
            llm_client.provider = req.provider
        if req.model:
            llm_client.model_name = req.model
            
        draft = req.draft_state
        prompt = (
            f"Based on the following worldbuilding metadata:\n{json.dumps(draft, indent=2)}\n\n"
        )
        if req.instruction:
            prompt += f"Special instruction/regeneration request: {req.instruction}\n\n"
            
        prompt += (
            "Generate:\n"
            "1. A 1-2 sentence 'summary' of this entity.\n"
            "2. A cohesive worldbuilding lore text 'content' (markdown body content) describing this entity, "
            "its relationships, and its role in the world.\n\n"
            "You MUST output strictly in JSON format with two keys: 'summary' and 'content'.\n"
            "Do not nest anything. Ensure the JSON is valid and clean."
        )
        
        system_instruction = (
            "You are the Editor Agent. Your job is to write a compelling lore description "
            "based strictly on the provided metadata fields. Output ONLY a clean JSON object."
        )
        
        raw_json_str = llm_client.generate(prompt=prompt, system_instruction=system_instruction)
        raw_json_str = raw_json_str.strip()
        
        import re
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_json_str, re.DOTALL)
        if json_match:
            raw_json_str = json_match.group(1)
        else:
            start = raw_json_str.find('{')
            end = raw_json_str.rfind('}')
            if start != -1 and end != -1:
                raw_json_str = raw_json_str[start:end+1]
                
        try:
            res_data = json.loads(raw_json_str)
        except Exception:
            res_data = {
                "summary": "Generated summary failed to parse.",
                "content": raw_json_str
            }
            
        return ApiResponse(
            status="success",
            current_step="Wizard Content Generated",
            data=res_data,
            message="Lore content generated by LLM."
        )
    except Exception as e:
        return ApiResponse(status="error", current_step="Wizard Content Error", data=None, message=str(e))

STATIC_DIR = os.path.join(os.path.dirname(__file__), "app", "static")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
