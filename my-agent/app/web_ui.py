import os
import re
import difflib
import time

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel

from .agent import check_prompt_injection, lore_seeker, truth_keeper, model_name
from .database import (
    get_all_entities,
    get_metadata,
    get_db_connection,
    insert_entity,
    insert_metadata,
    insert_link
)
from .parser import (
    scan_and_sync_vault,
    normalize_entity_id,
    parse_frontmatter,
    extract_wiki_links
)
from .validators import run_all_validators

app = FastAPI(title="Obsidian Lore Companion")

VAULT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "Knowledgebase", "Obsidian"))

import json
from datetime import date

USAGE_FILE = os.path.join(os.path.dirname(__file__), "llm_usage.json")

def get_persisted_usage():
    today = str(date.today())
    default_data = {
        "date": today,
        "daily_calls": 0,
        "total_calls": 0,
        "prompt_tokens": 0,
        "candidates_tokens": 0,
        "total_tokens": 0
    }
    if os.path.exists(USAGE_FILE):
        try:
            with open(USAGE_FILE, "r") as f:
                data = json.load(f)
                if data.get("date") == today:
                    return data
                else:
                    data["date"] = today
                    data["daily_calls"] = 0
                    return data
        except Exception:
            return default_data
    return default_data

def save_persisted_usage(data):
    try:
        with open(USAGE_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass

# LLM Token & Rate Limit Usage Tracking
LLM_USAGE = {
    "total_calls": 0,
    "prompt_tokens": 0,
    "candidates_tokens": 0,
    "total_tokens": 0,
    "timestamps": []  # List of timestamps for requests made in the last 60 seconds
}

# Pydantic schema for requests
class QueryRequest(BaseModel):
    message: str

class SaveDraftRequest(BaseModel):
    title: str
    content: str
    diff_only: bool = True

# Sync DB on startup
@app.on_event("startup")
def startup_event():
    scan_and_sync_vault(VAULT_PATH)

@app.get("/api/vault-path")
def get_vault_path():
    return {"path": VAULT_PATH}

@app.post("/api/sync")
def sync_vault():
    try:
        scan_and_sync_vault(VAULT_PATH)
        return {"status": "success", "message": "Obsidian vault successfully synchronized."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

@app.get("/api/entities")
def get_entities():
    entities = get_all_entities()
    for ent in entities:
        ent["metadata"] = get_metadata(ent["id"])
    return entities

@app.get("/api/validation")
def get_validation_report():
    return run_all_validators()

@app.get("/api/llm/usage")
def get_llm_usage():
    now = time.time()
    # Filter timestamps to within the last 60 seconds
    LLM_USAGE["timestamps"] = [t for t in LLM_USAGE["timestamps"] if now - t < 60]
    
    rpm_limit = 15  # Default free tier limit is 15 RPM
    current_rpm = len(LLM_USAGE["timestamps"])
    
    usage_data = get_persisted_usage()
    rpd_limit = 20  # Gemini 2.5 Flash Free Tier daily request limit is 20 RPD
    
    return {
        "model": model_name,
        "total_calls": usage_data["total_calls"],
        "prompt_tokens": usage_data["prompt_tokens"],
        "candidates_tokens": usage_data["candidates_tokens"],
        "total_tokens": usage_data["total_tokens"],
        "current_rpm": current_rpm,
        "rpm_limit": rpm_limit,
        "rpm_pct": min(100, int((current_rpm / rpm_limit) * 100)),
        "current_rpd": usage_data["daily_calls"],
        "rpd_limit": rpd_limit,
        "rpd_pct": min(100, int((usage_data["daily_calls"] / rpd_limit) * 100))
    }

@app.get("/api/graph")
def get_graph_data():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Fetch all nodes (entities)
    cursor.execute("SELECT id, name, type, summary FROM entities")
    nodes = [dict(row) for row in cursor.fetchall()]
    
    # Fetch all edges (links)
    cursor.execute("SELECT source_id, target_id, link_type FROM links")
    edges = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return {
        "nodes": nodes,
        "edges": edges
    }

session_service = InMemorySessionService()

def run_agent(agent_instance, user_message: str) -> str:
    # Update RPM tracker
    now = time.time()
    LLM_USAGE["timestamps"].append(now)
    LLM_USAGE["total_calls"] += 1

    # Update persisted daily tracker
    usage_data = get_persisted_usage()
    usage_data["daily_calls"] += 1
    usage_data["total_calls"] += 1

    try:
        session = session_service.create_session_sync(user_id="user", app_name="worldbuilding")
        runner = Runner(agent=agent_instance, session_service=session_service, app_name="worldbuilding")

        msg = types.Content(
            role="user",
            parts=[types.Part.from_text(text=user_message)]
        )

        events = list(runner.run(
            new_message=msg,
            user_id="user",
            session_id=session.id,
            run_config=RunConfig(streaming_mode=StreamingMode.SSE)
        ))

        # Accumulate usage tokens from the final response event
        final_metadata = None
        for event in reversed(events):
            if hasattr(event, "usage_metadata") and event.usage_metadata:
                final_metadata = event.usage_metadata
                break

        if final_metadata:
            prompt_tokens = final_metadata.prompt_token_count or 0
            candidates_tokens = final_metadata.candidates_token_count or 0
            total_tokens = final_metadata.total_token_count or 0

            LLM_USAGE["prompt_tokens"] += prompt_tokens
            LLM_USAGE["candidates_tokens"] += candidates_tokens
            LLM_USAGE["total_tokens"] += total_tokens

            usage_data["prompt_tokens"] += prompt_tokens
            usage_data["candidates_tokens"] += candidates_tokens
            usage_data["total_tokens"] += total_tokens

        save_persisted_usage(usage_data)

        # Try to retrieve from the persisted session events first (robust for tool call runs)
        final_session = session_service.get_session_sync(app_name="worldbuilding", user_id="user", session_id=session.id)
        if final_session:
            for event in reversed(final_session.events):
                if event.author == agent_instance.name and event.content and event.content.parts:
                    text = "".join(part.text for part in event.content.parts if part.text)
                    if text.strip():
                        return text

        # Fallback to the yielded events
        for event in reversed(events):
            if not event.partial and event.content and event.content.parts:
                text = "".join(part.text for part in event.content.parts if part.text)
                if text.strip():
                    return text

        # Second fallback: accumulate partials
        parts_text = []
        for event in events:
            if event.partial and event.content and event.content.parts:
                parts_text.append("".join(part.text for part in event.content.parts if part.text))
        accumulated = "".join(parts_text)
        if accumulated.strip():
            return accumulated

        return "I processed your request, but was unable to formulate a text response. Please try again."

    except Exception as e:
        err_str = str(e).lower()
        if "429" in err_str or "resource_exhausted" in err_str or "rate limit" in err_str:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded: You have hit the Gemini API rate limit (429 Resource Exhausted). Please wait a minute before retrying."
            ) from e
        raise e

@app.post("/api/lore-seeker/chat")
async def chat_lore_seeker(req: QueryRequest):
    # Injection check
    warning = check_prompt_injection(req.message)
    if warning:
        return {"status": "rejected", "message": warning}

    import random
    funny_messages = [
        "My crystal ball has gone foggy! A wizard at the local tavern demands 5 silver coins (or a fresh API key) to clear it.",
        "The magic ley-lines are temporarily depleted. The sprites are taking a union-mandated nap. Try again tomorrow!",
        "Alas! The scrolls of knowledge have been locked in the High Mage's vault for the night. No more scrying today.",
        "A mischievous goblin has chewed through the arcane network fibers. The technomancers are currently hunting him down.",
        "You have summoned me too many times today! My ethereal throat is dry. Fetch me a pint of dwarven ale and ask again on the morrow.",
        "The ancient spirits are whispering: 'Come back later, we are playing cards.' Let them finish their game.",
        "Your spell slot is exhausted for the day! Rest at the nearest inn to restore your mana.",
        "The carrier owls are on strike demanding higher quality field mice. Delivery of lore is suspended until dawn.",
        "My patron deity has put my divine inspiration on cooldown. Please consult the stars again tomorrow.",
        "A dragon is currently sleeping on the database. I dare not wake it for more queries until it finishes its nap."
    ]

    usage_data = get_persisted_usage()
    if usage_data.get("daily_calls", 0) >= 20:
        return {"status": "success", "message": random.choice(funny_messages)}

    try:
        response_text = run_agent(lore_seeker, req.message)
        if not response_text or not response_text.strip():
            return {"status": "success", "message": random.choice(funny_messages)}
        return {"status": "success", "message": response_text}
    except HTTPException as he:
        if he.status_code == 429:
            return {"status": "success", "message": random.choice(funny_messages)}
        raise he
    except Exception as e:
        err_str = str(e).lower()
        if "429" in err_str or "resource_exhausted" in err_str or "rate limit" in err_str:
            return {"status": "success", "message": random.choice(funny_messages)}
        raise HTTPException(status_code=500, detail=str(e)) from e

@app.post("/api/truth-keeper/validate")
async def validate_truth_keeper(req: SaveDraftRequest):
    # Injection check
    warning = check_prompt_injection(req.content)
    if warning:
        return {"status": "rejected", "message": warning}
        
    entity_id = normalize_entity_id(req.title)
    
    # 1. Fetch original state to restore later
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM entities WHERE id = ?", (entity_id,))
    original_entity = cursor.fetchone()
    original_entity = dict(original_entity) if original_entity else None
    
    cursor.execute("SELECT key, value FROM metadata WHERE entity_id = ?", (entity_id,))
    original_meta = {row["key"]: row["value"] for row in cursor.fetchall()}
    
    cursor.execute("SELECT target_id, link_type FROM links WHERE source_id = ?", (entity_id,))
    original_links = [(row["target_id"], row["link_type"]) for row in cursor.fetchall()]
    conn.close()
    
    # 2. Parse new draft and temporarily update DB
    try:
        meta, body = parse_frontmatter(req.content)
        links = extract_wiki_links(body)
        
        # Build temp entity record
        entity_type = meta.get("type", "general").strip().lower()
        summary = meta.get("summary", body.split("\n")[0][:200].strip() if body else "")
        
        # Insert draft to DB for static validation
        insert_entity(entity_id, req.title, entity_type, summary, body, f"Temp/{req.title}.md", 0.0)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM metadata WHERE entity_id = ?", (entity_id,))
        cursor.execute("DELETE FROM links WHERE source_id = ?", (entity_id,))
        conn.commit()
        conn.close()
        
        for k, v in meta.items():
            insert_metadata(entity_id, k, str(v))
        for link in links:
            insert_link(entity_id, link)
            
        # 3. Run Static Validators
        static_issues = run_all_validators()
        # Filter issues belonging to our active draft note
        draft_issues = [iss for iss in static_issues if iss["entity_id"] == entity_id]
        
        if draft_issues:
            # Restore original DB state
            restore_db_state(entity_id, original_entity, original_meta, original_links)
            
            issues_msg = "Static Validation Warnings Found:\n" + "\n".join(
                f"- [{iss['type'].upper()}] {iss['message']}" for iss in draft_issues
            )
            return {"status": "warning", "message": issues_msg}
            
        # 4. Calculate Diff / Full Note Payload
        if req.diff_only:
            old_body = original_entity["content"] if original_entity else ""
            diff = list(difflib.unified_diff(
                old_body.splitlines(),
                body.splitlines(),
                lineterm=""
            ))
            
            # Extract added/changed lines
            added_lines = [line[1:] for line in diff if line.startswith("+") and not line.startswith("+++")]
            changed_text = "\n".join(added_lines).strip()
            
            # If no changes, return early
            if not changed_text and original_entity:
                restore_db_state(entity_id, original_entity, original_meta, original_links)
                return {"status": "success", "message": "No new changes or additions detected in the draft note."}
            
            payload = changed_text if original_entity else body
            prompt_msg = (
                f"Review the following new additions to the note '{req.title}':\n\n"
                f"{payload}\n\n"
                f"Compare these additions against the existing database facts. Are there any logical contradictions?"
            )
        else:
            payload = body
            prompt_msg = (
                f"Review the full content of the note '{req.title}':\n\n"
                f"{payload}\n\n"
                f"Compare this note against the existing database facts. Are there any logical contradictions?"
            )
            
        # 5. Call Truth-keeper Agent
        response_text = run_agent(truth_keeper, prompt_msg)
        
        # Restore original DB state
        restore_db_state(entity_id, original_entity, original_meta, original_links)
        return {"status": "success", "message": response_text}
        
    except HTTPException as he:
        restore_db_state(entity_id, original_entity, original_meta, original_links)
        raise he
    except Exception as e:
        restore_db_state(entity_id, original_entity, original_meta, original_links)
        raise HTTPException(status_code=500, detail=str(e)) from e

def restore_db_state(entity_id, original_entity, original_meta, original_links):
    """Restores the database record of an entity to its original state."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM metadata WHERE entity_id = ?", (entity_id,))
    cursor.execute("DELETE FROM links WHERE source_id = ?", (entity_id,))
    cursor.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
    conn.commit()
    conn.close()
    
    if original_entity:
        insert_entity(
            original_entity["id"],
            original_entity["name"],
            original_entity["type"],
            original_entity["summary"],
            original_entity["content"],
            original_entity["path"],
            original_entity["last_modified"]
        )
        for k, v in original_meta.items():
            insert_metadata(entity_id, k, v)
        for target, link_type in original_links:
            insert_link(entity_id, target, link_type)

@app.post("/api/draft/approve")
def approve_draft(req: SaveDraftRequest):
    filename = f"{req.title.strip()}.md"
    filepath = os.path.join(VAULT_PATH, filename)

    # Strip leading/trailing markdown code block wrappers (e.g. ```markdown)
    content = req.content.strip()
    content = re.sub(r"^```[a-zA-Z]*\r?\n", "", content)
    content = re.sub(r"\r?\n```$", "", content)

    try:
        # Create subfolders if specified in the note title (e.g. Characters/Liam)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        # Re-sync vault to index the new entity
        scan_and_sync_vault(VAULT_PATH)
        return {"status": "success", "message": f"Successfully saved to vault: {filename}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

@app.get("/", response_class=HTMLResponse)
def index_page():
    return r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Obsidian Lore Companion</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&family=JetBrains+Mono&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-dark: #0f0f15;
            --bg-panel: #161622;
            --primary: #8a2be2;
            --primary-glow: rgba(138, 43, 226, 0.4);
            --secondary: #00ffcc;
            --text-main: #f5f5f7;
            --text-muted: #8e8e9f;
            --border: #28283a;
            --error: #ff4d4d;
            --warning: #ffaa00;
            --card-hover: rgba(255, 255, 255, 0.03);
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Outfit', sans-serif;
            background-color: var(--bg-dark);
            color: var(--text-main);
            display: flex;
            height: 100vh;
            overflow: hidden;
        }

        /* Sidebar styling */
        .sidebar {
            width: 300px;
            background-color: var(--bg-panel);
            border-right: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            padding: 20px;
        }

        .logo-area {
            font-size: 1.4rem;
            font-weight: 800;
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 25px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .sync-btn {
            background: none;
            border: 1px solid var(--border);
            color: var(--text-main);
            padding: 6px 12px;
            border-radius: 8px;
            font-family: inherit;
            cursor: pointer;
            font-size: 0.8rem;
            transition: all 0.3s;
        }

        .sync-btn:hover {
            border-color: var(--secondary);
            color: var(--secondary);
        }

        .section-title {
            font-size: 0.8rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: var(--text-muted);
            margin-bottom: 10px;
        }

        .entity-list {
            flex-grow: 1;
            overflow-y: auto;
            margin-bottom: 20px;
        }

        .entity-item {
            padding: 10px 14px;
            background: rgba(255,255,255,0.01);
            border: 1px solid var(--border);
            border-radius: 8px;
            margin-bottom: 8px;
            cursor: pointer;
            transition: all 0.2s;
        }

        .entity-item:hover {
            border-color: var(--primary);
            box-shadow: 0 0 10px var(--primary-glow);
            background: var(--card-hover);
        }

        .entity-name {
            font-weight: 600;
            font-size: 0.95rem;
        }

        .entity-meta {
            font-size: 0.75rem;
            color: var(--text-muted);
            margin-top: 4px;
            word-wrap: break-word;
            word-break: break-all;
            white-space: normal;
        }

        /* Main workspace area */
        .workspace {
            flex-grow: 1;
            display: flex;
            flex-direction: column;
            padding: 20px;
            overflow-y: auto;
        }

        /* Tabs Navigation */
        .tabs-nav {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            border-bottom: 1px solid var(--border);
            padding-bottom: 10px;
        }

        .tab-link {
            background: none;
            border: none;
            color: var(--text-muted);
            font-family: inherit;
            font-size: 0.95rem;
            font-weight: 600;
            cursor: pointer;
            padding: 8px 18px;
            border-radius: 8px;
            transition: all 0.2s;
        }

        .tab-link:hover {
            color: var(--text-main);
            background-color: var(--card-hover);
        }

        .tab-link.active {
            color: var(--text-main);
            background-color: var(--primary);
            box-shadow: 0 0 12px var(--primary-glow);
        }

        .tab-content {
            display: none;
            flex-grow: 1;
        }

        .tab-content.active {
            display: flex;
            flex-direction: column;
        }

        /* Stats Row */
        .top-stats {
            display: flex;
            gap: 20px;
            margin-bottom: 20px;
        }

        .stat-card {
            flex: 1;
            background-color: var(--bg-panel);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 15px;
        }

        .stat-val {
            font-size: 1.6rem;
            font-weight: 800;
            color: var(--secondary);
        }

        /* Columns Grid */
        .main-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            flex-grow: 1;
        }

        .panel {
            background-color: var(--bg-panel);
            border: 1px solid var(--border);
            border-radius: 16px;
            display: flex;
            flex-direction: column;
            padding: 20px;
            height: 520px;
        }

        .panel-header {
            font-size: 1.05rem;
            font-weight: 600;
            margin-bottom: 15px;
            border-bottom: 1px solid var(--border);
            padding-bottom: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        /* Chat Output */
        .chat-output {
            flex-grow: 1;
            overflow-y: auto;
            background: rgba(0,0,0,0.2);
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 15px;
            font-family: inherit;
        }

        .msg {
            margin-bottom: 12px;
            line-height: 1.4;
        }

        .msg-user {
            color: var(--secondary);
            font-weight: 600;
        }

        .msg-agent {
            color: var(--text-main);
            background: rgba(255,255,255,0.02);
            padding: 8px 12px;
            border-radius: 8px;
            border-left: 3px solid var(--primary);
        }

        .input-group {
            display: flex;
            gap: 10px;
        }

        textarea {
            flex-grow: 1;
            background: var(--bg-dark);
            border: 1px solid var(--border);
            border-radius: 10px;
            color: var(--text-main);
            padding: 10px;
            font-family: inherit;
            resize: none;
            height: 60px;
        }

        textarea:focus {
            outline: none;
            border-color: var(--primary);
        }

        .btn {
            background: var(--primary);
            color: var(--text-main);
            border: none;
            border-radius: 10px;
            padding: 10px 20px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
        }

        .btn:hover {
            box-shadow: 0 0 15px var(--primary-glow);
            transform: translateY(-1px);
        }

        .btn-secondary {
            background: #2b2b3c;
            border: 1px solid var(--border);
        }

        /* Validation UI */
        .validation-area {
            background: var(--bg-panel);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 20px;
        }

        .issue-item {
            padding: 12px 16px;
            border-radius: 8px;
            margin-bottom: 8px;
            font-size: 0.95rem;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .issue-error {
            background: rgba(255, 77, 77, 0.08);
            border-left: 4px solid var(--error);
            color: #ff8080;
        }

        .issue-warning {
            background: rgba(255, 170, 0, 0.08);
            border-left: 4px solid var(--warning);
            color: #ffd480;
        }

        /* Tutorial and Guide styling */
        .tutorial-area {
            background: var(--bg-panel);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 30px;
            line-height: 1.6;
            overflow-y: auto;
            max-height: 700px;
        }

        .tutorial-area h2 {
            margin-bottom: 15px;
            color: var(--secondary);
            border-bottom: 1px solid var(--border);
            padding-bottom: 8px;
        }

        .tutorial-area h3 {
            margin: 20px 0 10px 0;
            color: #fff;
        }

        .tutorial-area p {
            margin-bottom: 15px;
            color: var(--text-main);
        }

        .tutorial-area ul {
            margin-left: 20px;
            margin-bottom: 15px;
        }

        .tutorial-area li {
            margin-bottom: 8px;
        }

        .code-block {
            background: var(--bg-dark);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 12px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85rem;
            margin: 10px 0 20px 0;
            white-space: pre-wrap;
        }

        .highlight {
            color: var(--secondary);
            font-weight: 600;
        }
    </style>
    <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
</head>
<body>
    <div class="sidebar">
        <div class="logo-area">
            <span>Wiki Companion</span>
            <button class="sync-btn" onclick="syncVault()">Sync Vault</button>
        </div>
        <div class="section-title">Lore Vault Notes</div>
        <div class="entity-list" id="entities-container">
            <!-- Entities populated dynamically -->
        </div>
        <div class="entity-meta" id="vault-path-label" style="margin-bottom: 15px;">
            Loading path...
        </div>
        <!-- Quota Meter Widget -->
        <div class="quota-widget" style="background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: 10px; padding: 12px; font-size: 0.85rem; margin-top: auto; display: flex; flex-direction: column; gap: 8px;">
            <div>
                <div style="font-weight: 600; margin-bottom: 4px; display: flex; justify-content: space-between;">
                    <span>Gemini API Quota</span>
                    <span id="quota-rpm-text">0 / 15 RPM</span>
                </div>
                <div style="background: #1a1a2e; height: 6px; border-radius: 3px; overflow: hidden;">
                    <div id="quota-bar" style="background: var(--secondary); width: 0%; height: 100%; transition: width 0.3s;"></div>
                </div>
            </div>
            <div>
                <div style="font-weight: 600; margin-bottom: 4px; display: flex; justify-content: space-between;">
                    <span>Daily Limit</span>
                    <span id="quota-rpd-text">0 / 1500 RPD</span>
                </div>
                <div style="background: #1a1a2e; height: 6px; border-radius: 3px; overflow: hidden;">
                    <div id="quota-rpd-bar" style="background: var(--primary); width: 0%; height: 100%; transition: width 0.3s;"></div>
                </div>
            </div>
            <div style="color: var(--text-muted); display: flex; flex-direction: column; gap: 4px; border-top: 1px solid var(--border); padding-top: 6px; font-size: 0.75rem;">
                <div style="display: flex; justify-content: space-between;">
                    <span>Calls: <span id="quota-calls">0</span></span>
                    <span>Tokens: <span id="quota-tokens">0</span></span>
                </div>
                <div style="color: var(--text-muted); font-size: 0.75rem; text-align: left;">
                    Model: <span id="quota-model" style="color: var(--secondary); font-family: monospace;">Loading...</span>
                </div>
            </div>
        </div>
    </div>

    <div class="workspace">
        <!-- Tabs Navigation -->
        <div class="tabs-nav">
            <button class="tab-link active" onclick="switchTab(event, 'tab-seeker')">Lore-seeker (Generator)</button>
            <button class="tab-link" onclick="switchTab(event, 'tab-keeper')">Truth-keeper & Draft Editor</button>
            <button class="tab-link" onclick="switchTab(event, 'tab-graph'); loadGraph();">Interactive Graph</button>
            <button class="tab-link" onclick="switchTab(event, 'tab-validation')">Validation & Warnings</button>
            <button class="tab-link" onclick="switchTab(event, 'tab-tutorial')">How to Use (Tutorial)</button>
        </div>

        <!-- TAB 1: LORE-SEEKER GENERATOR -->
        <div id="tab-seeker" class="tab-content active">
            <div class="top-stats">
                <div class="stat-card">
                    <div class="section-title">Total Lore Entities</div>
                    <div class="stat-val" id="stat-count">0</div>
                </div>
                <div class="stat-card">
                    <div class="section-title">Vault Path</div>
                    <div style="font-size: 0.9rem; margin-top: 8px;" id="stat-path">None</div>
                </div>
            </div>

            <div class="main-grid">
                <!-- Lore-seeker Panel -->
                <div class="panel">
                    <div class="panel-header">
                        <span>Lore-seeker (Creative Generator)</span>
                    </div>
                    <div class="chat-output" id="seeker-output">
                        <div class="msg msg-agent">Welcome back! Describe the character, item, or place you want to generate. I'll automatically verify connections before making recommendations.</div>
                    </div>
                    <div class="input-group">
                        <textarea id="seeker-input" placeholder="Prompt the Lore-seeker to generate a note..."></textarea>
                        <button class="btn" onclick="askLoreSeeker()">Generate</button>
                    </div>
                </div>

                <!-- Seeker Draft Editor -->
                <div class="panel">
                    <div class="panel-header">
                        <span>Draft Editor</span>
                        <div style="display: flex; gap: 8px; align-items: center;">
                            <select id="template-select" style="background: #22223b; border: 1px solid var(--border); color: var(--text-main); border-radius: 8px; padding: 4px 8px; font-size: 0.8rem; font-family: inherit; outline: none; cursor: pointer;">
                                <option value="general">General Note</option>
                                <option value="character">Character</option>
                                <option value="location">Location</option>
                                <option value="item">Item</option>
                                <option value="faction">Faction</option>
                            </select>
                            <button class="btn btn-secondary" onclick="createNewNote()" style="padding: 4px 12px; font-size: 0.8rem; background: #22223b; border-color: var(--primary);">New Note</button>
                            <button class="btn btn-secondary" onclick="approveDraft('draft-editor-seeker')" style="padding: 4px 12px; font-size: 0.8rem;">Save & Approve</button>
                        </div>
                    </div>
                    <textarea id="draft-editor-seeker" oninput="syncEditors('draft-editor-seeker', 'draft-editor-keeper')" style="flex-grow: 1; height: auto; font-family: 'JetBrains Mono', monospace; font-size: 0.85rem;" placeholder="Generated Markdown draft content will appear here. Edit it freely."></textarea>
                </div>
            </div>
        </div>

        <!-- TAB 2: TRUTH-KEEPER CONSISTENCY -->
        <div id="tab-keeper" class="tab-content">
            <div class="main-grid">
                <!-- Keeper Draft Editor -->
                <div class="panel" style="height: 600px;">
                    <div class="panel-header">
                        <span>Active Note Editor</span>
                        <button class="btn btn-secondary" onclick="approveDraft('draft-editor-keeper')" style="padding: 4px 12px; font-size: 0.8rem;">Save & Approve</button>
                    </div>
                    <textarea id="draft-editor-keeper" oninput="syncEditors('draft-editor-keeper', 'draft-editor-seeker')" style="flex-grow: 1; height: auto; font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; margin-bottom: 15px;" placeholder="Active Markdown content. Edit it freely and run conflict checks."></textarea>
                    <button class="btn" style="background: var(--primary);" onclick="askTruthKeeper()">Check Conflict</button>
                </div>

                <!-- Truth-keeper Console -->
                <div class="panel" style="height: 600px;">
                    <div class="panel-header">
                        <span>Truth-keeper Conflict Inspector</span>
                        <div style="display: flex; gap: 8px; align-items: center; font-size: 0.85rem; color: var(--text-muted);">
                            <label style="cursor: pointer; display: flex; align-items: center; gap: 4px;">
                                <input type="checkbox" id="validation-diff-toggle" checked style="cursor: pointer; height: auto; width: auto; margin: 0;"> Changed Bits Only
                            </label>
                        </div>
                    </div>
                    <div class="chat-output" id="keeper-output" style="height: auto; flex-grow: 1;">
                        <div class="msg msg-agent">Click "Check Conflict" on the editor to inspect your additions. The system will run fast static validation checks first, then compare changed diff lines with existing database facts to check for semantic contradictions.</div>
                    </div>
                </div>
            </div>
        </div>

        <!-- TAB 2: VALIDATION -->
        <div id="tab-validation" class="tab-content">
            <div class="validation-area">
                <div class="panel-header">
                    <span>Deterministic Consistency Checks</span>
                    <button class="sync-btn" onclick="syncVault()">Run Full Validate</button>
                </div>
                <div id="validation-container" style="margin-top: 15px;">
                    <div style="color: var(--text-muted); font-size: 0.95rem;">No validation issues reported.</div>
                </div>
            </div>
        </div>

        <!-- TAB: RELATIONSHIP GRAPH -->
        <div id="tab-graph" class="tab-content">
            <div class="panel" style="height: calc(100vh - 120px); position: relative;">
                <div class="panel-header">
                    <span>Interactive Lore Graph</span>
                    <button class="sync-btn" onclick="loadGraph()">Reload Graph</button>
                </div>
                <div id="lore-graph-container" style="flex-grow: 1; height: 100%; background: #0f0f15; border-radius: 8px;"></div>
            </div>
        </div>

        <!-- TAB 3: TUTORIAL / GUIDE -->
        <div id="tab-tutorial" class="tab-content">
            <div class="tutorial-area">
                <h2>Lore Wiki Companion - User Guide</h2>
                <p>Welcome! This application acts as a companion validator and generator for your <span class="highlight">Obsidian Lore Wiki</span>. It indexes markdown files, verifies constraints statically using an SQLite DB, and provides agentic creation assistance.</p>

                <h3>Core Workflow</h3>
                <ul>
                    <li><strong>Step 1: Generate Lore</strong> - Type a request into the <strong>Lore-seeker</strong> console (e.g. <i>"Create a wizard character named Eldrin"</i>). The agent uses the database to research existing entities and writes a Markdown note draft.</li>
                    <li><strong>Step 2: Inspect Draft</strong> - The draft loads in the <strong>Draft Editor</strong>. You can manually tweak the frontmatter header or body content.</li>
                    <li><strong>Step 3: Check Conflicts</strong> - Copy/paste your edits into the <strong>Truth-keeper</strong> input (bottom-right) and check for logical or semantic contradictions.</li>
                    <li><strong>Step 4: Save & Approve</strong> - Click <strong>Save & Approve</strong>. The note is cleaned, structured directories are created if needed, and the file is written directly to your Obsidian vault.</li>
                </ul>

                <h3>Managing Subfolders & Organization</h3>
                <p>You can organize your Obsidian vault by placing notes in subfolders (e.g. <code>Characters/</code> or <code>Locations/Oakhaven/</code>). The app will automatically create any folder structures specified in the note name upon approval.</p>
                <div class="code-block">
name: "Characters/Liam the Blacksmith"  => Saves to: [Vault Path]/Characters/Liam the Blacksmith.md
name: "Locations/The Rusty Anvil"       => Saves to: [Vault Path]/Locations/The Rusty Anvil.md
                </div>

                <h3>Formatting Templates</h3>
                <p>To enable deterministic validation, ensure your notes contain clean YAML frontmatter. Select a template using the dropdown in the workspace tab, or use the formats below:</p>
                
                <h4>Character Schema</h4>
                <div class="code-block">
---
name: "Eldrin the Wise"
type: "character"
species: "human" # human | elf | dwarf | unknown | etc. (determines lifespan limit)
summary: "An old wizard."
status: "active" # active | deceased | unknown
location: "Oakhaven Town" # Must link to Location note, or "unknown"
age: "82" # Integer age or "unknown"
birth_year: "1210" # Optional (supports fantasy eras, e.g. 4E 201)
death_year: "unknown" # Optional (use unknown if still alive)
faction: "Mages Guild" # Optional - Must link to Faction, or "unknown"
relationships:
  positive:
    - "[[Maeve the Barkeep]] (friend)" # Wiki link with optional qualifier
  neutral: []
  negative: []
---
                </div>

                <h4>Location Schema</h4>
                <div class="code-block">
---
name: "Oakhaven Town"
type: "location"
summary: "A peaceful, rustic settlement."
region: "Great Oak Forest" # Region name or "unknown"
place_type: "town" # town | tavern | landmark | dungeon | etc.
---
                </div>

                <h4>Item Schema</h4>
                <div class="code-block">
---
name: "Sunfire Staff"
type: "item"
summary: "A golden staff emitting solar rays."
owner: "Eldrin the Wise" # Optional Character link, or "unknown"
origin: "Great Oak Forest" # Optional Location link, or "unknown"
location: "unknown" # Current Location link, or "unknown"
rarity: "legendary" # common | rare | legendary | unique
---
                </div>

                <h4>Faction Schema</h4>
                <div class="code-block">
---
name: "Mages Guild"
type: "faction"
summary: "An organization of arcane practitioners."
headquarters: "Oakhaven Town" # Location link, or "unknown"
leader: "Eldrin the Wise" # Character link, or "unknown"
---
                </div>

                <h3>Interactive Validation Reports</h3>
                <p>Under the <strong>Validation & Warnings</strong> tab, the app reports deterministic issues without using LLM API tokens. This tracks:</p>
                <ul>
                    <li><strong style="color: var(--error);">Timeline Conflicts:</strong> Flagging if a character's death year occurs before their birth year, or if their lifespan exceeds 150 years.</li>
                    <li><strong style="color: var(--warning);">Broken Links:</strong> Detecting wiki links <code>[[Link]]</code> referencing notes that don't exist.</li>
                    <li><strong style="color: var(--warning);">Missing Fields:</strong> Highlighting notes missing required template information (e.g. characters missing status).</li>
                </ul>
            </div>
        </div>
    </div>

    <script>
        let globalEntities = [];

        // Load initial data
        window.onload = async () => {
            await loadVaultPath();
            await refreshData();
        };

        function switchTab(evt, tabId) {
            // Hide all tab contents
            const contents = document.getElementsByClassName("tab-content");
            for (let i = 0; i < contents.length; i++) {
                contents[i].classList.remove("active");
            }

            // Remove active class from all buttons
            const links = document.getElementsByClassName("tab-link");
            for (let i = 0; i < links.length; i++) {
                links[i].classList.remove("active");
            }

            // Show active tab
            document.getElementById(tabId).classList.add("active");
            evt.currentTarget.classList.add("active");
        }

        async function loadVaultPath() {
            const res = await fetch('/api/vault-path');
            const data = await res.json();
            document.getElementById('vault-path-label').innerText = "Path: " + data.path;
            document.getElementById('stat-path').innerText = data.path;
        }

        async function updateQuotaMeter() {
            try {
                const res = await fetch('/api/llm/usage');
                const data = await res.json();
                document.getElementById('quota-rpm-text').innerText = `${data.current_rpm} / ${data.rpm_limit} RPM`;
                document.getElementById('quota-bar').style.width = `${data.rpm_pct}%`;
                
                document.getElementById('quota-rpd-text').innerText = `${data.current_rpd} / ${data.rpd_limit} RPD`;
                document.getElementById('quota-rpd-bar').style.width = `${data.rpd_pct}%`;
                
                document.getElementById('quota-calls').innerText = data.total_calls;
                document.getElementById('quota-tokens').innerText = data.total_tokens;
                document.getElementById('quota-model').innerText = data.model;

                const bar = document.getElementById('quota-bar');
                if (data.rpm_pct > 80) {
                    bar.style.backgroundColor = 'var(--error)';
                } else if (data.rpm_pct > 50) {
                    bar.style.backgroundColor = 'var(--warning)';
                } else {
                    bar.style.backgroundColor = 'var(--secondary)';
                }

                const rpdBar = document.getElementById('quota-rpd-bar');
                if (data.rpd_pct > 80) {
                    rpdBar.style.backgroundColor = 'var(--error)';
                } else if (data.rpd_pct > 50) {
                    rpdBar.style.backgroundColor = 'var(--warning)';
                } else {
                    rpdBar.style.backgroundColor = 'var(--primary)';
                }
            } catch (e) {
                console.error("Failed to update quota meter", e);
            }
        }

        async function refreshData() {
            // Load entities
            const resEnt = await fetch('/api/entities');
            const entities = await resEnt.json();
            globalEntities = entities;

            const container = document.getElementById('entities-container');
            container.innerHTML = '';

            entities.forEach(ent => {
                const item = document.createElement('div');
                item.className = 'entity-item';
                item.onclick = () => loadEntityToEditor(ent);

                item.innerHTML = `
                    <div class="entity-name">${ent.name}</div>
                    <div class="entity-meta">Type: ${ent.type} | ID: ${ent.id}</div>
                `;
                container.appendChild(item);
            });

            document.getElementById('stat-count').innerText = entities.length;

            // Load validation issues
            const resVal = await fetch('/api/validation');
            const issues = await resVal.json();

            const valContainer = document.getElementById('validation-container');
            if (issues.length === 0) {
                valContainer.innerHTML = '<div style="color: var(--text-muted); font-size: 0.95rem;">No validation issues reported.</div>';
            } else {
                valContainer.innerHTML = '';
                issues.forEach(issue => {
                    const item = document.createElement('div');
                    item.className = `issue-item issue-${issue.status}`;
                    item.style.cursor = 'pointer';
                    item.title = "Click to edit this note";
                    item.onclick = () => selectEntityById(issue.entity_id);
                    item.innerHTML = `<strong>${issue.type.toUpperCase()}:</strong> ${issue.message}`;
                    valContainer.appendChild(item);
                });
            }

            await updateQuotaMeter();
        }

        function selectEntityById(entityId) {
            const ent = globalEntities.find(e => e.id === entityId);
            if (ent) {
                loadEntityToEditor(ent);
                // Switch tab to the keeper/editor tab
                const keeperTabBtn = Array.from(document.querySelectorAll('.tab-link')).find(btn => btn.innerText.includes('Truth-keeper'));
                if (keeperTabBtn) {
                    keeperTabBtn.click();
                }
            } else {
                alert("Could not find the associated note in the database.");
            }
        }

        async function syncVault() {
            const res = await fetch('/api/sync', { method: 'POST' });
            const data = await res.json();
            alert(data.message);
            await refreshData();
        }

        function syncEditors(srcId, destId) {
            document.getElementById(destId).value = document.getElementById(srcId).value;
        }

        function loadEntityToEditor(ent) {
            let frontmatter = "---\n";
            frontmatter += `name: "${ent.name}"\n`;
            frontmatter += `type: "${ent.type}"\n`;
            for (const [k, v] of Object.entries(ent.metadata)) {
                if (k !== 'name' && k !== 'type') {
                    frontmatter += `${k}: ${v}\n`;
                }
            }
            frontmatter += "---\n";

            const fullContent = frontmatter + ent.content;
            document.getElementById('draft-editor-seeker').value = fullContent;
            document.getElementById('draft-editor-keeper').value = fullContent;
        }

        function createNewNote() {
            const templateType = document.getElementById('template-select').value;
            let template = "";
            if (templateType === 'character') {
                template = "---\nname: \"New Character\"\ntype: \"character\"\nspecies: \"human\"\nsummary: \"\"\nstatus: \"active\"\nlocation: \"unknown\"\nage: \"unknown\"\nbirth_year: \"unknown\"\ndeath_year: \"unknown\"\nfaction: \"unknown\"\nrelationships:\n  positive: []\n  neutral: []\n  negative: []\n---\n\nProse description here...";
            } else if (templateType === 'location') {
                template = "---\nname: \"New Location\"\ntype: \"location\"\nsummary: \"\"\nregion: \"unknown\"\nplace_type: \"town\"\n---\n\nProse description here...";
            } else if (templateType === 'item') {
                template = "---\nname: \"New Item\"\ntype: \"item\"\nsummary: \"\"\nowner: \"unknown\"\norigin: \"unknown\"\nlocation: \"unknown\"\nrarity: \"common\"\n---\n\nProse description here...";
            } else if (templateType === 'faction') {
                template = "---\nname: \"New Faction\"\ntype: \"faction\"\nsummary: \"\"\nheadquarters: \"unknown\"\nleader: \"unknown\"\n---\n\nProse description here...";
            } else {
                template = "---\nname: \"New Note\"\ntype: \"general\"\nsummary: \"\"\n---\n\nWrite note content here...";
            }
            document.getElementById('draft-editor-seeker').value = template;
            document.getElementById('draft-editor-keeper').value = template;
        }

        async function askLoreSeeker() {
            const inputEl = document.getElementById('seeker-input');
            const text = inputEl.value.trim();
            if (!text) return;

            appendMsg('seeker-output', 'User', text);
            inputEl.value = '';

            const res = await fetch('/api/lore-seeker/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text })
            });

            if (res.status === 429 || res.status === 500) {
                const errData = await res.json();
                alert(errData.detail || "An error occurred");
                appendMsg('seeker-output', 'System Error', errData.detail || "An error occurred");
                await updateQuotaMeter();
                return;
            }

            const data = await res.json();
            appendMsg('seeker-output', 'Lore-seeker', data.message);

            if (data.message.includes('---')) {
                document.getElementById('draft-editor-seeker').value = data.message;
                document.getElementById('draft-editor-keeper').value = data.message;
            }
            await updateQuotaMeter();
        }

        async function askTruthKeeper() {
            const content = document.getElementById('draft-editor-keeper').value.trim();
            if (!content) {
                alert("Please write or select a note first.");
                return;
            }

            // Simple title extraction
            const titleMatch = content.match(/name:\s*"(.*?)"/) || content.match(/name:\s*(.*?)\n/);
            let title = "";
            if (titleMatch) {
                title = titleMatch[1].replace(/['"]/g, '').trim();
            } else {
                title = prompt("Enter a filename title for this note to run validation:");
            }
            if (!title) return;

            const diffOnly = document.getElementById('validation-diff-toggle').checked;

            appendMsg('keeper-output', 'User (Verification Request)', `Checking conflicts for "${title}" (Diff only: ${diffOnly})...`);

            const res = await fetch('/api/truth-keeper/validate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title, content, diff_only: diffOnly })
            });

            if (res.status === 429 || res.status === 500) {
                const errData = await res.json();
                alert(errData.detail || "An error occurred");
                appendMsg('keeper-output', 'System Error', errData.detail || "An error occurred");
                await updateQuotaMeter();
                return;
            }

            const data = await res.json();
            appendMsg('keeper-output', 'Truth-keeper', data.message);
            await updateQuotaMeter();
        }

        let network = null;
        async function loadGraph() {
            const res = await fetch('/api/graph');
            const data = await res.json();
            
            const nodesArray = data.nodes.map(node => {
                let color = '#8a2be2'; // default character purple
                if (node.type === 'location') color = '#00ffcc'; // teal
                else if (node.type === 'item') color = '#ffaa00'; // orange
                else if (node.type === 'faction') color = '#ff4d4d'; // red
                
                return {
                    id: node.id,
                    label: node.name,
                    title: `Type: ${node.type}\nSummary: ${node.summary || 'None'}`,
                    color: {
                        background: color,
                        border: '#28283a',
                        highlight: { background: color, border: '#fff' }
                    },
                    font: { color: '#f5f5f7' },
                    shape: 'dot',
                    size: 20
                };
            });
            
            const seenPairs = new Set();
            const edgesArray = [];
            data.edges.forEach(edge => {
                const u = edge.source_id;
                const v = edge.target_id;
                if (u === v) return; // skip self-loops
                const pairKey = u < v ? `${u}-${v}` : `${v}-${u}`;
                if (!seenPairs.has(pairKey)) {
                    seenPairs.add(pairKey);
                    edgesArray.push({
                        from: u,
                        to: v,
                        label: edge.link_type !== 'wiki' ? edge.link_type : '',
                        arrows: 'to',
                        color: { color: '#28283a', highlight: '#8a2be2' },
                        font: { color: '#8e8e9f', size: 10, align: 'top' }
                    });
                }
            });
            
            const container = document.getElementById('lore-graph-container');
            const graphData = {
                nodes: new vis.DataSet(nodesArray),
                edges: new vis.DataSet(edgesArray)
            };
            
            const options = {
                physics: {
                    stabilization: true,
                    barnesHut: {
                        gravitationalConstant: -4000,
                        centralGravity: 0.15,
                        springLength: 180
                    }
                },
                interaction: {
                    hover: true,
                    tooltipDelay: 200
                }
            };
            
            if (network) network.destroy();
            network = new vis.Network(container, graphData, options);
            
            // Double-click a node to load it into the editor and switch to the editor tab
            network.on("doubleClick", function (params) {
                if (params.nodes.length > 0) {
                    const nodeId = params.nodes[0];
                    selectEntityById(nodeId);
                }
            });
        }

        async function approveDraft(editorId) {
            const content = document.getElementById(editorId).value;
            if (!content) {
                alert("Draft editor is empty.");
                return;
            }

            // Simple title extraction
            const titleMatch = content.match(/name:\s*"(.*?)"/) || content.match(/name:\s*(.*?)\n/);
            let title = "";
            if (titleMatch) {
                title = titleMatch[1].replace(/['"]/g, '').trim();
            } else {
                title = prompt("Enter a filename title for this note:");
            }

            if (!title) return;

            const res = await fetch('/api/draft/approve', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title, content })
            });
            const data = await res.json();
            alert(data.message);
            await refreshData();
        }

        function appendMsg(containerId, sender, text) {
            const container = document.getElementById(containerId);
            const msg = document.createElement('div');
            msg.className = 'msg';

            if (sender === 'User' || sender.startsWith('User')) {
                msg.innerHTML = `<span class="msg-user">${sender}:</span> ${text}`;
            } else {
                msg.className += ' msg-agent';
                msg.innerHTML = `<strong>${sender}:</strong> <pre style="white-space: pre-wrap; font-family: inherit;">${text}</pre>`;
            }
            container.appendChild(msg);
            container.scrollTop = container.scrollHeight;
        }
    </script>
</body>
</html>
    """

def run_server(port: int = 8000):
    uvicorn.run("app.web_ui:app", host="127.0.0.1", port=port, reload=True)
