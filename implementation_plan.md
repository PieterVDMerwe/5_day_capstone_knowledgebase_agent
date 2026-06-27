# Implementation Plan: Refactoring Worldbuilding Generation & Note-Adding Pipeline

This plan outlines the overhaul of the lore generation, metadata styling, verification, and saving workflow into a structured, multi-agent pipeline managed by an interactive, step-by-step wizard UI.

---

## Architecture & Design Decisions

### 1. Database & Indexing Layer
Transition from a simple EAV structure to a graph-relational SQLite database with specialized tables (`entities`, `genealogy`, `memberships`, `containment`), dynamic edge weight scoring, and a phonetic name index (`name_index`) for typo detection.

### 2. Living Context Management
Local LLM context is kept small via:
*   **Stateful Session Cache:** Only the active draft and schema are maintained in memory.
*   **1-Hop Neighborhood Retrieval:** Fetch only immediate neighbors and their summaries.
*   **Pre-population:** Auto-fill known relations based on DB queries before generating text.
*   **Tiny Footprint Relational DSL:** Serialize relationships into a compact format (e.g. `[Liam(char) -> status:Alive | links:Oakhaven(loc)]`).

### 3. Output Reliability & Validation
*   **Strict JSON Mode:** Agents output structured JSON. The backend handles conversion to final Markdown.
*   **Defensive Parsing & Field Extraction:** Attempt to salvage partial valid fields from malformed JSON.
*   **Incremental Self-Correction:** Max 1 retry, asking only for missing/invalid keys.

### 4. Documentation & Handoff Standards
To ensure seamless handoffs between agents or developers across phases, all code must adhere to:
*   **Strict Type Hinting:** All Python functions, methods, and variables must be explicitly type-hinted.
*   **Comprehensive Docstrings:** Every module, class, and function must have a clear docstring explaining its inputs, outputs, and purpose.
*   **Phase-End Checkpoints:** At the end of every phase, the active worker must update a `HANDOFF.md` file in the root of the project summarizing what was built, how it works, and what the next phase requires.
*   **Handoff Onboarding:** Any new developer or AI agent picking up a task MUST read `HANDOFF.md` and `implementation_plan.md` before writing any code.

---

## Detailed Modular Action Plan

### Phase 0: Centralized Data Models & Dependencies
**Objective:** Define the strict schemas that all other phases will depend on, and lock in package dependencies.
*   **Step 0.1: Pydantic Data Models (`app/models.py`)**
    *   *Action:* Create a dedicated file holding the exact Pydantic/JSON schemas for the 7 entity types (Character, Location, Item, Faction, General Lore, Event, Species). 
    *   *Constraint:* **The Flat Model Rule:** All models MUST be strictly flat dictionaries (no nested complex objects). Lists of simple strings are allowed. This forces complex relations into the graph DB and enables trivial dynamic UI forms.
*   **Step 0.2: Dependency Management (`pyproject.toml`)**
    *   *Constraint:* You MUST explicitly add all required packages (`google-genai`, `ollama`, `pydantic`, `jellyfish`, `fastapi`, `uvicorn`, and `python-dotenv`) via `uv add` to ensure CI/CD and subsequent developers can install the environment without crashes.

### Phase 1: Database, Concurrency, & Vault Sync Engine
**Objective:** Establish the graph-relational foundation, solve concurrency, and ensure the vault sync parses comprehensive dummy markdown into the new tables.
*   **Step 1.1: Dummy Vault Seeder (`seed_vault.py`)**
    *   *Action:* Create a script to generate a robust dummy vault utilizing the schemas defined in Phase 0.
    *   *Constraint:* Must include comprehensive dummy examples of: Characters, Locations, Items, Factions, General Lore, Events (Timelines), and Species (Bestiary/Races).
