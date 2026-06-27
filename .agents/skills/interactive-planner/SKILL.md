---
name: interactive-planner
description: Creates a detailed, modular, phase-by-phase implementation plan by interactively grilling the user on design decisions. Triggers when the user asks to plan a complex feature, create an implementation plan, or grill them on a plan.
---

# Interactive Planner Skill

When you are asked to plan a complex feature or create an implementation plan (especially if the user mentions `/grill-me`), you must follow this interactive, multi-step process to ensure a shared understanding and produce a highly delegatable action plan.

## 1. The Interactive Grilling Phase
Before writing any plan, you must break down the problem space into distinct architectural components (e.g., Database, Agent Logic, Frontend, API, Testing) and interview the user using the `ask_question` tool.
*   **One by One:** Walk down the design tree and resolve dependencies one decision at a time. Ask ONE question per tool call.
*   **Provide Options:** For each question, provide at least 3 well-thought-out options as choices.
*   **Recommended Prefix:** Always prefix your preferred or most logical option with "(Recommended) ".
*   **Codebase Exploration:** If a question can be answered by exploring the codebase first, do your research before asking.

## 2. The Synthesis Phase
Once the user has answered all necessary questions and the design is fully resolved, synthesize the decisions. Do NOT start writing code yet.

## 3. The Strict Modular Template
You must create or update the `implementation_plan.md` artifact using the exact format below. This format ensures that tasks are modular and can be easily delegated to other sub-agents with strict bounded constraints.

### Template Structure:
```markdown
# Implementation Plan: [Feature Name]

[Brief summary of the feature and the finalized design decisions.]

## Detailed Modular Action Plan

### Phase [N]: [Phase Name]
**Objective:** [Clear, single-sentence objective of this phase]
*   **Step [N].[M]: [Task Name] (`[Target File]`)**
    *   *Action:* [Specific, actionable instruction of what to build or change.]
    *   *Constraint:* [Any strict bounds, e.g., "Maintain backward compatibility", "Do not modify existing X", "Ensure output is strict JSON".]
```
*(Repeat the Phase structure for all components discussed during the grilling phase).*

## 4. The Relentless Critique Phase (Junior Handoff Simulation)
Before finalizing the plan, you MUST perform a relentless self-critique. Read through your generated plan as if you are a Junior Developer seeing it for the very first time. Check for:
1. **Chicken-and-Egg Loops:** Does Phase 1 rely on data models or validation scripts that aren't built until Phase 2?
2. **Missing Dependencies:** Does the plan say "save to the database" but fail to mention how the database connection is managed or where it is imported from?
3. **Vague Instructions:** Does the plan say "Build a frontend" without specifying if it should use ES6 Modules, React, or global Vanilla JS?
4. **Concurrency Blocking:** Does an API endpoint trigger a heavy background task synchronously, thereby freezing the server?

If you find flaws, you must report them to the user and dynamically patch the plan.

### Example Critique Process:
*   *Plan states:* "Phase 1: Write a script to generate dummy character files. Phase 2: Create the Pydantic schemas that validate characters."
*   *Agent Critique:* "Wait! If I hand this to a junior, they will have to guess the fields for the dummy files in Phase 1 because the schemas aren't built until Phase 2. This is a schema dependency conflict."
*   *Agent Fix:* "I must propose moving the Pydantic schemas to a new 'Phase 0: Data Models' so all subsequent phases have a source of truth."

## 5. Final Review
After generating and critiquing the `implementation_plan.md` artifact (ensure `request_feedback=true` in the tool call), stop calling tools and wait for the user to explicitly approve the plan before executing any code changes.
