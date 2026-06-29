# Agent Handoff Document

## Current Status
**Save Connection Maintenance & SQLite Cascade Fix** has been successfully completed.

### What was built:
1. **Procedural Seed Engine (`app/wizard_generators.py`)**: Built a robust fantasy seed data engine that generates names, species, biomes, relics, and factions. It queries the SQLite DB to dynamically assign random relationships from existing entities (near and far) while handling the cold-start (empty database) state safely.
2. **Wizard API Endpoints (`main.py`)**:
   - `GET /api/wizard/suggest`: Exposes the seed engine to fetch pre-populated drafts.
   - `POST /api/wizard/generate-content`: Formulates a clean LLM prompt to write the summary and body content strictly from the validated metadata fields.
3. **Step-by-Step Stepper Wizard (`index.html` & `wizard_controller.js`)**: A modal overlay UI that walks the user through creating notes:
   - **Step 1:** Choose Type.
   - **Step 2:** Edit/Review procedural fields.
   - **Step 3:** Generate Lore description with a dedicated "Regenerate Content" button + custom user instructions.
   - **Step 4:** Final Review before calling `/api/save`.
4. **Chat Decoupling & Mode Switch**: Restricted the left chat panel strictly to read-only queries. Added a tab switch at the bottom of the chat panel to toggle between RAG ("Lore Base" querying context tools) and direct, abstract prompts ("Direct LLM" passing text-only prompts without tool calls).
5. **SQLite Cascade Fix (`app/database.py`)**: Refactored `insert_entity` to use `ON CONFLICT(name) DO UPDATE` instead of `INSERT OR REPLACE`. This prevents SQLite from deleting rows and triggering cascade deletes on incoming links, fixing the graph disconnection issue.
6. **Save Connections Maintenance Dialog (`index.html`, `ui_state.js`, `wizard_controller.js`)**:
   - Created `GET /api/entity/{name}/incoming` to fetch all links, memberships, and containment relations referencing the entity.
   - Added a modal checklist on Save (both from Editor and Step 4 Wizard) prompting the user to maintain or forget incoming connections, with "Maintain All" and "Forget All" options.
7. **Stub Completion Wizard (`index.html`, `ui_state.js`, `wizard_controller.js`)**:
   - Added a `⚡ Complete with Wizard` button to the Editor header actions that appears exclusively when an empty stub note is loaded.
   - Click to open the stepper wizard pre-seeded with the stub's name, overriding the random name generators in Step 2 while providing procedural seed generation for the rest of the fields.

### How it works:
- Click the green **+ New Note** button in the Editor actions.
- Walk through the stepper modal to create a note using seeded/procedural fields, generate content via the LLM, and save.
- Toggle between "Lore Base" and "Direct LLM" in the chat panel to query the database vs. prompt the model directly.
- Saving an existing note with incoming connections will trigger a review popup allowing selective link retention/removal. Incoming links are preserved by default without breaking.
- Loading an empty stub note displays a `⚡ Complete with Wizard` button. Clicking it starts the wizard pre-populated with that stub's name.

### Next Phase Requires:
- **Phase 6: Supporting Skills Development**
  - Implement Step 5.1 from the master plan: Create the Telemetry Tracer Skill (`.agents/skills/telemetry-tracer`) to log and visualize token usage and tool call latencies.
- **Phase 7: Testing & Evaluation Suite**
  - Implement Phase 6 from the master plan: Write robust pytest cases in `tests/test_pipeline.py` leveraging the `llm-mocking-guide`.
  - Create the Real-LLM Evaluation Harness (`tests/run_evals.py`) to systematically test contradictory scenarios.