*   **Step 1.2: Database Schema & Concurrency (`database.py`)**
    *   *Action:* Refactor `database.py` to create the new tables.
    *   *Constraint:* **Strict Columns & Primary Keys:** 
        *   `entities`: `name` (PK), `entity_type` (str), `summary` (str), `raw_markdown` (text), `metadata` (JSON). *(Added metadata column to ensure scalar frontmatter fields like age/status are not lost).*
        *   `edges`: `id` (PK), `source_name` (FK), `target_name` (FK), `relation_type` (str), `weight` (int).
        *   `genealogy`: `parent_name` (FK), `child_name` (FK).
        *   `memberships`: `entity_name` (FK), `faction_name` (FK), `role` (str).
        *   `containment`: `item_name` (FK), `location_name` (FK).
        *   `name_index`: `original_name` (str), `phonetic_hash` (str).
    *   *Constraint:* Wipe existing `.db` and vault data from scratch.
    *   *Constraint:* **SQLite Concurrency & Safety:** Must implement `PRAGMA journal_mode=WAL;` and `PRAGMA foreign_keys = ON;` in a centralized connection manager (e.g., `get_db()`) to prevent DB locks and silent graph corruption.
    *   *Constraint:* **The Tuple Trap:** The connection manager MUST set `db.row_factory = sqlite3.Row`. If a junior leaves it returning raw tuples, the API endpoints will become an unreadable mess of index mapping (`row[0]`).
    *   *Constraint:* **Directed Graph Enforcement:** The `edges` table represents a strictly DIRECTED graph (from source to target). Any SQL queries must explicitly treat it as directed so we don't accidentally double the context footprint.
*   **Step 1.3: Vault Sync Update (`parser.py`)**
    *   *Action:* Update the parsing logic to extract frontmatter fields and `[[wikilinks]]` into the new relationship tables based on the files generated in Step 1.1.
    *   *Constraint:* **Incremental Sync:** `parser.py` must expose an `O(1)` incremental sync function (e.g., `sync_single_file(path)`) so the entire vault doesn't have to be rebuilt when a single file is saved.
    *   *Action:* Implement phonetic hashing (Soundex/Double Metaphone via `jellyfish`) and co-occurrence frequency calculators.

### Phase 2: Core Architecture (Agents, LLMs, & Linters)
**Objective:** Set up the centralized LLM clients, specialized agents, and static validation modules.
*   **Step 2.1: Centralized LLM Client (`app/llm_client.py`)**
    *   *Action:* Create a single file to initialize the Gemini/Ollama SDKs, manage API keys, and act as the unified mockable surface for our `llm-mocking-guide`.
    *   *Constraint:* **Secrets Management:** You MUST use a `.env` file loaded via `python-dotenv` for API keys, and include a `.env.example` file. Never hardcode API keys.
*   **Step 2.2: Context Tools (`context_tools.py`)**
    *   *Action:* Create `get_entity_graph` to return the Tiny Footprint Relational DSL.
    *   *Constraint:* **Hub Explosion Prevention:** `get_entity_graph` MUST limit context to the Top N highest-weight connections.
*   **Step 2.3: Schema Linter Module (`app/validators.py`)**
    *   *Action:* Build an importable Python module to validate drafted JSON and frontmatter against the models in `app/models.py`.
*   **Step 2.4: Agent Architecture Refactoring (`app/agents/` and `app/prompts/`)**
    *   *Action:* Break monolithic `agent.py` into `lore_seeker.py`, `editor_agent.py`, `linker_agent.py`, `truth_keeper.py`.
    *   *Constraint:* System instructions must be isolated in `app/prompts/`.
    *   *Constraint:* **The Orchestrator:** Must create an `app/agents/orchestrator.py` module that exposes clean functions (e.g., `generate_draft()`) to manage the transitions between agents, keeping the API routes completely isolated from agent logic.

### Phase 3: Backend Stepper API
**Objective:** Expose the pipeline steps to the frontend via a stateless, RESTful API.
*   **Step 3.1: API Modularization & Static Mounting (`app/api/routes.py` & `main.py`)**
    *   *Constraint:* Do NOT cram API routes into `web_ui.py`. Implement all `/api/pipeline/...` endpoints in `app/api/routes.py`. 
    *   *Constraint:* `main.py` must mount these routers AND explicitly use `StaticFiles` to mount the `app/static/` directory to serve `index.html` at the root `/` path.
*   **Step 3.2: Pre-populate Endpoint (`app/api/routes.py`)**
    *   *Action:* Implement `/api/pipeline/prepopulate` to extract entities from the prompt and construct a partial JSON schema.
    *   *Constraint:* Aggressively inject literal `<insert-description-here>` placeholders into the JSON schema for unknown fields.
