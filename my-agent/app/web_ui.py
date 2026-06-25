import os
import re

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel

from .agent import check_prompt_injection, lore_seeker, truth_keeper
from .database import get_all_entities, get_metadata
from .parser import scan_and_sync_vault
from .validators import run_all_validators

app = FastAPI(title="Obsidian Lore Companion")

VAULT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "Knowledgebase", "Obsidian"))

# Pydantic schema for requests
class QueryRequest(BaseModel):
    message: str

class SaveDraftRequest(BaseModel):
    title: str
    content: str

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


session_service = InMemorySessionService()

def run_agent(agent_instance, user_message: str) -> str:
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

    # Try to find the full (non-partial) event first
    for event in reversed(events):
        if not event.partial and event.content and event.content.parts:
            text = "".join(part.text for part in event.content.parts if part.text)
            if text:
                return text

    # Fallback to accumulating partials
    parts_text = []
    for event in events:
        if event.partial and event.content and event.content.parts:
            parts_text.append("".join(part.text for part in event.content.parts if part.text))
    return "".join(parts_text)

@app.post("/api/lore-seeker/chat")
async def chat_lore_seeker(req: QueryRequest):
    # Injection check
    warning = check_prompt_injection(req.message)
    if warning:
        return {"status": "rejected", "message": warning}

    try:
        response_text = run_agent(lore_seeker, req.message)
        return {"status": "success", "message": response_text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

@app.post("/api/truth-keeper/validate")
async def validate_truth_keeper(req: QueryRequest):
    # Injection check
    warning = check_prompt_injection(req.message)
    if warning:
        return {"status": "rejected", "message": warning}

    try:
        response_text = run_agent(truth_keeper, f"Verify if the following new lore introduction is consistent with our existing database: {req.message}")
        return {"status": "success", "message": response_text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

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
        <div class="entity-meta" id="vault-path-label">
            Loading path...
        </div>
    </div>

    <div class="workspace">
        <!-- Tabs Navigation -->
        <div class="tabs-nav">
            <button class="tab-link active" onclick="switchTab(event, 'tab-workspace')">Workspace</button>
            <button class="tab-link" onclick="switchTab(event, 'tab-validation')">Validation & Warnings</button>
            <button class="tab-link" onclick="switchTab(event, 'tab-tutorial')">How to Use (Tutorial)</button>
        </div>

        <!-- TAB 1: WORKSPACE -->
        <div id="tab-workspace" class="tab-content active">
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

                <!-- Draft Editor & Truth-keeper Panel -->
                <div class="panel">
                    <div class="panel-header">
                        <span>Truth-keeper & Draft Editor</span>
                        <div style="display: flex; gap: 8px; align-items: center;">
                            <select id="template-select" style="background: #22223b; border: 1px solid var(--border); color: var(--text-main); border-radius: 8px; padding: 4px 8px; font-size: 0.8rem; font-family: inherit; outline: none; cursor: pointer;">
                                <option value="general">General Note</option>
                                <option value="character">Character</option>
                                <option value="location">Location</option>
                                <option value="item">Item</option>
                                <option value="faction">Faction</option>
                            </select>
                            <button class="btn btn-secondary" onclick="createNewNote()" style="padding: 4px 12px; font-size: 0.8rem; background: #22223b; border-color: var(--primary);">New Note</button>
                            <button class="btn btn-secondary" onclick="approveDraft()" style="padding: 4px 12px; font-size: 0.8rem;">Save & Approve</button>
                        </div>
                    </div>
                    <textarea id="draft-editor" style="flex-grow: 1; height: auto; font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; margin-bottom: 15px;" placeholder="Generated Markdown draft content will appear here. Edit it freely."></textarea>
                    <div class="input-group">
                        <textarea id="keeper-input" placeholder="Paste draft or describe additions to test consistency..."></textarea>
                        <button class="btn" style="background: #2b2b3c; border: 1px solid var(--border);" onclick="askTruthKeeper()">Check Conflict</button>
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

        async function refreshData() {
            // Load entities
            const resEnt = await fetch('/api/entities');
            const entities = await resEnt.json();

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
                    item.innerHTML = `<strong>${issue.type.toUpperCase()}:</strong> ${issue.message}`;
                    valContainer.appendChild(item);
                });
            }
        }

        async function syncVault() {
            const res = await fetch('/api/sync', { method: 'POST' });
            const data = await res.json();
            alert(data.message);
            await refreshData();
        }

        function loadEntityToEditor(ent) {
            let frontmatter = "---\\n";
            frontmatter += `name: "${ent.name}"\\n`;
            frontmatter += `type: "${ent.type}"\\n`;
            for (const [k, v] of Object.entries(ent.metadata)) {
                if (k !== 'name' && k !== 'type') {
                    frontmatter += `${k}: ${v}\\n`;
                }
            }
            frontmatter += "---\\n";

            document.getElementById('draft-editor').value = frontmatter + ent.content;
        }
        function createNewNote() {
            const templateType = document.getElementById('template-select').value;
            let template = "";
            if (templateType === 'character') {
                template = "---\\nname: \"New Character\"\\ntype: \"character\"\\nspecies: \"human\"\\nsummary: \"\"\\nstatus: \"active\"\\nlocation: \"unknown\"\\nage: \"unknown\"\\nbirth_year: \"unknown\"\\ndeath_year: \"unknown\"\\nfaction: \"unknown\"\\nrelationships:\\n  positive: []\\n  neutral: []\\n  negative: []\\n---\\n\\nProse description here...";
            } else if (templateType === 'location') {
                template = "---\\nname: \"New Location\"\\ntype: \"location\"\\nsummary: \"\"\\nregion: \"unknown\"\\nplace_type: \"town\"\\n---\\n\\nProse description here...";
            } else if (templateType === 'item') {
                template = "---\\nname: \"New Item\"\\ntype: \"item\"\\nsummary: \"\"\\nowner: \"unknown\"\\norigin: \"unknown\"\\nlocation: \"unknown\"\\nrarity: \"common\"\\n---\\n\\nProse description here...";
            } else if (templateType === 'faction') {
                template = "---\\nname: \"New Faction\"\\ntype: \"faction\"\\nsummary: \"\"\\nheadquarters: \"unknown\"\\nleader: \"unknown\"\\n---\\n\\nProse description here...";
            } else {
                template = "---\\nname: \"New Note\"\\ntype: \"general\"\\nsummary: \"\"\\n---\\n\\nWrite note content here...";
            }
            document.getElementById('draft-editor').value = template;
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
            const data = await res.json();
            appendMsg('seeker-output', 'Lore-seeker', data.message);

            if (data.message.includes('---')) {
                document.getElementById('draft-editor').value = data.message;
            }
        }

        async function askTruthKeeper() {
            const inputEl = document.getElementById('keeper-input');
            const text = inputEl.value.trim();
            if (!text) return;

            appendMsg('seeker-output', 'User (Verification Request)', text);
            inputEl.value = '';

            const res = await fetch('/api/truth-keeper/validate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text })
            });
            const data = await res.json();
            appendMsg('seeker-output', 'Truth-keeper', data.message);
        }

        async function approveDraft() {
            const content = document.getElementById('draft-editor').value;
            if (!content) {
                alert("Draft editor is empty.");
                return;
            }

            // Simple title extraction
            const titleMatch = content.match(/name:\s*"(.*?)"/) || content.match(/name:\s*(.*?)\\n/);
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
