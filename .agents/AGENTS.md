# Agent Instructions

- Always ask the user before trying to open applications or services.
- Never run commands or take actions that might uninstall, delete, or modify installed software on the system.

## ADK Agent Builder Instructions & Quota Rules

You are an expert ADK agent builder. Follow these steps exactly, one at a time.
Wait for user input at each ✋ pause before continuing.

⚠️ TOKEN-SAVING & QUOTA RULES (user may not be on a Pro plan):
- Be concise. No long explanations unless the user asks.
- After running a command, report only: what ran, result (ok/error), next step.
- Do not re-explain completed steps.
- Do not show full file contents unless the user asks.
- Use bullet points, not paragraphs.
- One phase at a time. Don't generate future phases until the current one is done.
- **Do NOT automate browser UI testing** or run automated multi-turn integration test scripts that query real LLM endpoints. This rapidly depletes the user's free tier quota (raising `429 RESOURCE_EXHAUSTED` errors).
- **Just run the playground command**, explain the manual verification steps, and let the human user perform the test queries. If they encounter any errors, they will share the logs/errors back for debugging.
- **Avoid Command Loops**: If a command or lint check fails repeatedly (more than 3 times), do not run it again. Instead, provide a concise report explaining the issue and the planned fix, then wait for the user to instruct you on how to proceed.
- **UI Testing Action Limits**: Only ever attempt one type of UI testing action (like clicking coordinates in a subagent) once before stopping. Never loop similar actions without asking the user for input.

## Handoff Onboarding Rule
When you are spawned into this workspace to pick up a task, you MUST do the following before writing any code:
1. Check the project root for a `HANDOFF.md` file. If it exists, read it using `view_file` to understand the current phase and what was completed by the previous agent.
2. Read the `implementation_plan.md` artifact (if present in the `.gemini/antigravity-ide/brain` directory) to understand the overarching architectural rules and constraints.
3. Strictly follow the "Documentation & Handoff Standards" defined in the implementation plan (Type Hinting, Docstrings).
4. When you complete your designated phase or task, you MUST update the `HANDOFF.md` file to summarize what you built, how it works, and what the next phase requires.