*   **Step 3.3: Generation & Formatting Endpoints (`app/api/routes.py`)**
    *   *Action:* Implement `/api/pipeline/draft` and `/api/pipeline/format`. 
    *   *Constraint:* MUST run a "Static Fuzzy Enum Mapper" script (using `validators.py`) to salvage outputs (e.g., mapping `"alive and well"` to `"active"`).
*   **Step 3.4: Validation & Approval Endpoints (`app/api/routes.py`)**
    *   *Action:* Implement `/api/pipeline/validate` and `/api/pipeline/approve`.
    *   *Constraint:* **Markdown Serializer:** The `/approve` endpoint MUST explicitly serialize the final JSON draft back into an Obsidian-compliant Markdown string with YAML frontmatter BEFORE writing to disk. Do not just dump raw JSON into a `.md` file.
    *   *Constraint:* The `/approve` endpoint should execute the `parser.py` vault sync **synchronously**. However, it MUST use the `O(1)` incremental sync function (e.g. `sync_single_file`) so the server doesn't freeze parsing the entire vault.
*   **Step 3.5: Universal JSON Protocol Implementation**
    *   *Constraint:* All endpoints MUST return a strict REST JSON Envelope (status, current_step, data, message).
    *   *Constraint:* **Stateless API:** The backend API must be strictly stateless. The Frontend UI must hold the current draft and pass it back.
    *   *Constraint:* **HTTP Status Protocol:** If an LLM logic validation fails (e.g., it hallucinates a contradiction), the API MUST return a `200 OK` HTTP status with the JSON Envelope `status: "error"`. Do not use HTTP `400` or `500` for expected application-level fallback states.

### Phase 4: Frontend UI Refactoring
**Objective:** Replace the chat UI with a responsive, 5-step wizard.
*   **Step 4.1: UI Layout & Styling (`index.html` & CSS)**
    *   *Action:* Implement the glassmorphism design system using Outfit and JetBrains Mono fonts.
    *   *Constraint:* **CSS Isolation:** All styling MUST be placed in an isolated `app/static/css/style.css` file. Do not dump inline CSS into the HTML template.
    *   *Constraint:* **Offline-First Fonts:** Do NOT use Google Fonts CDN. All fonts (`.woff2`) must be downloaded and bundled locally in `app/static/fonts/` so the app remains fully functional offline.
*   **Step 4.2: Dynamic HTML Form Generator (`ui_renderer.js`)**
    *   *Action:* Build a sleek UI form generator that takes the partial JSON schema returned from the API and dynamically renders input boxes, dropdowns, and textareas. 
    *   *Constraint:* Because Phase 0 enforces the Flat Model Rule, the generator MUST be implemented as a simple, non-recursive loop (e.g. over `Object.keys()`) to maintain a minimal footprint.
*   **Step 4.3: Frontend State Management (`app/static/js/`)**
    *   *Action:* Separate the frontend logic into exactly four isolated files: `api_client.js`, `state_store.js`, `ui_renderer.js`, and `wizard_controller.js`.
    *   *Constraint:* **The Orchestrator:** Only `wizard_controller.js` is allowed to wire up DOM click listeners (like "Next Step") and orchestrate the flow between the API, State, and UI renderer.
    *   *Constraint:* Must strictly use native **ES6 Modules** (`<script type="module">`) and `import/export` syntax to guarantee isolated scopes and prevent global namespace pollution.
    *   *Constraint:* **Browser Import Gotcha:** Native browser ES6 imports MUST include the `.js` file extension (e.g., `import { X } from './state_store.js'`), or the browser will throw a fatal 404 error.

### Phase 5: Supporting Skills Development
**Objective:** Build specialized non-LLM tools to aid the ecosystem.
*   **Step 5.1: Telemetry Tracer Skill (`.agents/skills/telemetry-tracer`)**
    *   *Action:* Create a script to log and visualize token usage and tool call latencies.

### Phase 6: Testing & Evaluation Suite
**Objective:** Ensure reliability through automated checks and LLM evaluations.
*   **Step 6.1: Unit & Integration Tests (`tests/test_pipeline.py`)**
    *   *Action:* Write pytest cases mocking LLM outputs based on the `llm-mocking-guide`.
*   **Step 6.2: Real-LLM Evaluation Harness (`tests/run_evals.py`)**
    *   *Action:* Create an evaluation script that feeds predefined contradiction scenarios.
